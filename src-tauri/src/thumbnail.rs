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

/// 探测缩略图缓存：命中返回缓存路径，未命中返回 None。
/// 供协议层在排队生成前先查缓存，命中则免占并发许可直接读文件。
pub fn cached_thumb_path(
    source_path: &str,
    cache_dir: &str,
    size: (u32, u32),
) -> Option<String> {
    let path = thumb_path(cache_dir, source_path, size);
    if path.is_file() {
        Some(path.to_string_lossy().to_string())
    } else {
        None
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

    // 大比率降采样时 Lanczos3 的核宽度随缩放比放大（约 13× 缩小时每输出
    // 像素需 80+ 采样点），是缩略图生成的最大 CPU 热点；thumbnail() 的
    // box-filter 单趟降采样在此场景快数倍，160~220px 目标尺寸下画质肉眼
    // 无差。仅小比率调整（<2×）时保留 Lanczos3。
    let resized = if src_w >= new_w.saturating_mul(2) || src_h >= new_h.saturating_mul(2) {
        let t = img.thumbnail(new_w, new_h);
        // thumbnail 按比例取整可能比目标小 1px，补齐以保证可裁剪
        if t.width() < target_w || t.height() < target_h {
            t.resize_exact(
                target_w.max(t.width()),
                target_h.max(t.height()),
                image::imageops::FilterType::Lanczos3,
            )
        } else {
            t
        }
    } else {
        img.resize_exact(new_w, new_h, image::imageops::FilterType::Lanczos3)
    };

    // 居中裁剪
    let left = (resized.width().saturating_sub(target_w)) / 2;
    let top = (resized.height().saturating_sub(target_h)) / 2;
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

/// 清理缩略图缓存（维护操作）。
///
/// 两段策略：
/// ① 正确性清理——keep_sources 为全部活动源（对象封面+图片），按当前 mtime/size
///   计算各自在全部尺寸档位下"应存在"的缓存文件名；缓存目录中不在该集合内的
///   一律删除（已删对象残留、源文件替换后的失效版本等）。
/// ② 总量上限——清理后若总大小仍超 max_total_bytes，按 mtime 从旧到新删除直到
///   达标（被删的活动缓存下次访问时会自动重新生成）。
///
/// 返回 (删除文件数, 释放字节数)。写入中的 .tmp 临时文件跳过（生成流程即将
/// 原子改名接管；仅进程崩溃才会残留，体积极小）。
pub fn prune_thumb_cache(
    cache_dir: &str,
    keep_sources: &[String],
    max_total_bytes: u64,
) -> (usize, u64) {
    // ① 计算应保留的文件名集合
    let mut keep: std::collections::HashSet<String> = std::collections::HashSet::new();
    for src in keep_sources {
        for size in &[THUMBNAIL_SIZE, GRID_THUMB_SIZE, COVER_THUMB_SIZE] {
            let p = thumb_path(cache_dir, src, *size);
            if let Some(name) = p.file_name().and_then(|n| n.to_str()) {
                keep.insert(name.to_string());
            }
        }
    }

    let dir = match fs::read_dir(cache_dir) {
        Ok(d) => d,
        Err(_) => return (0, 0),
    };

    let mut removed = 0usize;
    let mut freed: u64 = 0;
    let mut kept_files: Vec<(std::path::PathBuf, u64, std::time::SystemTime)> = Vec::new();
    let mut kept_total: u64 = 0;

    for entry in dir.flatten() {
        let name = entry.file_name();
        let name = match name.to_str() {
            Some(s) => s.to_string(),
            None => continue,
        };
        if name.ends_with(".tmp") {
            continue;
        }
        let meta = match entry.metadata() {
            Ok(m) => m,
            Err(_) => continue,
        };
        if keep.contains(&name) {
            let mtime = meta.modified().unwrap_or(std::time::UNIX_EPOCH);
            kept_total += meta.len();
            kept_files.push((entry.path(), meta.len(), mtime));
        } else if fs::remove_file(entry.path()).is_ok() {
            removed += 1;
            freed += meta.len();
        }
    }

    // ② 总量超限时按最旧优先删除（活动缓存可再生，删除安全）
    if kept_total > max_total_bytes {
        kept_files.sort_by_key(|(_, _, mtime)| *mtime);
        for (path, len, _) in kept_files {
            if kept_total <= max_total_bytes {
                break;
            }
            if fs::remove_file(&path).is_ok() {
                removed += 1;
                freed += len;
                kept_total = kept_total.saturating_sub(len);
            }
        }
    }

    (removed, freed)
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

    #[test]
    fn prune_removes_stale_and_foreign_files_keeps_live() {
        let d = tmp("prune");
        let img = image::RgbImage::from_pixel(400, 600, image::Rgb([9, 90, 9]));
        let src = d.join("page.png");
        img.save(&src).unwrap();
        let cache = d.join("cache");
        fs::create_dir_all(&cache).unwrap();
        let t1 = generate_thumbnail(src.to_str().unwrap(), cache.to_str().unwrap(), crate::config::THUMBNAIL_SIZE).unwrap();

        // 外来文件（不属于任何活动源）
        fs::write(cache.join("deadbeef__123_456.jpg"), "x").unwrap();

        // 源文件被替换（内容变化 → mtime/size 变）→ 重新生成得到新缓存名，旧版本成为失效残留
        std::thread::sleep(std::time::Duration::from_millis(20));
        let img2 = image::RgbImage::from_pixel(410, 610, image::Rgb([9, 90, 9]));
        img2.save(&src).unwrap();
        let t2 = generate_thumbnail(src.to_str().unwrap(), cache.to_str().unwrap(), crate::config::THUMBNAIL_SIZE).unwrap();
        assert_ne!(t1, t2, "替换源后应产生新缓存文件名");
        assert!(PathBuf::from(&t1).is_file(), "旧缓存此刻仍残留（待清理）");

        let (removed, freed) = prune_thumb_cache(
            cache.to_str().unwrap(),
            &[src.to_string_lossy().to_string()],
            u64::MAX,
        );
        assert!(removed >= 2, "旧版本与外来文件都应被清理: removed={removed}");
        assert!(freed > 0);
        assert!(!PathBuf::from(&t1).exists(), "失效版本应被删除");
        assert!(PathBuf::from(&t2).is_file(), "活动缓存应保留");
    }

    #[test]
    fn prune_enforces_total_cap_by_oldest_first() {
        let d = tmp("prunecap");
        let cache = d.join("cache");
        fs::create_dir_all(&cache).unwrap();
        let img = image::RgbImage::from_pixel(60, 80, image::Rgb([7, 7, 7]));
        let s1 = d.join("a.png");
        let s2 = d.join("b.png");
        img.save(&s1).unwrap();
        std::thread::sleep(std::time::Duration::from_millis(20));
        img.save(&s2).unwrap();
        let t1 = generate_thumbnail(s1.to_str().unwrap(), cache.to_str().unwrap(), crate::config::THUMBNAIL_SIZE).unwrap();
        std::thread::sleep(std::time::Duration::from_millis(20));
        let t2 = generate_thumbnail(s2.to_str().unwrap(), cache.to_str().unwrap(), crate::config::THUMBNAIL_SIZE).unwrap();
        assert!(PathBuf::from(&t1).is_file() && PathBuf::from(&t2).is_file());

        // 上限设 0：两个活动缓存都被删（极端但可断言按序全删）
        let (removed, _) = prune_thumb_cache(cache.to_str().unwrap(), &[
            s1.to_string_lossy().to_string(),
            s2.to_string_lossy().to_string(),
        ], 0);
        assert!(removed >= 2, "超限应删除活动缓存: removed={removed}");
        assert!(!PathBuf::from(&t1).exists() && !PathBuf::from(&t2).exists());
    }
}
