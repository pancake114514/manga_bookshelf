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
        self._fs_rect = None      # 全屏前的窗口矩形，用于还原
        self._rs = None           # 边缘拖拽缩放状态（方向/初始矩形/光标起点）

    def toggle_fullscreen(self):
        """阅读器真全屏：窗口铺满整个显示器（含任务栏），再次调用还原。

        WebView2 宿主不响应 HTML requestFullscreen，全屏需在窗口层实现。
        """
        import ctypes
        import webview

        MONITOR_DEFAULTTONEAREST = 2
        SWP_NOZORDER = 0x0004

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

        u = ctypes.windll.user32
        u.MonitorFromWindow.restype = ctypes.c_void_p
        u.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        u.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        hwnd = int(webview.windows[0].native.Handle.ToInt64())
        if self._fs_rect is None:
            wr = RECT()
            u.GetWindowRect(hwnd, ctypes.byref(wr))
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST), ctypes.byref(mi))
            m = mi.rcMonitor
            u.SetWindowPos(hwnd, 0, m.left, m.top,
                           m.right - m.left, m.bottom - m.top, SWP_NOZORDER)
            self._fs_rect = (wr.left, wr.top, wr.right, wr.bottom)
        else:
            l, t, r, b = self._fs_rect
            u.SetWindowPos(hwnd, 0, l, t, r - l, b - t, SWP_NOZORDER)
            self._fs_rect = None
        return self._fs_rect is not None

    def exit_fullscreen(self):
        """退出全屏（非全屏态调用为空操作）。"""
        if self._fs_rect is not None:
            self.toggle_fullscreen()

    # ── 边缘拖拽缩放（WebView2 子窗口跨进程覆盖客户区，Win32 命中测试不可达，
    #    由前端边缘热区经桥接驱动，三段式：begin 记录起点 → move 实时调整 → end 结束）──
    def begin_window_resize(self, direction, screen_x, screen_y):
        import ctypes
        import webview

        u = ctypes.windll.user32
        hwnd = int(webview.windows[0].native.Handle.ToInt64())
        if u.IsZoomed(hwnd) or self._fs_rect is not None:
            return False
        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
        wr = RECT()
        u.GetWindowRect(hwnd, ctypes.byref(wr))
        self._rs = {'dir': direction, 'rect': (wr.left, wr.top, wr.right, wr.bottom),
                    'x': screen_x, 'y': screen_y}
        return True

    def move_window_resize(self, screen_x, screen_y):
        import ctypes
        import webview

        if not self._rs:
            return False
        u = ctypes.windll.user32
        hwnd = int(webview.windows[0].native.Handle.ToInt64())
        rs = self._rs
        dx, dy = screen_x - rs['x'], screen_y - rs['y']
        l, t, r, b = rs['rect']
        d = rs['dir']
        if 'e' in d:
            r += dx
        if 'w' in d:
            l += dx
        if 's' in d:
            b += dy
        if 'n' in d:
            t += dy
        MIN_W, MIN_H = 1000, 680   # 与 create_window 的 min_size 保持一致
        if r - l < MIN_W:
            if 'e' in d and 'w' not in d:
                r = l + MIN_W
            else:
                l = r - MIN_W
        if b - t < MIN_H:
            if 's' in d and 'n' not in d:
                b = t + MIN_H
            else:
                t = b - MIN_H
        u.SetWindowPos(hwnd, 0, l, t, r - l, b - t, 0x0004)   # SWP_NOZORDER
        return True

    def end_window_resize(self):
        self._rs = None
        return True

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


def enable_native_resize(window):
    """为无边框窗口恢复原生边缘缩放（Win32）。

    pywebview 的 frameless 在 Windows 上等价 FormBorderStyle.None，没有缩放边框。
    给 HWND 加回 WS_THICKFRAME（同时保留最大化/最小化盒子以支持 Win+方向 贴靠），
    边缘命中测试即由系统接管：拖动边缘/四角可缩放，且不绘制标题栏。
    """
    import ctypes

    GWL_STYLE = -16
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_FRAMECHANGED = 0x0020

    user32 = ctypes.windll.user32
    get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)

    def apply():
        try:
            hwnd = int(window.native.Handle.ToInt64())
            style = get_style(hwnd, GWL_STYLE)
            style = (style | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX) & ~WS_CAPTION
            set_style(hwnd, GWL_STYLE, style)
            # 通知系统重新计算非客户区（帧生效）
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED)
        except Exception as e:
            # 缩放是增强能力，失败不影响主流程
            print(f"原生边缘缩放启用失败：{e}", flush=True)

    window.events.shown += apply


