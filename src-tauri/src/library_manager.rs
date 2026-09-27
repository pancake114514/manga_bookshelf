//! 库配置与迁移 — 与 Python 版 library_manager.py 对等
//!
//! 三阶段：prepare（计划） → execute（执行） → rollback（回滚）
//! 含 DB 备份、目录移动回滚、缩略图缓存清理

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

use crate::config::THUMB_CACHE_DIR;
use crate::db::Database;
use crate::service::LibraryService;

#[derive(Debug)]
pub struct ObjectMigrationPlan {
    pub obj_id: String,
    pub name: String,
    pub old_dir: String,
    pub new_dir: String,
    pub cover_old: Option<String>,
    pub cover_new: Option<String>,
    pub image_updates: Vec<ImagePathUpdate>,
}

#[derive(Debug)]
pub struct ImagePathUpdate {
    pub img_id: String,
    pub old_path: String,
    pub new_path: String,
}

pub fn check_writable(path: &str) -> Result<(), String> {
    if !Path::new(path).is_dir() {
        return Err(format!("目录不存在：\n{path}"));
    }
    let test_file = Path::new(path).join(".manga_shelf_write_test");
    fs::write(&test_file, "test").map_err(|_| format!("没有写入权限，请选择其他目录：\n{path}"))?;
    let _ = fs::remove_file(&test_file);
    Ok(())
}

pub fn get_storage_root(db: &Database) -> Option<String> {
    db.get_config("storage_root").ok().flatten()
}

fn normalize_path(path: &str) -> String {
    let p = PathBuf::from(path);
    let canonical = fs::canonicalize(&p).unwrap_or(p);
    let mut s = canonical.to_string_lossy().to_string();
    if cfg!(target_os = "windows") {
        s = s.to_lowercase();
    }
    s
}

fn is_relative_to(path: &str, parent: &str) -> bool {
    let path = normalize_path(path);
    let parent = normalize_path(parent);
    path.starts_with(&parent)
}

fn map_path(path: &str, old_dir: &str, new_dir: &str) -> String {
    let normalized = normalize_path(path);
    let old_normalized = normalize_path(old_dir);
    if !normalized.starts_with(&old_normalized) {
        return path.to_string();
    }
    let relative = Path::new(&normalized)
        .strip_prefix(&old_normalized)
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|_| path.to_string());
    Path::new(new_dir).join(&relative).to_string_lossy().to_string()
}

pub fn prepare_library_migration(
    db: &Database,
    new_root: &str,
) -> Result<(String, String, Vec<ObjectMigrationPlan>), String> {
    let old_root = get_storage_root(db)
        .ok_or("当前还没有已配置的图库目录。")?;
    let old_root = fs::canonicalize(&old_root)
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or(old_root);
    let new_root = fs::canonicalize(new_root)
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|_| new_root.to_string());

    if normalize_path(&old_root) == normalize_path(&new_root) {
        return Err("新旧图库目录相同，无需迁移。".to_string());
    }
    if is_relative_to(&new_root, &old_root) || is_relative_to(&old_root, &new_root) {
        return Err("新旧图库目录不能互相包含。".to_string());
    }

    check_writable(&new_root)?;

    let objects = db.get_all_objects(true)?;
    let mut plans: Vec<ObjectMigrationPlan> = Vec::new();
    let mut seen_targets: HashSet<String> = HashSet::new();

    for obj in objects {
        let old_dir = obj.storage_path.as_deref().unwrap_or("").trim().to_string();
        if old_dir.is_empty() {
            return Err(format!("对象\"{}\"缺少存储路径，无法迁移。", obj.name));
        }
        if !Path::new(&old_dir).is_dir() {
            return Err(format!("对象\"{}\"的目录不存在：\n{old_dir}", obj.name));
        }

        // 目标目录冲突时自动加后缀重命名
        let base_name = Path::new(&old_dir)
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();
        let mut candidate = base_name.clone();
        let mut counter = 0;
        let new_dir = loop {
            let nd = Path::new(&new_root).join(&candidate);
            let nd_key = normalize_path(&nd.to_string_lossy());
            if !seen_targets.contains(&nd_key) && !nd.exists() {
                break nd.to_string_lossy().to_string();
            }
            counter += 1;
            candidate = format!("{base_name} ({counter})");
        };
        seen_targets.insert(normalize_path(&new_dir));

        let images = db.get_images(&obj.id)?;
        let image_updates: Vec<ImagePathUpdate> = images
            .iter()
            .map(|img| ImagePathUpdate {
                img_id: img.id.clone(),
                old_path: img.filepath.clone(),
                new_path: map_path(&img.filepath, &old_dir, &new_dir),
            })
            .collect();

        let cover_old = obj.cover_image.clone();
        let cover_new = cover_old.as_ref().map(|c| map_path(c, &old_dir, &new_dir));

        plans.push(ObjectMigrationPlan {
            obj_id: obj.id,
            name: obj.name,
            old_dir,
            new_dir,
            cover_old,
            cover_new,
            image_updates,
        });
    }

    Ok((old_root, new_root, plans))
}

