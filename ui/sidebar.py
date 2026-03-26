"""
侧边栏 - 标签筛选 + R18 开关
所有交互控件均为自绘，完全绕开 PyQt6/Windows/Fusion 的样式表渲染问题
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea,
    QFrame, QPushButton, QHBoxLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QRectF, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath
from config import app_state, TAG_CATEGORIES, TAG_CATEGORY_ORDER
from .widgets import C
from .widgets import SectionLabel, Divider


class CheckBox(QWidget):
    stateChanged = pyqtSignal(bool)

    BOX = 15
    RADIUS = 3
    H = 24

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._checked = False
        self._hovered = False
        self._text = text
        self.setFixedHeight(self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, val: bool, emit: bool = True):
        if self._checked == val:
            return
        self._checked = val
        self.update()
        if emit:
            self.stateChanged.emit(val)

    def text(self) -> str:
        return self._text

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        bx = 0
        by = (rect.height() - self.BOX) // 2
        box_rect = QRectF(bx, by, self.BOX, self.BOX)

        if self._checked:
            p.setPen(QPen(QColor(C['accent_bd']), 1))
            p.setBrush(QColor(C['accent']))
            p.drawRoundedRect(box_rect, self.RADIUS, self.RADIUS)

            p.setBrush(Qt.BrushStyle.NoBrush)
            tick_pen = QPen(QColor("#f5ede8"), 2, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(tick_pen)
            path = QPainterPath()
            path.moveTo(bx + self.BOX * 0.2, by + self.BOX * 0.5)
            path.lineTo(bx + self.BOX * 0.45, by + self.BOX * 0.75)
            path.lineTo(bx + self.BOX * 0.8, by + self.BOX * 0.25)
            p.drawPath(path)
        else:
            border_color = C['border2'] if self._hovered else C['border']
            p.setPen(QPen(QColor(border_color), 1))
            p.setBrush(QColor("#ffffff"))
            p.drawRoundedRect(box_rect, self.RADIUS, self.RADIUS)

        if self._text:
            text_color = C['text'] if self._checked else (
                C['text2'] if self._hovered else C['text3']
            )
            p.setPen(QColor(text_color))
            p.setFont(QFont("Microsoft YaHei UI", 10))
            text_rect = rect.adjusted(self.BOX + 8, 0, 0, 0)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()


class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    W = 36
    H = 20
    KNOB_R = 8
    PAD = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._hovered = False
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, val: bool, emit: bool = True):
        if self._checked == val:
            return
        self._checked = val
        self.update()
        if emit:
            self.toggled.emit(val)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        track_color = C['accent'] if self._checked else C['bg3']
        if self._hovered:
            track_color = C['accent2'] if self._checked else C['border']
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(track_color))
        p.drawRoundedRect(0, 0, self.W, self.H, self.H // 2, self.H // 2)

        kx = self.W - self.PAD - self.KNOB_R * 2 if self._checked else self.PAD
        ky = (self.H - self.KNOB_R * 2) // 2
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(kx, ky, self.KNOB_R * 2, self.KNOB_R * 2)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()


class TagFilterGroup(QWidget):
    filter_changed = pyqtSignal()

    def __init__(self, category: str, label: str, parent=None):
        super().__init__(parent)
        self.category = category
        self._checkboxes: dict[str, CheckBox] = {}
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(SectionLabel(label))

        self.items_layout = QVBoxLayout()
        self.items_layout.setSpacing(2)
        layout.addLayout(self.items_layout)

    def populate(self, values: list[str]):
        current_selected = self.get_selected()

        existing_tags = list(self._checkboxes.keys())
        if set(existing_tags) == set(values):
            return

        for cb in self._checkboxes.values():
            cb.setParent(None)
            cb.deleteLater()
        self._checkboxes.clear()

        for v in values:
            cb = CheckBox(v)
            if v in current_selected:
                cb.setChecked(True, emit=False)
            cb.stateChanged.connect(lambda _: self.filter_changed.emit())
            self.items_layout.addWidget(cb)
            self._checkboxes[v] = cb

    def get_selected(self) -> list[str]:
        return [v for v, cb in self._checkboxes.items() if cb.isChecked()]

    def clear_all(self):
        for cb in self._checkboxes.values():
            cb.setChecked(False, emit=False)
        self.update()


class SidebarWidget(QFrame):
    filter_changed = pyqtSignal()
    r18_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._groups: dict[str, TagFilterGroup] = {}
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(8)

        logo = QLabel("MangaShelf")
        logo.setStyleSheet(
            f"color: {C['accent']}; font-size: 16px; font-weight: 700;"
            f"font-family: 'Georgia', 'Times New Roman', serif;"
            f"letter-spacing: 1px; padding-bottom: 4px;"
        )
        layout.addWidget(logo)
        layout.addWidget(Divider())

        r18_row = QHBoxLayout()
        r18_row.setSpacing(8)
        r18_lbl = QLabel("显示 R-18")
        r18_lbl.setStyleSheet(f"color: #8b2a2a; font-size: 14px; font-weight: 600;")
        r18_row.addWidget(r18_lbl)
        r18_row.addStretch()
        self.r18_switch = ToggleSwitch()
        self.r18_switch.toggled.connect(self._on_r18_changed)
        r18_row.addWidget(self.r18_switch)
        layout.addLayout(r18_row)
        layout.addWidget(Divider())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 4, 0)
        inner_layout.setSpacing(12)

        filter_cats = [c for c in TAG_CATEGORY_ORDER if c != "r18"]
        for cat in filter_cats:
            group = TagFilterGroup(cat, TAG_CATEGORIES[cat])
            group.filter_changed.connect(self._on_filter_changed)
            inner_layout.addWidget(group)
            self._groups[cat] = group
            if cat != filter_cats[-1]:
                inner_layout.addWidget(Divider())

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        clear_btn = QPushButton("清除筛选")
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['bg2']}; border: 1px solid {C['border']};
                border-radius: 5px; color: {C['text2']};
                font-size: 13px; padding: 5px 0;
            }}
            QPushButton:hover {{ background: {C['bg3']}; color: {C['text']}; }}
        """)
        clear_btn.clicked.connect(self.clear_filters)
        layout.addWidget(clear_btn)

    def refresh_tags(self):
        for cat, group in self._groups.items():
            values = app_state.db.get_all_tag_values(cat)
            group.populate(values)

    def _on_r18_changed(self, checked: bool):
        app_state.show_r18 = checked
        self.r18_changed.emit(checked)

    def _on_filter_changed(self):
        filters = {}
        for cat, group in self._groups.items():
            selected = group.get_selected()
            if selected:
                filters[cat] = selected
        app_state.tag_filters = filters
        self.filter_changed.emit()

    def clear_filters(self):
        for group in self._groups.values():
            group.clear_all()
        app_state.tag_filters = {}
        self.filter_changed.emit()

    def get_filters(self) -> dict:
        return app_state.tag_filters