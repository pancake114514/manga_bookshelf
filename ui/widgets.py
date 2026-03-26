"""
通用 UI 控件 — 浅色纸色主题
"""
from PyQt6.QtWidgets import (
    QLabel, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QFrame, QScrollArea, QSizePolicy, QCheckBox,
    QComboBox, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
    QApplication, QToolButton, QMainWindow
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, QTimer, QPoint
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont, QIcon, QPalette, QPen

# ─── 调色板 ────────────────────────────────────────────────────────────────────
C = {
    "bg":          "#f5f0e8",   # 主背景：暖米白
    "bg2":         "#ede8df",   # 次级背景：稍深米色
    "bg3":         "#e4ddd2",   # 第三级：卡片/分割
    "sidebar":     "#eae4d8",   # 侧边栏背景
    "topbar":      "#e8e2d6",   # 顶栏背景
    "border":      "#c8bfaa",   # 通用边框
    "border2":     "#b0a590",   # 深边框
    "text":        "#2a2418",   # 主文字：深墨
    "text2":       "#5a5040",   # 次级文字
    "text3":       "#8a7f6a",   # 弱文字
    "accent":      "#6b3a2a",   # 主强调色：深赭红
    "accent2":     "#8b4a35",   # 悬停强调
    "accent_bg":   "#f0e6e0",   # 强调背景
    "accent_bd":   "#c4856a",   # 强调边框
    "blue":        "#2a4a6b",   # 辅助蓝（标签等）
    "green":       "#2a5a3a",   # 辅助绿
    "scroll":      "#c8bfaa",   # 滚动条
    "scroll_h":    "#a09080",   # 滚动条悬停
    "sel":         "#d8cfc0",   # 选中背景
    "titlebar":    "#ddd6c8",   # 标题栏
    "titlebar_btn":"#c8bfaa",   # 标题栏按钮
    "close_hover": "#c0392b",   # 关闭按钮悬停
}

STYLE_MAIN = f"""
QWidget {{
    background-color: {C['bg']};
    color: {C['text']};
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QScrollBar:vertical {{
    background: {C['bg2']};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['scroll']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {C['scroll_h']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {C['bg2']};
    height: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {C['scroll']};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {C['scroll_h']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QPushButton {{
    background-color: {C['bg2']};
    color: {C['text']};
    border: 1px solid {C['border']};
    border-radius: 5px;
    padding: 5px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {C['bg3']};
    border-color: {C['border2']};
}}
QPushButton:pressed {{ background-color: {C['sel']}; }}
QPushButton#accent {{
    background-color: {C['accent']};
    border-color: {C['accent2']};
    color: #f5ede8;
}}
QPushButton#accent:hover {{ background-color: {C['accent2']}; }}

QLineEdit {{
    background-color: #ffffff;
    border: 1px solid {C['border']};
    border-radius: 5px;
    padding: 5px 10px;
    color: {C['text']};
    selection-background-color: {C['sel']};
}}
QLineEdit:focus {{ border-color: {C['accent_bd']}; }}

QCheckBox {{
    color: {C['text2']};
    spacing: 6px;
}}

QComboBox {{
    background-color: #ffffff;
    border: 1px solid {C['border']};
    border-radius: 5px;
    padding: 5px 10px;
    color: {C['text']};
}}
QComboBox:hover {{ border-color: {C['border2']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background-color: #ffffff;
    border: 1px solid {C['border']};
    selection-background-color: {C['sel']};
    color: {C['text']};
}}

QListWidget {{
    background-color: #ffffff;
    border: 1px solid {C['border']};
    border-radius: 5px;
    color: {C['text']};
}}
QListWidget::item {{ padding: 4px 8px; border-radius: 3px; }}
QListWidget::item:hover {{ background: {C['bg2']}; }}
QListWidget::item:selected {{ background: {C['sel']}; color: {C['text']}; }}

QFrame#sidebar {{
    background-color: {C['sidebar']};
    border-right: 1px solid {C['border']};
}}
QFrame#topbar {{
    background-color: {C['topbar']};
    border-bottom: 1px solid {C['border']};
}}

QDialog {{
    background-color: {C['bg']};
}}
QDialogButtonBox QPushButton {{
    min-width: 80px;
}}
QMenu {{
    background-color: {C['bg']};
    border: 1px solid {C['border']};
    border-radius: 6px;
    padding: 4px;
    color: {C['text']};
}}
QMenu::item {{ padding: 7px 20px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C['sel']}; }}
QMenu::separator {{ background: {C['border']}; height: 1px; margin: 4px 8px; }}
"""


# ─── 自定义标题栏 ──────────────────────────────────────────────────────────────

class TitleBar(QWidget):
    """可拖动的自定义标题栏，含最小化/最大化/关闭按钮"""

    def __init__(self, parent: QWidget, title: str = "", icon: str = ""):
        super().__init__(parent)
        self._win = parent
        self._drag_pos = None
        self._maximized = False
        self.setFixedHeight(36)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._build(title, icon)

    def _build(self, title: str, icon: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 6, 0)
        layout.setSpacing(0)

        # 应用图标 + 标题（衬线字体）
        if icon:
            ico = QLabel(icon)
            ico.setStyleSheet(f"color: {C['accent']}; font-size: 14px; background: transparent;")
            ico.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
            layout.addWidget(ico)
            layout.addSpacing(6)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(
            f"color: {C['text2']}; font-family: 'Georgia', 'Times New Roman', serif;"
            f"font-size: 13px; font-weight: 600; background: transparent; letter-spacing: 0.5px;"
        )
        self.title_lbl.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        layout.addWidget(self.title_lbl)
        layout.addStretch()

        # 窗口控制按钮
        for sym, tip, cb, obj_name in [
            ("─", "最小化", self._minimize, "tb_min"),
            ("□", "最大化", self._toggle_max, "tb_max"),
            ("✕", "关闭",   self._close,    "tb_close"),
        ]:
            btn = QPushButton(sym)
            btn.setObjectName(obj_name)
            btn.setToolTip(tip)
            btn.setFixedSize(36, 36)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: {C['text3']};
                    font-size: 13px;
                    border-radius: 0;
                    padding: 0;
                }}
                QPushButton:hover {{
                    background: {C['bg3']};
                    color: {C['text']};
                }}
                QPushButton#tb_close:hover {{
                    background: {C['close_hover']};
                    color: #ffffff;
                }}
            """)
            btn.clicked.connect(cb)
            layout.addWidget(btn)

    def set_title(self, title: str):
        self.title_lbl.setText(title)

    def _minimize(self):
        self._win.showMinimized()

    def _toggle_max(self):
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()

    def _close(self):
        self._win.close()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C['titlebar']))
        # 底部细线
        p.setPen(QPen(QColor(C['border']), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            if self._win.isMaximized():
                self._win.showNormal()
                self._drag_pos = QPoint(self._win.width() // 2, self.height() // 2)
            self._win.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()


class FramelessMixin:
    """
    混入类：去掉系统边框，插入自定义标题栏。
    用法：class MyWindow(FramelessMixin, QMainWindow): ...
    在 __init__ 末尾调用 self.setup_frameless(title, icon)
    """
    def setup_frameless(self, title: str = "", icon: str = "📚"):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        # 保留任务栏显示
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # 在 central widget 外层包一个容器，把标题栏插在最顶部
        if isinstance(self, QMainWindow):
            container = QWidget()
            container.setStyleSheet(f"background: {C['bg']};")
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(0, 0, 0, 0)
            vbox.setSpacing(0)
            self._titlebar = TitleBar(self, title, icon)
            vbox.addWidget(self._titlebar)
            # 把原 central widget 移过来
            old = self.centralWidget()
            if old:
                vbox.addWidget(old)
            self.setCentralWidget(container)
        else:
            # QDialog 等：在已有 layout 前插入标题栏
            layout = self.layout()
            if layout:
                self._titlebar = TitleBar(self, title, icon)
                layout.insertWidget(0, self._titlebar)
                layout.setContentsMargins(0, 0, 0, 0)

    def update_title(self, title: str):
        if hasattr(self, "_titlebar"):
            self._titlebar.set_title(title)


class FramelessDialog(QDialog):
    """无边框对话框基类，自带自定义标题栏"""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Dialog
        )
        self._drag_pos = None
        self._dialog_title = title
        # 子类在 _build() 后调用 _install_titlebar()

    def _install_titlebar(self, icon: str = ""):
        layout = self.layout()
        if layout:
            tb = TitleBar(self, self._dialog_title, icon)
            layout.insertWidget(0, tb)
            layout.setContentsMargins(0, 0, 0, 12)


# ─── 工具函数 ──────────────────────────────────────────────────────────────────

def make_placeholder_pixmap(width: int, height: int,
                             text: str = "", color: str = None) -> QPixmap:
    bg = color or C['bg3']
    pm = QPixmap(width, height)
    pm.fill(QColor(bg))
    if text:
        painter = QPainter(pm)
        painter.setPen(QColor(C['text3']))
        font = painter.font()
        font.setPointSize(16)
        painter.setFont(font)
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
    return pm


# ─── 通用控件 ──────────────────────────────────────────────────────────────────

class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    right_clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class TagBadge(QLabel):
    COLORS = {
        "work":      ("#e8ddd0", "#6b3a2a"),
        "author":    ("#d8e4ee", "#2a4a6b"),
        "character": ("#d8eee0", "#2a5a3a"),
        "cm":        ("#eee8d0", "#6b5a2a"),
        "r18":       ("#f0d8d8", "#8b2a2a"),
        "censored":  ("#e8e8d8", "#5a5a2a"),
    }

    def __init__(self, text: str, category: str = "", parent=None):
        super().__init__(text, parent)
        bg, fg = self.COLORS.get(category, (C['bg3'], C['text2']))
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {fg}60;
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 11px;
                font-family: "Georgia", "Times New Roman", "Microsoft YaHei UI", serif;
            }}
        """)
        self.setFixedHeight(20)


class TagFlowWidget(QWidget):
    def __init__(self, tags: dict, parent=None):
        super().__init__(parent)
        self._tags = tags
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        from config import TAG_CATEGORIES, TAG_CATEGORY_ORDER
        for cat in TAG_CATEGORY_ORDER:
            vals = self._tags.get(cat)
            if not vals:
                continue
            if cat == "r18":
                if vals:
                    layout.addWidget(TagBadge("R-18", "r18"))
            elif isinstance(vals, list):
                for v in vals:
                    layout.addWidget(TagBadge(v, cat))
            else:
                layout.addWidget(TagBadge(str(vals), cat))
        layout.addStretch()


class SectionLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setObjectName("section_title")
        self.setStyleSheet(f"""
            color: {C['text3']};
            font-size: 10px;
            font-weight: 700;
            font-family: "Georgia", "Times New Roman", serif;
            letter-spacing: 2px;
            padding: 4px 0;
        """)


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(
            f"color: {C['border']}; background: {C['border']}; border: none; max-height: 1px;"
        )


class LoadingLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__("加载中…", parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"color: {C['text3']}; font-size: 14px;")