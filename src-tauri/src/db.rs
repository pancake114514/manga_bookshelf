//! 数据库层 — 与 Python 版 database.py 对等的 Rust 实现
//!
//! 设计要点：
//! - 使用 rusqlite（bundled SQLite，无需系统安装）
//! - 连接绑定线程（与 Python 版相同约束），通过 Mutex 保护
//! - 外键 CASCADE 删除、唯一索引去重，保持与原版 DDL 一致
//! - 新增 schema_version 版本管理

use std::collections::HashMap;

use rusqlite::{params, Connection, Row};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ── 数据模型 ──────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ObjectRow {
    pub id: String,
    #[serde(rename = "type")]
    pub obj_type: String,
    pub name: String,
    pub source_path: Option<String>,
    pub storage_path: Option<String>,
    pub cover_image: Option<String>,
    pub last_read_idx: i64,
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TagRow {
    pub id: i64,
    pub object_id: String,
    pub category: String,
    pub value: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageRow {
    pub id: String,
    pub object_id: String,
    pub filename: String,
    pub filepath: String,
    pub sort_order: i64,
    pub created_at: Option<String>,
}

/// 组装后的完整对象（含标签、图片数量、首图路径），对应当前 Python 版的 _assemble_objects
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssembledObject {
    pub id: String,
    #[serde(rename = "type")]
    pub obj_type: String,
    pub name: String,
    pub source_path: Option<String>,
    pub storage_path: Option<String>,
    pub cover_image: Option<String>,
    pub last_read_idx: i64,
    pub created_at: Option<String>,
    pub tags: Tags,
    pub image_count: i64,
    pub first_image: Option<String>,
}

/// 标签以 category → Vec<value> 的形式组织，r18 特殊处理为 bool
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(transparent)]
pub struct Tags(pub HashMap<String, TagValue>);

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum TagValue {
    Bool(bool),
    List(Vec<String>),
}

impl Tags {
    pub fn is_r18(&self) -> bool {
        self.0
            .get("r18")
            .and_then(|v| match v {
                TagValue::Bool(b) => Some(*b),
                _ => None,
            })
            .unwrap_or(false)
    }
}

// ── Database ──────────────────────────────────────────────────────────────────

pub struct Database {
    pub conn: Connection,
}

impl Database {
    pub fn open(path: &str) -> Result<Self, String> {
        let conn = Connection::open(path).map_err(|e| format!("打开数据库失败: {e}"))?;
        conn.execute_batch("PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;")
            .map_err(|e| format!("设置 PRAGMA 失败: {e}"))?;
        let mut db = Self { conn };
        db.init_tables()?;
        Ok(db)
    }

    pub fn init_tables(&mut self) -> Result<(), String> {
        self.conn
            .execute_batch(
                r#"
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS config (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS objects (
                    id            TEXT PRIMARY KEY,
                    type          TEXT NOT NULL CHECK(type IN ('directory','file')),
                    name          TEXT NOT NULL,
                    source_path   TEXT,
                    storage_path  TEXT,
                    cover_image   TEXT,
                    last_read_idx INTEGER DEFAULT 0,
                    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tags (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_id TEXT NOT NULL,
                    category  TEXT NOT NULL,
                    value     TEXT NOT NULL,
                    FOREIGN KEY (object_id) REFERENCES objects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS images (
                    id         TEXT PRIMARY KEY,
                    object_id  TEXT NOT NULL,
                    filename   TEXT NOT NULL,
                    filepath   TEXT NOT NULL,
                    sort_order INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (object_id) REFERENCES objects(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_tags_object ON tags(object_id);
                CREATE INDEX IF NOT EXISTS idx_images_object ON images(object_id);
                CREATE INDEX IF NOT EXISTS idx_tags_category_value ON tags(category, value);
                CREATE INDEX IF NOT EXISTS idx_objects_created ON objects(created_at DESC);

                -- 去除历史重复标签后建唯一约束
                DELETE FROM tags WHERE id NOT IN (
                    SELECT MIN(id) FROM tags GROUP BY object_id, category, value
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_unique
                    ON tags(object_id, category, value);

                -- 清理历史遗留孤儿
                DELETE FROM tags WHERE object_id NOT IN (SELECT id FROM objects);
                DELETE FROM images WHERE object_id NOT IN (SELECT id FROM objects);

                -- Schema 版本标记
                INSERT OR IGNORE INTO config(key, value) VALUES('schema_version', '1');
                "#,
            )
            .map_err(|e| format!("初始化表失败: {e}"))?;
        Ok(())
    }

    // ── 配置 ───────────────────────────────────────────────────────────────

    pub fn get_config(&self, key: &str) -> Result<Option<String>, String> {
        self.conn
            .query_row(
                "SELECT value FROM config WHERE key=?",
                params![key],
                |row| row.get::<_, String>(0),
            )
            .map(|v| Some(v))
            .or_else(|e| match e {
                rusqlite::Error::QueryReturnedNoRows => Ok(None),
                _ => Err(e),
            })
            .map_err(|e| format!("读取配置失败: {e}"))
    }

    pub fn set_config(&self, key: &str, value: &str) -> Result<(), String> {
        self.conn
            .execute(
                "INSERT OR REPLACE INTO config(key,value) VALUES(?,?)",
                params![key, value],
            )
            .map_err(|e| format!("写入配置失败: {e}"))?;
        Ok(())
    }

    pub fn get_config_bool(&self, key: &str, default: bool) -> Result<bool, String> {
        match self.get_config(key)? {
            Some(v) => Ok(matches!(
                v.trim().to_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )),
            None => Ok(default),
        }
    }

    pub fn get_config_int(&self, key: &str, default: i64) -> Result<i64, String> {
        match self.get_config(key)? {
            Some(v) => v.parse().map_err(|_| format!("配置值不是整数: {v}")),
            None => Ok(default),
        }
    }

    pub fn set_config_bool(&self, key: &str, value: bool) -> Result<(), String> {
        self.set_config(key, if value { "1" } else { "0" })
    }

    // ── 对象 CRUD ────────────────────────────────────────────────────────────

    pub fn create_object(
        &self,
        obj_id: &str,
        obj_type: &str,
        name: &str,
        source_path: &str,
        storage_path: &str,
    ) -> Result<bool, String> {
        match self.conn.execute(
            "INSERT INTO objects(id,type,name,source_path,storage_path) VALUES(?,?,?,?,?)",
            params![obj_id, obj_type, name, source_path, storage_path],
        ) {
            Ok(_) => Ok(true),
            Err(rusqlite::Error::SqliteFailure(err, _))
                if err.code == rusqlite::ErrorCode::ConstraintViolation =>
            {
                Ok(false)
            }
            Err(e) => Err(format!("创建对象失败: {e}")),
        }
    }

    pub fn get_object(&self, obj_id: &str) -> Result<ObjectRow, String> {
        self.conn
            .query_row(
                "SELECT * FROM objects WHERE id=?",
                params![obj_id],
                |row| ObjectRow::from_row(row),
            )
            .map_err(|e| format!("查询对象失败: {e}"))
    }

    pub fn get_object_opt(&self, obj_id: &str) -> Result<Option<ObjectRow>, String> {
        match self.get_object(obj_id) {
            Ok(o) => Ok(Some(o)),
            Err(_) => Ok(None),
        }
    }

    pub fn update_object_name(&self, obj_id: &str, name: &str) -> Result<(), String> {
        self.conn
            .execute(
                "UPDATE objects SET name=? WHERE id=?",
                params![name, obj_id],
            )
            .map_err(|e| format!("更新对象名失败: {e}"))?;
        Ok(())
    }

    pub fn update_object_cover(&self, obj_id: &str, cover_image: &str) -> Result<(), String> {
        self.conn
            .execute(
                "UPDATE objects SET cover_image=? WHERE id=?",
                params![cover_image, obj_id],
            )
            .map_err(|e| format!("更新封面失败: {e}"))?;
        Ok(())
    }

    pub fn update_object_storage_path(
        &self,
        obj_id: &str,
        storage_path: &str,
    ) -> Result<(), String> {
        self.conn
            .execute(
                "UPDATE objects SET storage_path=? WHERE id=?",
                params![storage_path, obj_id],
            )
            .map_err(|e| format!("更新存储路径失败: {e}"))?;
        Ok(())
    }

    pub fn update_last_read(&self, obj_id: &str, idx: i64) -> Result<(), String> {
        self.conn
            .execute(
                "UPDATE objects SET last_read_idx=? WHERE id=?",
                params![idx, obj_id],
            )
            .map_err(|e| format!("更新阅读进度失败: {e}"))?;
        Ok(())
    }

    pub fn delete_object(&self, obj_id: &str) -> Result<(), String> {
        self.conn
            .execute("DELETE FROM objects WHERE id=?", params![obj_id])
            .map_err(|e| format!("删除对象失败: {e}"))?;
        Ok(())
    }

    // ── 批量查询 ────────────────────────────────────────────────────────────

    pub fn get_all_object_ids(&self, include_r18: bool) -> Result<Vec<String>, String> {
        let sql = "SELECT id FROM objects ORDER BY created_at DESC";
        let mut stmt = self
            .conn
            .prepare(sql)
            .map_err(|e| format!("查询对象列表失败: {e}"))?;
        let ids: Result<Vec<String>, _> = stmt
            .query_map([], |row| row.get::<_, String>(0))
            .map_err(|e| format!("查询对象列表失败: {e}"))?
            .collect();
        let ids = ids.map_err(|e| format!("查询对象列表失败: {e}"))?;

        if include_r18 {
            return Ok(ids);
        }
        // 过滤 R-18
        let mut result = Vec::with_capacity(ids.len());
        for id in ids {
            let tags = self.get_tags(&id)?;
            if !tags.is_r18() {
                result.push(id);
            }
        }
        Ok(result)
    }

    /// 批量组装对象（一次查 tags、图片数量、首图路径，避免 N+1）
    pub fn assemble_objects(
        &self,
        rows: &[ObjectRow],
        include_r18: bool,
    ) -> Result<Vec<AssembledObject>, String> {
        if rows.is_empty() {
            return Ok(Vec::new());
        }

        let obj_ids: Vec<&str> = rows.iter().map(|r| r.id.as_str()).collect();
        let placeholders = vec!["?"; obj_ids.len()].join(",");

        // 批量查 tags
        let sql_tags = format!(
            "SELECT object_id, category, value FROM tags WHERE object_id IN ({placeholders})"
        );
        let mut tag_map: HashMap<String, Vec<(String, String)>> = HashMap::new();
        {
            let mut stmt = self
                .conn
                .prepare(&sql_tags)
                .map_err(|e| format!("批量查标签失败: {e}"))?;
            let rows_iter = stmt
                .query_map(rusqlite::params_from_iter(obj_ids.iter()), |row| {
                    (
                        row.get::<_, String>(0)?, // object_id
                        row.get::<_, String>(1)?, // category
                        row.get::<_, String>(2)?, // value
                    )
                })
                .map_err(|e| format!("批量查标签失败: {e}"))?;
            for r in rows_iter {
                let (oid, cat, val) = r.map_err(|e| format!("读取标签行失败: {e}"))?;
                tag_map.entry(oid).or_default().push((cat, val));
            }
        }

        // 批量查图片数量
        let sql_count = format!(
            "SELECT object_id, COUNT(*) AS cnt FROM images WHERE object_id IN ({placeholders}) GROUP BY object_id"
        );
        let mut count_map: HashMap<String, i64> = HashMap::new();
        {
            let mut stmt = self
                .conn
                .prepare(&sql_count)
                .map_err(|e| format!("批量查图片数失败: {e}"))?;
            let rows_iter = stmt
                .query_map(rusqlite::params_from_iter(obj_ids.iter()), |row| {
                    (row.get::<_, String>(0)?, row.get::<_, i64>(1)?)
                })
                .map_err(|e| format!("批量查图片数失败: {e}"))?;
            for r in rows_iter {
                let (oid, cnt) = r.map_err(|e| format!("读取图片数失败: {e}"))?;
                count_map.insert(oid, cnt);
            }
        }

        // 批量查首图路径
        let sql_first = format!(
            r#"SELECT object_id, filepath FROM (
                    SELECT object_id, filepath,
                           ROW_NUMBER() OVER (
                               PARTITION BY object_id
                               ORDER BY sort_order, filename
                           ) AS rn
                    FROM images
                    WHERE object_id IN ({placeholders})
                ) WHERE rn = 1"#
        );
        let mut first_map: HashMap<String, String> = HashMap::new();
        {
            let mut stmt = self
                .conn
                .prepare(&sql_first)
                .map_err(|e| format!("批量查首图失败: {e}"))?;
            let rows_iter = stmt
                .query_map(rusqlite::params_from_iter(obj_ids.iter()), |row| {
                    (row.get::<_, String>(0)?, row.get::<_, String>(1)?)
                })
                .map_err(|e| format!("批量查首图失败: {e}"))?;
            for r in rows_iter {
                let (oid, fp) = r.map_err(|e| format!("读取首图失败: {e}"))?;
                first_map.insert(oid, fp);
            }
        }

        // 组装
        let mut result = Vec::new();
        for row in rows {
            let tags = Self::tags_from_raw(&tag_map.get(&row.id).cloned().unwrap_or_default());
            if !include_r18 && tags.is_r18() {
                continue;
            }
            result.push(AssembledObject {
                id: row.id.clone(),
                obj_type: row.obj_type.clone(),
                name: row.name.clone(),
                source_path: row.source_path.clone(),
                storage_path: row.storage_path.clone(),
                cover_image: row.cover_image.clone(),
                last_read_idx: row.last_read_idx,
                created_at: row.created_at.clone(),
                tags,
                image_count: *count_map.get(&row.id).unwrap_or(&0),
                first_image: first_map.get(&row.id).cloned(),
            });
        }
        Ok(result)
    }

    pub fn get_all_objects(&self, include_r18: bool) -> Result<Vec<AssembledObject>, String> {
        let sql = "SELECT * FROM objects ORDER BY created_at DESC";
        let mut stmt = self
            .conn
            .prepare(sql)
            .map_err(|e| format!("查询全部对象失败: {e}"))?;
        let rows: Vec<ObjectRow> = stmt
            .query_map([], |row| ObjectRow::from_row(row))
            .map_err(|e| format!("查询全部对象失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        self.assemble_objects(&rows, include_r18)
    }

    pub fn search_objects(
        &self,
        keyword: &str,
        include_r18: bool,
    ) -> Result<Vec<AssembledObject>, String> {
        // 转义 LIKE 通配符
        let escaped = keyword
            .replace('\\', "\\\\")
            .replace('%', "\\%")
            .replace('_', "\\_");
        let pattern = format!("%{escaped}%");
        let sql = r#"
            SELECT DISTINCT o.* FROM objects o
            LEFT JOIN tags t ON t.object_id = o.id
            WHERE o.name LIKE ? ESCAPE '\' OR t.value LIKE ? ESCAPE '\'
            ORDER BY o.created_at DESC
        "#;
        let mut stmt = self
            .conn
            .prepare(sql)
            .map_err(|e| format!("搜索对象失败: {e}"))?;
        let rows: Vec<ObjectRow> = stmt
            .query_map(params![pattern, pattern], |row| ObjectRow::from_row(row))
            .map_err(|e| format!("搜索对象失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        self.assemble_objects(&rows, include_r18)
    }

    pub fn filter_by_tags(
        &self,
        filters: &HashMap<String, Vec<String>>,
        include_r18: bool,
    ) -> Result<Vec<AssembledObject>, String> {
        let all = self.get_all_objects(include_r18)?;
        if filters.is_empty() {
            return Ok(all);
        }
        let result: Vec<AssembledObject> = all
            .into_iter()
            .filter(|obj| {
                for (cat, values) in filters {
                    if values.is_empty() {
                        continue;
                    }
                    let obj_vals: Vec<String> = match obj.tags.0.get(cat) {
                        Some(TagValue::List(v)) => v.clone(),
                        Some(TagValue::Bool(true)) => vec!["true".to_string()],
                        _ => Vec::new(),
                    };
                    if !values.iter().any(|v| obj_vals.contains(v)) {
                        return false;
                    }
                }
                true
            })
            .collect();
        Ok(result)
    }

    // ── 标签 ──────────────────────────────────────────────────────────────────

    pub fn get_tags(&self, obj_id: &str) -> Result<Tags, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT category, value FROM tags WHERE object_id=? ORDER BY id")
            .map_err(|e| format!("查询标签失败: {e}"))?;
        let raw: Vec<(String, String)> = stmt
            .query_map(params![obj_id], |row| {
                (row.get::<_, String>(0)?, row.get::<_, String>(1)?)
            })
            .map_err(|e| format!("查询标签失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(Self::tags_from_raw(&raw))
    }

    fn tags_from_raw(raw: &[(String, String)]) -> Tags {
        let mut map: HashMap<String, TagValue> = HashMap::new();
        for (cat, val) in raw {
            if cat == "r18" {
                map.insert("r18".into(), TagValue::Bool(val == "true"));
            } else {
                match map.entry(cat.clone()) {
                    std::collections::HashMapEntry::Occupied(mut e) => {
                        if let TagValue::List(v) = e.get_mut() {
                            v.push(val.clone());
                        }
                    }
                    std::collections::HashMapEntry::Vacant(e) => {
                        e.insert(TagValue::List(vec![val.clone()]));
                    }
                }
            }
        }
        Tags(map)
    }

    /// 整体替换对象标签（原子事务）
    pub fn set_tags(&self, obj_id: &str, tags: &Tags) -> Result<(), String> {
        // 构建标签行并保序去重
        let mut rows: Vec<(String, String, String)> = Vec::new();
        for (cat, val) in &tags.0 {
            match val {
                TagValue::Bool(b) => {
                    rows.push((obj_id.to_string(), cat.clone(), b.to_string()));
                }
                TagValue::List(vals) => {
                    for v in vals {
                        if !v.is_empty() {
                            rows.push((obj_id.to_string(), cat.clone(), v.clone()));
                        }
                    }
                }
            }
        }
        // 保序去重
        let mut seen = std::collections::HashSet::new();
        rows.retain(|r| seen.insert(r.clone()));

        let tx = self.conn.unchecked_transaction().map_err(|e| format!("开启事务失败: {e}"))?;
        tx.execute(
            "DELETE FROM tags WHERE object_id=?",
            params![obj_id],
        )
        .map_err(|e| format!("清空标签失败: {e}"))?;
        for (oid, cat, val) in &rows {
            tx.execute(
                "INSERT INTO tags(object_id,category,value) VALUES(?,?,?)",
                params![oid, cat, val],
            )
            .map_err(|e| format!("插入标签失败: {e}"))?;
        }
        tx.commit().map_err(|e| format!("提交标签事务失败: {e}"))?;
        Ok(())
    }

    pub fn get_all_tag_values(&self, category: &str) -> Result<Vec<String>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT DISTINCT value FROM tags WHERE category=? ORDER BY value")
            .map_err(|e| format!("查询标签值失败: {e}"))?;
        let vals: Vec<String> = stmt
            .query_map(params![category], |row| row.get::<_, String>(0))
            .map_err(|e| format!("查询标签值失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(vals)
    }

    // ── 图片 ──────────────────────────────────────────────────────────────────

    pub fn add_image(
        &self,
        img_id: &str,
        obj_id: &str,
        filename: &str,
        filepath: &str,
        sort_order: i64,
    ) -> Result<(), String> {
        self.conn
            .execute(
                "INSERT OR IGNORE INTO images(id,object_id,filename,filepath,sort_order) VALUES(?,?,?,?,?)",
                params![img_id, obj_id, filename, filepath, sort_order],
            )
            .map_err(|e| format!("添加图片失败: {e}"))?;
        Ok(())
    }

    pub fn update_image_filepath(&self, img_id: &str, filepath: &str) -> Result<(), String> {
        self.conn
            .execute(
                "UPDATE images SET filepath=? WHERE id=?",
                params![filepath, img_id],
            )
            .map_err(|e| format!("更新图片路径失败: {e}"))?;
        Ok(())
    }

    pub fn delete_image(&self, img_id: &str) -> Result<(), String> {
        self.conn
            .execute("DELETE FROM images WHERE id=?", params![img_id])
            .map_err(|e| format!("删除图片失败: {e}"))?;
        Ok(())
    }

    pub fn get_images(&self, obj_id: &str) -> Result<Vec<ImageRow>, String> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT * FROM images WHERE object_id=? ORDER BY sort_order, filename",
            )
            .map_err(|e| format!("查询图片失败: {e}"))?;
        let rows: Vec<ImageRow> = stmt
            .query_map(params![obj_id], |row| ImageRow::from_row(row))
            .map_err(|e| format!("查询图片失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(rows)
    }

    pub fn get_image_count(&self, obj_id: &str) -> Result<i64, String> {
        self.conn
            .query_row(
                "SELECT COUNT(*) as cnt FROM images WHERE object_id=?",
                params![obj_id],
                |row| row.get::<_, i64>(0),
            )
            .map_err(|e| format!("查询图片数量失败: {e}"))
    }

    pub fn get_images_map(&self, obj_id: &str) -> Result<HashMap<String, String>, String> {
        let images = self.get_images(obj_id)?;
        Ok(images.into_iter().map(|i| (i.id, i.filepath)).collect())
    }
}

// ── Row 映射 trait ────────────────────────────────────────────────────────────

pub trait FromRow: Sized {
    fn from_row(row: &Row) -> rusqlite::Result<Self>;
}

impl FromRow for ObjectRow {
    fn from_row(row: &Row) -> rusqlite::Result<Self> {
        Ok(Self {
            id: row.get("id")?,
            obj_type: row.get("type")?,
            name: row.get("name")?,
            source_path: row.get("source_path")?,
            storage_path: row.get("storage_path")?,
            cover_image: row.get("cover_image")?,
            last_read_idx: row.get("last_read_idx").unwrap_or(0),
            created_at: row.get("created_at")?,
        })
    }
}

impl FromRow for ImageRow {
    fn from_row(row: &Row) -> rusqlite::Result<Self> {
        Ok(Self {
            id: row.get("id")?,
            object_id: row.get("object_id")?,
            filename: row.get("filename")?,
            filepath: row.get("filepath")?,
            sort_order: row.get("sort_order").unwrap_or(0),
            created_at: row.get("created_at")?,
        })
    }
}

// ── 辅助函数 ──────────────────────────────────────────────────────────────────

pub fn new_uuid() -> String {
    Uuid::new_v4().to_string()
}
