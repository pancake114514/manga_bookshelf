//! Tauri commands 层 — 替代 Python 版 backend/api.py 的 FastAPI 路由
//!
//! 通过 Tauri IPC 暴露给前端调用的命令，每个命令对应一个原 API 端点。
//! 使用 tauri::State 共享 LibraryService 实例。
//! 图片/缩略图通过 convert_file_src 以前端可访问的 URL 返回。

use std::collections::HashMap;
use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::config::{tag_category_order, THUMBNAIL_SIZE, GRID_THUMB_SIZE, COVER_THUMB_SIZE};
use crate::db::{AssembledObject, ImageRow, TagValue, Tags, new_uuid};
use crate::library_manager;
use crate::service::LibraryService;
use crate::thumbnail::generate_thumbnail;
use crate::file_ops::{validate_windows_path_name, collect_images};
// ── 请求体 ────────────────────────────────────────────────────────────────────

#[derive(Deserialize)]
pub struct SetupBody {
    pub path: String,
}

#[derive(Deserialize)]
pub struct PathBody {
    pub path: String,
}

#[derive(Deserialize)]
pub struct ObjectPatch {
    pub name: Option<String>,
    pub tags: Option< serde_json::Value>,
    pub cover_image: Option<String>,
}

#[derive(Deserialize)]
pub struct LastReadBody {
    pub idx: i64,
}

#[derive(Deserialize)]
pub struct ImportDirectoryBody {
    pub source_dir: String,
    pub name: String,
    #[serde(default)]
    pub tags: serde_json::Value,
    #[serde(default = "default_true")]
    pub is_new: bool,
    pub obj_id: Option<String>,
}

fn default_true() -> bool {
    true
}

#[derive(Deserialize)]
pub struct ImportFilesBody {
    pub obj_id: String,
    pub paths: Vec<String>,
}

#[derive(Deserialize)]
pub struct MigrateBody {
    pub new_root: String,
}

#[derive(Deserialize)]
pub struct ConfigBody {
    pub key: String,
    pub value: String,
}

#[derive(Deserialize)]
pub struct NameBody {
    pub name: String,
}

// ── 响应体 ────────────────────────────────────────────────────────────────────

#[derive(Serialize)]
pub struct StateResponse {
    pub storage_root: Option<String>,
    pub valid: bool,
}

#[derive(Serialize)]
pub struct ObjectSummary {
    pub id: String,
    pub name: String,
    #[serde(rename = "type")]
    pub obj_type: String,
    pub tags: serde_json::Value,
    pub image_count: i64,
    pub last_read_idx: i64,
    pub created_at: Option<String>,
    pub cover_url: String,
}

#[derive(Serialize)]
pub struct ObjectDetail {
    pub id: String,
    pub name: String,
    #[serde(rename = "type")]
    pub obj_type: String,
    pub tags: serde_json::Value,
    pub image_count: i64,
    pub last_read_idx: i64,
    pub created_at: Option<String>,
    pub cover_url: String,
    pub storage_path: Option<String>,
    pub images: Vec<ImageSummary>,
}

#[derive(Serialize)]
pub struct ImageSummary {
    pub id: String,
    pub filename: String,
    pub sort_order: i64,
    pub thumb_url: String,
    pub image_url: String,
}

#[derive(Serialize)]
pub struct ImportResult {
    pub ok: bool,
    pub obj_id: Option<String>,
    pub success: i64,
    pub failed: i64,
}

/// 批量导入：统计单个文件夹中受支持图片的数量。
#[tauri::command(async)]
pub fn count_images(dir: String) -> Result<i64, String> {
    if !Path::new(&dir).is_dir() {
        return Err(format!("目录不存在：{dir}"));
    }
    Ok(collect_images(&dir).len() as i64)
}

#[derive(Serialize)]
pub struct MigrateResult {
    pub ok: bool,
    pub moved: usize,
    pub warnings: Vec<String>,
}

#[derive(Serialize)]
pub struct SimpleResult {
    pub ok: bool,
    pub error: Option<String>,
}

