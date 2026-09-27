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
    pub series_id: Option<String>,
    pub series_name: Option<String>,
    pub volume: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SeriesRow {
    pub id: String,
    pub name: String,
    pub count: i64,
    pub first_cover: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BookmarkRow {
    pub id: i64,
    pub object_id: String,
    pub page_idx: i64,
    pub note: Option<String>,
    pub created_at: Option<String>,
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
    pub series_id: Option<String>,
    pub series_name: Option<String>,
    pub volume: Option<i64>,
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

// ── 基线 DDL 与迁移步骤 ──────────────────────────────────────────────────────

/// 基线 DDL（v1 schema）——全新库建表脚本，含去重/清孤儿。
/// 老库迁移时不执行此段，仅由增量步骤补列/建表。
const BASELINE_DDL: &str = r#"
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

    -- Schema 版本标记（兼容旧版 config 记录）
    INSERT OR IGNORE INTO config(key, value) VALUES('schema_version', '1');
    "#;

/// 增量迁移步骤：(目标版本, SQL)。
/// 每步在事务内执行，成功提交后设置 PRAGMA user_version。
const MIGRATE_STEPS: &[(i64, &str)] = &[
    (2, r#"
        -- v1→v2：系列表 + 对象关联
        CREATE TABLE IF NOT EXISTS series (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE objects ADD COLUMN series_id TEXT REFERENCES series(id) ON DELETE SET NULL;
        ALTER TABLE objects ADD COLUMN volume INTEGER;
        CREATE INDEX IF NOT EXISTS idx_objects_series ON objects(series_id);
    "#),
    (3, r#"
        -- v2→v3：书签表
        CREATE TABLE IF NOT EXISTS bookmarks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id  TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
            page_idx   INTEGER NOT NULL,
            note       TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(object_id, page_idx)
        );
    "#),
];

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
        Self::migrate(&mut self.conn)?;
        Ok(())
    }

    /// 版本化迁移：读 PRAGMA user_version，按需执行基线 DDL 或增量步骤。
    /// - user_version == 0 且 objects 表已存在（老库）：仅置基线 1，不重建表
    /// - user_version == 0 且无 objects 表（全新库）：执行基线 DDL 后置 1
    /// - 逐版本增量迁移至最新
    fn migrate(conn: &mut Connection) -> Result<(), String> {
        let current: i64 = conn
            .query_row("PRAGMA user_version", [], |row| row.get(0))
            .map_err(|e| format!("读取 schema 版本失败: {e}"))?;

        if current == 0 {
            // 判断是否为老库（objects 表已存在）
            let table_count: i64 = conn
                .query_row(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='objects'",
                    [],
                    |row| row.get(0),
                )
                .map_err(|e| format!("检测已有表失败: {e}"))?;

            // 基线 DDL 与版本号同事务原子提交：PRAGMA user_version 写库头、随事务落盘，
            // 消除"DDL 已提交而版本未更新"的崩溃窗口（该窗口会导致重启后重跑 ALTER 报
            // duplicate column、库无法打开），也避免全新库半初始化被误判为老库
            let tx = conn
                .unchecked_transaction()
                .map_err(|e| format!("开启基线事务失败: {e}"))?;
            if table_count == 0 {
                tx.execute_batch(BASELINE_DDL)
                    .map_err(|e| format!("初始化表失败: {e}"))?;
            }
            tx.execute_batch("PRAGMA user_version = 1")
                .map_err(|e| format!("设置 schema 版本失败: {e}"))?;
            tx.commit()
                .map_err(|e| format!("提交基线事务失败: {e}"))?;
        }

        // 逐版本增量迁移：DDL 与版本号在同一事务内原子提交（同上理由）
        for &(target, sql) in MIGRATE_STEPS {
            if current < target {
                let tx = conn
                    .unchecked_transaction()
                    .map_err(|e| format!("开启迁移事务失败: {e}"))?;
                tx.execute_batch(sql)
                    .map_err(|e| format!("迁移至 v{target} 失败: {e}"))?;
                tx.execute_batch(&format!("PRAGMA user_version = {target}"))
                    .map_err(|e| format!("设置 schema 版本失败: {e}"))?;
                tx.commit()
                    .map_err(|e| format!("提交迁移事务失败: {e}"))?;
            }
        }

        Ok(())
    }

    /// 将 WAL 合并回主库文件并截断（备份前调用，确保复制主文件即含全部数据）
    pub fn checkpoint(&self) -> Result<(), String> {
        self.conn
            .query_row("PRAGMA wal_checkpoint(TRUNCATE)", [], |_| Ok(()))
            .map_err(|e| format!("WAL checkpoint 失败: {e}"))
    }

    // ── 配置 ───────────────────────────────────────────────────────────────

    pub fn get_config(&self, key: &str) -> Result<Option<String>, String> {
        self.conn
            .query_row(
                "SELECT value FROM config WHERE key=?",
                params![key],
                |row| row.get::<_, String>(0),
            )
            .map(Some)
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

    pub fn get_object_opt(&self, obj_id: &str) -> Result<Option<ObjectRow>, String> {
        match self.conn.query_row(
            "SELECT o.*, s.name AS series_name FROM objects o \
             LEFT JOIN series s ON o.series_id = s.id WHERE o.id=?",
            params![obj_id],
            ObjectRow::from_row,
        ) {
            Ok(o) => Ok(Some(o)),
            // 仅"不存在"映射为 None；其他错误原样上抛，
            // 避免瞬时 DB 故障被调用方（如追加导入的目录重建）误判为对象缺失
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(format!("查询对象失败: {e}")),
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

    /// 设置对象所属系列与卷号（单条 UPDATE）。
    /// series_id 为 None 时清除关联，volume 为 None 时清除卷号。
    pub fn set_object_series(
        &self,
        obj_id: &str,
        series_id: Option<&str>,
        volume: Option<i64>,
    ) -> Result<(), String> {
        self.conn
            .execute(
                "UPDATE objects SET series_id=?, volume=? WHERE id=?",
                params![series_id, volume, obj_id],
            )
            .map_err(|e| format!("设置对象系列失败: {e}"))?;
        Ok(())
    }

    /// 卷号查重：同系列下是否已有其他对象占用该卷号，返回冲突对象名
    pub fn find_series_volume_conflict(
        &self,
        series_id: &str,
        volume: i64,
        exclude_obj: &str,
    ) -> Result<Option<String>, String> {
        self.conn
            .query_row(
                "SELECT name FROM objects WHERE series_id=? AND volume=? AND id!=? LIMIT 1",
                params![series_id, volume, exclude_obj],
                |r| r.get::<_, String>(0),
            )
            .map(Some)
            .or_else(|e| match e {
                rusqlite::Error::QueryReturnedNoRows => Ok(None),
                _ => Err(format!("查询卷号冲突失败: {e}")),
            })
    }

    // ── 批量查询 ────────────────────────────────────────────────────────────

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
                    Ok((
                        row.get::<_, String>(0)?, // object_id
                        row.get::<_, String>(1)?, // category
                        row.get::<_, String>(2)?, // value
                    ))
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
                    Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
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
                    Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
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
                series_id: row.series_id.clone(),
                series_name: row.series_name.clone(),
                volume: row.volume,
                tags,
                image_count: *count_map.get(&row.id).unwrap_or(&0),
                first_image: first_map.get(&row.id).cloned(),
            });
        }
        Ok(result)
    }

    pub fn get_all_objects(&self, include_r18: bool) -> Result<Vec<AssembledObject>, String> {
        let sql = "SELECT o.*, s.name AS series_name FROM objects o \
                   LEFT JOIN series s ON o.series_id = s.id \
                   ORDER BY o.created_at DESC";
        let mut stmt = self
            .conn
            .prepare(sql)
            .map_err(|e| format!("查询全部对象失败: {e}"))?;
        let rows: Vec<ObjectRow> = stmt
            .query_map([], ObjectRow::from_row)
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
            SELECT DISTINCT o.*, s.name AS series_name FROM objects o
            LEFT JOIN tags t ON t.object_id = o.id
            LEFT JOIN series s ON o.series_id = s.id
            WHERE o.name LIKE ? ESCAPE '\' OR t.value LIKE ? ESCAPE '\' OR s.name LIKE ? ESCAPE '\'
            ORDER BY o.created_at DESC
        "#;
        let mut stmt = self
            .conn
            .prepare(sql)
            .map_err(|e| format!("搜索对象失败: {e}"))?;
        let rows: Vec<ObjectRow> = stmt
            .query_map(params![pattern, pattern, pattern], ObjectRow::from_row)
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
        Ok(filter_assembled_by_tags(all, filters))
    }

    /// 按系列名筛选对象（供侧栏系列筛选用）
    pub fn get_objects_by_series_names(
        &self,
        names: &[String],
        include_r18: bool,
    ) -> Result<Vec<AssembledObject>, String> {
        if names.is_empty() {
            return self.get_all_objects(include_r18);
        }
        let placeholders = vec!["?"; names.len()].join(",");
        let sql = format!(
            r#"SELECT DISTINCT o.*, s.name AS series_name FROM objects o
               LEFT JOIN series s ON o.series_id = s.id
               WHERE s.name IN ({placeholders})
               ORDER BY o.created_at DESC"#
        );
        let mut stmt = self
            .conn
            .prepare(&sql)
            .map_err(|e| format!("按系列查询失败: {e}"))?;
        let rows: Vec<ObjectRow> = stmt
            .query_map(rusqlite::params_from_iter(names.iter()), ObjectRow::from_row)
            .map_err(|e| format!("按系列查询失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        self.assemble_objects(&rows, include_r18)
    }

    // ── 系列 ──────────────────────────────────────────────────────────────────

    /// 创建系列，返回是否成功（重名 UNIQUE 冲突时返回 false）
    pub fn create_series(&self, id: &str, name: &str) -> Result<bool, String> {
        match self.conn.execute(
            "INSERT INTO series(id, name) VALUES(?, ?)",
            params![id, name],
        ) {
            Ok(_) => Ok(true),
            Err(rusqlite::Error::SqliteFailure(err, _))
                if err.code == rusqlite::ErrorCode::ConstraintViolation => Ok(false),
            Err(e) => Err(format!("创建系列失败: {e}")),
        }
    }

    /// 按名称获取或创建系列，返回系列 ID（重名时查回已有 ID，幂等）。
    pub fn get_or_create_series_by_name(&self, name: &str) -> Result<String, String> {
        let id = new_uuid();
        if self.create_series(&id, name)? {
            return Ok(id);
        }
        // UNIQUE 冲突：按名查回已有系列
        self.conn
            .query_row(
                "SELECT id FROM series WHERE name=?",
                params![name],
                |row| row.get::<_, String>(0),
            )
            .map_err(|e| format!("查回系列失败: {e}"))
    }

    /// 重命名系列（UNIQUE 冲突时返回中文错误）
    pub fn rename_series(&self, id: &str, new_name: &str) -> Result<(), String> {
        match self.conn.execute(
            "UPDATE series SET name=? WHERE id=?",
            params![new_name, id],
        ) {
            Ok(_) => Ok(()),
            Err(rusqlite::Error::SqliteFailure(err, _))
                if err.code == rusqlite::ErrorCode::ConstraintViolation =>
            {
                Err(format!("系列名已存在: {new_name}"))
            }
            Err(e) => Err(format!("重命名系列失败: {e}")),
        }
    }

    /// 删除系列（对象 series_id 靠 ON DELETE SET NULL 自动置空）
    pub fn delete_series(&self, id: &str) -> Result<(), String> {
        self.conn
            .execute("DELETE FROM series WHERE id=?", params![id])
            .map_err(|e| format!("删除系列失败: {e}"))?;
        Ok(())
    }

    /// 列出全部系列，含成员数与首封面。
    /// first_cover 取该系列内 volume 最小（NULLS LAST）对象的封面。
    pub fn list_series(&self) -> Result<Vec<SeriesRow>, String> {
        let mut stmt = self.conn
            .prepare(
                r#"SELECT s.id, s.name, COUNT(o.id) AS cnt,
                          (SELECT o2.cover_image FROM objects o2
                           WHERE o2.series_id = s.id
                           ORDER BY o2.volume IS NULL, o2.volume ASC, o2.created_at DESC
                           LIMIT 1) AS first_cover
                   FROM series s
                   LEFT JOIN objects o ON o.series_id = s.id
                   GROUP BY s.id, s.name
                   ORDER BY s.name"#,
            )
            .map_err(|e| format!("查询系列失败: {e}"))?;
        let rows: Vec<SeriesRow> = stmt
            .query_map([], |row| {
                Ok(SeriesRow {
                    id: row.get(0)?,
                    name: row.get(1)?,
                    count: row.get(2)?,
                    first_cover: row.get(3)?,
                })
            })
            .map_err(|e| format!("查询系列失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(rows)
    }

    // ── 标签 ──────────────────────────────────────────────────────────────────

    pub fn get_tags(&self, obj_id: &str) -> Result<Tags, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT category, value FROM tags WHERE object_id=? ORDER BY id")
            .map_err(|e| format!("查询标签失败: {e}"))?;
        let raw: Vec<(String, String)> = stmt
            .query_map(params![obj_id], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
            })
            .map_err(|e| format!("查询标签失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(Self::tags_from_raw(&raw))
    }

    fn tags_from_raw(raw: &[(String, String)]) -> Tags {
        use std::collections::hash_map::Entry;
        let mut map: HashMap<String, TagValue> = HashMap::new();
        for (cat, val) in raw {
            if cat == "r18" {
                map.insert("r18".into(), TagValue::Bool(val == "true"));
            } else {
                match map.entry(cat.clone()) {
                    Entry::Occupied(mut e) => {
                        if let TagValue::List(v) = e.get_mut() {
                            v.push(val.clone());
                        }
                    }
                    Entry::Vacant(e) => {
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
            .query_map(params![obj_id], ImageRow::from_row)
            .map_err(|e| format!("查询图片失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(rows)
    }

    /// 按图片 ID 直查（协议层缩略图/原图请求用，避免每次全量查询后线性查找）
    pub fn get_image_by_id(&self, obj_id: &str, img_id: &str) -> Result<Option<ImageRow>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT * FROM images WHERE object_id=? AND id=?")
            .map_err(|e| format!("查询图片失败: {e}"))?;
        let mut rows: Vec<ImageRow> = stmt
            .query_map(params![obj_id, img_id], ImageRow::from_row)
            .map_err(|e| format!("查询图片失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(rows.pop())
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

    /// 全部对象的封面路径（缓存维护用）
    pub fn get_all_cover_paths(&self) -> Result<Vec<String>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT cover_image FROM objects WHERE cover_image IS NOT NULL AND cover_image != ''")
            .map_err(|e| format!("查询封面失败: {e}"))?;
        let vals: Vec<String> = stmt
            .query_map([], |row| row.get::<_, String>(0))
            .map_err(|e| format!("查询封面失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(vals)
    }

    /// 全部图片的文件路径（缓存维护用）
    pub fn get_all_image_filepaths(&self) -> Result<Vec<String>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT filepath FROM images")
            .map_err(|e| format!("查询图片路径失败: {e}"))?;
        let vals: Vec<String> = stmt
            .query_map([], |row| row.get::<_, String>(0))
            .map_err(|e| format!("查询图片路径失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(vals)
    }

    // ── 书签 ──────────────────────────────────────────────────────────────────

    /// 列出对象的全部书签（按 page_idx 升序）
    pub fn list_bookmarks(&self, object_id: &str) -> Result<Vec<BookmarkRow>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT * FROM bookmarks WHERE object_id=? ORDER BY page_idx")
            .map_err(|e| format!("查询书签失败: {e}"))?;
        let rows: Vec<BookmarkRow> = stmt
            .query_map(params![object_id], BookmarkRow::from_row)
            .map_err(|e| format!("查询书签失败: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(rows)
    }

    /// 添加书签。UNIQUE(object_id, page_idx) 冲突时改为更新备注（幂等 upsert）。
    /// 对象删除时书签靠外键 ON DELETE CASCADE 自动清理。
    pub fn add_bookmark(
        &self,
        object_id: &str,
        page_idx: i64,
        note: Option<&str>,
    ) -> Result<BookmarkRow, String> {
        self.conn
            .execute(
                "INSERT INTO bookmarks(object_id, page_idx, note) VALUES(?, ?, ?) \
                 ON CONFLICT(object_id, page_idx) DO UPDATE SET note=excluded.note",
                params![object_id, page_idx, note],
            )
            .map_err(|e| format!("添加书签失败: {e}"))?;
        // 查回书签行（含自增 id 与时间戳）
        self.conn
            .query_row(
                "SELECT * FROM bookmarks WHERE object_id=? AND page_idx=?",
                params![object_id, page_idx],
                BookmarkRow::from_row,
            )
            .map_err(|e| format!("查回书签失败: {e}"))
    }

    /// 删除书签
    pub fn remove_bookmark(&self, id: i64) -> Result<(), String> {
        self.conn
            .execute("DELETE FROM bookmarks WHERE id=?", params![id])
            .map_err(|e| format!("删除书签失败: {e}"))?;
        Ok(())
    }

}

// ── Row 映射 trait ────────────────────────────────────────────────────────────

/// 内存标签过滤（各筛选条件取 AND、条件内取 OR），供 filter_by_tags
/// 与"系列 + 标签"组合筛选复用
pub fn filter_assembled_by_tags(
    list: Vec<AssembledObject>,
    filters: &HashMap<String, Vec<String>>,
) -> Vec<AssembledObject> {
    list.into_iter()
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
        .collect()
}

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
            series_id: row.get::<_, Option<String>>("series_id").unwrap_or(None),
            series_name: row.get::<_, Option<String>>("series_name").unwrap_or(None),
            volume: row.get::<_, Option<i64>>("volume").unwrap_or(None),
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

impl FromRow for BookmarkRow {
    fn from_row(row: &Row) -> rusqlite::Result<Self> {
        Ok(Self {
            id: row.get("id")?,
            object_id: row.get("object_id")?,
            page_idx: row.get("page_idx")?,
            note: row.get("note")?,
            created_at: row.get("created_at")?,
        })
    }
}

// ── 辅助函数 ──────────────────────────────────────────────────────────────────

pub fn new_uuid() -> String {
    Uuid::new_v4().to_string()
}

// ── 单元测试 ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn tmp_db(tag: &str) -> PathBuf {
        std::env::temp_dir().join(format!("ms_dbtest_{tag}_{}.db", uuid::Uuid::new_v4()))
    }

    /// 老版（v1）schema：无 series/bookmarks 表、objects 无 series_id/volume 列
    const V1_DDL: &str = r#"
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
        INSERT OR IGNORE INTO config(key, value) VALUES('schema_version', '1');
    "#;

    fn table_exists(conn: &Connection, name: &str) -> bool {
        conn.query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            params![name],
            |r| r.get::<_, i64>(0),
        )
        .map(|c| c > 0)
        .unwrap_or(false)
    }

    fn user_version(conn: &Connection) -> i64 {
        conn.query_row("PRAGMA user_version", [], |r| r.get(0)).unwrap()
    }

    /// 老库迁移：先用 v1 DDL 手工建库再打开触发迁移，验证 series/bookmarks 表
    /// 存在且数据未丢
    #[test]
    fn migrate_old_db_adds_series_and_bookmarks_preserving_data() {
        let path = tmp_db("oldmig");
        // 手工建 v1 老库并写入数据
        {
            let conn = Connection::open(&path).unwrap();
            conn.execute_batch(V1_DDL).unwrap();
            conn.execute(
                "INSERT INTO objects(id, type, name, source_path, storage_path, cover_image) \
                 VALUES('o1', 'directory', '老对象', 'src', 'dst', 'cover1.jpg')",
                [],
            )
            .unwrap();
            conn.execute(
                "INSERT INTO tags(object_id, category, value) VALUES('o1', 'author', '老作者')",
                [],
            )
            .unwrap();
        }
        // 重新打开 → 触发迁移
        let db = Database::open(path.to_str().unwrap()).unwrap();
        assert!(table_exists(&db.conn, "series"), "迁移应创建 series 表");
        assert!(table_exists(&db.conn, "bookmarks"), "迁移应创建 bookmarks 表");
        assert_eq!(user_version(&db.conn), 3);
        // 老数据未丢
        let obj = db.get_object_opt("o1").unwrap().unwrap();
        assert_eq!(obj.name, "老对象");
        assert_eq!(obj.cover_image.as_deref(), Some("cover1.jpg"));
        assert_eq!(obj.series_id, None, "迁移后新列 series_id 默认 NULL");
        assert_eq!(obj.series_name, None);
        assert_eq!(obj.volume, None, "迁移后新列 volume 默认 NULL");
        let tags = db.get_tags("o1").unwrap();
        assert!(tags.0.contains_key("author"), "老标签应保留");
        // 迁移后系列功能可用
        let sid = db.get_or_create_series_by_name("迁移系列").unwrap();
        db.set_object_series("o1", Some(&sid), Some(2)).unwrap();
        let obj2 = db.get_object_opt("o1").unwrap().unwrap();
        assert_eq!(obj2.series_id.as_deref(), Some(sid.as_str()));
        assert_eq!(obj2.series_name.as_deref(), Some("迁移系列"));
        assert_eq!(obj2.volume, Some(2));
        let series = db.list_series().unwrap();
        assert_eq!(series.len(), 1);
        assert_eq!(series[0].count, 1);
        assert_eq!(series[0].first_cover.as_deref(), Some("cover1.jpg"));
    }

    /// 全新库：基线 DDL + 增量步骤一次到位
    #[test]
    fn migrate_fresh_db_creates_all_tables() {
        let path = tmp_db("freshmig");
        let db = Database::open(path.to_str().unwrap()).unwrap();
        for t in ["config", "objects", "tags", "images", "series", "bookmarks"] {
            assert!(table_exists(&db.conn, t), "表 {t} 应存在");
        }
        assert_eq!(user_version(&db.conn), 3);
    }

    /// 二次打开应直接跳过迁移且不破坏数据
    #[test]
    fn migrate_reopen_is_idempotent() {
        let path = tmp_db("idemig");
        {
            let db = Database::open(path.to_str().unwrap()).unwrap();
            db.create_object("oid-1", "directory", "对象", "src", "dst").unwrap();
            let sid = db.get_or_create_series_by_name("稳定系列").unwrap();
            db.set_object_series("oid-1", Some(&sid), Some(1)).unwrap();
            db.add_bookmark("oid-1", 3, Some("bk")).unwrap();
        }
        let db2 = Database::open(path.to_str().unwrap()).unwrap();
        assert_eq!(user_version(&db2.conn), 3);
        let series = db2.list_series().unwrap();
        assert_eq!(series.len(), 1);
        assert_eq!(series[0].name, "稳定系列");
        assert_eq!(series[0].count, 1);
        assert_eq!(db2.list_bookmarks("oid-1").unwrap().len(), 1);
    }

    /// 系列创建与重名 UNIQUE：create_series 拒绝重名，get_or_create 查回已有
    #[test]
    fn series_create_and_unique_conflict() {
        let path = tmp_db("seruniq");
        let db = Database::open(path.to_str().unwrap()).unwrap();
        assert!(db.create_series("s1", "系列甲").unwrap(), "首次创建应成功");
        assert!(!db.create_series("s2", "系列甲").unwrap(), "重名应被 UNIQUE 拒绝");
        // 按名幂等获取：重名冲突时查回已有 ID
        assert_eq!(db.get_or_create_series_by_name("系列甲").unwrap(), "s1");
        // 新名创建返回新 ID，系列列表两条
        db.get_or_create_series_by_name("系列乙").unwrap();
        assert_eq!(db.list_series().unwrap().len(), 2);
    }
}
