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
pub fn next_seq_number(storage_obj_dir: &str) -> i64 {
    let mut max_seq: i64 = 0;
    let entries = match fs::read_dir(storage_obj_dir) {
        Ok(e) => e,
        Err(_) => return 1,
    };
    for entry in entries.flatten() {
        let fname = entry.file_name();
        let fname = match fname.to_str() {
            Some(s) => s,
            None => continue,
        };
        if fname.starts_with('.') {
            continue;
        }
        let path = entry.path();
        let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
        let ext_lower = format!(".{}", ext.to_lowercase());
        if !is_supported_image(&format!("x{ext_lower}")) {
            continue;
        }
        let stem = Path::new(fname).file_stem().and_then(|s| s.to_str()).unwrap_or("");
        if let Ok(n) = stem.parse::<i64>() {
            max_seq = max_seq.max(n);
        }
    }
    max_seq + 1
}

/// 将图片复制到存储目录，以 7 位序号重命名（如 000001.jpg）。
/// 返回 (filename, dest_path, used_seq)，失败返回 None。
pub fn copy_image_with_seq_name(
    src_path: &str,
    storage_obj_dir: &str,
    seq: i64,
) -> Option<(String, String, i64)> {
    let _ = fs::create_dir_all(storage_obj_dir);
    let src = Path::new(src_path);
    let ext = src
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| format!(".{}", e.to_lowercase()))
        .unwrap_or_default();

    let mut seq = seq;
    let (filename, dest) = loop {
        let fname = format!("{seq:07}{ext}");
        let dest = Path::new(storage_obj_dir).join(&fname);
        if !dest.exists() {
            break (fname, dest.to_string_lossy().to_string());
        }
        seq += 1;
    };

    match fs::copy(src_path, &dest) {
        Ok(_) => Some((filename, dest, seq)),
        Err(e) => {
            log::warn!("图片复制失败: {e} | {src_path}");
            None
        }
    }
}

/// 校验是否是合法 Windows 路径名，返回 (ok, error_msg)
pub fn validate_windows_path_name(name: &str) -> Result<(), String> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err("名称不能为空".to_string());
    }
    if name.len() > 200 {
        return Err("名称过长（最多 200 个字符）".to_string());
    }
    let illegal = r'\/:*?"<>|';
    let bad: Vec<char> = name.chars().filter(|c| illegal.contains(*c)).collect();
    if !bad.is_empty() {
        let unique: String = bad.iter().collect::<std::collections::HashSet<_>>().into_iter().collect();
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
