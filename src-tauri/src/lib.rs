//! MangaShelf — Tauri 2 应用入口 (lib)
//!
//! 初始化 LibraryService、注册 commands、配置插件。

use tauri::Manager;

mod commands;
mod config;
mod db;
mod file_ops;
mod library_manager;
mod service;
mod thumbnail;

use commands::{cached_thumb_path, get_thumbnail_path, resolve_image_url};
use service::LibraryService;

/// 缩略图生成并发上限。
/// 首次打开详情页时 WebView 会同时涌入上百个图片请求，若每个都裸开线程
/// 各自解码+Lanczos 缩放，会瞬间吃满所有核心（风扇狂转）。用计数信号量
/// 把"重活"（缓存未命中的缩略图生成）限制在少数几个线程，其余排队。
const THUMB_CONCURRENCY: usize = 2;

struct Semaphore {
    count: std::sync::Mutex<usize>,
    cond: std::sync::Condvar,
}

impl Semaphore {
    fn new(permits: usize) -> Self {
        Self {
            count: std::sync::Mutex::new(permits),
            cond: std::sync::Condvar::new(),
        }
    }

    /// 获取一个许可（无可用时阻塞排队）
    fn acquire(&self) {
        let mut n = self.count.lock().unwrap();
        while *n == 0 {
            n = self.cond.wait(n).unwrap();
        }
        *n -= 1;
    }

    /// 归还一个许可
    fn release(&self) {
        let mut n = self.count.lock().unwrap();
        *n += 1;
        self.cond.notify_one();
    }
}

static THUMB_SEMAPHORE: std::sync::OnceLock<Semaphore> = std::sync::OnceLock::new();

fn thumb_semaphore() -> &'static Semaphore {
    THUMB_SEMAPHORE.get_or_init(|| Semaphore::new(THUMB_CONCURRENCY))
}

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
        // 单实例：二次启动时唤起已有主窗口，随后新进程立即退出
        // （须注册为第一个插件；避免多进程并发写同一 SQLite 库）
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.show();
                let _ = win.unminimize();
                let _ = win.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .manage(service)
        .register_asynchronous_uri_scheme_protocol("mangashelf", move |ctx, request, responder| {
            // wry 在 Windows 上将 http://mangashelf.localhost/path 还原为
            // mangashelf://localhost/path 后传给此 handler
            let url = request.uri().to_string();
            log::info!("mangashelf URI request: {}", url);

            // 同步版协议 handler 在 WebView2 上于主线程执行，而缩略图生成
            // （解码原图 + Lanczos3 缩放）是重活，会堵死 UI 事件循环导致窗口无响应；
            // 必须用异步版并把处理放到后台线程，完成后经 responder 回给 WebView
            let app = ctx.app_handle().clone();
            std::thread::spawn(move || {
                let svc = app.state::<LibraryService>();
                let response = match resolve_image_url(&svc, &url) {
                    Ok((path, thumb_size)) => {
                        if let Some(size) = thumb_size {
                            // 需要缩略图：先无锁探测缓存，命中则直接读文件（轻，
                            // 不占许可）；未命中则排队生成（重活，受并发上限约束）
                            let sem = thumb_semaphore();
                            let kind = format!("{}_{}", size.0, size.1);
                            if let Some(cached) =
                                cached_thumb_path(&svc, &path, &kind)
                            {
                                read_file_response(&cached)
                            } else {
                                sem.acquire();
                                let resp = get_thumbnail_path(&svc, &path, &kind)
                                    .map(|p| read_file_response(&p))
                                    .unwrap_or_else(|_| read_file_response(&path));
                                sem.release();
                                resp
                            }
                        } else {
                            read_file_response(&path)
                        }
                    }
                    Err(e) => {
                        log::warn!("解析图片 URL 失败: {e} | {url}");
                        tauri::http::Response::builder()
                            .status(404)
                            .body(e.into_bytes().into())
                            .unwrap()
                    }
                };
                responder.respond(response);
            });
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_state,
            commands::setup,
            commands::check_writable,
            commands::validate_name,
            commands::get_objects,
            commands::get_object_detail,
            commands::get_tag_values,
            commands::update_object,
            commands::set_last_read,
            commands::delete_object,
            commands::import_directory,
            commands::import_files,
            commands::count_images,
            commands::migrate,
            commands::get_config_value,
            commands::set_config_value,
            commands::prune_thumb_cache,
            commands::open_in_explorer,
        ])
        // 关闭拦截：删除进行中时阻止直接退出，确认后才放行（防文件删到一半被杀进程）
        .on_window_event({
            use std::sync::atomic::{AtomicBool, Ordering};
            let exiting = std::sync::Arc::new(AtomicBool::new(false));
            move |window, event| {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    // 已确认退出（或无任务在跑）：放行
                    if exiting.load(Ordering::SeqCst)
                        || commands::deletions_in_progress() == 0
                    {
                        return;
                    }
                    api.prevent_close();
                    let win = window.clone();
                    let exiting = exiting.clone();
                    // 原生模态框会阻塞，放独立线程跑，避免卡死主线程事件循环
                    std::thread::spawn(move || {
                        use tauri_plugin_dialog::{DialogExt, MessageDialogButtons};
                        let confirmed = win
                            .app_handle()
                            .dialog()
                            .message("正在删除，确定退出吗？")
                            .title("MangaShelf")
                            .buttons(MessageDialogButtons::OkCancelCustom(
                                "退出".into(),
                                "取消".into(),
                            ))
                            .blocking_show();
                        if confirmed {
                            exiting.store(true, Ordering::SeqCst);
                            let _ = win.close();
                        }
                    });
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("启动 MangaShelf 失败");
}

fn read_file_response(path: &str) -> tauri::http::Response<std::borrow::Cow<'static, [u8]>> {
    match std::fs::read(path) {
        Ok(data) => {
            let mime = guess_mime(path);
            tauri::http::Response::builder()
                .status(200)
                .header("Content-Type", mime)
                .header("Cache-Control", "max-age=3600")
                .body(std::borrow::Cow::Owned(data))
                .unwrap()
        }
        Err(_) => tauri::http::Response::builder()
            .status(404)
            .body(std::borrow::Cow::Borrowed("File not found".as_bytes()))
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
