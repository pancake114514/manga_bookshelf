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
    SectionLabel, Divider, LoadingLabel, C
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


import os
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QWidget, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath


class ObjectCard(QFrame):
    """优化版：通过容器封装实现完美对称的封面图"""
    double_clicked = pyqtSignal(dict)
    edit_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(dict)
    cover_change_requested = pyqtSignal(dict)

    CARD_W = 180
    CARD_H = 280
    # 封面图相对于边框的内缩边距
    CONTENT_PADDING = 3
    BORDER_RADIUS = 10

    def __init__(self, obj: dict, cache_dir: str, parent=None):
        super().__init__(parent)
        self.obj = obj
        self.cache_dir = cache_dir

        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # QSS 保持简洁，仅处理背景和描边
        self.setStyleSheet(f"""
            QFrame#ObjectCard {{
                background-color: {C['bg']};
                border: 1px solid {C['border']};
                border-radius: {self.BORDER_RADIUS}px;
            }}
            QFrame#ObjectCard:hover {{
                border-color: {C['accent_bd']};
                background-color: {C['accent_bg']};
            }}
        """)
        self.setObjectName("ObjectCard")
        self._build()
        self._load_cover()

    def _build(self):
        # 主布局：不设置边距，由内部容器控制
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- 1. 封面图封装层 ---
        # 这个 wrapper 占据卡片上半部分，负责将内容水平居中
        self.cover_wrapper = QWidget()
        self.cover_wrapper.setFixedHeight(235)  # 稍微给高一点
        wrapper_layout = QVBoxLayout(self.cover_wrapper)

        # 关键点：居中对齐，不设边距，手动计算 Label 尺寸
        wrapper_layout.setContentsMargins(0, self.CONTENT_PADDING, 0, 0)
        wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # 精确计算图片宽度：180 - (3 * 2) = 174px
        self.cover_w = self.CARD_W - (self.CONTENT_PADDING * 2)
        self.cover_h = 230 - self.CONTENT_PADDING

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(self.cover_w, self.cover_h)
        self.cover_label.setStyleSheet("background: transparent; border: none;")

        # 初始占位图
        pm = make_placeholder_pixmap(self.cover_w, self.cover_h, "📖", "transparent")
        self.cover_label.setPixmap(pm)

        wrapper_layout.addWidget(self.cover_label)
        self.main_layout.addWidget(self.cover_wrapper)

        # --- 2. 文字信息层 ---
        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        # 信息区的左右间距建议稍微大一点，视觉上更稳重
        info_layout.setContentsMargins(12, 5, 12, 10)
        info_layout.setSpacing(2)

        name = QLabel()
        name.setStyleSheet(f"color: {C['text']}; font-size: 13px; font-weight: 600; border: none;")
        name_text = self.obj.get("name", "未命名")
        # 根据实际可用宽度动态裁剪文字
        elided = name.fontMetrics().elidedText(name_text, Qt.TextElideMode.ElideRight, self.CARD_W - 24)
        name.setText(elided)

        count = app_state.db.get_image_count(self.obj["id"])
        count_lbl = QLabel(f"{count} 张图片")
        count_lbl.setStyleSheet(f"color: {C['text3']}; font-size: 11px; border: none;")

        info_layout.addWidget(name)
        info_layout.addWidget(count_lbl)
        self.main_layout.addWidget(info_container)

        # --- 3. R18 标签 ---
        if self.obj.get("tags", {}).get("r18"):
            self.badge = QLabel("R18", self)
            self.badge.setFixedSize(34, 18)
            self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.badge.setStyleSheet("""
                background-color: #8b2a2a; color: #f5ddd8;
                font-size: 10px; font-weight: 800; border-radius: 4px;
            """)
            # 右上角绝对定位偏移
            self.badge.move(self.CARD_W - 44, 10)

    def _get_rounded_pixmap(self, src_pixmap, width, height, radius):
        """圆角处理，确保抗锯齿边缘平滑"""
        target = QPixmap(width, height)
        target.fill(Qt.GlobalColor.transparent)

        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        path = QPainterPath()
        path.addRoundedRect(0, 0, width, height, radius, radius)

        painter.setClipPath(path)
        painter.drawPixmap(0, 0, src_pixmap)
        painter.end()
        return target

    def _on_thumb_loaded(self, obj_id: str, thumb_path: str):
        if obj_id != self.obj["id"] or not os.path.isfile(thumb_path):
            return

        try:
            pm = QPixmap(thumb_path)
            # 1. 填充裁剪
            scaled_pm = pm.scaled(
                self.cover_w, self.cover_h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )

            # 2. 居中切图
            if scaled_pm.width() > self.cover_w or scaled_pm.height() > self.cover_h:
                x = (scaled_pm.width() - self.cover_w) // 2
                y = (scaled_pm.height() - self.cover_h) // 2
                scaled_pm = scaled_pm.copy(x, y, self.cover_w, self.cover_h)

            # 3. 完美圆角应用
            # 内缩半径 = 原始半径 - 边距
            final_pm = self._get_rounded_pixmap(
                scaled_pm, self.cover_w, self.cover_h, self.BORDER_RADIUS - 2
            )
            self.cover_label.setPixmap(final_pm)
        except Exception as e:
            print(f"Error processing thumbnail: {e}")

    # --- 剩余交互代码（contextMenuEvent等）与之前版本保持一致 ---
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setWindowFlags(
            menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.setStyleSheet("""
            QMenu { background: #f5f0e8; border: 1px solid #c8bfaa; border-radius: 8px; padding: 4px; }
            QMenu::item { padding: 8px 24px; border-radius: 4px; color: #2a2418; }
            QMenu::item:selected { background: #e4ddd2; }
        """)
        act_edit = menu.addAction("✏️  编辑信息")
        act_cover = menu.addAction("🖼  设置封面")
        menu.addSeparator()
        act_del = menu.addAction("🗑  删除对象")
        action = menu.exec(event.globalPos())
        if action == act_edit:
            self.edit_requested.emit(self.obj)
        elif action == act_cover:
            self.cover_change_requested.emit(self.obj)
        elif action == act_del:
            self.delete_requested.emit(self.obj)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.obj)

    def _load_cover(self):
        cover = self.obj.get("cover_image")
        if not cover:
            images = app_state.db.get_images(self.obj["id"])
            if images: cover = images[0]["filepath"]
        if cover and os.path.isfile(cover):
            self._set_cover_async(cover)

    def _set_cover_async(self, path: str):
        self._loader = ThumbnailLoader([(self.obj["id"], path, self.cache_dir)])
        self._loader.loaded.connect(self._on_thumb_loaded)
        self._loader.start()