#[derive(Serialize)]
pub struct ConfigResponse {
    pub key: String,
    pub value: Option<String>,
}

// ── 序列化辅助 ────────────────────────────────────────────────────────────────

fn tags_to_json(tags: &Tags) -> serde_json::Value {
    let mut map = serde_json::Map::new();
    for (cat, val) in &tags.0 {
        match val {
            TagValue::Bool(b) => {
                map.insert(cat.clone(), serde_json::Value::Bool(*b));
            }
            TagValue::List(v) => {
                map.insert(
                    cat.clone(),
                    serde_json::Value::Array(v.iter().map(|s| serde_json::Value::String(s.clone())).collect()),
                );
            }
        }
    }
    serde_json::Value::Object(map)
}

fn json_to_tags(value: &serde_json::Value) -> Tags {
    let mut map: HashMap<String, TagValue> = HashMap::new();
    if let Some(obj) = value.as_object() {
        for (cat, val) in obj {
            if cat == "r18" {
                map.insert("r18".into(), TagValue::Bool(val.as_bool().unwrap_or(false)));
            } else if let Some(arr) = val.as_array() {
                let vals: Vec<String> = arr
                    .iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect();
                map.insert(cat.clone(), TagValue::List(vals));
            } else if let Some(s) = val.as_str() {
                map.insert(cat.clone(), TagValue::List(vec![s.to_string()]));
            }
        }
    }
    Tags(map)
}

fn serialize_object(o: &AssembledObject) -> ObjectSummary {
    ObjectSummary {
        id: o.id.clone(),
        name: o.name.clone(),
        obj_type: o.obj_type.clone(),
        tags: tags_to_json(&o.tags),
        image_count: o.image_count,
        last_read_idx: o.last_read_idx,
        created_at: o.created_at.clone(),
        cover_url: asset_url(&format!("object/{}/cover", o.id)),
    }
}

fn serialize_image(img: &ImageRow, obj_id: &str) -> ImageSummary {
    ImageSummary {
        id: img.id.clone(),
        filename: img.filename.clone(),
        sort_order: img.sort_order,
        thumb_url: asset_url(&format!("object/{}/thumb/{}", obj_id, img.id)),
        image_url: asset_url(&format!("object/{}/image/{}", obj_id, img.id)),
    }
}

fn storage_root_of(svc: &LibraryService) -> Option<String> {
    svc.get_config("storage_root").ok().flatten()
}

fn asset_url(path: &str) -> String {
    // Tauri 2 自定义协议 URL 格式因平台而异：
    // Windows (WebView2):  http://mangashelf.localhost/{path}  (默认 http, 非 https)
    // macOS/Linux:         mangashelf://localhost/{path}
    if cfg!(target_os = "windows") {
        format!("http://mangashelf.localhost/{}", path)
    } else {
        format!("mangashelf://localhost/{}", path)
    }
}

// ── Tauri Commands ────────────────────────────────────────────────────────────

#[tauri::command]
pub fn get_state(svc: State<'_, LibraryService>) -> Result<StateResponse, String> {
    let root = storage_root_of(&svc);
    let valid = root
        .as_ref()
        .map(|r| Path::new(r).is_dir() && library_manager::check_writable(r).is_ok())
        .unwrap_or(false);
    Ok(StateResponse {
        storage_root: root,
        valid,
    })
}

#[tauri::command]
pub fn setup(svc: State<'_, LibraryService>, body: SetupBody) -> Result<SimpleResult, String> {
    if let Err(e) = library_manager::check_writable(&body.path) {
        return Ok(SimpleResult { ok: false, error: Some(e) });
    }
    svc.set_config("storage_root", &body.path)?;
    Ok(SimpleResult { ok: true, error: None })
}

#[tauri::command]
pub fn check_writable(body: PathBody) -> Result<SimpleResult, String> {
    match library_manager::check_writable(&body.path) {
        Ok(()) => Ok(SimpleResult { ok: true, error: None }),
        Err(e) => Ok(SimpleResult { ok: false, error: Some(e) }),
    }
}

