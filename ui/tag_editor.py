"""
标签编辑对话框 + 对象名编辑
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QScrollArea, QWidget, QFrame,
    QDialogButtonBox, QMessageBox, QCompleter, QListWidget,
    QListWidgetItem, QAbstractItemView, QGroupBox, QSizePolicy,
    QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from config import TAG_CATEGORIES, TAG_CATEGORY_ORDER, app_state
from .widgets import SectionLabel, Divider, TagBadge


class MultiTagInput(QWidget):
    """
    单个标签类别的多值输入控件：
    输入框 + 添加按钮 + 标签列表（可点击删除）
    """
    changed = pyqtSignal()

    def __init__(self, category: str, label: str, initial: list = None, parent=None):
        super().__init__(parent)
        self.category = category
        self._values: list[str] = list(initial or [])
        self._build(label)

    def _build(self, label: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        lbl = SectionLabel(label)
        layout.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.input = QLineEdit()
        self.input.setPlaceholderText(f"输入{label}后按 Enter 或点击添加")
        self.input.returnPressed.connect(self._add_current)
        row.addWidget(self.input)

        btn = QPushButton("添加")
        btn.setFixedWidth(72)
        btn.clicked.connect(self._add_current)
        row.addWidget(btn)
        layout.addLayout(row)

        # 已添加标签区域
        self.tag_row = QHBoxLayout()
        self.tag_row.setSpacing(4)
        self.tag_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.tag_row.addStretch()
        layout.addLayout(self.tag_row)

        self._refresh_tags()

        # 历史建议
        existing = app_state.db.get_all_tag_values(self.category)
        if existing:
            completer = QCompleter(existing)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self.input.setCompleter(completer)

    def _refresh_tags(self):
        # 清除旧标签（保留 stretch）
        while self.tag_row.count() > 1:
            item = self.tag_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for v in self._values:
            badge = TagBadge(f"✕ {v}", self.category)
            badge.setToolTip("点击删除")
            badge.setCursor(Qt.CursorShape.PointingHandCursor)
            badge.mousePressEvent = lambda e, val=v: self._remove(val)
            self.tag_row.insertWidget(self.tag_row.count() - 1, badge)

    def _add_current(self):
        v = self.input.text().strip()
        if v and v not in self._values:
            self._values.append(v)
            self._refresh_tags()
            self.changed.emit()
        self.input.clear()

    def _remove(self, val: str):
        if val in self._values:
            self._values.remove(val)
            self._refresh_tags()
            self.changed.emit()

    def get_values(self) -> list[str]:
        return list(self._values)


class TagEditorDialog(QDialog):
    """
    标签和名称编辑对话框
    """
    def __init__(self, obj: dict = None, parent=None):
        super().__init__(parent)
        self.obj = obj or {}
        tags = obj.get("tags", {}) if obj else {}
        self.setWindowTitle("编辑对象信息")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._build(tags)

    def _build(self, tags: dict):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 对象名
        layout.addWidget(SectionLabel("对象名称"))
        self.name_input = QLineEdit(self.obj.get("name", ""))
        self.name_input.setPlaceholderText("输入对象名称")
        layout.addWidget(self.name_input)

        layout.addWidget(Divider())

        # 滚动区域放标签输入
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(8)
        inner_layout.setContentsMargins(0, 0, 8, 0)

        self.tag_inputs: dict[str, MultiTagInput | QCheckBox] = {}

        for cat in TAG_CATEGORY_ORDER:
            label = TAG_CATEGORIES[cat]
            if cat == "r18":
                cb = QCheckBox(f"  {label}")
                cb.setChecked(bool(tags.get("r18", False)))
                cb.setStyleSheet("font-size: 13px; color: #e86a6a; padding: 4px 0;")
                self.tag_inputs[cat] = cb
                inner_layout.addWidget(cb)
            elif cat == "censored":
                widget = MultiTagInput(cat, label,
                    initial=tags.get(cat, []) if isinstance(tags.get(cat), list)
                            else ([tags[cat]] if tags.get(cat) else []))
                self.tag_inputs[cat] = widget
                inner_layout.addWidget(widget)
            else:
                initial = tags.get(cat, [])
                if not isinstance(initial, list):
                    initial = [initial] if initial else []
                widget = MultiTagInput(cat, label, initial=initial)
                self.tag_inputs[cat] = widget
                inner_layout.addWidget(widget)
            if cat != TAG_CATEGORY_ORDER[-1]:
                inner_layout.addWidget(Divider())

        inner_layout.addStretch()
        scroll.setWidget(inner)
        scroll.setMinimumHeight(320)
        layout.addWidget(scroll)

        # 按钮
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        name = self.name_input.text().strip()
        if not name:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "对象名称不能为空")
            return
        self.accept()

    def get_name(self) -> str:
        return self.name_input.text().strip()

    def get_tags(self) -> dict:
        result = {}
        for cat, widget in self.tag_inputs.items():
            if isinstance(widget, QCheckBox):
                result[cat] = widget.isChecked()
            else:
                result[cat] = widget.get_values()
        return result