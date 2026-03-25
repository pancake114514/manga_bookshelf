import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer,QThread
from PyQt6.QtGui import QPixmap
from config import app_state, TAG_CATEGORIES, TAG_CATEGORY_ORDER
from .widgets import make_placeholder_pixmap, TagBadge

# ── Loader 和 Card 保持原样 ──

class GridThumbLoader(QThread):
    loaded = pyqtSignal(str, str)
    def __init__(self, tasks: list, cache_dir: str):
        super().__init__()
        self.tasks = tasks
        self.cache_dir = cache_dir

    def run(self):
        from utils.thumbnail import generate_grid_thumbnail
        for img_id, filepath in self.tasks:
            if os.path.isfile(filepath):
                path = generate_grid_thumbnail(filepath, self.cache_dir)
                if path:
                    self.loaded.emit(img_id, path)

class ImageThumbCard(QWidget):
    double_clicked = pyqtSignal(int)
    W, H = 150, 150
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
        self.thumb.setStyleSheet("border-radius: 6px; background: #0e0d18;")
        pm = make_placeholder_pixmap(self.W - 4, self.H - 4, "🖼", "#0e0d18")
        self.thumb.setPixmap(pm)
        layout.addWidget(self.thumb)
        name = QLabel(img["filename"])
        name.setStyleSheet("color: #5a5070; font-size: 9px; border: none;")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setFixedWidth(self.W - 4)
        name.setText(name.fontMetrics().elidedText(img["filename"], Qt.TextElideMode.ElideRight, self.W - 8))
        layout.addWidget(name)
        self.setStyleSheet("""
            QWidget { background: #1a1828; border-radius: 8px; border: 1px solid #2a2540; }
            QWidget:hover { border-color: #5c3f8a; background: #1e1c30; }
        """)

    def set_pixmap(self, pm: QPixmap):
        scaled = pm.scaled(self.W - 4, self.H - 4, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.thumb.setPixmap(scaled)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.idx)

# ── 核心修复后的 DirectoryView ──

class DirectoryView(QWidget):
    # 【修复】必须在这里定义信号
    back_requested = pyqtSignal()
    image_open_requested = pyqtSignal(int)

    def __init__(self, obj: dict, storage_root: str, parent=None):
        super().__init__(parent)
        self.obj = obj
        self.storage_root = storage_root
        self.cache_dir = os.path.join(storage_root, ".thumbcache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._thumb_cards = {}
        self._build()
        self._load_images()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 顶部信息栏 ──
        info_bar = QFrame()
        info_bar.setObjectName("topbar")
        info_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        info_bar.setStyleSheet("QFrame#topbar { background: #0e0d18; border-bottom: 1px solid #2a2540; }")

        info_outer = QVBoxLayout(info_bar)
        info_outer.setContentsMargins(16, 10, 16, 12)
        info_outer.setSpacing(10)

        back_btn = QPushButton("◀ 书架")
        back_btn.setFixedWidth(80)
        back_btn.clicked.connect(self.back_requested) # 现在不会报错了
        info_outer.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(16)
        content_row.setAlignment(Qt.AlignmentFlag.AlignTop) # 【关键】内容行顶部对齐

        self.cover_thumb = QLabel()
        self.cover_thumb.setFixedSize(144, 192)
        self.cover_thumb.setStyleSheet("border-radius: 6px; background: #1a1828;")
        pm = make_placeholder_pixmap(144, 192, "📖", "#1a1828")
        self.cover_thumb.setPixmap(pm)
        content_row.addWidget(self.cover_thumb)

        meta = QVBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(8)

        name_row = QHBoxLayout()
        name_row.setSpacing(12)
        self.title_label = QLabel(self.obj["name"])
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 700; color: #f0e8ff;")
        self.title_label.setWordWrap(True)
        name_row.addWidget(self.title_label, alignment=Qt.AlignmentFlag.AlignTop) # 【关键】标题置顶

        name_row.addStretch()

        self.read_btn = QPushButton("▶ 继续阅读")
        self.read_btn.setObjectName("accent")
        self.read_btn.setFixedWidth(110)
        self.read_btn.clicked.connect(self._on_continue_read)
        name_row.addWidget(self.read_btn, alignment=Qt.AlignmentFlag.AlignTop)

        meta.addLayout(name_row)

        tags = self.obj.get("tags", {})
        has_any = False
        for cat in TAG_CATEGORY_ORDER:
            vals = tags.get(cat)
            if not vals: continue
            display = [("R-18", "r18")] if cat == "r18" else ([(v, cat) for v in vals if v] if isinstance(vals, list) else [(str(vals), cat)])
            if not display: continue
            has_any = True
            row = QHBoxLayout()
            row.setSpacing(4)
            cat_lbl = QLabel(TAG_CATEGORIES[cat] + "：")
            cat_lbl.setStyleSheet("color: #5a5070; font-size: 11px;")
            cat_lbl.setFixedWidth(40)
            row.addWidget(cat_lbl)
            for text, category in display:
                row.addWidget(TagBadge(text, category))
            row.addStretch()
            meta.addLayout(row)

        if not has_any:
            no_tag = QLabel("暂无标签")
            no_tag.setStyleSheet("color: #3a3060; font-size: 11px;")
            meta.addWidget(no_tag)

        content_row.addLayout(meta, stretch=1) # 【关键】让元信息区域占据剩余空间
        info_outer.addLayout(content_row)
        layout.addWidget(info_bar)

        # ── 网格区域 ──
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background: transparent;")
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
            if images: cover = images[0]["filepath"]
        if cover and os.path.isfile(cover):
            from utils.thumbnail import generate_thumbnail
            path = generate_thumbnail(cover, self.cache_dir, (144, 192))
            if path:
                pm = QPixmap(path).scaled(144, 192, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
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

    def _on_thumb_loaded(self, img_id, thumb_path):
        card = self._thumb_cards.get(img_id)
        if card and os.path.isfile(thumb_path):
            card.set_pixmap(QPixmap(thumb_path))

    def _on_continue_read(self):
        self.image_open_requested.emit(self.obj.get("last_read_idx", 0))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(150, self._relayout)

    def _relayout(self):
        cols = max(1, (self.width() - 40) // (ImageThumbCard.W + 12)) or 6
        items = []
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget(): items.append(item.widget())
        for i, card in enumerate(items):
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(card, row, col)