#[tauri::command]
pub fn validate_name(body: NameBody) -> Result<SimpleResult, String> {
    match validate_windows_path_name(&body.name) {
        Ok(()) => Ok(SimpleResult { ok: true, error: None }),
        Err(e) => Ok(SimpleResult { ok: false, error: Some(e) }),
    }
}

#[tauri::command]
pub fn get_objects(
    svc: State<'_, LibraryService>,
    q: Option<String>,
    include_r18: Option<bool>,
    filters: Option<String>,
) -> Result<Vec<ObjectSummary>, String> {
    let q = q.unwrap_or_default();
    let include_r18 = include_r18.unwrap_or(false);
    let filters_str = filters.unwrap_or_else(|| "{}".to_string());

    let tag_filters: HashMap<String, Vec<String>> = if filters_str.is_empty() || filters_str == "{}" {
        HashMap::new()
    } else {
        let parsed: serde_json::Value = serde_json::from_str(&filters_str)
            .map_err(|e| format!("filters 不是合法 JSON: {e}"))?;
        let mut map = HashMap::new();
        if let Some(obj) = parsed.as_object() {
            for (cat, val) in obj {
                if let Some(arr) = val.as_array() {
                    let vals: Vec<String> = arr
                        .iter()
                        .filter_map(|v| v.as_str().map(|s| s.to_string()))
                        .collect();
                    map.insert(cat.clone(), vals);
                }
            }
        }
        map
    };

    let objects = if !q.is_empty() {
        svc.search_objects(&q, include_r18)?
    } else if !tag_filters.is_empty() {
        svc.filter_by_tags(&tag_filters, include_r18)?
    } else {
        svc.get_all_objects(include_r18)?
    };

    Ok(objects.iter().map(serialize_object).collect())
}

#[tauri::command]
pub fn get_object_detail(
    svc: State<'_, LibraryService>,
    oid: String,
) -> Result<ObjectDetail, String> {
    let obj = svc
        .get_object(&oid)?
        .ok_or("对象不存在")?;
    let images = svc.get_images(&oid)?;
    let image_count = images.len() as i64;
    let detail = ObjectDetail {
        id: obj.id.clone(),
        name: obj.name.clone(),
        obj_type: obj.obj_type.clone(),
        tags: tags_to_json(&obj.tags),
        image_count,
        last_read_idx: obj.last_read_idx,
        created_at: obj.created_at.clone(),
        cover_url: asset_url(&format!("object/{}/cover", obj.id)),
        storage_path: obj.storage_path.clone(),
        images: images
            .iter()
            .map(|i| serialize_image(i, &obj.id))
            .collect(),
    };
    Ok(detail)
}

#[tauri::command]
pub fn get_tag_values(
    svc: State<'_, LibraryService>,
) -> Result<HashMap<String, Vec<String>>, String> {
    let mut result = HashMap::new();
    for cat in tag_category_order() {
        if cat == "r18" {
            continue;
        }
        let vals = svc.get_tag_values(cat)?;
        result.insert(cat.to_string(), vals);
    }
    Ok(result)
}

#[tauri::command]
pub fn update_object(
    svc: State<'_, LibraryService>,
    oid: String,
    body: ObjectPatch,
) -> Result<SimpleResult, String> {
    let obj = svc.get_object(&oid)?;
    if obj.is_none() {
        return Err("对象不存在".to_string());
    }
    if let Some(name) = body.name {
        svc.update_object_name(&oid, &name)?;
    }
    if let Some(tags) = body.tags {
        let tags = json_to_tags(&tags);
        svc.set_object_tags(&oid, &tags)?;
    }
    if let Some(cover) = body.cover_image {
        svc.update_object_cover(&oid, &cover)?;
    }
    Ok(SimpleResult { ok: true, error: None })
}

#[tauri::command]
pub fn set_last_read(
    svc: State<'_, LibraryService>,
    oid: String,
    body: LastReadBody,
) -> Result<SimpleResult, String> {
    svc.update_last_read(&oid, body.idx)?;
    Ok(SimpleResult { ok: true, error: None })
}

