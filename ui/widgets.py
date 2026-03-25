"""
通用 UI 控件
"""
from PyQt6.QtWidgets import (
    QLabel, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QFrame, QScrollArea, QSizePolicy, QCheckBox,
    QComboBox, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
    QApplication, QToolButton
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, pyqtSlot, QTimer
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont, QIcon, QPalette

# ─── 主题色定义 ────────────────────────────────────────────────────────────────
STYLE_MAIN = """
QWidget {
    background-color: #12111a;
    color: #e8e0f0;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}
QScrollBar:vertical {
    background: #1e1c2a;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #4a3f6b;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #7a6aab; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #1e1c2a;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #4a3f6b;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #7a6aab; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QPushButton {
    background-color: #2a2540;
    color: #c8b8e8;
    border: 1px solid #4a3f6b;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #3a3060;
    border-color: #8a7abb;
    color: #f0e8ff;
}
QPushButton:pressed { background-color: #1a1530; }
QPushButton#accent {
    background-color: #5c3f8a;
    border-color: #9a7adb;
    color: #f0e8ff;
}
QPushButton#accent:hover { background-color: #7a55aa; }

QLineEdit {
    background-color: #1e1c2a;
    border: 1px solid #3a3060;
    border-radius: 6px;
    padding: 6px 10px;
    color: #e8e0f0;
    selection-background-color: #5c3f8a;
}
QLineEdit:focus { border-color: #8a7abb; }
QLineEdit::placeholder { color: #5a5070; }

QCheckBox {
    color: #c8b8e8;
    spacing: 6px;
}

QComboBox {
    background-color: #1e1c2a;
    border: 1px solid #3a3060;
    border-radius: 6px;
    padding: 5px 10px;
    color: #e8e0f0;
}
QComboBox:hover { border-color: #6a5aab; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background-color: #1e1c2a;
    border: 1px solid #4a3f6b;
    selection-background-color: #3a2d60;
    color: #e8e0f0;
}

QListWidget {
    background-color: #1a1828;
    border: 1px solid #2a2540;
    border-radius: 6px;
    color: #c8b8e8;
}
QListWidget::item { padding: 4px 8px; border-radius: 4px; }
QListWidget::item:hover { background: #2a2540; }
QListWidget::item:selected { background: #3a2d60; color: #f0e8ff; }

QLabel#section_title {
    color: #9a8abb;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
}

QFrame#sidebar {
    background-color: #0e0d18;
    border-right: 1px solid #2a2540;
}
QFrame#topbar {
    background-color: #0e0d18;
    border-bottom: 1px solid #2a2540;
}

QDialog {
    background-color: #12111a;
}
QDialogButtonBox QPushButton {
    min-width: 80px;
}
"""


def make_placeholder_pixmap(width: int, height: int,
                             text: str = "", color: str = "#2a2540") -> QPixmap:
    """生成占位图（纯色+文字）"""
    pm = QPixmap(width, height)
    pm.fill(QColor(color))
    if text:
        painter = QPainter(pm)
        painter.setPen(QColor("#5a5070"))
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
    return pm


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
    """单个标签徽章"""
    COLORS = {
        "work":      ("#2a1f4a", "#7a6aab"),
        "author":    ("#1f2a3a", "#5a8aab"),
        "character": ("#1f3a2a", "#5aab7a"),
        "cm":        ("#3a2a1f", "#ab8a5a"),
        "r18":       ("#3a1f1f", "#ab5a5a"),
        "censored":  ("#2a2a1f", "#8a8a5a"),
    }

    def __init__(self, text: str, category: str = "", parent=None):
        super().__init__(text, parent)
        bg, fg = self.COLORS.get(category, ("#2a2540", "#8a7abb"))
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {fg}55;
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 11px;
            }}
        """)
        self.setFixedHeight(20)


class TagFlowWidget(QWidget):
    """流式布局展示标签列表"""
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
        self.setStyleSheet("""
            color: #6a5a8a; font-size: 10px; font-weight: 700;
            letter-spacing: 2px; padding: 4px 0;
        """)


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet("color: #2a2540; background: #2a2540; border: none; max-height: 1px;")


class LoadingLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__("加载中…", parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("color: #5a5070; font-size: 14px;")