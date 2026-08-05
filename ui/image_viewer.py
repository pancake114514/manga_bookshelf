"""
图片阅览界面 - 漫画阅读器
进度条从右向左增长（右侧=起始），点击左1/3翻到下一页，右1/3翻到上一页
"""
import os
import time
from collections import deque
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRect, QPoint, QTimer, QThread
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QFont, QKeySequence, QShortcut,
    QPen, QBrush, QLinearGradient, QRadialGradient, QImage
)
from config import SUPPORTED_FORMATS
# from .widgets import C

# ─── 看图界面深色主题颜色 ───────────────────────────────────────────────────
C = {
    "bg":        "#f5f0e8",   # 主背景：暖米白
    "bg2":       "#ede8df",   # 次级背景：稍深米色
    "track":     "#29251C",   # 进度条轨道
    "accent":    "#F7D9BA",   # 主强调色
    "accent2":   "#F6A452",   # 强调深色
    "knob":      "#CC9933",   # 滑块主体
    "knob_bd":   "#ECECBD",   # 滑块边框
    "text":      "#2a2418",   # 主文字：深墨
    "text2":     "#5a5040",   # 次级文字
    "text3":     "#8a7f6a",   # 弱文字
    "border":    "#c4856a",   # 边框
    "border_h":  "#c4856a",   # 边框悬停
}


