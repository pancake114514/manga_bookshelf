"""MangaShelf 桌面入口（Web 技术栈版）。

用法：
  venv/Scripts/python.exe backend/server.py             # 桌面窗口（pywebview）
  venv/Scripts/python.exe backend/server.py --serve     # 仅本地服务，浏览器打开调试
  venv/Scripts/python.exe backend/server.py --port 8765 # 固定端口（配合 vite proxy）
"""
import argparse
import os
import sys
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Bridge:
    """暴露给前端 window.pywebview.api 的本地能力（目录/文件选择、窗口控制）。"""

    def __init__(self):
        self._maximized = False   # 无边框窗口无原生状态可查，由按钮路径自行跟踪

    def pick_dir(self, title: str = "选择目录"):
        import webview
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

    def pick_files(self, title: str = "选择文件"):
        import webview
        file_types = ("图片文件", "*.jpg;*.jpeg;*.png;*.bmp;*.webp;*.gif;*.tiff;*.tif")
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True, file_types=file_types)
        return list(result) if result else []

    # ── 自定义标题栏的窗口控制 ──
    def minimize(self):
        import webview
        webview.windows[0].minimize()

    def toggle_maximize(self):
        """最大化/还原切换，返回切换后的状态供前端更新按钮图标。"""
        import webview
        w = webview.windows[0]
        if self._maximized:
            w.restore()
            self._maximized = False
        else:
            w.maximize()
            self._maximized = True
        return self._maximized

    def close_window(self):
        import webview
        webview.windows[0].destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="仅启动本地服务（浏览器调试）")
    parser.add_argument("--port", type=int, default=0, help="固定端口（默认随机）")
    args = parser.parse_args()

    import uvicorn
    from backend.api import app

    port = args.port or _free_port()
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)

    url = f"http://127.0.0.1:{port}"
    print(f"MangaShelf 服务已启动：{url}", flush=True)

    if args.serve:
        # 阻塞主线程保持服务运行，Ctrl+C 退出
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return

    import webview
    webview.create_window(
        "MangaShelf", url,
        width=1280, height=820, min_size=(1000, 680),
        js_api=Bridge(),
        frameless=True,      # 去掉系统标题栏，由前端 TitleBar 组件接管
        easy_drag=False,     # 仅标题栏拖拽区可拖动，避免干扰正文交互
    )
    webview.start()


if __name__ == "__main__":
    main()
