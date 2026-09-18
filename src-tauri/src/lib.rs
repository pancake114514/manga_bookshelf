//! MangaShelf — Tauri 2 应用入口 (lib)
//!
//! 初始化 LibraryService、注册 commands、配置插件。

use std::sync::Mutex;

use mangashelf_lib::commands::*;
use mangashelf_lib::config;
use mangashelf_lib::service::LibraryService;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::init();

    let db_path = config::db_path();
    log::info!("数据库路径: {db_path}");

    let service = match LibraryService::new(&db_path) {
        Ok(s) => s,
        Err(e) => {
            log::error!("初始化数据库失败: {e}");
            panic!("初始化数据库失败: {e}");
        }
    };

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .manage(service)
        .register_uri_scheme_protocol("mangashelf", move |app, request| {
            let svc = app.state::<LibraryService>();
            let url = request.uri().to_string();

            match resolve_image_url(&svc, &url) {
                Ok((path, thumb_size)) => {
                    if let Some(size) = thumb_size {
                        // 需要缩略图
                        match get_thumbnail_path(&svc, &path, &format!("{}_{}", size.0, size.1)) {
                            Ok(thumb_path) => {
                                read_file_response(&thumb_path)
                            }
                            Err(_) => {
                                // 缩略图失败，返回原图
                                read_file_response(&path)
                            }
                        }
                    } else {
                        read_file_response(&path)
                    }
                }
                Err(e) => {
                    log::warn!("解析图片 URL 失败: {e} | {url}");
                    tauri::http::Response::builder()
                        .status(404)
                        .body(e.into_bytes())
                        .unwrap()
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_state,
            setup,
            check_writable,
            validate_name,
            get_objects,
            get_object_detail,
            get_tag_values,
            update_object,
            set_last_read,
            delete_object,
            import_directory,
            import_files,
            migrate,
            get_config_value,
            set_config_value,
        ])
        .run(tauri::generate_context!())
        .expect("启动 MangaShelf 失败");
}

fn read_file_response(path: &str) -> tauri::http::Response<Vec<u8>> {
    match std::fs::read(path) {
        Ok(data) => {
            let mime = guess_mime(path);
            tauri::http::Response::builder()
                .status(200)
                .header("Content-Type", mime)
                .header("Cache-Control", "max-age=3600")
                .body(data)
                .unwrap()
        }
        Err(_) => tauri::http::Response::builder()
            .status(404)
            .body(b"文件不存在".to_vec())
            .unwrap(),
    }
}

fn guess_mime(path: &str) -> &'static str {
    let lower = path.to_lowercase();
    if lower.ends_with(".jpg") || lower.ends_with(".jpeg") {
        "image/jpeg"
    } else if lower.ends_with(".png") {
        "image/png"
    } else if lower.ends_with(".webp") {
        "image/webp"
    } else if lower.ends_with(".gif") {
        "image/gif"
    } else if lower.ends_with(".bmp") {
        "image/bmp"
    } else if lower.ends_with(".tif") || lower.ends_with(".tiff") {
        "image/tiff"
    } else {
        "application/octet-stream"
    }
}
