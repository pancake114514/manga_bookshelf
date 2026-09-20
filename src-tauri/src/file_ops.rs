//! 文件操作工具 — 与 Python 版 utils/file_utils.py 对等

use std::fs;
use std::path::Path;

use crate::config::is_supported_image;

/// 收集目录中所有支持格式的图片，按文件名升序排列。
/// 以 '.' 开头的隐藏文件不收集。
pub fn collect_images(directory: &str) -> Vec<String> {
    let mut result = Vec::new();
    let entries = match fs::read_dir(directory) {
        Ok(e) => e,
        Err(_) => return result,
    };
    let mut names: Vec<String> = entries
        .filter_map(|e| e.ok())
        .filter_map(|e| e.file_name().to_str().map(|s| s.to_string()))
        .filter(|n| !n.starts_with('.'))
        .filter(|n| is_supported_image(n))
        .collect();
    names.sort();
    for name in names {
        result.push(
            Path::new(directory)
                .join(&name)
                .to_string_lossy()
                .to_string(),
        );
    }
    result
}

/// 扫描存储目录，返回下一个可用序号（已有文件最大序号 + 1，从 1 开始）。
/// 只识别形如 000001.ext 的文件名（纯数字部分）。
/// 将图片复制到存储目录，保留原文件名；目标已存在时在扩展名前加 (1)、(2)… 递增。
/// 返回 (filename, dest_path)，失败返回 None。
pub fn copy_image_keep_name(src_path: &str, storage_obj_dir: &str) -> Option<(String, String)> {
    let _ = fs::create_dir_all(storage_obj_dir);
    let src = Path::new(src_path);
    let orig = src.file_name()?.to_str()?.to_string();
    let (stem, ext) = match src.extension().and_then(|e| e.to_str()) {
        Some(e) => (orig.trim_end_matches(e).trim_end_matches('.'), format!(".{e}")),
        None => (orig.as_str(), String::new()),
    };

    let mut n: i64 = 0;
    let (filename, dest) = loop {
        let fname = if n == 0 {
            orig.clone()
        } else {
            format!("{stem}({n}){ext}")
        };
        let dest = Path::new(storage_obj_dir).join(&fname);
        if !dest.exists() {
            break (fname, dest.to_string_lossy().to_string());
        }
        n += 1;
    };

    match fs::copy(src_path, &dest) {
        Ok(_) => Some((filename, dest)),
        Err(e) => {
            log::warn!("图片复制失败: {e} | {src_path}");
            None
        }
    }
}

/// 校验是否是合法 Windows 路径名
pub fn validate_windows_path_name(name: &str) -> Result<(), String> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err("名称不能为空".to_string());
    }
    if name.len() > 200 {
        return Err("名称过长（最多 200 个字符）".to_string());
    }
    let illegal_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|'];
    let bad: Vec<char> = name.chars().filter(|c| illegal_chars.contains(c)).collect();
    if !bad.is_empty() {
        let unique: String = {
            let mut seen: std::collections::HashSet<char> = std::collections::HashSet::new();
            let mut result = String::new();
            for c in &bad {
                if seen.insert(*c) {
                    result.push(*c);
                }
            }
            result
        };
        return Err(format!("包含非法字符：{unique}"));
    }
    let reserved = [
        "CON", "PRN", "AUX", "NUL", "COM0", "COM1", "COM2", "COM3", "COM4", "COM5",
        "COM6", "COM7", "COM8", "COM9", "LPT0", "LPT1", "LPT2", "LPT3", "LPT4",
        "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    ];
    let stem = name.split('.').next().unwrap_or("").to_uppercase();
    if reserved.contains(&stem.as_str()) {
        return Err(format!("'{name}' 是 Windows 保留名称"));
    }
    if name != name.trim_matches(|c| c == '.' || c == ' ') {
        return Err("名称不能以点或空格开头/结尾".to_string());
    }
    Ok(())
}