_wndproc_refs = []   # 持有 WNDPROC 回调引用，防止被垃圾回收导致窗口过程失效


def clamp_maximize_to_work_area(window):
    """让无边框窗口最大化只占工作区（不覆盖任务栏）。

    Win32 对无 WS_CAPTION 样式的窗口，系统默认最大化到整个显示器而非工作区。
    子类化窗口过程拦截 WM_GETMINMAXINFO，把最大化目标改写为窗口所在显示器
    的工作区（rcWork），坐标公式取自微软《自定义窗口框架》官方示例。
    同时拦截 WM_NCCALCSIZE 去掉非客户区（WS_THICKFRAME 的不可见边框否则会让
    内容四周内缩）；最大化时按系统惯例把窗口矩形外扩 frame、客户区内缩 frame，
    与系统的最大化/还原坐标记账一致，避免每轮循环窗口尺寸/位置漂移。
    客户区铺满后系统边缘缩放命中随之失效，故按边框带宽接管 WM_NCHITTEST。
    """
    import ctypes

    GWLP_WNDPROC = -4
    WM_GETMINMAXINFO = 0x0024
    WM_NCCALCSIZE = 0x0083
    WM_NCHITTEST = 0x0084
    HTCLIENT = 1
    HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT = 10, 11, 12, 13
    HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 14, 15, 16, 17
    MONITOR_DEFAULTTONEAREST = 2
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_FRAMECHANGED = 0x0020

    user32 = ctypes.windll.user32
    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    get_long.restype = ctypes.c_ssize_t
    get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
    set_long.restype = ctypes.c_ssize_t
    set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    call_proc = user32.CallWindowProcW
    call_proc.restype = ctypes.c_ssize_t
    call_proc.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                          ctypes.c_size_t, ctypes.c_ssize_t]
    user32.MonitorFromWindow.restype = ctypes.c_void_p
    user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetMonitorInfoW.restype = ctypes.c_int
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MINMAXINFO(ctypes.Structure):
        _fields_ = [("ptReserved", POINT), ("ptMaxSize", POINT),
                    ("ptMaxPosition", POINT), ("ptMinTrackSize", POINT),
                    ("ptMaxTrackSize", POINT)]

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                    ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

    class NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [("rgrc", RECT * 3), ("lppos", ctypes.c_void_p)]

    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p,
                                 ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)

    def apply():
        try:
            hwnd = int(window.native.Handle.ToInt64())
            old_proc = get_long(hwnd, GWLP_WNDPROC)

            # 以窗口自身样式向系统取边框记账口径（最大化/还原坐标补偿用的就是它，
            # 用 GetSystemMetrics 的通用值会与之差 1px 导致还原尺寸漂移）
            user32.AdjustWindowRectEx.restype = ctypes.c_int
            user32.AdjustWindowRectEx.argtypes = [ctypes.POINTER(RECT), ctypes.c_uint,
                                                  ctypes.c_int, ctypes.c_uint]
            adj = RECT()
            user32.AdjustWindowRectEx(ctypes.byref(adj),
                                      get_long(hwnd, GWL_STYLE) & 0xFFFFFFFF,
                                      0, get_long(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF)
            frame = -adj.left

            def is_fullscreen():
                """窗口矩形与所在显示器完全一致即为真全屏（区别于最大化）。"""
                wr = RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(wr))
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
                if mon and user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                    return (wr.left, wr.top, wr.right, wr.bottom) == \
                           (mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom)
                return False

            def proc(h, msg, wp, lp):
                if msg == WM_NCCALCSIZE and wp:
                    if user32.IsZoomed(h):
                        # 最大化时窗口矩形按惯例外扩了 frame，客户区对应内缩
                        ncp = ctypes.cast(lp, ctypes.POINTER(NCCALCSIZE_PARAMS)).contents
                        rc = ncp.rgrc[0]
                        rc.left += frame
                        rc.top += frame
                        rc.right -= frame
                        rc.bottom -= frame
                    return 0   # 其余状态客户区铺满整个窗口，不留非客户区
                if msg == WM_NCHITTEST:
                    res = call_proc(old_proc, h, msg, wp, lp)
                    # 客户区铺满后默认链对边框带返回 HTNOWHERE/HTCLIENT，
                    # 这里按边框带宽自行返回缩放命中码；顶部/右侧命中带避开
                    # 行尾窗口按钮（3×46px、58px 顶栏行），按钮点击优先于缩放
                    if not user32.IsZoomed(h) and not is_fullscreen():
                        wr = RECT()
                        user32.GetWindowRect(h, ctypes.byref(wr))
                        x = ctypes.c_short(lp & 0xFFFF).value
                        y = ctypes.c_short((lp >> 16) & 0xFFFF).value
                        top_h, btn_w = 58, 46 * 3
                        left = x - wr.left < frame
                        right = wr.right - x <= frame and y - wr.top > top_h
                        top = y - wr.top < frame and x < wr.right - btn_w
                        bottom = wr.bottom - y <= frame
                        if left and top:
                            return HTTOPLEFT
                        if left and bottom:
                            return HTBOTTOMLEFT
                        if right and bottom:
                            return HTBOTTOMRIGHT
                        if left:
                            return HTLEFT
                        if right:
                            return HTRIGHT
                        if top:
                            return HTTOP
                        if bottom:
                            return HTBOTTOM
                        # 命中带之外默认链可能给无效值（如窗口按钮外沿），回落客户区
                        if res != HTCLIENT:
                            return HTCLIENT
                    return res
                if msg == WM_GETMINMAXINFO:
                    mi = MONITORINFO()
                    mi.cbSize = ctypes.sizeof(MONITORINFO)
                    mon = user32.MonitorFromWindow(h, MONITOR_DEFAULTTONEAREST)
                    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                        # 先走原逻辑保留最小尺寸等默认值，再按系统惯例写入最大化
                        # 目标：矩形=工作区四周外扩 frame，配合上面 NCCALCSIZE 的
                        # 内缩，可见客户区恰为工作区，且还原坐标不漂移
                        call_proc(old_proc, h, msg, wp, lp)
                        mmi = ctypes.cast(lp, ctypes.POINTER(MINMAXINFO)).contents
                        mmi.ptMaxPosition.x = mi.rcWork.left - mi.rcMonitor.left - frame
                        mmi.ptMaxPosition.y = mi.rcWork.top - mi.rcMonitor.top - frame
                        mmi.ptMaxSize.x = (mi.rcWork.right - mi.rcWork.left) + 2 * frame
                        mmi.ptMaxSize.y = (mi.rcWork.bottom - mi.rcWork.top) + 2 * frame
                        return 0
                return call_proc(old_proc, h, msg, wp, lp)

            callback = WNDPROC(proc)
            _wndproc_refs.append(callback)
            set_long(hwnd, GWLP_WNDPROC, ctypes.cast(callback, ctypes.c_void_p))
            # 强制重发 WM_NCCALCSIZE，让客户区立即按新规则铺满（否则要等下一次状态变化）
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED)
            # 注：WebView2 渲染子窗口跨进程、无法子类化，边缘缩放由前端边缘热区
            # （EdgeResize）经 Bridge 驱动，顶层的 WM_NCHITTEST 仅作兜底。
        except Exception as e:
            # 修正属于增强能力，失败不影响主流程
            print(f"最大化区域修正启用失败：{e}", flush=True)

    window.events.shown += apply


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
    window = webview.create_window(
        "MangaShelf", url,
        width=1280, height=820, min_size=(1000, 680),
        js_api=Bridge(),
        frameless=True,      # 去掉系统标题栏，由前端 TitleBar 组件接管
        easy_drag=False,     # 仅标题栏拖拽区可拖动，避免干扰正文交互
    )
    enable_native_resize(window)   # 无边框下恢复拖边缘缩放
    clamp_maximize_to_work_area(window)   # 最大化只占工作区，不盖任务栏
    webview.start()


if __name__ == "__main__":
    main()
