//! 业务服务层 — 与 Python 版 services/library_service.py 对等
//!
//! UI/Tauri commands 只依赖本服务，不直接访问 Database。
//! 借助 Mutex<Connection> 实现线程安全（rusqlite Connection 本身不是 Sync）。

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use crate::config::THUMB_CACHE_DIR;
use crate::db::{
    self, AssembledObject, Database, ImageRow, TagValue, Tags, new_uuid,
};
use crate::file_ops::{
    collect_images, copy_image_with_seq_name, next_seq_number,
};
use crate::thumbnail::{clear_cached_thumbs, get_thumb_cache_dir};

pub struct LibraryService {
    pub db: Mutex<Database>,
}

/// 导入被取消
#[derive(Debug)]
pub struct ImportCancelled;

impl LibraryService {
    pub fn new(db_path: &str) -> Result<Self, String> {
        let db = Database::open(db_path)?;
        Ok(Self {
            db: Mutex::new(db),
        })
    }

    // ── 配置 ───────────────────────────────────────────────────────────────

    pub fn get_config(&self, key: &str) -> Result<Option<String>, String> {
        self.db.lock().unwrap().get_config(key)
    }

    pub fn set_config(&self, key: &str, value: &str) -> Result<(), String> {
        self.db.lock().unwrap().set_config(key, value)
    }

    pub fn get_config_bool(&self, key: &str, default: bool) -> Result<bool, String> {
        self.db.lock().unwrap().get_config_bool(key, default)
    }

    pub fn set_config_bool(&self, key: &str, value: bool) -> Result<(), String> {
        self.db.lock().unwrap().set_config_bool(key, value)
    }

    // ── 查询 ───────────────────────────────────────────────────────────────

    pub fn get_all_objects(&self, include_r18: bool) -> Result<Vec<AssembledObject>, String> {
        self.db.lock().unwrap().get_all_objects(include_r18)
    }

    pub fn search_objects(
        &self,
        keyword: &str,
        include_r18: bool,
    ) -> Result<Vec<AssembledObject>, String> {
        self.db.lock().unwrap().search_objects(keyword, include_r18)
    }

    pub fn filter_by_tags(
        &self,
        filters: &HashMap<String, Vec<String>>,
        include_r18: bool,
    ) -> Result<Vec<AssembledObject>, String> {
        self.db.lock().unwrap().filter_by_tags(filters, include_r18)
    }

    pub fn get_object(&self, obj_id: &str) -> Result<Option<AssembledObject>, String> {
        let db = self.db.lock().unwrap();
        let obj = db.get_object_opt(obj_id)?;
        if obj.is_none() {
            return Ok(None);
        }
        let row = obj.unwrap();
        let tags = db.get_tags(obj_id)?;
        let images = db.get_images(obj_id)?;
        let first_image = images.first().map(|i| i.filepath.clone());
        let image_count = images.len() as i64;
        Ok(Some(AssembledObject {
            id: row.id,
            obj_type: row.obj_type,
            name: row.name,
            source_path: row.source_path,
            storage_path: row.storage_path,
            cover_image: row.cover_image,
            last_read_idx: row.last_read_idx,
            created_at: row.created_at,
            tags,
            image_count,
            first_image,
        }))
    }

    pub fn get_images(&self, obj_id: &str) -> Result<Vec<ImageRow>, String> {
        self.db.lock().unwrap().get_images(obj_id)
    }

    pub fn get_image_count(&self, obj_id: &str) -> Result<i64, String> {
        self.db.lock().unwrap().get_image_count(obj_id)
    }

    pub fn get_tag_values(&self, category: &str) -> Result<Vec<String>, String> {
        self.db.lock().unwrap().get_all_tag_values(category)
    }