// ── 单元测试（对标原 Python 版 test_file_utils 语义）────────────────────────
#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    fn tmp(tag: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("ms_test_fo_{tag}_{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&d).unwrap();
        d
    }

    fn mk_img(dir: &std::path::Path, name: &str) -> String {
        let img = image::RgbImage::from_pixel(40, 60, image::Rgb([200, 100, 50]));
        let p = dir.join(name);
        img.save(&p).unwrap();
        p.to_string_lossy().to_string()
    }

    #[test]
    fn collect_images_filters_supported_and_hidden() {
        let d = tmp("collect");
        mk_img(&d, "a.png");
        mk_img(&d, "b.jpg");
        fs::write(d.join("c.txt"), "x").unwrap();
        fs::write(d.join(".hidden.png"), "x").unwrap();
        let names: Vec<String> = collect_images(d.to_str().unwrap())
            .into_iter()
            .map(|p| PathBuf::from(p).file_name().unwrap().to_string_lossy().to_string())
            .collect();
        assert_eq!(names.len(), 2, "只收集受支持格式且跳过隐藏文件: {names:?}");
        assert!(names.contains(&"a.png".to_string()));
        assert!(names.contains(&"b.jpg".to_string()));
    }

    #[test]
    fn copy_keeps_original_name() {
        let src_dir = tmp("cpkeep");
        let dst_dir = tmp("cpkeep2");
        let src = mk_img(&src_dir, "我的照片.png");
        let (fname, dest) = copy_image_keep_name(&src, dst_dir.to_str().unwrap()).unwrap();
        assert_eq!(fname, "我的照片.png");
        assert!(dst_dir.join("我的照片.png").is_file());
        assert_eq!(dest, dst_dir.join("我的照片.png").to_string_lossy().to_string());
    }

    #[test]
    fn copy_appends_counter_on_collision() {
        let src_dir = tmp("cpcoll");
        let dst_dir = tmp("cpcoll2");
        let src = mk_img(&src_dir, "dup.jpg");
        // 第一次 → 原名；第二、三次 → (1)、(2)
        let (f1, _) = copy_image_keep_name(&src, dst_dir.to_str().unwrap()).unwrap();
        let (f2, _) = copy_image_keep_name(&src, dst_dir.to_str().unwrap()).unwrap();
        let (f3, _) = copy_image_keep_name(&src, dst_dir.to_str().unwrap()).unwrap();
        assert_eq!(f1, "dup.jpg");
        assert_eq!(f2, "dup(1).jpg");
        assert_eq!(f3, "dup(2).jpg");
        assert!(dst_dir.join("dup.jpg").is_file());
        assert!(dst_dir.join("dup(1).jpg").is_file());
        assert!(dst_dir.join("dup(2).jpg").is_file());
    }

    #[test]
    fn copy_collision_preserves_extensionless_and_multi_dot() {
        let src_dir = tmp("cpext");
        let dst_dir = tmp("cpext2");
        let p = src_dir.join("archive.tar.gz");
        std::fs::write(&p, "x").unwrap();
        let (f1, _) = copy_image_keep_name(p.to_str().unwrap(), dst_dir.to_str().unwrap()).unwrap();
        let (f2, _) = copy_image_keep_name(p.to_str().unwrap(), dst_dir.to_str().unwrap()).unwrap();
        assert_eq!(f1, "archive.tar.gz");
        assert_eq!(f2, "archive.tar(1).gz", "多扩展名只按最后一段处理");
    }

    #[test]
    fn validate_path_name_rules() {
        assert!(validate_windows_path_name("正常名字").is_ok());
        assert!(validate_windows_path_name("带 空格-1").is_ok());
        for bad in ["a/b", "a\\b", "..", "a:b", "a?b", "a*b", "a<b", "a|b", ""] {
            assert!(validate_windows_path_name(bad).is_err(), "应拒绝: {bad:?}");
        }
    }
}
