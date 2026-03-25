"""
图片阅览界面 - 漫画阅读器
进度条从右向左增长（右侧=起始），点击左1/3翻到下一页，右1/3翻到上一页
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSizePolicy, QShortcut, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRect, QPoint, QTimer
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QFont, QKeySequence,
    QPen, QBrush, QLinearGradient, QRadialGradient
)
from config import app_state, SUPPORTED_FORMATS


class MangaProgressBar(QWidget):
    """
    自定义进度条：
    - 从右向左增长（右侧=第一页）
    - 滑块为圆形
    - 深色渐变风格
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

        pad = 20
        bar_y = self.height() // 2
        bar_h = 4
        w = self.width() - 2 * pad

        # 轨道背景
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1e1c2a"))
        painter.drawRoundedRect(pad, bar_y - bar_h // 2, w, bar_h, 2, 2)

        # 已读进度（右侧起点 → 当前位置）
        if self._maximum > 0:
            ratio = self._value / self._maximum
            filled_w = int(w * ratio)
            # 右侧开始填充
            grad = QLinearGradient(self.width() - pad, 0, self.width() - pad - filled_w, 0)
            grad.setColorAt(0, QColor("#9a7adb"))
            grad.setColorAt(1, QColor("#5c3f8a"))
            painter.setBrush(grad)
            painter.drawRoundedRect(
                self.width() - pad - filled_w,
                bar_y - bar_h // 2,
                filled_w, bar_h, 2, 2
            )

        # 圆形滑块
        if self._maximum > 0:
            ratio = self._value / self._maximum
            knob_x = self.width() - pad - int(w * ratio)
        else:
            knob_x = self.width() - pad
        knob_r = 8

        # 外发光
        glow = QRadialGradient(knob_x, bar_y, knob_r * 2)
        glow.setColorAt(0, QColor(154, 122, 219, 80))
        glow.setColorAt(1, QColor(154, 122, 219, 0))
        painter.setBrush(glow)
        painter.drawEllipse(QPoint(knob_x, bar_y), knob_r * 2, knob_r * 2)

        # 主体
        painter.setBrush(QColor("#c8a8f8"))
        painter.setPen(QPen(QColor("#7a5aab"), 1.5))
        painter.drawEllipse(QPoint(knob_x, bar_y), knob_r, knob_r)

        # 页码文字
        painter.setPen(QColor("#7a6aab"))
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        text = f"{self._value + 1} / {self._maximum + 1}"
        painter.drawText(QRect(0, 0, self.width(), self.height()),
                         Qt.AlignmentFlag.AlignCenter, text)
        painter.end()

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


class ImageViewer(QWidget):
    """
    图片阅览主界面
    """
    back_requested = pyqtSignal()

    def __init__(self, obj: dict, images: list, start_index: int = 0, parent=None):
        super().__init__(parent)
        self.obj = obj
        self.images = images   # list of image dicts from db
        self._current = max(0, min(start_index, len(images) - 1))
        self._pixmap_cache: dict[int, QPixmap] = {}
        self._build()
        self._go_to(self._current)
        self._setup_shortcuts()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setStyleSheet("background: #08070f;")

        # ── 顶部栏 ────────────────────────────────────────────────────────────
        top = QWidget()
        top.setFixedHeight(44)
        top.setStyleSheet("background: rgba(10,9,20,0.95); border-bottom: 1px solid #1a1828;")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(12, 0, 12, 0)
        top_layout.setSpacing(12)

        back_btn = QPushButton("◀ 返回")
        back_btn.setFixedWidth(72)
        back_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: 1px solid #2a2540;
                border-radius: 5px; color: #7a6aab; font-size: 12px; padding: 4px 8px;
            }
            QPushButton:hover { border-color: #5c3f8a; color: #c8b8e8; }
        """)
        back_btn.clicked.connect(self._on_back)
        top_layout.addWidget(back_btn)

        self.title_lbl = QLabel(self.obj["name"])
        self.title_lbl.setStyleSheet("color: #c8b8e8; font-size: 13px; font-weight: 600;")
        top_layout.addWidget(self.title_lbl)
        top_layout.addStretch()

        self.filename_lbl = QLabel()
        self.filename_lbl.setStyleSheet("color: #4a4070; font-size: 11px;")
        top_layout.addWidget(self.filename_lbl)

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
        bottom.setStyleSheet("""
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 transparent, stop:1 rgba(8,7,15,0.98));
        """)
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

    def _go_to(self, idx: int):
        if not self.images:
            return
        idx = max(0, min(idx, len(self.images) - 1))
        self._current = idx

        # 加载图片
        pm = self._load_pixmap(idx)
        self.image_area.set_pixmap(pm)
        self.progress_bar.set_value(idx)

        img = self.images[idx]
        self.filename_lbl.setText(img["filename"])

        # 保存阅读进度
        app_state.db.update_last_read(self.obj["id"], idx)
        self.obj["last_read_idx"] = idx

        # 预加载相邻图片
        QTimer.singleShot(100, lambda: self._preload(idx))

    def _load_pixmap(self, idx: int) -> QPixmap | None:
        if idx in self._pixmap_cache:
            return self._pixmap_cache[idx]
        img = self.images[idx]
        path = img["filepath"]
        if os.path.isfile(path):
            pm = QPixmap(path)
            self._pixmap_cache[idx] = pm
            # 控制缓存大小
            if len(self._pixmap_cache) > 10:
                oldest = min(k for k in self._pixmap_cache if k != idx)
                del self._pixmap_cache[oldest]
            return pm
        return None

    def _preload(self, idx: int):
        for offset in [1, -1, 2, -2]:
            nidx = idx + offset
            if 0 <= nidx < len(self.images) and nidx not in self._pixmap_cache:
                self._load_pixmap(nidx)

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
        self.setStyleSheet("background: #08070f;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_pixmap(self, pm: QPixmap | None):
        self._pixmap = pm
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#08070f"))
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
            painter.setPen(QColor("#2a2540"))
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
