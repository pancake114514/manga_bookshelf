"""
目录内部视图 - 展示对象中的所有图片缩略图
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QPixmap, QFont, QIcon, QPainter, QPainterPath
from config import app_state, GRID_THUMB_SIZE
from .widgets import make_placeholder_pixmap,TagBadge, C


class GridThumbLoader(QThread):
    loaded = pyqtSignal(str, str)   # img_id, thumb_path

    def __init__(self, tasks: list, cache_dir: str):
        super().__init__()
        self.tasks = tasks   # [(img_id, filepath), ...]
        self.cache_dir = cache_dir

    def run(self):
        from utils.thumbnail import generate_grid_thumbnail
        for img_id, filepath in self.tasks:
            if os.path.isfile(filepath):
                path = generate_grid_thumbnail(filepath, self.cache_dir)
                if path:
                    self.loaded.emit(img_id, path)


class ImageThumbCard(QWidget):
    """单张图片的缩略图卡片"""
    double_clicked = pyqtSignal(int)  # 图片在列表中的 index

    W, H = 150, 150
    THUMB_W = W - 4
    THUMB_H = H - 4
    BORDER_RADIUS = 6  # 圆角半径，与样式表中的 border-radius 保持一致

    def __init__(self, img: dict, idx: int, parent=None):
        super().__init__(parent)
        self.img = img
        self.idx = idx
        self.setFixedSize(self.W, self.H + 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.thumb = QLabel()
        self.thumb.setFixedSize(self.W - 4, self.H - 4)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setStyleSheet("border-radius: 6px; background: #e4ddd2;")
        pm = make_placeholder_pixmap(self.W - 4, self.H - 4, "🖼", "#e4ddd2")
        self.thumb.setPixmap(pm)
        layout.addWidget(self.thumb)

        name = QLabel(img["filename"])
        name.setStyleSheet("color: #8a7f6a; font-size: 9px; border: none; font-family: Georgia, serif;")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setFixedWidth(self.W - 4)
        name.setText(name.fontMetrics().elidedText(
            img["filename"], Qt.TextElideMode.ElideRight, self.W - 8))
        layout.addWidget(name)

        self.setStyleSheet("""
            QWidget { background: #ede8df; border-radius: 8px; border: 1px solid #c8bfaa; }
            QWidget:hover { border-color: #c4856a; background: #f0e6e0; }
        """)

    def _get_rounded_pixmap(self, src_pixmap: QPixmap) -> QPixmap:
        """对图片应用圆角裁剪"""
        width = src_pixmap.width()
        height = src_pixmap.height()

        target = QPixmap(width, height)
        target.fill(Qt.GlobalColor.transparent)

        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        path = QPainterPath()
        path.addRoundedRect(0, 0, width, height, self.BORDER_RADIUS, self.BORDER_RADIUS)

        painter.setClipPath(path)
        painter.drawPixmap(0, 0, src_pixmap)
        painter.end()
        return target

    def set_pixmap(self, pm: QPixmap):
        # 缩放到目标尺寸
        scaled = pm.scaled(self.THUMB_W, self.THUMB_H,
                           Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
        # 居中裁剪
        if scaled.width() > self.THUMB_W or scaled.height() > self.THUMB_H:
            x = (scaled.width() - self.THUMB_W) // 2
            y = (scaled.height() - self.THUMB_H) // 2
            scaled = scaled.copy(x, y, self.THUMB_W, self.THUMB_H)
        # 应用圆角
        rounded = self._get_rounded_pixmap(scaled)
        self.thumb.setPixmap(rounded)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.idx)

cover_w = 180
cover_h = 240
class DirectoryView(QWidget):
    """
    点击书架上的对象后进入的目录视图
    """
    back_requested = pyqtSignal()
    image_open_requested = pyqtSignal(int)   # 请求打开第 N 张图

    def __init__(self, obj: dict, storage_root: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: transparent;")
        self.obj = obj
        self.storage_root = storage_root
        self.cache_dir = os.path.join(storage_root, ".thumbcache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._thumb_cards: dict[str, ImageThumbCard] = {}
        self._build()
        self._load_images()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 顶部信息栏（纵向：返回按钮 → 封面+元信息横排）────────────────────
        info_bar = QFrame()
        info_bar.setObjectName("topbar")
        info_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        info_bar.setStyleSheet(f"""
            QFrame#topbar {{
                background: {C['topbar']};
                border-bottom: 1px solid {C['border']};
            }}
        """)

        # 外层纵向布局
        info_outer = QVBoxLayout(info_bar)
        info_outer.setContentsMargins(16, 10, 16, 12)
        info_outer.setSpacing(10)

        # 第一行：返回按钮（靠左）
        back_btn = QPushButton("◀ 书架")
        back_btn.setFixedWidth(80)
        back_btn.setStyleSheet("""
            QPushButton {
                background: #ede8df; border: 1px solid #c8bfaa;
                border-radius: 5px; color: #5a5040;
                font-size: 12px; padding: 4px 10px;
            }
            QPushButton:hover { background: #e4ddd2; border-color: #b0a590; color: #2a2418; }
        """)
        back_btn.clicked.connect(self.back_requested)
        info_outer.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        # 第二行：封面 + 右侧元信息
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(16)

        # 封面缩略图（固定尺寸）
        self.cover_thumb = QLabel()
        self.cover_thumb.setFixedSize(cover_w, cover_h)
        self.cover_thumb.setStyleSheet(f"border-radius: 6px; background: {C['bg3']};")
        self.cover_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = make_placeholder_pixmap(cover_w, cover_h, "📖", "#e4ddd2")
        self.cover_thumb.setPixmap(pm)
        content_row.addWidget(self.cover_thumb, alignment=Qt.AlignmentFlag.AlignTop)

        # 右侧：标题 + 阅读按钮 + 标签
        meta = QVBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(8)
        meta.setAlignment(Qt.AlignmentFlag.AlignTop)  # 顶部对齐，确保标题与缩略图顶端平齐

        name_row = QHBoxLayout()
        name_row.setSpacing(12)
        self.title_label = QLabel(self.obj["name"])
        self.title_label.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {C['text']};")
        self.title_label.setWordWrap(True)
        name_row.addWidget(self.title_label)
        name_row.addStretch()
        self.read_btn = QPushButton("▶ 继续阅读")
        self.read_btn.setObjectName("accent")
        # 在这里添加 color 属性
        self.read_btn.setStyleSheet("color: #2A2418; font-weight: bold;")
        self.read_btn.setFixedWidth(110)
        self.read_btn.clicked.connect(self._on_continue_read)
        name_row.addWidget(self.read_btn, alignment=Qt.AlignmentFlag.AlignTop)
        meta.addLayout(name_row)

        # 按类别逐行展示标签
        tags = self.obj.get("tags", {})
        from config import TAG_CATEGORIES, TAG_CATEGORY_ORDER
        has_any = False
        for cat in TAG_CATEGORY_ORDER:
            vals = tags.get(cat)
            if not vals:
                continue
            if cat == "r18":
                display = [("R-18", "r18")]
            elif isinstance(vals, list):
                display = [(v, cat) for v in vals if v]
            else:
                display = [(str(vals), cat)]
            if not display:
                continue
            has_any = True
            row = QHBoxLayout()
            row.setSpacing(4)
            row.setContentsMargins(0, 0, 0, 0)
            cat_lbl = QLabel(TAG_CATEGORIES[cat] + "：")
            cat_lbl.setStyleSheet(f"color: {C['text3']}; font-size: 12px; font-family: 'Georgia', serif;")
            cat_lbl.setFixedWidth(40)
            row.addWidget(cat_lbl)
            for text, category in display:
                row.addWidget(TagBadge(text, category))
            row.addStretch()
            meta.addLayout(row)
        if not has_any:
            no_tag = QLabel("暂无标签")
            no_tag.setStyleSheet("color: #8a7f6a; font-size: 12px;")
            meta.addWidget(no_tag)

        content_row.addLayout(meta)
        info_outer.addLayout(content_row)
        layout.addWidget(info_bar)

        # ── 图片网格区域 ──────────────────────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: #f5f0e8;")

        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background: #f5f0e8;")
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(20, 20, 20, 20)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.scroll.setWidget(self.grid_widget)
        layout.addWidget(self.scroll)

        self._load_cover_thumb()

    def _load_cover_thumb(self):
        cover = self.obj.get("cover_image")
        if not cover:
            images = app_state.db.get_images(self.obj["id"])
            if images:
                cover = images[0]["filepath"]
        if cover and os.path.isfile(cover):
            from utils.thumbnail import generate_thumbnail
            path = generate_thumbnail(cover, self.cache_dir, (cover_w, cover_h))
            if path:
                pm = QPixmap(path).scaled(cover_w, cover_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                self.cover_thumb.setPixmap(pm)

    def _load_images(self):
        self.images = app_state.db.get_images(self.obj["id"])
        effective_w = self.width() if self.width() > 100 else 900
        cols = max(1, (effective_w - 40) // (ImageThumbCard.W + 12))

        tasks = []
        for i, img in enumerate(self.images):
            card = ImageThumbCard(img, i)
            card.double_clicked.connect(self.image_open_requested)
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(card, row, col)
            self._thumb_cards[img["id"]] = card
            tasks.append((img["id"], img["filepath"]))

        if tasks:
            self._loader = GridThumbLoader(tasks, self.cache_dir)
            self._loader.loaded.connect(self._on_thumb_loaded)
            self._loader.start()

    def _on_thumb_loaded(self, img_id: str, thumb_path: str):
        card = self._thumb_cards.get(img_id)
        if card and os.path.isfile(thumb_path):
            pm = QPixmap(thumb_path)
            card.set_pixmap(pm)

    def _on_continue_read(self):
        last_idx = self.obj.get("last_read_idx", 0)
        self.image_open_requested.emit(last_idx)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(150, self._relayout)

    def _relayout(self):
        """只重新排列已有卡片，不销毁重建，避免异步缩略图信号打到已销毁对象"""
        cols = max(1, (self.width() - 40) // (ImageThumbCard.W + 12)) or 6
        # 取出所有卡片（保持顺序）
        items = []
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                items.append(item.widget())
        # 按新列数重新放置（不 deleteLater）
        for i, card in enumerate(items):
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(card, row, col)