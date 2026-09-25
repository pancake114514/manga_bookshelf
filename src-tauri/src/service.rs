//! 业务服务层 — 与 Python 版 services/library_service.py 对等
//!
//! UI/Tauri commands 只依赖本服务，不直接访问 Database。
//! 借助 Mutex<Connection> 实现线程安全（rusqlite Connection 本身不是 Sync）。
//! 加锁一律 unwrap_or_else(|p| p.into_inner())：DB 操作均为单语句/事务级原子操作，
//! 持锁线程 panic 后从毒锁恢复是安全的，避免一次 panic 永久瘫痪整个后端。

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use crate::db::{AssembledObject, Database, ImageRow, Tags, new_uuid};
use crate::file_ops::{
    collect_images, copy_image_keep_name, find_thumb_cover,
};
use crate::thumbnail::{clear_cached_thumbs, get_thumb_cache_dir};

pub struct LibraryService {
    pub db: Mutex<Database>,
}

impl LibraryService {
    pub fn new(db_path: &str) -> Result<Self, String> {
        let db = Database::open(db_path)?;
        Ok(Self {
            db: Mutex::new(db),
        })
    }

    // ── 配置 ───────────────────────────────────────────────────────────────

    pub fn get_config(&self, key: &str) -> Result<Option<String>, String> {
        self.db.lock().unwrap_or_else(|p| p.into_inner()).get_config(key)
    }

    pub fn set_config(&self, key: &str, value: &str) -> Result<(), String> {
        self.db.lock().unwrap_or_else(|p| p.into_inner()).set_config(key, value)
    }

    // ── 查询 ───────────────────────────────────────────────────────────────

    pub fn get_all_objects(&self, include_r18: bool) -> Result<Vec<AssembledObject>, String> {
        self.db.lock().unwrap_or_else(|p| p.into_inner()).get_all_objects(include_r18)
    }

    pub fn search_objects(
        &self,
        keyword: &str,
        include_r18: bool,
    ) -> Result<Vec<AssembledObject>, String> {
        self.db.lock().unwrap_or_else(|p| p.into_inner()).search_objects(keyword, include_r18)
    }

    pub fn filter_by_tags(
        &self,
        filters: &HashMap<String, Vec<String>>,
        include_r18: bool,
    ) -> Result<Vec<AssembledObject>, String> {
        self.db.lock().unwrap_or_else(|p| p.into_inner()).filter_by_tags(filters, include_r18)
    }

    pub fn get_object(&self, obj_id: &str) -> Result<Option<AssembledObject>, String> {
        let db = self.db.lock().unwrap_or_else(|p| p.into_inner());
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
        self.db.lock().unwrap_or_else(|p| p.into_inner()).get_images(obj_id)
    }

    pub fn get_image_by_id(&self, obj_id: &str, img_id: &str) -> Result<Option<ImageRow>, String> {
        self.db.lock().unwrap_or_else(|p| p.into_inner()).get_image_by_id(obj_id, img_id)
    }

    pub fn get_tag_values(&self, category: &str) -> Result<Vec<String>, String> {
        self.db.lock().unwrap_or_else(|p| p.into_inner()).get_all_tag_values(category)
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
        self.db.lock().unwrap_or_else(|p| p.into_inner()).update_object_name(obj_id, name)
    }

    pub fn set_object_tags(&self, obj_id: &str, tags: &Tags) -> Result<(), String> {
        self.db.lock().unwrap_or_else(|p| p.into_inner()).set_tags(obj_id, tags)
    }

    pub fn update_object_cover(&self, obj_id: &str, cover_image: &str) -> Result<(), String> {
        self.db
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .update_object_cover(obj_id, cover_image)
    }

    pub fn update_last_read(&self, obj_id: &str, idx: i64) -> Result<(), String> {
        self.db.lock().unwrap_or_else(|p| p.into_inner()).update_last_read(obj_id, idx)
    }

