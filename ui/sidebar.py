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
from .widgets import SectionLabel, Divider


# ─── 自绘 Checkbox ────────────────────────────────────────────────────────────

class CheckBox(QWidget):
    """
    完全自绘的复选框：
    - 未选中：深色背景方框
    - 选中：紫色背景 + 白色 ✓（QPainter 绘制折线）
    """
    stateChanged = pyqtSignal(bool)

    BOX = 15      # 方框尺寸
    RADIUS = 3    # 圆角半径
    H = 24        # 行高

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._checked = False
        self._hovered = False
        self._text = text
        self.setFixedHeight(self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    # ── 公开接口 ──────────────────────────────────────────────────────────────

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

    # ── 绘制 ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 计算居中绘图区
        rect = self.rect()
        bx = 0
        by = (rect.height() - self.BOX) // 2

        # 1. 绘制背景方框
        box_rect = QRectF(bx, by, self.BOX, self.BOX)

        if self._checked:
            # 选中状态：紫色填充
            p.setPen(QPen(QColor("#9a7adb"), 1))
            p.setBrush(QColor("#5c3f8a"))
            p.drawRoundedRect(box_rect, self.RADIUS, self.RADIUS)

            # 2. 绘制勾号 (使用 QPainterPath 保证折线平滑连接)
            p.setBrush(Qt.BrushStyle.NoBrush)
            tick_pen = QPen(QColor("#ffffff"), 2, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(tick_pen)

            # 使用相对坐标计算打勾位置
            path = QPainterPath()
            path.moveTo(bx + self.BOX * 0.2, by + self.BOX * 0.5)
            path.lineTo(bx + self.BOX * 0.45, by + self.BOX * 0.75)
            path.lineTo(bx + self.BOX * 0.8, by + self.BOX * 0.25)
            p.drawPath(path)
        else:
            # 未选中状态
            border_color = "#6a5a8a" if self._hovered else "#3a3060"
            p.setPen(QPen(QColor(border_color), 1))
            p.setBrush(QColor("#1e1c2a"))
            p.drawRoundedRect(box_rect, self.RADIUS, self.RADIUS)

        # 3. 绘制文字
        if self._text:
            text_color = "#e8e0f0" if self._checked else (
                "#c8b8e8" if self._hovered else "#9a8abb"
            )
            p.setPen(QColor(text_color))
            p.setFont(QFont("Segoe UI", 9))
            # 偏移文字，避免紧贴方框
            text_rect = rect.adjusted(self.BOX + 8, 0, 0, 0)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)

    # ── 事件 ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()


# ─── 自绘 Toggle Switch ───────────────────────────────────────────────────────

class ToggleSwitch(QWidget):
    """
    iOS 风格的切换开关，完全自绘。
    关闭：深灰色轨道 + 左侧白色圆钮
    开启：红紫色轨道 + 右侧白色圆钮
    """
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

        # 轨道
        track_color = "#8a1a3a" if self._checked else "#2a2540"
        if self._hovered:
            track_color = "#aa2a50" if self._checked else "#3a3060"
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(track_color))
        p.drawRoundedRect(0, 0, self.W, self.H, self.H // 2, self.H // 2)

        # 圆钮位置
        if self._checked:
            kx = self.W - self.PAD - self.KNOB_R * 2
        else:
            kx = self.PAD
        ky = (self.H - self.KNOB_R * 2) // 2

        # 圆钮
        p.setBrush(QColor("#f0e8ff"))
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


# ─── 标签筛选组 ───────────────────────────────────────────────────────────────

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
        # 获取当前已选中的标签，用于恢复状态
        current_selected = self.get_selected()

        # 只有当标签内容真的变了，才重新构建 UI
        existing_tags = list(self._checkboxes.keys())
        if set(existing_tags) == set(values):
            return

            # 清理旧控件
        for cb in self._checkboxes.values():
            cb.setParent(None)
            cb.deleteLater()
        self._checkboxes.clear()

        # 重新添加
        for v in values:
            cb = CheckBox(v)
            if v in current_selected:
                cb.setChecked(True, emit=False)  # 恢复状态
            cb.stateChanged.connect(lambda _: self.filter_changed.emit())
            self.items_layout.addWidget(cb)
            self._checkboxes[v] = cb

    def get_selected(self) -> list[str]:
        return [v for v, cb in self._checkboxes.items() if cb.isChecked()]

    def clear_all(self):
        for cb in self._checkboxes.values():
            cb.setChecked(False, emit=False)
        self.update()


# ─── 侧边栏主体 ───────────────────────────────────────────────────────────────

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

        # Logo
        logo = QLabel("MangaShelf")
        logo.setStyleSheet(
            "color: #7a5aab; font-size: 16px; font-weight: 700;"
            "letter-spacing: 1px; padding-bottom: 4px;"
        )
        layout.addWidget(logo)
        layout.addWidget(Divider())

        # R18 开关行
        r18_row = QHBoxLayout()
        r18_row.setSpacing(8)
        r18_lbl = QLabel("显示 R-18")
        r18_lbl.setStyleSheet("color: #c86a6a; font-size: 12px; font-weight: 600;")
        r18_row.addWidget(r18_lbl)
        r18_row.addStretch()
        self.r18_switch = ToggleSwitch()
        self.r18_switch.toggled.connect(self._on_r18_changed)
        r18_row.addWidget(self.r18_switch)
        layout.addLayout(r18_row)
        layout.addWidget(Divider())

        # 可滚动标签筛选区
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