#[tauri::command]
pub fn delete_object(
    svc: State<'_, LibraryService>,
    oid: String,
    delete_files: Option<bool>,
) -> Result<SimpleResult, String> {
    let delete_files = delete_files.unwrap_or(false);
    let root = storage_root_of(&svc);
    svc.delete_object(&oid, delete_files, root.as_deref())?;
    Ok(SimpleResult { ok: true, error: None })
}

/// 重活命令标记 async：在独立线程执行而非 UI 主线程，
/// 避免大库导入/迁移期间窗口冻结（配合服务层"复制阶段不持锁"保证并发命令可用）
#[tauri::command(async)]
pub fn import_directory(
    svc: State<'_, LibraryService>,
    body: ImportDirectoryBody,
) -> Result<ImportResult, String> {
    if !Path::new(&body.source_dir).is_dir() {
        return Err(format!("源目录不存在：{}", body.source_dir));
    }
    let obj_id = body.obj_id.unwrap_or_else(new_uuid);
    let tags = json_to_tags(&body.tags);
    let root = storage_root_of(&svc).ok_or("图库未配置")?;

    let (ok, fail) = svc.import_directory(
        &obj_id,
        &body.name,
        &tags,
        &body.source_dir,
        &root,
        body.is_new,
        None,
        None,
    )?;
    Ok(ImportResult {
        ok: true,
        obj_id: Some(obj_id),
        success: ok,
        failed: fail,
    })
}

#[tauri::command(async)]
pub fn import_files(
    svc: State<'_, LibraryService>,
    body: ImportFilesBody,
) -> Result<ImportResult, String> {
    for p in &body.paths {
        if !Path::new(p).is_file() {
            return Err(format!("文件不存在：{p}"));
        }
    }
    let root = storage_root_of(&svc).ok_or("图库未配置")?;
    let (ok, fail) = svc.import_single_files(&body.obj_id, &body.paths, &root)?;
    Ok(ImportResult {
        ok: true,
        obj_id: Some(body.obj_id),
        success: ok,
        failed: fail,
    })
}

#[tauri::command(async)]
pub fn migrate(
    svc: State<'_, LibraryService>,
    body: MigrateBody,
) -> Result<MigrateResult, String> {
    let (moved, warnings) = svc.migrate_library(&body.new_root, None)?;
    Ok(MigrateResult {
        ok: true,
        moved,
        warnings,
    })
}

#[tauri::command]
pub fn get_config_value(
    svc: State<'_, LibraryService>,
    key: String,
) -> Result<ConfigResponse, String> {
    let value = svc.get_config(&key)?;
    Ok(ConfigResponse { key, value })
}

#[tauri::command]
pub fn set_config_value(
    svc: State<'_, LibraryService>,
    body: ConfigBody,
) -> Result<SimpleResult, String> {
    svc.set_config(&body.key, &body.value)?;
    Ok(SimpleResult { ok: true, error: None })
}

// ── 图片/缩略图 URL scheme 处理 ───────────────────────────────────────────────