    /// 返回对象封面路径；未设置封面时取第一张图片
    pub fn resolve_cover(&self, obj: &AssembledObject) -> Option<String> {
        let cover = obj.cover_image.as_ref().filter(|p| Path::new(p).is_file());
        if cover.is_some() {
            return cover.cloned();
        }
        let first = obj.first_image.as_ref().filter(|p| Path::new(p).is_file());
        if first.is_some() {
            return first.cloned();
        }
        // fallback: query DB
        if let Ok(images) = self.get_images(&obj.id) {
            if let Some(img) = images.first() {
                if Path::new(&img.filepath).is_file() {
                    return Some(img.filepath.clone());
                }
            }
        }
        None
    }

    // ── 变更 ───────────────────────────────────────────────────────────────

    pub fn update_object_name(&self, obj_id: &str, name: &str) -> Result<(), String> {
        self.db.lock().unwrap().update_object_name(obj_id, name)
    }

    pub fn set_object_tags(&self, obj_id: &str, tags: &Tags) -> Result<(), String> {
        self.db.lock().unwrap().set_tags(obj_id, tags)
    }

    pub fn update_object_cover(&self, obj_id: &str, cover_image: &str) -> Result<(), String> {
        self.db
            .lock()
            .unwrap()
            .update_object_cover(obj_id, cover_image)
    }

    pub fn update_last_read(&self, obj_id: &str, idx: i64) -> Result<(), String> {
        self.db.lock().unwrap().update_last_read(obj_id, idx)
    }

