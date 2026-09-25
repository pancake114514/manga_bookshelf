//! 配置常量 — 与 Python 版 config.py 对等

pub const SUPPORTED_FORMATS: &[&str] = &[
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff", ".tif",
];

pub const THUMBNAIL_SIZE: (u32, u32) = (220, 300);
pub const GRID_THUMB_SIZE: (u32, u32) = (160, 160);
pub const COVER_THUMB_SIZE: (u32, u32) = (180, 240);

pub const THUMB_CACHE_DIR: &str = ".thumbcache";

/// 缩略图缓存总量上限（正确性清理后仍超此值则按最旧优先删除，删除后可按需重新生成）
pub const THUMB_CACHE_MAX_BYTES: u64 = 2 * 1024 * 1024 * 1024; // 2 GB

pub fn tag_category_order() -> Vec<&'static str> {
    vec!["work", "author", "character", "cm", "censored", "r18"]
}

pub fn is_supported_image(filename: &str) -> bool {
    let lower = filename.to_lowercase();
    SUPPORTED_FORMATS.iter().any(|ext| lower.ends_with(ext))
}

/// 返回数据库路径
/// Windows: %APPDATA%\MangaShelf\library.db
/// Linux/Mac: ~/.local/share/MangaShelf/library.db
/// 可用环境变量 MANGASHELF_DB 覆盖
pub fn db_path() -> String {
    if let Ok(custom) = std::env::var("MANGASHELF_DB") {
        return custom;
    }
    let base = if cfg!(target_os = "windows") {
        std::env::var("APPDATA")
            .unwrap_or_else(|_| std::env::var("USERPROFILE").unwrap_or_else(|_| ".".to_string()))
    } else {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        format!("{home}/.local/share")
    };
    let dir = format!("{base}/MangaShelf");
    let _ = std::fs::create_dir_all(&dir);
    format!("{dir}/library.db")
}