class MangaProgressBar(QWidget):
    """
    自定义进度条：
    - 从右向左增长（右侧=第一页）
    - 滑块为圆形
    - 扁平化纯色风格，背景 #DDD6C8
    """
    value_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._maximum = 100
        self._dragging = False
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def set_range(self, maximum: int):
        self._maximum = max(1, maximum)
        self.update()

    def set_value(self, value: int):
        self._value = max(0, min(value, self._maximum))
        self.update()

    def value(self) -> int:
        return self._value

    def _pos_to_value(self, x: int) -> int:
        pad = 20
        w = self.width() - 2 * pad
        if w <= 0:
            return 0
        # 从右向左：x越大 value越小
        ratio = (self.width() - pad - x) / w
        ratio = max(0.0, min(1.0, ratio))
        return round(ratio * self._maximum)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # --- 1. 绘制整体背景 ---
        painter.fillRect(self.rect(), QColor("transparent"))

        pad = 20
        bar_y = self.height() // 2
        bar_h = 4
        w = self.width() - 2 * pad

        # --- 2. 轨道背景 (未读部分) ---
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#C4BCAD"))  # 稍深一点的底色作为轨道
        painter.drawRoundedRect(pad, bar_y - bar_h // 2, w, bar_h, 2, 2)

        # --- 3. 已读进度 (右侧起点 → 当前位置) ---
        if self._maximum > 0:
            ratio = self._value / self._maximum
            filled_w = int(w * ratio)

            # 【修改点】移除线性渐变，改用纯色填充 (深咖啡色，与背景契合)
            painter.setBrush(QColor("#6A5C4D"))
            painter.drawRoundedRect(
                self.width() - pad - filled_w,
                bar_y - bar_h // 2,
                filled_w, bar_h, 2, 2
            )

        # --- 4. 圆形滑块 ---
        if self._maximum > 0:
            ratio = self._value / self._maximum
            knob_x = self.width() - pad - int(w * ratio)
        else:
            knob_x = self.width() - pad

        knob_r = 8

        # 【修改点】移除外发光渐变，直接绘制扁平化圆形滑块
        painter.setBrush(QColor("#F4EFE6"))  # 滑块内部颜色（亮米色）
        painter.setPen(QPen(QColor("#6A5C4D"), 2.0))  # 滑块边框颜色（同进度条颜色）
        painter.drawEllipse(QPoint(knob_x, bar_y), knob_r, knob_r)

        # --- 5. 页码文字 ---
        # 设置字体颜色与滑块边框一致，保持整体视觉统一
        painter.setPen(QColor("#4A3F35"))
        font = painter.font()
        font.setPointSize(9)
        # font.setBold(True) # 如果觉得文字不够清晰可以取消这行的注释
        painter.setFont(font)
        text = f"{self._value + 1} / {self._maximum + 1}"
        text_offset_y = 15  # 向下偏移的像素，可自行微调
        text_rect = self.rect().adjusted(
            0,
            text_offset_y,
            0,
            text_offset_y
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignCenter,
            text
        )
        painter.end()

    # --- 鼠标事件保持不变 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            v = self._pos_to_value(event.position().toPoint().x())
            self.set_value(v)
            self.value_changed.emit(v)

    def mouseMoveEvent(self, event):
        if self._dragging:
            v = self._pos_to_value(event.position().toPoint().x())
            self.set_value(v)
            self.value_changed.emit(v)

    def mouseReleaseEvent(self, event):
        self._dragging = False

class ImageLoaderThread(QThread):
    """后台图片解码线程。

    QPixmap 只能在 GUI 线程使用，因此后台线程用 QImage 解码，
    信号传回 GUI 线程后再转 QPixmap。快速翻页时丢弃最旧任务。
    """
    loaded = pyqtSignal(int, object)   # idx, QImage

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: deque = deque()
        self._running = True

    def load(self, idx: int, path: str):
        self._tasks.append((idx, path))
        while len(self._tasks) > 6:
            self._tasks.popleft()

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            if not self._tasks:
                time.sleep(0.02)
                continue
            idx, path = self._tasks.popleft()
            if not self._running:
                break
            img = QImage(path)
            if not img.isNull():
                self.loaded.emit(idx, img)


class ImageViewer(QWidget):
    """
    图片阅览主界面
    """
    back_requested = pyqtSignal()

    def __init__(self, svc, obj: dict, images: list, start_index: int = 0, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.obj = obj
        self.images = images   # list of image dicts from db
        self._current = max(0, min(start_index, len(images) - 1))
        self._pixmap_cache: dict[int, QPixmap] = {}
        # 阅读进度落库节流：连续翻页时合并为一次写
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_last_read)
        # 预加载定时器（成员持有，销毁时停止，避免 singleShot lambda 访问已销毁对象）
        self._preload_timer = QTimer(self)
        self._preload_timer.setSingleShot(True)
        self._preload_timer.timeout.connect(self._on_preload_timeout)
        self._loader = ImageLoaderThread()
        self._loader.loaded.connect(self._on_image_loaded)
        self._loader.start()
        self.destroyed.connect(self._on_destroyed)
        self._build()
        self._go_to(self._current)
        self._setup_shortcuts()

    def _on_preload_timeout(self):
        self._preload(self._current)

    def _flush_last_read(self):
        """把缓存的阅读进度写入 DB。"""
        if self.obj.get("last_read_idx") is not None:
            self.svc.update_last_read(self.obj["id"], self.obj["last_read_idx"])

    def _on_destroyed(self):
        self._flush_last_read()
        self._save_timer.stop()
        self._preload_timer.stop()
        self._loader.stop()
        self._loader.wait(500)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setStyleSheet(f"background: {C['bg']};")

        # ── 顶部栏 ────────────────────────────────────────────────────────────
        top = QWidget()
        top.setFixedHeight(44)
        top.setStyleSheet(f"background: {C['bg']}; border-bottom: 1px solid {C['bg2']};")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(12, 0, 12, 0)
        top_layout.setSpacing(12)

        back_btn = QPushButton("◀ 返回")
        back_btn.setFixedWidth(72)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {C['border']};
                border-radius: 5px; color: {C['text2']}; font-size: 12px; padding: 4px 8px;
            }}
            QPushButton:hover {{ border-color: {C['border_h']}; color: {C['text']}; }}
        """)
        back_btn.clicked.connect(self._on_back)
        top_layout.addWidget(back_btn)

        self.title_lbl = QLabel(self.obj["name"])
        self.title_lbl.setStyleSheet(f"color: {C['text']}; font-size: 13px; font-weight: 600;")
        top_layout.addWidget(self.title_lbl)
        top_layout.addStretch()

        self.filename_lbl = QLabel()
        self.filename_lbl.setStyleSheet(f"color: {C['text3']}; font-size: 11px;")
        top_layout.addWidget(self.filename_lbl)

        fullscreen_btn = QPushButton("⛶ 全屏")
        fullscreen_btn.setFixedHeight(28)
        fullscreen_btn.setMinimumWidth(72)

        fullscreen_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {C['border']};
                border-radius: 5px; color: {C['text2']}; font-size: 12px; padding: 4px 8px;
            }}
            QPushButton:hover {{ border-color: {C['border_h']}; color: {C['text']}; }}
        """)
        fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        top_layout.addWidget(fullscreen_btn)

        layout.addWidget(top)

        # ── 图片显示区域（可点击） ────────────────────────────────────────────
        self.image_area = _ClickableImageArea(self)
        self.image_area.left_clicked.connect(self._next_page)
        self.image_area.right_clicked.connect(self._prev_page)
        self.image_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.image_area)

        # ── 进度条区域 ────────────────────────────────────────────────────────
        bottom = QWidget()
        bottom.setFixedHeight(56)
        bottom.setStyleSheet(f"background-color: {C['bg2']};")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(24, 4, 24, 8)

        self.progress_bar = MangaProgressBar()
        if self.images:
            self.progress_bar.set_range(len(self.images) - 1)
        self.progress_bar.value_changed.connect(self._on_seek)
        bottom_layout.addWidget(self.progress_bar)

        layout.addWidget(bottom)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Left), self).activated.connect(self._next_page)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self).activated.connect(self._prev_page)
        QShortcut(QKeySequence(Qt.Key.Key_Up), self).activated.connect(self._prev_page)
        QShortcut(QKeySequence(Qt.Key.Key_Down), self).activated.connect(self._next_page)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self._on_back)
        QShortcut(QKeySequence(Qt.Key.Key_F11), self).activated.connect(self._toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_F), self).activated.connect(self._toggle_fullscreen)

    def _toggle_fullscreen(self):
        """切换全屏/窗口模式（F 或 F11）"""
        parent = self.window()
        if parent.isFullScreen():
            parent.showNormal()
        else:
            parent.showFullScreen()

    def wheelEvent(self, event):
        """鼠标滚轮翻页"""
        delta = event.angleDelta().y()
        if delta < 0:
            self._next_page()
        elif delta > 0:
            self._prev_page()

    def _go_to(self, idx: int):
        if not self.images:
            return
        idx = max(0, min(idx, len(self.images) - 1))
        self._current = idx

        # 异步加载图片（缓存命中则立即显示）
        self._request_pixmap(idx)
        self.progress_bar.set_value(idx)

        img = self.images[idx]
        self.filename_lbl.setText(img["filename"])

        # 保存阅读进度（节流合并，避免每翻一页同步写一次 DB）
        self.obj["last_read_idx"] = idx
        self._save_timer.start(400)

        # 预加载相邻图片（用成员 timer，销毁时停止）
        self._preload_timer.start(100)

    def _request_pixmap(self, idx: int):
        """请求加载第 idx 张图：命中缓存立即显示，否则交给后台线程。"""
        if idx in self._pixmap_cache:
            self.image_area.set_pixmap(self._pixmap_cache[idx])
            return
        img = self.images[idx]
        path = img["filepath"]
        if os.path.isfile(path):
            self._loader.load(idx, path)
        else:
            self.image_area.set_pixmap(None)

    def _on_image_loaded(self, idx: int, image):
        pm = QPixmap.fromImage(image)
        self._pixmap_cache[idx] = pm
        # 控制缓存大小
        if len(self._pixmap_cache) > 10:
            oldest = min(k for k in self._pixmap_cache if k != self._current)
            del self._pixmap_cache[oldest]
        if idx == self._current:
            self.image_area.set_pixmap(pm)

    def _preload(self, idx: int):
        for offset in [1, -1, 2, -2]:
            nidx = idx + offset
            if 0 <= nidx < len(self.images) and nidx not in self._pixmap_cache:
                self._request_pixmap(nidx)

    def _next_page(self):
        """下一页（下一张图片）"""
        if self._current < len(self.images) - 1:
            self._go_to(self._current + 1)

    def _prev_page(self):
        """上一页（上一张图片）"""
        if self._current > 0:
            self._go_to(self._current - 1)

    def _on_seek(self, value: int):
        self._go_to(value)

    def _on_back(self):
        self._save_timer.stop()
        self._flush_last_read()
        self.back_requested.emit()


class _ClickableImageArea(QWidget):
    """
    图片显示区域
    点击左侧1/3 → next_page
    点击右侧1/3 → prev_page
    中间1/3无动作（或可扩展为显示菜单）
    """
    left_clicked = pyqtSignal()
    right_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self.setStyleSheet(f"background: {C['bg']};")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_pixmap(self, pm: QPixmap | None):
        self._pixmap = pm
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(C["bg"]))
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor(C["border"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "图片加载失败")
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            x = event.position().toPoint().x()
            w3 = self.width() // 3
            if x < w3:
                self.left_clicked.emit()   # 左1/3 → 下一页
            elif x > 2 * w3:
                self.right_clicked.emit()  # 右1/3 → 上一页

    def mouseDoubleClickEvent(self, event):
        pass  # 防止双击触发两次