    /// 检查存储路径是否已被（其他）对象占用
    fn storage_path_taken(&self, path: &str, exclude_id: Option<&str>) -> bool {
        let db = self.db.lock().unwrap();
        let target = normalize_path(path);
        let conn = &db.conn;
        let mut stmt = match conn.prepare("SELECT id, storage_path FROM objects") {
            Ok(s) => s,
            Err(_) => return false,
        };
        let rows = stmt
            .query_map([], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, Option<String>>(1)?,
                ))
            })
            .ok();
        if let Some(rows) = rows {
            for r in rows.flatten() {
                let (oid, sp) = r;
                let sp = match sp {
                    Some(s) if !s.trim().is_empty() => s,
                    _ => continue,
                };
                if normalize_path(&sp) == target {
                    if exclude_id.is_none() || exclude_id != Some(oid.as_str()) {
                        return true;
                    }
                }
            }
        }
        false
    }

    /// 删除对象（DB + 可选本地文件 + 缩略图缓存）
    pub fn delete_object(
        &self,
        obj_id: &str,
        delete_files: bool,
        storage_root: Option<&str>,
    ) -> Result<(), String> {
        let db = self.db.lock().unwrap();
        let obj = db.get_object_opt(obj_id)?;

        // 清理缩略图缓存
        let root = storage_root
            .map(|r| r.to_string())
            .or_else(|| {
                obj.as_ref()
                    .and_then(|o| o.storage_path.as_ref())
                    .map(|sp| Path::new(sp).parent().map(|p| p.to_string_lossy().to_string()).unwrap_or_default())
            });
        if let (Some(obj), Some(root)) = (&obj, &root) {
            let cache_dir = get_thumb_cache_dir(root);
            let mut paths: Vec<String> = Vec::new();
            if let Some(cover) = &obj.cover_image {
                paths.push(cover.clone());
            }
            if let Ok(images) = db.get_images(obj_id) {
                paths.extend(images.iter().map(|i| i.filepath.clone()));
            }
            clear_cached_thumbs(&cache_dir, &paths);
        }

        // 删除对象（tags / images 通过外键 CASCADE 一并删除）
        db.delete_object(obj_id)?;

        // 物理删除文件
        if delete_files {
            if let Some(obj) = &obj {
                if let Some(sp) = &obj.storage_path {
                    if Path::new(sp).is_dir() {
                        // 防御：历史数据可能存在多对象共享同一存储目录
                        if !self.storage_path_taken(sp, None) {
            let _ = fs::remove_dir_all(sp);
                        } else {
                            log::warn!("对象 {} 的存储目录与其他对象共享，跳过物理删除: {}", obj_id, sp);
                        }
                    }
                }
            }
        }
        Ok(())
    }

    // ── 导入 ───────────────────────────────────────────────────────────────

    /// 追加导入时解析目标目录
    fn resolve_append_target_dir(
        &self,
        obj_id: &str,
        obj_name: &str,
        storage_root: &str,
    ) -> Result<String, String> {
        let db = self.db.lock().unwrap();
        let obj = db.get_object_opt(obj_id)?;
        let storage_path = obj
            .as_ref()
            .and_then(|o| o.storage_path.as_ref())
            .map(|s| s.trim().to_string())
            .unwrap_or_default();

        if !storage_path.is_empty() && Path::new(&storage_path).is_dir() {
            return Ok(storage_path);
        }

        // 重建
        let name = obj
            .as_ref()
            .map(|o| o.name.as_str())
            .unwrap_or(obj_name);
        let rebuilt = Path::new(storage_root).join(name).to_string_lossy().to_string();
        if self.storage_path_taken(&rebuilt, Some(obj_id)) {
            return Err(format!("存储目录已被其他对象占用，无法重建：{rebuilt}"));
        }
        fs::create_dir_all(&rebuilt).map_err(|e| format!("创建目录失败: {e}"))?;
        db.update_object_storage_path(obj_id, &rebuilt)?;
        Ok(rebuilt)
    }

    /// 导入整个目录到 storage_root 下。返回 (成功数, 失败数)。
    pub fn import_directory(
        &self,
        obj_id: &str,
        name: &str,
        tags: &Tags,
        source_dir: &str,
        storage_root: &str,
        is_new: bool,
        progress_cb: Option<&dyn Fn(usize, usize)>,
        cancel_check: Option<&dyn Fn() -> bool>,
    ) -> Result<(i64, i64), String> {
        if !Path::new(source_dir).is_dir() {
            return Err(format!("源目录不存在：{source_dir}"));
        }

        let mut created_object = false;
        let mut created_dir = false;
        let mut created_images: Vec<(String, String)> = Vec::new();
        let storage_obj_dir;

        let db = self.db.lock().unwrap();

        if is_new {
            storage_obj_dir = Path::new(storage_root).join(name).to_string_lossy().to_string();
            if self.storage_path_taken(&storage_obj_dir, None) {
                return Err(format!("存储目录已被其他对象占用：{name}"));
            }
            // M4 防御：库根下已存在同名非空目录
            if Path::new(&storage_obj_dir).is_dir()
                && fs::read_dir(&storage_obj_dir)
                    .map(|mut d| d.next().is_some())
                    .unwrap_or(false)
            {
                return Err(format!(
                    "目录已存在且非空（不属于任何对象），为避免误删其中文件已拒绝导入：{storage_obj_dir}"
                ));
            }
            let dir_existed = Path::new(&storage_obj_dir).is_dir();
            created_dir = !dir_existed;
            fs::create_dir_all(&storage_obj_dir)
                .map_err(|e| format!("创建存储目录失败: {e}"))?;

            if !db.create_object(obj_id, "directory", name, source_dir, &storage_obj_dir)? {
                if created_dir {
                    let _ = fs::remove_dir_all(&storage_obj_dir);
                }
                return Err(format!("对象 ID 冲突，创建失败：{obj_id}"));
            }
            created_object = true;
            db.set_tags(obj_id, tags)?;
        } else {
            // 追加导入：使用 DB 记录的目录
            drop(db);
            storage_obj_dir = self.resolve_append_target_dir(obj_id, name, storage_root)?;
        }

        // 收集图片并复制
        let images = collect_images(source_dir);
        let total = images.len();
        let mut seq = next_seq_number(&storage_obj_dir);
        let db = self.db.lock().unwrap();
        let sort_start = db.get_image_count(obj_id).unwrap_or(0);

        let mut ok: i64 = 0;
        let mut fail: i64 = 0;

        for (i, src) in images.iter().enumerate() {
            // 检查取消
            if let Some(cancel) = cancel_check {
                if cancel() {
                    // 回滚
                    drop(db);
                    self.rollback_import(obj_id, created_object, created_dir, &storage_obj_dir, &created_images)?;
                    return Err("导入已取消".to_string());
                }
            }

            if let Some((filename, dest, used_seq)) =
                copy_image_with_seq_name(src, &storage_obj_dir, seq)
            {
                let img_id = new_uuid();
                db.add_image(&img_id, obj_id, &filename, &dest, sort_start + i as i64)?;
                created_images.push((img_id, dest));
                seq = used_seq + 1;
                ok += 1;
            } else {
                fail += 1;
            }

            if let Some(cb) = progress_cb {
                cb(i + 1, total);
            }
        }

        // 新建对象默认用第一张图作为封面
        if is_new {
            let images = db.get_images(obj_id)?;
            let obj = db.get_object_opt(obj_id)?;
            if let (Some(images), Some(obj)) = (images.first(), obj) {
                if obj.cover_image.is_none() {
                    db.update_object_cover(obj_id, &images.filepath)?;
                }
            }
        }

        Ok((ok, fail))
    }

    fn rollback_import(
        &self,
        obj_id: &str,
        created_object: bool,
        created_dir: bool,
        storage_obj_dir: &str,
        created_images: &[(String, String)],
    ) -> Result<(), String> {
        let db = self.db.lock().unwrap();
        if created_object {
            db.delete_object(obj_id)?;
            if created_dir && Path::new(storage_obj_dir).is_dir() {
                let _ = fs::remove_dir_all(storage_obj_dir);
            }
        } else {
            for (img_id, dest) in created_images {
                db.delete_image(img_id)?;
                let _ = fs::remove_file(dest);
            }
        }
        Ok(())
    }

    /// 导入单张/多张图片到已有对象。返回 (成功数, 失败数)。
    pub fn import_single_files(
        &self,
        obj_id: &str,
        paths: &[String],
        storage_root: &str,
    ) -> Result<(i64, i64), String> {
        let storage_obj_dir = self.resolve_append_target_dir(obj_id, "unnamed", storage_root)?;

        let db = self.db.lock().unwrap();
        let mut ok: i64 = 0;
        let mut fail: i64 = 0;
        let cur_count = db.get_image_count(obj_id).unwrap_or(0);
        let mut seq = next_seq_number(&storage_obj_dir);

        let mut sorted: Vec<String> = paths
            .iter()
            .filter(|p| !Path::new(p)
                .file_name()
                .and_then(|n| n.to_str())
                .map(|n| n.starts_with('.'))
                .unwrap_or(true))
            .map(|p| p.clone())
            .collect();
        sorted.sort_by_key(|p| {
            Path::new(p)
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default()
        });

        for src in &sorted {
            if let Some((filename, dest, used_seq)) =
                copy_image_with_seq_name(src, &storage_obj_dir, seq)
            {
                let img_id = new_uuid();
                db.add_image(&img_id, obj_id, &filename, &dest, cur_count + ok)?;
                ok += 1;
                seq = used_seq + 1;
            } else {
                fail += 1;
            }
        }
        Ok((ok, fail))
    }

    // ── 库迁移 ──────────────────────────────────────────────────────────────

    pub fn migrate_library(
        &self,
        new_root: &str,
        progress_cb: Option<&dyn Fn(usize, usize, &str)>,
    ) -> Result<(usize, Vec<String>), String> {
        crate::library_manager::migrate_library(self, new_root, progress_cb)
    }
}

// ── 辅助函数 ──────────────────────────────────────────────────────────────────

fn normalize_path(path: &str) -> String {
    let p = PathBuf::from(path);
    // normcase + abspath 等价
    let canonical = fs::canonicalize(&p).unwrap_or(p);
    let mut s = canonical.to_string_lossy().to_string();
    if cfg!(target_os = "windows") {
        s = s.to_lowercase();
    }
    s
}