/// 解析自定义协议 URL 并返回本地文件路径
/// Tauri 2 自定义协议在不同平台上 URI 格式不同：
///   Windows:  https://mangashelf.localhost/object/{oid}/cover
///   macOS/Linux: mangashelf://localhost/object/{oid}/cover
/// 统一提取 /object/{oid}/... 路径部分进行解析。
pub fn resolve_image_url(svc: &LibraryService, url: &str) -> Result<(String, Option<(u32, u32)>), String> {
    // 提取 path 部分：找到 "/object/" 的位置
    let path = url
        .find("/object/")
        .map(|i| &url[i + 1..])  // 去掉前导 '/'
        .ok_or("无效的 URL: 缺少 /object/ 路径")?;

    // 分割路径
    let parts: Vec<&str> = path.split('/').collect();
    // parts: ["object", oid, "cover" | "image" | "thumb", img_id?]
    if parts.len() < 3 {
        return Err("URL 路径不完整".to_string());
    }
    let oid = parts[1];
    let kind = parts[2];

    match kind {
        "cover" => {
            let obj = svc
                .get_object(oid)?
                .ok_or("对象不存在")?;
            let cover = svc.resolve_cover(&obj).ok_or("无封面")?;
            // .thumb 封面（源目录自带的封面缩略图）本身就是缩放好的小图，
            // 直出原图，跳过缩略图生成；其余封面正常走缩略图管线
            let is_thumb = Path::new(&cover)
                .file_name()
                .and_then(|n| n.to_str())
                .map(|n| n.to_lowercase().starts_with(".thumb"))
                .unwrap_or(false);
            if is_thumb {
                Ok((cover, None))
            } else {
                Ok((cover, Some(COVER_THUMB_SIZE)))
            }
        }
        "image" | "thumb" => {
            if parts.len() < 4 {
                return Err("缺少图片 ID".to_string());
            }
            let img_id = parts[3];
            let img = svc
                .get_image_by_id(oid, img_id)?
                .ok_or("图片不存在")?;
            if kind == "thumb" {
                Ok((img.filepath.clone(), Some(GRID_THUMB_SIZE)))
            } else {
                Ok((img.filepath.clone(), None))
            }
        }
        _ => Err(format!("未知的图片类型: {kind}")),
    }
}

/// 生成缩略图并返回路径，供 Tauri 的 asset protocol 使用。
/// kind 格式为 "{w}_{h}"，直接解析为尺寸。
pub fn get_thumbnail_path(
    svc: &LibraryService,
    source_path: &str,
    kind: &str,
) -> Result<String, String> {
    let root = storage_root_of(svc).ok_or("图库未配置")?;
    let cache_dir = crate::thumbnail::get_thumb_cache_dir(&root);
    // 解析 "w_h" 格式
    let size = kind
        .split_once('_')
        .and_then(|(w, h)| {
            let w: u32 = w.parse().ok()?;
            let h: u32 = h.parse().ok()?;
            Some((w, h))
        })
        .unwrap_or(THUMBNAIL_SIZE);
    let thumb = generate_thumbnail(source_path, &cache_dir, size)
        .ok_or("缩略图生成失败")?;
    Ok(thumb)
}

// ── 系统集成 ──────────────────────────────────────────────────────────────────

/// 在系统资源管理器中打开对象的存储目录（Windows: explorer 选中该文件夹）
#[tauri::command]
pub fn open_in_explorer(
    app: tauri::AppHandle,
    svc: State<'_, LibraryService>,
    oid: String,
) -> Result<(), String> {
    let obj = svc
        .get_object(&oid)?
        .ok_or("对象不存在")?;
    let path = obj.storage_path.ok_or("该对象没有存储目录")?;
    if !Path::new(&path).is_dir() {
        return Err(format!("目录不存在：{path}"));
    }
    use tauri_plugin_opener::OpenerExt;
    app.opener()
        .reveal_item_in_dir(path)
        .map_err(|e| format!("打开资源管理器失败: {e}"))
}


// ── 单元测试 ────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn count_images_counts_supported_only() {
        let d = std::env::temp_dir().join(format!("ms_count_{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&d).unwrap();
        for name in ["a.png", "b.jpg", "c.txt", ".thumb.jpg", "d.webp"] {
            if name.ends_with(".txt") {
                fs::write(d.join(name), "x").unwrap();
            } else {
                let p = d.join(name);
                image::RgbImage::from_pixel(20, 30, image::Rgb([9, 9, 9]))
                    .save(&p)
                    .unwrap();
            }
        }
        // a/b/d 三张受支持图片；.thumb.jpg 是隐藏文件不计数，c.txt 非图片
        assert_eq!(count_images(d.to_str().unwrap().to_string()).unwrap(), 3);
    }

    #[test]
    fn count_images_rejects_missing_dir() {
        let d = std::env::temp_dir().join(format!("ms_count_none_{}", uuid::Uuid::new_v4()));
        assert!(count_images(d.to_str().unwrap().to_string()).is_err());
    }
}