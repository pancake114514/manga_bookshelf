"""
书架界面 - 展示所有目录对象的封面卡片
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSizePolicy, QMenu,
    QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QThread, QTimer, QPoint
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont, QAction, QCursor
from config import app_state, THUMBNAIL_SIZE
from .widgets import (
    make_placeholder_pixmap, TagFlowWidget, ClickableLabel,
    SectionLabel, Divider, LoadingLabel
)


class ThumbnailLoader(QThread):
    loaded = pyqtSignal(str, str)   # obj_id, thumb_path

    def __init__(self, tasks: list):   # tasks: [(obj_id, img_path, cache_dir), ...]
        super().__init__()
        self.tasks = tasks

    def run(self):
        from utils.thumbnail import generate_thumbnail
        for obj_id, img_path, cache_dir in self.tasks:
            if img_path and os.path.isfile(img_path):
                path = generate_thumbnail(img_path, cache_dir)
                if path:
                    self.loaded.emit(obj_id, path)


class ObjectCard(QFrame):
    """单个目录对象的封面卡片"""
    double_clicked = pyqtSignal(dict)
    edit_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(dict)
    cover_change_requested = pyqtSignal(dict)

    CARD_W = 180
    CARD_H = 280

    def __init__(self, obj: dict, cache_dir: str, parent=None):
        super().__init__(parent)
        self.obj = obj
        self.cache_dir = cache_dir
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QFrame {
                background-color: #1a1828;
                border: 1px solid #2a2540;
                border-radius: 10px;
            }
            QFrame:hover {
                border-color: #5c3f8a;
                background-color: #1e1c30;
            }
        """)
        self._build()
        self._load_cover()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 封面图区域
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(self.CARD_W, 230)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("""
            border-radius: 10px 10px 0 0;
            background: #0e0d18;
        """)
        pm = make_placeholder_pixmap(self.CARD_W, 230, "📖", "#0e0d18")
        self.cover_label.setPixmap(pm)
        layout.addWidget(self.cover_label)

        # 名称区域
        info = QWidget()
        info.setStyleSheet("background: transparent; border: none;")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(8, 6, 8, 6)
        info_layout.setSpacing(2)

        name = QLabel(self.obj["name"])
        name.setStyleSheet("color: #e8e0f0; font-size: 12px; font-weight: 600; border: none;")
        name.setWordWrap(False)
        name.setMaximumWidth(self.CARD_W - 16)
        name.setText(name.fontMetrics().elidedText(
            self.obj["name"], Qt.TextElideMode.ElideRight, self.CARD_W - 16))
        info_layout.addWidget(name)

        # 图片数量
        count = app_state.db.get_image_count(self.obj["id"])
        count_lbl = QLabel(f"{count} 张图片")
        count_lbl.setStyleSheet("color: #5a5070; font-size: 10px; border: none;")
        info_layout.addWidget(count_lbl)

        layout.addWidget(info)

        # R18 角标
        if self.obj.get("tags", {}).get("r18"):
            badge = QLabel("R18", self)
            badge.setFixedSize(32, 18)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet("""
                background-color: #8a1a1a; color: #ffaaaa;
                font-size: 9px; font-weight: 700;
                border-radius: 4px;
            """)
            badge.move(self.CARD_W - 40, 8)

    def _load_cover(self):
        cover = self.obj.get("cover_image")
        if not cover:
            # 尝试获取第一张图片
            images = app_state.db.get_images(self.obj["id"])
            if images:
                cover = images[0]["filepath"]
        if cover and os.path.isfile(cover):
            self._set_cover_async(cover)

    def _set_cover_async(self, path: str):
        self._loader = ThumbnailLoader([(self.obj["id"], path, self.cache_dir)])
        self._loader.loaded.connect(self._on_thumb_loaded)
        self._loader.start()

    def _on_thumb_loaded(self, obj_id: str, thumb_path: str):
        if obj_id == self.obj["id"] and os.path.isfile(thumb_path):
            pm = QPixmap(thumb_path)
            pm = pm.scaled(self.CARD_W, 230,
                           Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
            # 居中裁剪
            if pm.width() > self.CARD_W or pm.height() > 230:
                x = (pm.width() - self.CARD_W) // 2
                y = (pm.height() - 230) // 2
                pm = pm.copy(x, y, self.CARD_W, 230)
            self.cover_label.setPixmap(pm)

    def set_pixmap(self, pm: QPixmap):
        self.cover_label.setPixmap(pm)

    def update_object(self, obj: dict):
        self.obj = obj

    # ── 事件 ──────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.obj)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1a1828; border: 1px solid #3a2d60;
                border-radius: 8px; padding: 4px;
            }
            QMenu::item { padding: 8px 20px; border-radius: 4px; color: #c8b8e8; }
            QMenu::item:selected { background: #2a2050; }
            QMenu::separator { background: #2a2540; height: 1px; margin: 4px 8px; }
        """)
        act_edit = menu.addAction("✏️  编辑信息")
        act_cover = menu.addAction("🖼  设置封面")
        menu.addSeparator()
        act_del = menu.addAction("🗑  删除对象")
        act_del.setProperty("color", "#e86a6a")

        action = menu.exec(event.globalPos())
        if action == act_edit:
            self.edit_requested.emit(self.obj)
        elif action == act_cover:
            self.cover_change_requested.emit(self.obj)
        elif action == act_del:
            self.delete_requested.emit(self.obj)


class BookshelfView(QWidget):
    """
    书架主视图
    """
    object_opened = pyqtSignal(dict)
    tags_updated = pyqtSignal()   # 标签有变动（编辑/删除），通知外部刷新侧边栏

    def __init__(self, storage_root: str, parent=None):
        super().__init__(parent)
        self.storage_root = storage_root
        self.cache_dir = os.path.join(storage_root, ".thumbcache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._cards: dict[str, ObjectCard] = {}
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 滚动区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(24, 24, 24, 24)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.scroll.setWidget(self.grid_widget)
        layout.addWidget(self.scroll)

        self.empty_label = QLabel("书架空空如也\n点击右上角「导入」添加图片吧 📚")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #3a3060; font-size: 18px; line-height: 2;")
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

    def load_objects(self, objects: list):
        # 清除旧卡片
        self._cards.clear()
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not objects:
            self.scroll.hide()
            self.empty_label.show()
            return

        self.empty_label.hide()
        self.scroll.show()

        effective_w = self.width() if self.width() > 200 else 900
        cols = max(1, (effective_w - 48) // (ObjectCard.CARD_W + 20))

        for i, obj in enumerate(objects):
            card = ObjectCard(obj, self.cache_dir)
            card.double_clicked.connect(self.object_opened)
            card.edit_requested.connect(self._on_edit)
            card.delete_requested.connect(self._on_delete)
            card.cover_change_requested.connect(self._on_change_cover)
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(card, row, col)
            self._cards[obj["id"]] = card

    def refresh(self):
        """重新从数据库加载"""
        objects = app_state.db.get_all_objects(include_r18=app_state.show_r18)
        self.load_objects(objects)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 延迟重排，避免 resize 时频繁重绘
        QTimer.singleShot(100, self._relayout)

    def _relayout(self):
        objects = [c.obj for c in self._cards.values()]
        if objects:
            self.load_objects(objects)

    # ── 右键菜单动作 ──────────────────────────────────────────────────────────

    def _on_edit(self, obj: dict):
        from .tag_editor import TagEditorDialog
        dlg = TagEditorDialog(obj, self)
        if dlg.exec() == TagEditorDialog.DialogCode.Accepted:
            name = dlg.get_name()
            tags = dlg.get_tags()
            app_state.db.update_object_name(obj["id"], name)
            app_state.db.set_tags(obj["id"], tags)
            self.refresh()
            self.tags_updated.emit()

    def _on_delete(self, obj: dict):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要从书架删除「{obj['name']}」吗？\n（本地图片文件不会被删除）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            app_state.db.delete_object(obj["id"])
            self.refresh()
            self.tags_updated.emit()

    def _on_change_cover(self, obj: dict):
        from PyQt6.QtWidgets import QFileDialog
        images = app_state.db.get_images(obj["id"])
        if not images:
            QMessageBox.information(self, "提示", "该对象中没有图片")
            return

        # 弹出当前目录中图片选择
        storage = app_state.db.get_object(obj["id"]).get("storage_path", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", storage,
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp *.gif)"
        )
        if path:
            app_state.db.update_object_cover(obj["id"], path)
            self.refresh()