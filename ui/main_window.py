"""
主窗口 - 协调书架、目录视图、图片阅览器
"""
import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QStackedWidget, QFrame, QSizePolicy,
    QFileDialog, QMessageBox, QToolButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QIcon, QKeySequence, QShortcut

from config import app_state
from .widgets import STYLE_MAIN, Divider
from .sidebar import SidebarWidget
from .bookshelf import BookshelfView
from .directory_view import DirectoryView
from .image_viewer import ImageViewer
from .import_dialog import ImportDialog


# 视图索引
VIEW_BOOKSHELF = 0
VIEW_DIRECTORY = 1
VIEW_VIEWER = 2


class TopBar(QFrame):
    search_changed = pyqtSignal(str)
    import_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topbar")
        self.setFixedHeight(52)
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        # 搜索框
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  搜索标签或对象名…")
        self.search.setFixedHeight(34)
        self.search.setMaximumWidth(400)
        self.search.textChanged.connect(self.search_changed)
        self.search.setStyleSheet("""
            QLineEdit {
                background: #1a1828;
                border: 1px solid #2a2540;
                border-radius: 17px;
                padding: 0 16px;
                color: #c8b8e8;
                font-size: 13px;
            }
            QLineEdit:focus { border-color: #5c3f8a; }
        """)
        layout.addWidget(self.search)
        layout.addStretch()

        # 导入按钮
        import_btn = QPushButton("＋  导入")
        import_btn.setFixedHeight(34)
        import_btn.setFixedWidth(96)
        import_btn.setObjectName("accent")
        import_btn.setStyleSheet("""
            QPushButton {
                background: #5c3f8a;
                border: 1px solid #9a7adb;
                border-radius: 6px;
                color: #f0e8ff;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background: #7a55aa; }
            QPushButton:pressed { background: #3a2568; }
        """)
        import_btn.clicked.connect(self.import_clicked)
        layout.addWidget(import_btn)


class MainWindow(QMainWindow):
    def __init__(self, storage_root: str):
        super().__init__()
        self.storage_root = storage_root
        self.setWindowTitle("MangaShelf")
        self.setMinimumSize(1000, 680)
        self.resize(1280, 800)
        self._current_obj = None
        self._images_for_viewer: list = []
        self._build()
        self._load_shelf()

    def _build(self):
        self.setStyleSheet(STYLE_MAIN)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶栏
        self.topbar = TopBar()
        self.topbar.search_changed.connect(self._on_search)
        self.topbar.import_clicked.connect(self._on_import)
        root.addWidget(self.topbar)

        # 内容区
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        # 侧边栏
        self.sidebar = SidebarWidget()
        self.sidebar.filter_changed.connect(self._on_filter_changed)
        self.sidebar.r18_changed.connect(self._on_r18_changed)
        content.addWidget(self.sidebar)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #2a2540; background: #2a2540; border: none; max-width: 1px;")
        content.addWidget(sep)

        # 堆叠视图
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: #12111a;")

        # 书架视图
        self.bookshelf = BookshelfView(self.storage_root)
        self.bookshelf.object_opened.connect(self._open_directory)
        self.stack.addWidget(self.bookshelf)   # index 0

        # 目录视图（动态创建，占位）
        self._dir_placeholder = QWidget()
        self.stack.addWidget(self._dir_placeholder)   # index 1

        # 图片阅览（动态创建，占位）
        self._viewer_placeholder = QWidget()
        self.stack.addWidget(self._viewer_placeholder)  # index 2

        content.addWidget(self.stack)
        root.addLayout(content)

        # 快捷键
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            lambda: self.topbar.search.setFocus()
        )

    def _load_shelf(self):
        self.sidebar.refresh_tags()
        filters = app_state.tag_filters
        keyword = app_state.search_keyword
        db = app_state.db

        if keyword:
            objects = db.search_objects(keyword, include_r18=app_state.show_r18)
        elif filters:
            objects = db.filter_by_tags(filters, include_r18=app_state.show_r18)
        else:
            objects = db.get_all_objects(include_r18=app_state.show_r18)

        self.bookshelf.load_objects(objects)

    def _show_bookshelf(self):
        self.stack.setCurrentIndex(VIEW_BOOKSHELF)
        self.topbar.show()
        self.sidebar.show()

    # ── 导入 ──────────────────────────────────────────────────────────────────

    def _on_import(self):
        dlg = ImportDialog(self.storage_root, self)
        dlg.import_done.connect(self._on_import_done)
        dlg.exec()

    def _on_import_done(self, obj_id: str):
        self.sidebar.refresh_tags()
        self._load_shelf()
        QMessageBox.information(self, "导入完成", "图片导入成功！")

    # ── 搜索 / 筛选 ───────────────────────────────────────────────────────────

    def _on_search(self, text: str):
        app_state.search_keyword = text.strip()
        QTimer.singleShot(300, self._load_shelf)

    def _on_filter_changed(self):
        self._load_shelf()

    def _on_r18_changed(self, show: bool):
        self._load_shelf()

    # ── 导航 ──────────────────────────────────────────────────────────────────

    def _open_directory(self, obj: dict):
        self._current_obj = obj

        # 移除旧目录视图
        old = self.stack.widget(VIEW_DIRECTORY)
        self.stack.removeWidget(old)
        old.deleteLater()

        dir_view = DirectoryView(obj, self.storage_root)
        dir_view.back_requested.connect(self._show_bookshelf)
        dir_view.image_open_requested.connect(self._open_image_at)
        self.stack.insertWidget(VIEW_DIRECTORY, dir_view)
        self.stack.setCurrentIndex(VIEW_DIRECTORY)

        # 刷新对象（获取最新 last_read_idx）
        refreshed = app_state.db.get_object(obj["id"])
        if refreshed:
            self._current_obj = refreshed

    def _open_image_at(self, idx: int):
        if not self._current_obj:
            return
        images = app_state.db.get_images(self._current_obj["id"])
        if not images:
            return
        self._images_for_viewer = images

        # 移除旧 viewer
        old = self.stack.widget(VIEW_VIEWER)
        self.stack.removeWidget(old)
        old.deleteLater()

        viewer = ImageViewer(self._current_obj, images, idx)
        viewer.back_requested.connect(self._back_from_viewer)
        self.stack.insertWidget(VIEW_VIEWER, viewer)
        self.stack.setCurrentIndex(VIEW_VIEWER)
        self.sidebar.hide()
        self.topbar.hide()

    def _back_from_viewer(self):
        # 刷新阅读进度后直接切回目录视图，不重建 widget（避免 deleteLater 竞态）
        if self._current_obj:
            refreshed = app_state.db.get_object(self._current_obj["id"])
            if refreshed:
                self._current_obj = refreshed
                # 更新目录视图中「继续阅读」按钮指向的 obj
                dir_view = self.stack.widget(VIEW_DIRECTORY)
                if hasattr(dir_view, "obj"):
                    dir_view.obj = refreshed
        self.stack.setCurrentIndex(VIEW_DIRECTORY)
        self.sidebar.show()
        self.topbar.show()