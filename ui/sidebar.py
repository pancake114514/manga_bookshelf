"""
侧边栏 - 标签筛选 + R18 开关
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QCheckBox, QScrollArea,
    QFrame, QPushButton, QHBoxLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from config import app_state, TAG_CATEGORIES, TAG_CATEGORY_ORDER
from .widgets import SectionLabel, Divider


class TagFilterGroup(QWidget):
    """单个标签类别的复选框列表"""
    filter_changed = pyqtSignal()

    def __init__(self, category: str, label: str, parent=None):
        super().__init__(parent)
        self.category = category
        self._checkboxes: dict[str, QCheckBox] = {}
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.title = SectionLabel(label)
        layout.addWidget(self.title)

        self.items_layout = QVBoxLayout()
        self.items_layout.setSpacing(2)
        layout.addLayout(self.items_layout)

    def populate(self, values: list[str]):
        # 清除旧复选框
        for cb in self._checkboxes.values():
            cb.deleteLater()
        self._checkboxes.clear()
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for v in values:
            cb = QCheckBox(v)
            cb.setStyleSheet("""
                QCheckBox { color: #9a8abb; font-size: 12px; padding: 2px 0; }
                QCheckBox:hover { color: #c8b8e8; }
                QCheckBox::indicator { width:14px; height:14px; border-radius:3px; }
                QCheckBox::indicator:checked { background: #5c3f8a; border-color: #9a7adb; }
            """)
            cb.stateChanged.connect(lambda _: self.filter_changed.emit())
            self.items_layout.addWidget(cb)
            self._checkboxes[v] = cb

    def get_selected(self) -> list[str]:
        return [v for v, cb in self._checkboxes.items() if cb.isChecked()]

    def clear_all(self):
        for cb in self._checkboxes.values():
            cb.setChecked(False)


class SidebarWidget(QFrame):
    """
    左侧边栏：
    - R18 开关
    - 各标签类别筛选
    - 清除筛选按钮
    """
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

        # Logo / 标题
        logo = QLabel("MangaShelf")
        logo.setStyleSheet("""
            color: #7a5aab;
            font-size: 16px;
            font-weight: 700;
            letter-spacing: 1px;
            padding-bottom: 4px;
        """)
        layout.addWidget(logo)
        layout.addWidget(Divider())

        # R18 开关
        r18_row = QHBoxLayout()
        r18_lbl = QLabel("显示 R-18")
        r18_lbl.setStyleSheet("color: #c86a6a; font-size: 12px; font-weight: 600;")
        r18_row.addWidget(r18_lbl)
        r18_row.addStretch()
        self.r18_cb = QCheckBox()
        self.r18_cb.setChecked(False)
        self.r18_cb.setStyleSheet("""
            QCheckBox::indicator { width:18px; height:18px; border-radius:9px; border:1px solid #6a2a2a; background:#1e1c2a; }
            QCheckBox::indicator:checked { background:#8a1a1a; border-color:#e86a6a; }
        """)
        self.r18_cb.stateChanged.connect(self._on_r18_changed)
        r18_row.addWidget(self.r18_cb)
        layout.addLayout(r18_row)
        layout.addWidget(Divider())

        # 标签筛选区（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 4, 0)
        inner_layout.setSpacing(12)

        filter_cats = [c for c in TAG_CATEGORY_ORDER if c not in ("r18",)]
        for cat in filter_cats:
            label = TAG_CATEGORIES[cat]
            group = TagFilterGroup(cat, label)
            group.filter_changed.connect(self._on_filter_changed)
            inner_layout.addWidget(group)
            self._groups[cat] = group
            if cat != filter_cats[-1]:
                inner_layout.addWidget(Divider())

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        # 清除按钮
        clear_btn = QPushButton("清除筛选")
        clear_btn.clicked.connect(self.clear_filters)
        layout.addWidget(clear_btn)

    def refresh_tags(self):
        """从数据库重新加载所有标签值"""
        for cat, group in self._groups.items():
            values = app_state.db.get_all_tag_values(cat)
            group.populate(values)

    def _on_r18_changed(self, state: int):
        app_state.show_r18 = bool(state)
        self.r18_changed.emit(bool(state))

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