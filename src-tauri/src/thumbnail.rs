//! 缩略图生成 — 与 Python 版 utils/thumbnail.py 对等
//!
//! 策略：等比缩放后居中裁剪到目标尺寸，JPEG 缓存，文件名混入 mtime+size 自动失效。

use std::fs;
use std::io::Cursor;
use std::path::{Path, PathBuf};

use image::{DynamicImage, ImageDecoder, ImageFormat};
use sha2::{Digest, Sha256};

use crate::config::{COVER_THUMB_SIZE, GRID_THUMB_SIZE, THUMBNAIL_SIZE, is_supported_image};

pub const THUMB_CACHE_DIR_NAME: &str = ".thumbcache";

pub fn get_thumb_cache_dir(base_dir: &str) -> String {
    let cache = Path::new(base_dir).join(THUMB_CACHE_DIR_NAME);
    let _ = fs::create_dir_all(&cache);
    cache.to_string_lossy().to_string()
}

/// 缓存前缀（基于源路径+尺寸的 hash，不含 mtime），用于按路径精确清理所有版本
fn thumb_prefix(cache_dir: &str, source_path: &str, size: (u32, u32)) -> PathBuf {
    let mut hasher = Sha256::new();
    hasher.update(format!("{source_path}{size:?}").as_bytes());
    let h = hex::encode(&hasher.finalize()[..16]);
    Path::new(cache_dir).join(h)
}

/// 缓存文件名混入源文件的 mtime 与 size，源图被替换后旧缩略图自动失效
fn thumb_path(cache_dir: &str, source_path: &str, size: (u32, u32)) -> PathBuf {
    let base = thumb_prefix(cache_dir, source_path, size);
    match fs::metadata(source_path) {
        Ok(meta) => {
            let mtime = meta
                .modified()
                .ok()
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_nanos())
                .unwrap_or(0);
            let sz = meta.len();
            base.with_file_name(format!("{}__{mtime}_{sz}.jpg", base.file_name().unwrap().to_string_lossy()))
        }
        Err(_) => base.with_extension("jpg"),
    }
}

/// 生成缩略图，返回缓存路径；失败返回 None。
/// 策略：等比缩放后居中裁剪到目标尺寸，不填充任何背景色。
pub fn generate_thumbnail(
    source_path: &str,
    cache_dir: &str,
    size: (u32, u32),
) -> Option<String> {
    let path = Path::new(source_path);
    if !path.is_file() {
        return None;
    }
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| format!(".{}", e.to_lowercase()))
        .unwrap_or_default();
    if !is_supported_image(&format!("x{ext}")) {
        return None;
    }

    let thumb_path = thumb_path(cache_dir, source_path, size);
    if thumb_path.exists() {
        return Some(thumb_path.to_string_lossy().to_string());
    }

    // 读取图片：image::open 不会应用 EXIF 方向，需显式读取并应用，
    // 否则带旋转标记的照片（常见于手机拍摄）缩略图方向错误
    let reader = image::ImageReader::open(source_path).ok()?;
    let mut decoder = reader.into_decoder().ok()?;
    let orientation = decoder
        .orientation()
        .unwrap_or(image::metadata::Orientation::NoTransforms);
    let mut img = DynamicImage::from_decoder(decoder).ok()?;
    img.apply_orientation(orientation);
    let img = DynamicImage::ImageRgb8(img.into_rgb8());

    let (target_w, target_h) = size;
    let (src_w, src_h) = (img.width(), img.height());

    // 等比缩放后能覆盖目标尺寸的最小缩放比
    let scale = (target_w as f64 / src_w as f64).max(target_h as f64 / src_h as f64);
    let new_w = (src_w as f64 * scale).round() as u32;
    let new_h = (src_h as f64 * scale).round() as u32;

    let resized = img.resize_exact(new_w, new_h, image::imageops::FilterType::Lanczos3);

    // 居中裁剪
    let left = (new_w.saturating_sub(target_w)) / 2;
    let top = (new_h.saturating_sub(target_h)) / 2;
    let cropped = resized.crop_imm(left, top, target_w, target_h);

    // 先写临时文件再原子替换
    let tmp_path = format!("{}.tmp", thumb_path.to_string_lossy());
    let mut buf = Cursor::new(Vec::new());
    cropped
        .write_to(&mut buf, ImageFormat::Jpeg)
        .ok()?;
    fs::write(&tmp_path, buf.into_inner()).ok()?;
    fs::rename(&tmp_path, &thumb_path).ok()?;

    Some(thumb_path.to_string_lossy().to_string())
}