pub type ProgressCb<'a> = Option<&'a dyn Fn(usize, usize, &str)>;

/// 将已移动的目录按逆序移回原位，返回回滚失败的描述列表
fn rollback_moved_dirs(moved_dirs: &[(String, String)]) -> Vec<String> {
    let mut errors: Vec<String> = Vec::new();
    for (old_dir, new_dir) in moved_dirs.iter().rev() {
        if Path::new(new_dir).exists() && !Path::new(old_dir).exists() {
            if let Err(e) = fs::rename(new_dir, old_dir) {
                errors.push(format!("{new_dir} → {old_dir}: {e}"));
            }
        }
    }
    errors
}

pub fn migrate_library(
    service: &LibraryService,
    new_root: &str,
    progress_cb: ProgressCb,
) -> Result<(usize, Vec<String>), String> {
    let db = service.db.lock().unwrap_or_else(|p| p.into_inner());
    let (old_root, new_root, plans) = prepare_library_migration(&db, new_root)?;

    let total_steps = (plans.len() * 2 + 1).max(1);
    let mut current_step = 0usize;
    let mut moved_dirs: Vec<(String, String)> = Vec::new();
    let backup_path = format!("{}.bak", db.conn.path().unwrap_or("library.db"));

    // 收集库外路径警告
    let mut warnings: Vec<String> = Vec::new();
    for plan in &plans {
        for update in &plan.image_updates {
            if update.old_path == update.new_path {
                warnings.push(format!("未迁移的图片（库外路径）：{}", update.old_path));
            }
        }
        if let (Some(old), Some(new)) = (&plan.cover_old, &plan.cover_new) {
            if old == new {
                warnings.push(format!("未迁移的封面（库外路径）：{old}"));
            }
        }
    }
    warnings.dedup();

    let mut emit = |message: &str| {
        current_step += 1;
        if let Some(cb) = progress_cb {
            cb(current_step, total_steps, message);
        }
    };

    // 迁移前备份数据库。三重保障：
    // 1) 先 checkpoint 把 WAL 合入主库——否则最近写入仍在 -wal 文件里，复制主文件
    //    得到的是缺数据的残缺备份；
    // 2) 备份失败直接中止迁移（不移动任何目录）——否则后续失败时没有恢复手段；
    // 3) 先写 .bak.tmp 再改名——避免复制中途失败时把上一次完好的备份覆盖掉
    let tmp_backup = format!("{backup_path}.tmp");
    let backup_result = (|| -> Result<(), String> {
        db.checkpoint()?;
        fs::copy(db.conn.path().unwrap_or("library.db"), &tmp_backup)
            .map_err(|e| format!("复制数据库失败: {e}"))?;
        fs::rename(&tmp_backup, &backup_path)
            .map_err(|e| format!("备份改名失败: {e}"))?;
        Ok(())
    })();
    if let Err(e) = backup_result {
        let _ = fs::remove_file(&tmp_backup);
        return Err(format!("迁移已中止——创建备份失败：{e}"));
    }

    fs::create_dir_all(&new_root).map_err(|e| format!("创建新根目录失败: {e}"))?;

    // 执行迁移（目录移动）。任一步失败必须回滚已移动的目录，
    // 否则库会进入"文件在新根、DB 仍指旧根"的损坏状态
    let rename_result: Result<(), String> = (|| {
        for plan in &plans {
            emit(&format!("正在迁移：{}", plan.name));
            if let Err(e) = fs::rename(&plan.old_dir, &plan.new_dir) {
                return Err(format!(
                    "迁移目录失败 ({} → {}): {e}",
                    plan.old_dir, plan.new_dir
                ));
            }
            moved_dirs.push((plan.old_dir.clone(), plan.new_dir.clone()));
        }
        Ok(())
    })();

    if let Err(e) = rename_result {
        let rollback_errors = rollback_moved_dirs(&moved_dirs);
        if !rollback_errors.is_empty() {
            return Err(format!(
                "迁移失败：{e}\n\n以下目录回滚失败，请手动恢复：\n{}",
                rollback_errors.join("\n")
            ));
        }
        return Err(e);
    }

    // 更新数据库（事务内）
    db.conn
        .execute_batch("BEGIN")
        .map_err(|e| format!("开始事务失败: {e}"))?;
    let db_result: Result<(), String> = (|| {
        for plan in &plans {
            emit(&format!("正在更新数据库：{}", plan.name));
            db.update_object_storage_path(&plan.obj_id, &plan.new_dir)?;
            for update in &plan.image_updates {
                db.update_image_filepath(&update.img_id, &update.new_path)?;
            }
            if plan.cover_old != plan.cover_new {
                if let Some(new_cover) = &plan.cover_new {
                    db.update_object_cover(&plan.obj_id, new_cover)?;
                }
            }
        }
        db.set_config("storage_root", &new_root)?;
        Ok(())
    })();

    match db_result {
        Ok(_) => {
            db.conn.execute_batch("COMMIT").map_err(|e| format!("提交事务失败: {e}"))?;
        }
        Err(e) => {
            let _ = db.conn.execute_batch("ROLLBACK");
            // 回滚已移动的目录
            let rollback_errors = rollback_moved_dirs(&moved_dirs);
            if !rollback_errors.is_empty() {
                return Err(format!(
                    "迁移失败：{e}\n\n以下目录回滚失败，请手动恢复：\n{}",
                    rollback_errors.join("\n")
                ));
            }
            return Err(e);
        }
    }

    emit("迁移完成");

    // 清理旧根的缩略图缓存
    let old_cache = Path::new(&old_root).join(THUMB_CACHE_DIR);
    if old_cache.is_dir() {
        let _ = fs::remove_dir_all(&old_cache);
    }

    // 清理备份（迁移成功才删；失败路径保留 .bak 作为手工恢复手段）
    let _ = fs::remove_file(&backup_path);

    Ok((plans.len(), warnings))
}