    /// 检查存储路径是否已被（其他）对象占用
    /// 注意：调用方必须已持有 db 锁（对 std::sync::Mutex 重入加锁会死锁）
    fn storage_path_taken(db: &Database, path: &str, exclude_id: Option<&str>) -> bool {
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
                if normalize_path(&sp) == target
                    && (exclude_id.is_none() || exclude_id != Some(oid.as_str())) {
                        return true;
                    }
            }
        }
        false
    }

    /// 删除对象（DB + 可选本地文件 + 缩略图缓存）。
    /// 返回警告列表：文件删除失败、共享目录跳过等不阻断删除（DB 记录已删干净），
    /// 仅作为提示透出给前端。
    pub fn delete_object(
        &self,
        obj_id: &str,
        delete_files: bool,
        storage_root: Option<&str>,
    ) -> Result<Vec<String>, String> {
        let db = self.db.lock().unwrap_or_else(|p| p.into_inner());
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

        // 物理删除文件（失败/跳过不回滚：DB 已删干净，仅向用户提示残留）
        let mut warnings: Vec<String> = Vec::new();
        if delete_files {
            if let Some(obj) = &obj {
                if let Some(sp) = &obj.storage_path {
                    if Path::new(sp).is_dir() {
                        // 防御：历史数据可能存在多对象共享同一存储目录
                        if !Self::storage_path_taken(&db, sp, None) {
                            if let Err(e) = fs::remove_dir_all(sp) {
                                log::warn!("对象 {} 的本地文件删除失败: {sp}: {e}", obj_id);
                                warnings.push(format!(
                                    "本地文件删除失败（可能被其他程序占用）：{sp}"
                                ));
                            }
                        } else {
                            log::warn!("对象 {} 的存储目录与其他对象共享，跳过物理删除: {}", obj_id, sp);
                            warnings.push(format!("存储目录与其他对象共享，已跳过物理删除：{sp}"));
                        }
                    }
                }
            }
        }
        Ok(warnings)
    }

    // ── 导入 ───────────────────────────────────────────────────────────────

    /// 追加导入时解析目标目录（必要时按对象名重建）。
    /// db 由调用方持锁传入（本函数在导入流程的短锁阶段内调用）
    fn resolve_append_target_dir(
        db: &Database,
        obj_id: &str,
        obj_name: &str,
        storage_root: &str,
    ) -> Result<String, String> {
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
        if Self::storage_path_taken(db, &rebuilt, Some(obj_id)) {
            return Err(format!("存储目录已被其他对象占用，无法重建：{rebuilt}"));
        }
        fs::create_dir_all(&rebuilt).map_err(|e| format!("创建目录失败: {e}"))?;
        db.update_object_storage_path(obj_id, &rebuilt)?;
        Ok(rebuilt)
    }

    /// 导入整个目录到 storage_root 下。返回 (成功数, 失败数)。
    ///
    /// 执行分三段，把慢速文件 IO 排除在 db 锁之外，导入期间其他命令不被阻塞：
    /// ① 短锁：建对象/标签，或解析追加目标目录；
    /// ② 无锁：复制文件（支持取消/进度回调）；
    /// ③ 短锁：图片记录入库 + 封面。
    /// 任一步失败统一走回滚，不残留半成品对象/目录/文件。
    #[allow(clippy::too_many_arguments)]  // 参数组与 Python 版导入语义一一对应
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
        let mut copied_files: Vec<String> = Vec::new();
        let mut storage_obj_dir = String::new();

        let result: Result<(i64, i64), String> = (|| {
            // ── ① 短锁：建对象，或解析追加目标 ──
            if is_new {
                let db = self.db.lock().unwrap_or_else(|p| p.into_inner());
                let dir = Path::new(storage_root).join(name).to_string_lossy().to_string();
                if Self::storage_path_taken(&db, &dir, None) {
                    return Err(format!("存储目录已被其他对象占用：{name}"));
                }
                // M4 防御：库根下已存在同名非空目录
                if Path::new(&dir).is_dir()
                    && fs::read_dir(&dir)
                        .map(|mut d| d.next().is_some())
                        .unwrap_or(false)
                {
                    return Err(format!(
                        "目录已存在且非空（不属于任何对象），为避免误删其中文件已拒绝导入：{dir}"
                    ));
                }
                let dir_existed = Path::new(&dir).is_dir();
                created_dir = !dir_existed;
                fs::create_dir_all(&dir)
                    .map_err(|e| format!("创建存储目录失败: {e}"))?;

                if !db.create_object(obj_id, "directory", name, source_dir, &dir)? {
                    // ID 冲突：目录是我们刚建的，直接清理并复位标记
                    if created_dir {
                        let _ = fs::remove_dir_all(&dir);
                        created_dir = false;
                    }
                    return Err(format!("对象 ID 冲突，创建失败：{obj_id}"));
                }
                created_object = true;
                db.set_tags(obj_id, tags)?;
                storage_obj_dir = dir;
            } else {
                let db = self.db.lock().unwrap_or_else(|p| p.into_inner());
                storage_obj_dir =
                    Self::resolve_append_target_dir(&db, obj_id, name, storage_root)?;
            }

            // ── ② 无锁：复制文件（慢 IO），支持取消/进度 ──
            let images = collect_images(source_dir);
            let total = images.len();
            let sort_start = {
                let db = self.db.lock().unwrap_or_else(|p| p.into_inner());
                db.get_image_count(obj_id).unwrap_or(0)
            };

            // .thumb 封面：源目录存在 .thumb 文件时，复制进存储目录（保持
            // dot 前缀命名，collect_images 的隐藏过滤保证它不进正文），
            // 并记为该对象封面。复制失败仅记录警告，不影响导入。
            let mut thumb_cover: Option<String> = None;
            if is_new {
                if let Some(src_thumb) = find_thumb_cover(source_dir) {
                    match copy_image_keep_name(&src_thumb, &storage_obj_dir) {
                        Some((_, dest)) => {
                            copied_files.push(dest.clone());
                            thumb_cover = Some(dest);
                        }
                        None => log::warn!(".thumb 封面复制失败: {src_thumb}"),
                    }
                }
            }

            let mut rows: Vec<(String, String, i64)> = Vec::new(); // (filename, dest, sort_order)
            let mut ok: i64 = 0;
            let mut fail: i64 = 0;

            for (i, src) in images.iter().enumerate() {
                // 检查取消（已复制文件由外层统一回滚清理）
                if let Some(cancel) = cancel_check {
                    if cancel() {
                        return Err("导入已取消".to_string());
                    }
                }

                if let Some((filename, dest)) = copy_image_keep_name(src, &storage_obj_dir) {
                    copied_files.push(dest.clone());
                    rows.push((filename, dest, sort_start + i as i64));
                    ok += 1;
                } else {
                    fail += 1;
                }

                if let Some(cb) = progress_cb {
                    cb(i + 1, total);
                }
            }

            // ── ③ 短锁：入库 + 封面 ──
            let db = self.db.lock().unwrap_or_else(|p| p.into_inner());
            for (filename, dest, sort_order) in &rows {
                let img_id = new_uuid();
                db.add_image(&img_id, obj_id, filename, dest, *sort_order)?;
                created_images.push((img_id, dest.clone()));
            }

            // 新建对象默认用第一张图作为封面；若导入了 .thumb 文件则优先用它
            if is_new {
                let images = db.get_images(obj_id)?;
                let obj = db.get_object_opt(obj_id)?;
                if let (Some(images), Some(obj)) = (images.first(), obj) {
                    if obj.cover_image.is_none() {
                        let cover = thumb_cover
                            .as_deref()
                            .filter(|p| Path::new(p).is_file())
                            .unwrap_or(&images.filepath);
                        db.update_object_cover(obj_id, cover)?;
                    }
                }
            }

            Ok((ok, fail))
        })();

        match result {
            Ok(r) => Ok(r),
            Err(e) => {
                self.rollback_import(
                    obj_id,
                    created_object,
                    created_dir,
                    &storage_obj_dir,
                    &created_images,
                    &copied_files,
                )?;
                Err(e)
            }
        }
    }

    /// 导入回滚：撤销一次 import 产生的全部副作用。
    /// created_images 为已入库的 (img_id, dest)；copied_files 为已落盘的全部文件
    /// （含未入库的，入库失败/取消时也存在）。
    fn rollback_import(
        &self,
        obj_id: &str,
        created_object: bool,
        created_dir: bool,
        storage_obj_dir: &str,
        created_images: &[(String, String)],
        copied_files: &[String],
    ) -> Result<(), String> {
        {
            let db = self.db.lock().unwrap_or_else(|p| p.into_inner());
            if created_object {
                db.delete_object(obj_id)?;
            } else {
                for (img_id, _) in created_images {
                    db.delete_image(img_id)?;
                }
            }
        }
        if created_object && created_dir && Path::new(storage_obj_dir).is_dir() {
            let _ = fs::remove_dir_all(storage_obj_dir);
        }
        // 已复制文件逐个清理（目录整体已删时为无害空操作）
        for dest in copied_files {
            let _ = fs::remove_file(dest);
        }
        Ok(())
    }

    /// 导入单张/多张图片到已有对象。返回 (成功数, 失败数)。
    /// 与目录导入相同：复制阶段不持 db 锁，失败统一回滚本次新增。
    pub fn import_single_files(
        &self,
        obj_id: &str,
        paths: &[String],
        storage_root: &str,
    ) -> Result<(i64, i64), String> {
        let mut created_images: Vec<(String, String)> = Vec::new();
        let mut copied_files: Vec<String> = Vec::new();

        let result: Result<(i64, i64), String> = (|| {
            // ── 短锁：解析目标目录 ──
            let (storage_obj_dir, cur_count) = {
                let db = self.db.lock().unwrap_or_else(|p| p.into_inner());
                let dir = Self::resolve_append_target_dir(&db, obj_id, "unnamed", storage_root)?;
                let count = db.get_image_count(obj_id).unwrap_or(0);
                (dir, count)
            };

            // ── 无锁：复制文件 ──
            let mut sorted: Vec<String> = paths
                .iter()
                .filter(|p| !Path::new(p)
                    .file_name()
                    .and_then(|n| n.to_str())
                    .map(|n| n.starts_with('.'))
                    .unwrap_or(true)).cloned()
                .collect();
            sorted.sort_by_key(|p| {
                Path::new(p)
                    .file_name()
                    .map(|n| n.to_string_lossy().to_string())
                    .unwrap_or_default()
            });

            let mut rows: Vec<(String, String, i64)> = Vec::new(); // (filename, dest, sort_order)
            let mut ok: i64 = 0;
            let mut fail: i64 = 0;

            for src in &sorted {
                if let Some((filename, dest)) = copy_image_keep_name(src, &storage_obj_dir) {
                    copied_files.push(dest.clone());
                    rows.push((filename, dest, cur_count + ok));
                    ok += 1;
                } else {
                    fail += 1;
                }
            }

            // ── 短锁：入库 ──
            let db = self.db.lock().unwrap_or_else(|p| p.into_inner());
            for (filename, dest, sort_order) in &rows {
                let img_id = new_uuid();
                db.add_image(&img_id, obj_id, filename, dest, *sort_order)?;
                created_images.push((img_id, dest.clone()));
            }
            Ok((ok, fail))
        })();

        match result {
            Ok(r) => Ok(r),
            Err(e) => {
                self.rollback_import(obj_id, false, false, "", &created_images, &copied_files)?;
                Err(e)
            }
        }
    }

    // ── 库迁移 ──────────────────────────────────────────────────────────────

    pub fn migrate_library(
        &self,
        new_root: &str,
        progress_cb: crate::library_manager::ProgressCb,
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

// ── 单元测试（对标原 Python 版 test_library_service 语义）────────────────────
#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::{TagValue, Tags};
    use std::collections::HashMap;
    use std::fs;
    use std::path::{Path, PathBuf};

    fn tmp(tag: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("ms_test_{}_{}", tag, uuid::Uuid::new_v4()));
        fs::create_dir_all(&d).unwrap();
        d
    }

    fn mk_img(dir: &Path, name: &str) -> String {
        let img = image::RgbImage::from_pixel(60, 90, image::Rgb([80, 120, 200]));
        let p = dir.join(name);
        img.save(&p).unwrap();
        p.to_string_lossy().to_string()
    }

    fn tags(pairs: Vec<(&str, TagValue)>) -> Tags {
        Tags(pairs.into_iter().map(|(k, v)| (k.to_string(), v)).collect())
    }

    fn list(vals: &[&str]) -> TagValue {
        TagValue::List(vals.iter().map(|s| s.to_string()).collect())
    }

    fn new_svc(tag: &str) -> (LibraryService, PathBuf) {
        let d = tmp(tag);
        let svc = LibraryService::new(d.join("lib.db").to_str().unwrap()).unwrap();
        (svc, d)
    }

    /// 造一个含 2 张图的对象，返回 (svc, 临时根, obj_id)
    fn seeded(tag: &str, name: &str, tg: Tags) -> (LibraryService, PathBuf, String) {
        let (svc, d) = new_svc(tag);
        let src = d.join("src");
        fs::create_dir_all(&src).unwrap();
        mk_img(&src, "a.png");
        mk_img(&src, "b.png");
        let root = d.join("storage");
        fs::create_dir_all(&root).unwrap();
        let oid = uuid::Uuid::new_v4().to_string();
        let (ok, fail) = svc
            .import_directory(&oid, name, &tg, src.to_str().unwrap(), root.to_str().unwrap(), true, None, None)
            .unwrap();
        assert_eq!((ok, fail), (2, 0));
        // 库迁移从配置读取 storage_root
        svc.set_config("storage_root", root.to_str().unwrap()).unwrap();
        (svc, d, oid)
    }

    #[test]
    fn config_roundtrip() {
        let (svc, _d) = new_svc("cfg");
        assert_eq!(svc.get_config("k1").unwrap(), None);
        svc.set_config("k1", "v1").unwrap();
        assert_eq!(svc.get_config("k1").unwrap().as_deref(), Some("v1"));
        svc.set_config("k1", "v2").unwrap();
        assert_eq!(svc.get_config("k1").unwrap().as_deref(), Some("v2"));
    }

    #[test]
    fn import_new_object_copies_files_and_records() {
        let (svc, d, oid) = seeded("imp", "Alpha", tags(vec![("work", list(&["Alpha"]))]));
        let obj = svc.get_object(&oid).unwrap().unwrap();
        assert_eq!(obj.name, "Alpha");
        assert_eq!(obj.image_count, 2);
        let dir = d.join("storage").join("Alpha");
        assert!(dir.join("a.png").is_file(), "保留原文件名");
        assert!(dir.join("b.png").is_file());
        assert!(obj.first_image.as_deref().is_some());
    }

    #[test]
    fn thumb_cover_imported_as_cover_not_content() {
        // 源目录带 .thumb.jpg：导入后封面指向库内 .thumb 文件，且不进正文
        let (svc, d) = new_svc("thumbc");
        let src = d.join("src");
        fs::create_dir_all(&src).unwrap();
        mk_img(&src, "a.png");
        mk_img(&src, "b.png");
        mk_img(&src, ".thumb.jpg");
        let root = d.join("storage");
        fs::create_dir_all(&root).unwrap();
        let oid = uuid::Uuid::new_v4().to_string();
        let (ok, fail) = svc.import_directory(&oid, "带thumb本", &tags(vec![]),
            src.to_str().unwrap(), root.to_str().unwrap(), true, None, None).unwrap();
        assert_eq!((ok, fail), (2, 0), ".thumb 不应计入正文图片");
        let obj = svc.get_object(&oid).unwrap().unwrap();
        assert_eq!(obj.image_count, 2, "正文不应包含 .thumb");
        let cover = obj.cover_image.clone().expect("应设置封面");
        let cover_name = Path::new(&cover).file_name().unwrap().to_string_lossy().to_string();
        assert!(cover_name.to_lowercase().starts_with(".thumb"), "封面应是 .thumb 文件: {cover_name}");
        // .thumb 已复制进存储目录
        let sp = PathBuf::from(obj.storage_path.clone().unwrap());
        assert!(sp.join(".thumb.jpg").is_file(), ".thumb 应复制到存储目录");
        // resolve_cover 优先显式封面
        assert_eq!(svc.resolve_cover(&obj).as_deref(), Some(cover.as_str()));
    }

    #[test]
    fn thumb_cover_rolls_back_with_import() {
        // 导入失败（目标目录被占用）时 .thumb 复制品随回滚清理
        let (svc, d) = new_svc("thumbrb");
        let src = d.join("src");
        fs::create_dir_all(&src).unwrap();
        mk_img(&src, "a.png");
        mk_img(&src, ".thumb.jpg");
        let root = d.join("storage");
        fs::create_dir_all(root.join("占用名")).unwrap();
        fs::write(root.join("占用名").join("keep.txt"), "x").unwrap();
        let oid = uuid::Uuid::new_v4().to_string();
        let res = svc.import_directory(&oid, "占用名", &tags(vec![]),
            src.to_str().unwrap(), root.to_str().unwrap(), true, None, None);
        assert!(res.is_err(), "应因目录占用失败");
        // .thumb 不应残留在被回滚的目录中（目录本身可能保留——占用检查在复制前拒绝，
        // 但防御性验证：存储目录内无新增 .thumb）
        let leftovers: Vec<_> = fs::read_dir(root.join("占用名")).unwrap()
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().to_string())
            .collect();
        assert!(!leftovers.iter().any(|n| n.to_lowercase().starts_with(".thumb")),
            "回滚后不应残留 .thumb: {leftovers:?}");
    }

    #[test]
    fn fake_thumb_ignored_and_falls_back_to_first_image() {
        // 伪 .thumb（非图片）：忽略，封面回退首图
        let (svc, d) = new_svc("fakethumb");
        let src = d.join("src");
        fs::create_dir_all(&src).unwrap();
        mk_img(&src, "a.png");
        fs::write(src.join(".thumb"), "definitely not an image").unwrap();
        let root = d.join("storage");
        fs::create_dir_all(&root).unwrap();
        let oid = uuid::Uuid::new_v4().to_string();
        let (ok, _) = svc.import_directory(&oid, "伪thumb本", &tags(vec![]),
            src.to_str().unwrap(), root.to_str().unwrap(), true, None, None).unwrap();
        assert_eq!(ok, 1);
        let obj = svc.get_object(&oid).unwrap().unwrap();
        let cover = obj.cover_image.expect("应回退首图为封面");
        assert!(cover.ends_with("a.png"), "伪 .thumb 应回退首图: {cover}");
        let sp = PathBuf::from(obj.storage_path.clone().unwrap());
        assert!(!sp.join(".thumb").exists(), "伪 .thumb 不应被复制");
    }

    #[test]
    fn r18_hidden_by_default() {
        let (svc, d, _) = seeded("r18a", "普通本", tags(vec![]));
        let _ = d;
        // 同一库里再造一个 r18 对象
        let src = tmp("r18src");
        mk_img(&src, "x.png");
        let oid2 = uuid::Uuid::new_v4().to_string();
        svc.import_directory(&oid2, "R18本", &tags(vec![("r18", TagValue::Bool(true))]),
            src.to_str().unwrap(), svc_r18_root(&svc, "普通本").to_str().unwrap(),
            true, None, None).unwrap();
        assert_eq!(svc.get_all_objects(false).unwrap().len(), 1, "默认应只见普通对象");
        assert_eq!(svc.get_all_objects(true).unwrap().len(), 2, "显式包含应见全部");
    }

    // 取已导入对象的存储根（storage_path 的父目录）
    fn svc_r18_root(svc: &LibraryService, name: &str) -> PathBuf {
        let obj = svc.get_all_objects(true).unwrap()
            .into_iter().find(|o| o.name == name).unwrap();
        PathBuf::from(obj.storage_path.clone().unwrap())
            .parent().unwrap().to_path_buf()
    }

    #[test]
    fn search_by_keyword_matches_name() {
        let (svc, d, _) = seeded("search", "深夜食堂画集", tags(vec![("work", list(&["深夜食堂"]))]));
        let _ = d;
        assert_eq!(svc.search_objects("深夜", true).unwrap().len(), 1);
        assert_eq!(svc.search_objects("不存在的关键字", true).unwrap().len(), 0);
    }

    #[test]
    fn filter_by_tag_category() {
        let (svc, _d, _) = seeded("filt", "星海航路", tags(vec![("author", list(&["水濑叶月"]))]));
        let mut f = HashMap::new();
        f.insert("author".to_string(), vec!["水濑叶月".to_string()]);
        assert_eq!(svc.filter_by_tags(&f, true).unwrap().len(), 1);
        let mut f2 = HashMap::new();
        f2.insert("author".to_string(), vec!["别人".to_string()]);
        assert_eq!(svc.filter_by_tags(&f2, true).unwrap().len(), 0);
    }

    #[test]
    fn tag_values_aggregate() {
        let (svc, _d, _) = seeded("tv", "作品一", tags(vec![("work", list(&["星海航路"]))]));
        let vals = svc.get_tag_values("work").unwrap();
        assert!(vals.contains(&"星海航路".to_string()));
    }

    #[test]
    fn update_name_tags_lastread() {
        let (svc, _d, oid) = seeded("upd", "旧名", tags(vec![("work", list(&["旧作"]))]));
        svc.update_object_name(&oid, "新名").unwrap();
        svc.set_object_tags(&oid, &tags(vec![("author", list(&["新作者"]))])).unwrap();
        svc.update_last_read(&oid, 1).unwrap();
        let obj = svc.get_object(&oid).unwrap().unwrap();
        assert_eq!(obj.name, "新名");
        assert!(obj.tags.0.contains_key("author"));
        assert!(!obj.tags.0.contains_key("work"), "set_tags 应整体替换");
        assert_eq!(obj.last_read_idx, 1);
    }

    #[test]
    fn resolve_cover_prefers_explicit_and_falls_back() {
        let (svc, _d, oid) = seeded("cov", "封面对象", tags(vec![]));
        // 未设置封面：回退到首图
        let obj = svc.get_object(&oid).unwrap().unwrap();
        let fallback = svc.resolve_cover(&obj).unwrap();
        assert!(fallback.ends_with("a.png"), "应回退首图: {fallback}");
        // 显式指定第二张为封面
        let explicit = PathBuf::from(obj.storage_path.clone().unwrap()).join("b.png");
        svc.update_object_cover(&oid, explicit.to_str().unwrap()).unwrap();
        let obj2 = svc.get_object(&oid).unwrap().unwrap();
        assert_eq!(svc.resolve_cover(&obj2).as_deref(), Some(explicit.to_string_lossy().to_string()).as_deref());
    }

    #[test]
    fn import_append_extends_existing_object() {
        let (svc, d, oid) = seeded("app", "合集", tags(vec![]));
        let more = d.join("more");
        fs::create_dir_all(&more).unwrap();
        mk_img(&more, "c.png");
        mk_img(&more, "d.png");
        let root = d.join("storage");
        let (ok, fail) = svc.import_directory(&oid, "合集", &tags(vec![]),
            more.to_str().unwrap(), root.to_str().unwrap(), false, None, None).unwrap();
        assert_eq!((ok, fail), (2, 0));
        assert_eq!(svc.get_object(&oid).unwrap().unwrap().image_count, 4);
        // 同名源再次导入：保留原名机制下生成 a(1)/b(1)
        let again = svc.import_directory(&oid, "合集", &tags(vec![]),
            d.join("src").to_str().unwrap(), root.to_str().unwrap(), false, None, None).unwrap();
        assert_eq!(again, (2, 0));
        let sp = PathBuf::from(svc.get_object(&oid).unwrap().unwrap().storage_path.clone().unwrap());
        assert!(sp.join("a(1).png").is_file(), "重名应加 (1) 标记");
        assert_eq!(svc.get_object(&oid).unwrap().unwrap().image_count, 6);
    }

    #[test]
    fn import_rejects_nonempty_unowned_dir() {
        let (svc, d) = new_svc("rej");
        let root = d.join("storage");
        // 目标位置预置一个非空目录（不属于任何对象）
        fs::create_dir_all(root.join("占用名")).unwrap();
        fs::write(root.join("占用名").join("keep.txt"), "x").unwrap();
        let src = d.join("src");
        fs::create_dir_all(&src).unwrap();
        mk_img(&src, "a.png");
        let oid = uuid::Uuid::new_v4().to_string();
        let res = svc.import_directory(&oid, "占用名", &tags(vec![]),
            src.to_str().unwrap(), root.to_str().unwrap(), true, None, None);
        assert!(res.is_err(), "非空且不属于任何对象的目录应拒绝导入");
        // 预置文件不受影响
        assert!(root.join("占用名").join("keep.txt").is_file());
    }

    #[test]
    fn delete_object_keep_files_vs_with_files() {
        // 仅删记录：文件保留
        let (svc, _d, oid) = seeded("del1", "保留文件", tags(vec![]));
        let dir1 = PathBuf::from(svc.get_object(&oid).unwrap().unwrap().storage_path.clone().unwrap());
        svc.delete_object(&oid, false, None).unwrap();
        assert!(svc.get_object(&oid).unwrap().is_none());
        assert!(dir1.join("a.png").is_file());
        // 连文件删除：存储目录移除
        let (svc2, _d2, oid2) = seeded("del2", "连文件删", tags(vec![]));
        let sp = PathBuf::from(svc2.get_object(&oid2).unwrap().unwrap().storage_path.clone().unwrap());
        let root2 = sp.parent().unwrap();
        let warnings = svc2.delete_object(&oid2, true, Some(root2.to_str().unwrap())).unwrap();
        assert!(warnings.is_empty(), "正常删除不应有警告: {warnings:?}");
        assert!(svc2.get_object(&oid2).unwrap().is_none());
        assert!(!sp.exists(), "存储目录应被删除");
    }

    #[test]
    fn delete_object_warns_on_shared_storage_dir() {
        // 两对象人为共享存储目录：删除其一应产生警告、不物理删目录、DB 记录删干净
        let (svc, d) = new_svc("delshared");
        let root = d.join("storage");
        fs::create_dir_all(&root).unwrap();
        let src = d.join("src");
        fs::create_dir_all(&src).unwrap();
        mk_img(&src, "a.png");
        let oid1 = uuid::Uuid::new_v4().to_string();
        let oid2 = uuid::Uuid::new_v4().to_string();
        svc.import_directory(&oid1, "甲", &tags(vec![]), src.to_str().unwrap(), root.to_str().unwrap(), true, None, None).unwrap();
        svc.import_directory(&oid2, "乙", &tags(vec![]), src.to_str().unwrap(), root.to_str().unwrap(), true, None, None).unwrap();
        let sp1 = svc.get_object(&oid1).unwrap().unwrap().storage_path.clone().unwrap();
        svc.db.lock().unwrap().update_object_storage_path(&oid2, &sp1).unwrap();
        let warnings = svc.delete_object(&oid1, true, Some(root.to_str().unwrap())).unwrap();
        assert_eq!(warnings.len(), 1, "共享目录应产生警告: {warnings:?}");
        assert!(Path::new(&sp1).is_dir(), "共享目录不应被物理删除");
        assert!(svc.get_object(&oid1).unwrap().is_none(), "DB 记录应已删除");
        assert!(svc.get_object(&oid2).unwrap().is_some(), "另一对象不受影响");
    }

    #[test]
    fn import_single_files_appends() {
        let (svc, d, oid) = seeded("single", "散图目标", tags(vec![]));
        let loose = d.join("loose");
        fs::create_dir_all(&loose).unwrap();
        mk_img(&loose, "p1.png");
        mk_img(&loose, "p2.png");
        let root = d.join("storage").to_string_lossy().to_string();
        let (ok, fail) = svc.import_single_files(&oid, &[
            loose.join("p1.png").to_string_lossy().to_string(),
            loose.join("p2.png").to_string_lossy().to_string(),
            loose.join("nope.png").to_string_lossy().to_string(),
        ], &root).unwrap();
        assert_eq!((ok, fail), (2, 1), "缺失文件计入失败");
        assert_eq!(svc.get_object(&oid).unwrap().unwrap().image_count, 4);
    }

    #[test]
    fn import_cancel_rolls_back_partial_work() {
        use std::cell::Cell;
        let (svc, d) = new_svc("cancel");
        let src = d.join("src");
        fs::create_dir_all(&src).unwrap();
        mk_img(&src, "a.png");
        mk_img(&src, "b.png");
        mk_img(&src, "c.png");
        let root = d.join("storage");
        fs::create_dir_all(&root).unwrap();
        let oid = uuid::Uuid::new_v4().to_string();
        let calls = Cell::new(0i32);
        // 第一次取消检查放行（复制完第一张后），第二次取消 → 应整体回滚
        let res = svc.import_directory(
            &oid, "取消对象", &tags(vec![]),
            src.to_str().unwrap(), root.to_str().unwrap(), true,
            Some(&|_, _| {}),
            Some(&|| { calls.set(calls.get() + 1); calls.get() > 1 }),
        );
        assert!(res.is_err(), "应以取消失败: {res:?}");
        assert!(svc.get_object(&oid).unwrap().is_none(), "半成品对象应被回滚");
        assert!(!root.join("取消对象").exists(), "新建存储目录应被回滚删除");
    }

    #[test]
    fn migrate_library_moves_dir_and_updates_paths() {
        let (svc, d, oid) = seeded("mig", "迁移对象", tags(vec![]));
        let old_dir = PathBuf::from(svc.get_object(&oid).unwrap().unwrap().storage_path.clone().unwrap());
        let new_root = d.join("new_root");
        fs::create_dir_all(&new_root).unwrap();
        let (moved, warnings) = svc.migrate_library(new_root.to_str().unwrap(), None).unwrap();
        assert_eq!(moved, 1);
        assert!(warnings.is_empty(), "不应有库外警告: {warnings:?}");
        assert!(!old_dir.exists(), "旧目录应被移走");
        let obj = svc.get_object(&oid).unwrap().unwrap();
        let new_dir = PathBuf::from(obj.storage_path.clone().unwrap());
        // 迁移写入的是 canonicalize 路径（Windows 带 \?\ 前缀），对比前同样规范化
        let new_root_c = fs::canonicalize(&new_root).unwrap();
        assert!(new_dir.starts_with(&new_root_c), "路径应指向新根: {new_dir:?}");
        assert!(new_dir.join("a.png").is_file());
        let imgs = svc.get_images(&oid).unwrap();
        assert!(PathBuf::from(&imgs[0].filepath).is_file(), "图片路径应指向新位置");
    }

    #[test]
    fn migrate_same_name_dir_auto_renames() {
        let (svc, d, oid) = seeded("mig2", "同名目录", tags(vec![]));
        let new_root = d.join("new_root2");
        // 新根下预置同名非空目录 → 迁移应自动重命名而非失败
        fs::create_dir_all(new_root.join("同名目录")).unwrap();
        fs::write(new_root.join("同名目录").join("keep.txt"), "x").unwrap();
        let res = svc.migrate_library(new_root.to_str().unwrap(), None);
        assert!(res.is_ok(), "同名目录应自动重命名: {res:?}");
        let obj = svc.get_object(&oid).unwrap().unwrap();
        let new_dir = PathBuf::from(obj.storage_path.clone().unwrap());
        let new_root_c = fs::canonicalize(&new_root).unwrap();
        assert!(new_dir.starts_with(&new_root_c));
        assert!(new_dir.join("a.png").is_file());
        assert!(new_root.join("同名目录").join("keep.txt").is_file(), "预置文件不应被破坏");
    }
}