/// 清理指定源文件的所有缩略图缓存（含全部尺寸常量、含该源文件的所有 mtime 版本）
pub fn clear_cached_thumbs(cache_dir: &str, source_paths: &[String]) -> usize {
    if source_paths.is_empty() {
        return 0;
    }
    let dir = match fs::read_dir(cache_dir) {
        Ok(d) => d,
        Err(_) => return 0,
    };

    // 构建前缀集合
    use std::collections::HashSet;
    let mut prefixes: HashSet<String> = HashSet::new();
    for src in source_paths {
        for size in &[THUMBNAIL_SIZE, GRID_THUMB_SIZE, COVER_THUMB_SIZE] {
            let mut hasher = Sha256::new();
            hasher.update(format!("{src}{size:?}").as_bytes());
            prefixes.insert(hex::encode(&hasher.finalize()[..16]));
        }
    }

    let mut removed = 0;
    for entry in dir.flatten() {
        let fname = entry.file_name();
        let fname = match fname.to_str() {
            Some(s) => s.to_string(),
            None => continue,
        };
        // 文件名格式：<hash>__<mtime>_<size>.jpg 或 <hash>.jpg
        // 提取 hash 部分（去掉 __ 后缀和 .jpg 后缀）
        let stem = fname.split("__").next().unwrap_or(&fname);
        let stem = stem.rsplit_once('.').map(|(s, _)| s).unwrap_or(stem);
        if prefixes.contains(stem)
            && fs::remove_file(entry.path()).is_ok() {
                removed += 1;
            }
    }
    removed
}


// ── 单元测试 ────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    fn tmp(tag: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("ms_test_th_{tag}_{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn generate_and_cache_thumbnail() {
        let d = tmp("gen");
        let img = image::RgbImage::from_pixel(800, 1200, image::Rgb([10, 200, 90]));
        let src = d.join("big.png");
        img.save(&src).unwrap();
        let cache = d.join("cache");
        fs::create_dir_all(&cache).unwrap();
        let t1 = generate_thumbnail(src.to_str().unwrap(), cache.to_str().unwrap(), crate::config::THUMBNAIL_SIZE);
        let t1 = t1.expect("应生成缩略图");
        assert!(PathBuf::from(&t1).is_file());
        // 尺寸符合要求（等比缩放至上限内）
        let meta = image::image_dimensions(&t1).unwrap();
        assert!(meta.0 <= 220 && meta.1 <= 300, "尺寸超限: {meta:?}");
        // 再次生成 → 缓存命中（同一路径）
        let t2 = generate_thumbnail(src.to_str().unwrap(), cache.to_str().unwrap(), crate::config::THUMBNAIL_SIZE).unwrap();
        assert_eq!(t1, t2, "未变更的源应命中缓存");
    }

    #[test]
    fn generate_thumbnail_missing_file_is_none() {
        let d = tmp("miss");
        assert!(generate_thumbnail(d.join("nope.png").to_str().unwrap(), d.to_str().unwrap(), crate::config::THUMBNAIL_SIZE).is_none());
    }

    #[test]
    fn clear_cached_thumbs_removes_only_given_sources() {
        let d = tmp("clear");
        let img = image::RgbImage::from_pixel(50, 70, image::Rgb([5, 5, 5]));
        let s1 = d.join("one.png");
        let s2 = d.join("two.png");
        img.save(&s1).unwrap();
        img.save(&s2).unwrap();
        let cache = d.join("c");
        fs::create_dir_all(&cache).unwrap();
        let t1 = generate_thumbnail(s1.to_str().unwrap(), cache.to_str().unwrap(), crate::config::THUMBNAIL_SIZE).unwrap();
        let t2 = generate_thumbnail(s2.to_str().unwrap(), cache.to_str().unwrap(), crate::config::THUMBNAIL_SIZE).unwrap();
        assert!(PathBuf::from(&t1).is_file() && PathBuf::from(&t2).is_file());
        let removed = clear_cached_thumbs(cache.to_str().unwrap(), &[s1.to_string_lossy().to_string()]);
        assert!(removed >= 1, "应至少移除 1 个缓存");
        assert!(!PathBuf::from(&t1).exists(), "指定源的缓存应被清除");
        assert!(PathBuf::from(&t2).exists(), "未指定源的缓存应保留");
    }
}