class BookshelfView(QWidget):
    object_opened = pyqtSignal(dict)
    tags_updated = pyqtSignal()

    def __init__(self, storage_root: str, parent=None):
        super().__init__(parent)
        self.storage_root = storage_root
        self.cache_dir = os.path.join(storage_root, ".thumbcache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._cards: dict[str, ObjectCard] = {}
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._relayout)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background: #f5f0e8;")
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(24, 24, 24, 24)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.scroll.setWidget(self.grid_widget)
        layout.addWidget(self.scroll)

        self.empty_label = QLabel("书架空空如也\n点击右上角「导入」添加图片吧 📚")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {C['text3']}; font-size: 18px;")
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

    def load_objects(self, objects: list):
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

        cols = self._calc_cols()
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
        objects = app_state.db.get_all_objects(include_r18=app_state.show_r18)
        self.load_objects(objects)

    def _calc_cols(self) -> int:
        effective_w = self.width() if self.width() > 200 else 900
        return max(1, (effective_w - 48) // (ObjectCard.CARD_W + 20))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start(200)

    def _relayout(self):
        cols = self._calc_cols()
        items = []
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                items.append(item.widget())
        for i, card in enumerate(items):
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(card, row, col)

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
        storage = app_state.db.get_object(obj["id"]).get("storage_path", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", storage,
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp *.gif)"
        )
        if path:
            app_state.db.update_object_cover(obj["id"], path)
            self.refresh()