// ── 单元测试（对标原 Python 版 test_library_manager 语义）───────────────────
#[cfg(test)]
mod tests {
    use super::*;


    // ── 迁移备份保障测试 ──────────────────────────────────────────────────

    /// 造一个含 2 张图并写入配置的对象库，返回 (svc, 库根目录)
    fn seeded_for_backup(tag: &str) -> (crate::service::LibraryService, std::path::PathBuf, String) {
        use crate::db::Tags;
        let d = std::env::temp_dir().join(format!("ms_test_bk_{tag}_{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(d.join("src")).unwrap();
        let img = image::RgbImage::from_pixel(40, 60, image::Rgb([90, 90, 200]));
        img.save(d.join("src/a.png")).unwrap();
        img.save(d.join("src/b.png")).unwrap();
        std::fs::create_dir_all(d.join("storage")).unwrap();
        let svc = crate::service::LibraryService::new(d.join("lib.db").to_str().unwrap()).unwrap();
        let oid = uuid::Uuid::new_v4().to_string();
        svc.import_directory(&oid, "备份对象", &Tags(Default::default()),
            d.join("src").to_str().unwrap(), d.join("storage").to_str().unwrap(),
            true, None, None).unwrap();
        // 迁移前最新写入（大概率仍在 WAL 中未 checkpoint）
        svc.set_config("storage_root", d.join("storage").to_str().unwrap()).unwrap();
        svc.set_config("wal_marker", "最新写入").unwrap();
        (svc, d, oid)
    }

    /// 备份配方（checkpoint + 复制主文件）必须捕获 WAL 中未落盘的最新数据——
    /// 这是迁移备份修复①的核心语义：直接复现 migrate_library 的备份三步并检验副本
    #[test]
    fn backup_recipe_includes_wal_data() {
        let (svc, d, oid) = seeded_for_backup("wal");

        // 复现迁移备份流程：checkpoint → 复制主文件（不复制 -wal）
        let bak = d.join("lib.db.bak");
        {
            let db = svc.db.lock().unwrap_or_else(|p| p.into_inner());
            db.checkpoint().expect("checkpoint 应成功");
        }
        std::fs::copy(d.join("lib.db"), &bak).unwrap();

        // WAL 已被截断（数据在主文件里）
        if let Ok(meta) = std::fs::metadata(d.join("lib.db-wal")) {
            assert_eq!(meta.len(), 0, "checkpoint(TRUNCATE) 后 WAL 应为空");
        }
        // 备份副本包含最近写入的配置与对象数据
        let bak_svc = crate::service::LibraryService::new(bak.to_str().unwrap()).unwrap();
        assert_eq!(bak_svc.get_config("wal_marker").unwrap().as_deref(), Some("最新写入"),
            "备份缺少 WAL 中未 checkpoint 的写入");
        assert!(bak_svc.get_object(&oid).unwrap().is_some(), "备份缺少对象数据");
        // 原库未受影响
        assert!(d.join("storage").join("备份对象").join("a.png").is_file());
    }

    /// 备份创建失败（.bak.tmp 被目录占用导致复制失败）必须中止迁移，
    /// 不移动任何目录、不改动数据库记录
    #[test]
    fn backup_failure_aborts_migration_without_moving_anything() {
        let (svc, d, oid) = seeded_for_backup("abort");
        let new_root = d.join("new_root");
        std::fs::create_dir_all(&new_root).unwrap(); // 新根合法（通过 prepare 校验）
        // 占位：让备份临时文件路径无法写入（复制阶段失败）
        std::fs::create_dir_all(d.join("lib.db.bak.tmp")).unwrap();

        let res = migrate_library(&svc, new_root.to_str().unwrap(), None);
        assert!(res.is_err(), "备份失败必须中止迁移");
        let msg = res.unwrap_err();
        assert!(msg.contains("中止") || msg.contains("备份"), "错误应说明备份中止: {msg}");

        // 未移动任何目录、未建新根、DB 记录仍指旧位置
        // 新根内不应有任何被移入的对象目录（本测试预建了空新根）
        assert_eq!(new_root.read_dir().unwrap().count(), 0, "不应移动任何目录到新根");
        let old_dir = d.join("storage").join("备份对象");
        assert!(old_dir.join("a.png").is_file(), "原目录必须原样保留");
        let obj = svc.get_object(&oid).unwrap().unwrap();
        assert!(obj.storage_path.clone().unwrap().contains("备份对象"), "DB 仍指向旧路径");
    }

    #[test]
    fn check_writable_accepts_writable_dir() {
        let d = std::env::temp_dir().join(format!("ms_test_lm_{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&d).unwrap();
        assert!(check_writable(d.to_str().unwrap()).is_ok());
        // 校验后不应留下测试文件
        assert!(!d.join(".manga_shelf_write_test").exists());
    }

    #[test]
    fn check_writable_rejects_missing_dir() {
        let missing = std::env::temp_dir()
            .join(format!("ms_test_lm_none_{}", uuid::Uuid::new_v4()));
        assert!(check_writable(missing.to_str().unwrap()).is_err());
    }

    #[test]
    fn rollback_moved_dirs_restores_positions() {
        let d = std::env::temp_dir().join(format!("ms_test_rb_{}", uuid::Uuid::new_v4()));
        let old_root = d.join("old");
        let new_root = d.join("new");
        fs::create_dir_all(old_root.join("obj1")).unwrap();
        fs::create_dir_all(old_root.join("obj2")).unwrap();
        fs::create_dir_all(&new_root).unwrap();
        fs::rename(old_root.join("obj1"), new_root.join("obj1")).unwrap();
        fs::rename(old_root.join("obj2"), new_root.join("obj2")).unwrap();
        let moved = vec![
            (
                old_root.join("obj1").to_string_lossy().to_string(),
                new_root.join("obj1").to_string_lossy().to_string(),
            ),
            (
                old_root.join("obj2").to_string_lossy().to_string(),
                new_root.join("obj2").to_string_lossy().to_string(),
            ),
        ];
        assert!(rollback_moved_dirs(&moved).is_empty());
        assert!(old_root.join("obj1").is_dir(), "obj1 应回到原位");
        assert!(old_root.join("obj2").is_dir(), "obj2 应回到原位");
        assert!(!new_root.join("obj1").exists());
        assert!(!new_root.join("obj2").exists());
        let _ = fs::remove_dir_all(&d);
    }
}
