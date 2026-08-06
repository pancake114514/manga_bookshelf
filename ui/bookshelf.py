"""
书架界面 - 展示所有目录对象的封面卡片
"""
import os
import time
from collections import deque
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSizePolicy, QMenu,
    QMessageBox, QCheckBox, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QThread, QTimer, QPoint
from PyQt6.QtGui import QPixmap, QColor, QPainter, QPainterPath
import logging
from config import THUMBNAIL_SIZE, SUPPORTED_FORMATS
from utils.thumbnail import get_thumb_cache_dir
from .widgets import (
    make_placeholder_pixmap, C, FramelessDialog
)

logger = logging.getLogger(__name__)


class ThumbnailLoader(QThread):
    """常驻后台缩略图生成线程。

    所有卡片共享一个实例，避免「每张卡片一个 QThread」造成的线程风暴；
    刷新时旧任务会被丢弃（卡片已销毁），无需也无法取消。
    """
    loaded = pyqtSignal(str, str)   # obj_id, thumb_path

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: deque = deque()
        self._running = True

    def add_task(self, obj_id: str, img_path: str, cache_dir: str):
        self._tasks.append((obj_id, img_path, cache_dir))
        # 积压超过上限时丢弃最旧任务，避免快速刷新时队列堆积
        while len(self._tasks) > 64:
            self._tasks.popleft()

    def stop(self):
        self._running = False

    def run(self):
        from utils.thumbnail import generate_thumbnail
        while self._running:
            if not self._tasks:
                time.sleep(0.02)
                continue
            obj_id, img_path, cache_dir = self._tasks.popleft()
            if not self._running:
                break
            if img_path and os.path.isfile(img_path):
                path = generate_thumbnail(img_path, cache_dir)
                if path:
                    self.loaded.emit(obj_id, path)




class _DeleteObjectWorker(QThread):
    """后台删除对象：文件删除可能很慢（数 GB），不能在 UI 线程执行。

    使用独立 LibraryService 实例，避免共享 sqlite 连接。
    """
    ok = pyqtSignal()
    err = pyqtSignal(str)

    def __init__(self, db_path: str, obj_id: str, delete_files: bool,
                 storage_root: str):
        super().__init__()
        self.db_path = db_path
        self.obj_id = obj_id
        self.delete_files = delete_files
        self.storage_root = storage_root

    def run(self):
        from services.library_service import LibraryService
        svc = None
        try:
            svc = LibraryService(self.db_path)
            svc.delete_object(self.obj_id, delete_files=self.delete_files,
                              storage_root=self.storage_root)
            self.ok.emit()
        except Exception as e:
            self.err.emit(str(e))
        finally:
            if svc is not None:
                svc.close()


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
    # 卡片外边距（用于容纳圆角，防止被父容器裁剪）
    CARD_MARGIN = 2

    def __init__(self, obj: dict, cache_dir: str, svc, loader, parent=None):
        super().__init__(parent)
        self.obj = obj
        self.cache_dir = cache_dir
        self.svc = svc
        self._loader = loader

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
        # 主布局：设置边距以容纳圆角，防止被父容器裁剪
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(self.CARD_MARGIN, self.CARD_MARGIN, self.CARD_MARGIN, self.CARD_MARGIN)
        self.main_layout.setSpacing(0)

        self.cover_wrapper = QWidget()
        self.cover_wrapper.setFixedHeight(235)

        wrapper_layout = QVBoxLayout(self.cover_wrapper)
        wrapper_layout.setContentsMargins(
            self.CONTENT_PADDING,
            self.CONTENT_PADDING,
            self.CONTENT_PADDING,
            self.CONTENT_PADDING
        )
        wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        self.cover_w = self.CARD_W - self.CONTENT_PADDING * 2
        self.cover_h = 235 - self.CONTENT_PADDING * 2  # ✅ 和 wrapper 对齐

        self.cover_label = QLabel()

        self.cover_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        self.cover_label.setFixedHeight(self.cover_h)

        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("background: transparent; border: none;")

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

        count = self.obj.get("image_count")
        if count is None:
            count = self.svc.get_image_count(self.obj["id"])
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
            logger.warning("缩略图处理失败: %s", e)

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
        cover = self.svc.resolve_cover(self.obj)
        if cover and os.path.isfile(cover):
            self._loader.add_task(self.obj["id"], cover, self.cache_dir)

class BookshelfView(QWidget):
    object_opened = pyqtSignal(dict)
    tags_updated = pyqtSignal()

    def __init__(self, svc, storage_root: str, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.storage_root = storage_root
        self.cache_dir = get_thumb_cache_dir(storage_root)
        self._cards: dict[str, ObjectCard] = {}
        self._loader = ThumbnailLoader()
        self._loader.loaded.connect(self._on_thumb_loaded)
        self._loader.start()
        self.destroyed.connect(self._on_loader_destroyed)
        self._delete_workers: list = []
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._relayout)
        self._build()

    def _on_loader_destroyed(self):
        self._loader.stop()
        # run() 的 _running 检查保证当前任务完成后退出，无限等待无超时风险
        self._loader.wait()

    def update_storage_root(self, storage_root: str):
        """库根目录变更后更新缓存目录（迁移成功时由 MainWindow 调用）。"""
        self.storage_root = storage_root
        self.cache_dir = get_thumb_cache_dir(storage_root)

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
            card = ObjectCard(obj, self.cache_dir, self.svc, self._loader)
            card.double_clicked.connect(self.object_opened)
            card.edit_requested.connect(self._on_edit)
            card.delete_requested.connect(self._on_delete)
            card.cover_change_requested.connect(self._on_change_cover)
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(card, row, col)
            self._cards[obj["id"]] = card

    def _on_thumb_loaded(self, obj_id: str, thumb_path: str):
        """卡片可能已被重建/销毁，按当前卡片字典匹配。"""
        card = self._cards.get(obj_id)
        if card is not None:
            card._on_thumb_loaded(obj_id, thumb_path)

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
            self.svc.update_object_name(obj["id"], name)
            self.svc.set_object_tags(obj["id"], tags)
            self.tags_updated.emit()

    def _on_delete(self, obj: dict):
        """删除对象，可选择是否同时删除本地文件"""
        dlg = FramelessDialog("🗑️", self)
        dlg.setMinimumWidth(400)
        dlg.setModal(True)

        # 应用与 TagEditorDialog 相同的外框描边和背景样式
        dlg.setObjectName("DeleteConfirmDialog")
        dlg.setStyleSheet("""
            #DeleteConfirmDialog {
                border: 1px solid #c4a484; 
                background: #f5f0e8;
                padding: 1px; /* 强制内边距1px，防止背景色吞噬边框 */
            }
        """)

        # 1. 主布局：设置与 TagEditorDialog 相同的 20px 基础边距
        layout = QVBoxLayout(dlg)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # 2. 文本内容区域：使用独立布局包装，并追加左右 8px 内边距防止贴边
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(8, 0, 8, 0)
        content_layout.setSpacing(12)

        # 消息文本
        msg = QLabel(f"确定要从书架删除「{obj['name']}」吗？")
        msg.setStyleSheet("font-size: 14px; color: #2a2418;")
        content_layout.addWidget(msg)

        # 警告文本
        warn = QLabel("注意：删除后此操作无法撤销！")
        warn.setStyleSheet("font-size: 12px; color: #8b2a2a;")
        content_layout.addWidget(warn)

        # 复选框
        checkbox = QCheckBox("同时删除本地图片文件")
        checkbox.setStyleSheet("font-size: 13px; color: #5a5040;")
        content_layout.addWidget(checkbox)

        # 将内容布局加入主布局
        layout.addLayout(content_layout)

        # 3. 按钮区域：同样追加左右 8px 内边距
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(8, 0, 8, 0)
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #ede8df; border: 1px solid #c8bfaa;
                border-radius: 5px; color: #5a5040; padding: 6px 12px;
            }
            QPushButton:hover { background: #e4ddd2; }
        """)
        cancel_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("确认删除")
        confirm_btn.setFixedWidth(100)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background: #8b2a2a; border: 1px solid #6b1a1a;
                border-radius: 5px; color: #f5ede8; padding: 6px 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: #a03030; }
        """)
        confirm_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(confirm_btn)

        layout.addLayout(btn_layout)

        # 在所有布局组装完成后，安装自定义标题栏
        dlg._install_titlebar()
        layout = dlg.layout()
        l, t, r, b = layout.getContentsMargins()
        layout.setContentsMargins(
            l,
            t + 5,
            2,  # 右边距按“当前底部距离”对齐（减 1px）
            -2
        )
        dlg.adjustSize()

        # --- 后续执行逻辑 ---
        if dlg.exec() == QDialog.DialogCode.Accepted:
            delete_files = checkbox.isChecked()
            worker = _DeleteObjectWorker(
                self.svc.db_path, obj["id"], delete_files, self.storage_root
            )
            worker.ok.connect(self._on_delete_done)
            worker.err.connect(self._on_delete_error)
            # 保存引用避免 GC 导致线程被析构；完成后移出列表
            self._delete_workers.append(worker)
            worker.finished.connect(
                lambda w=worker: self._delete_workers.remove(w)
                if w in self._delete_workers else None
            )
            worker.start()

    def _on_delete_done(self):
        self.tags_updated.emit()

    def _on_delete_error(self, msg: str):
        QMessageBox.warning(
            self, "删除失败",
            f"无法删除本地文件：{msg}\n数据库记录已删除。"
        )
        self.tags_updated.emit()

    def _on_change_cover(self, obj: dict):
        from PyQt6.QtWidgets import QFileDialog
        images = self.svc.get_images(obj["id"])
        if not images:
            QMessageBox.information(self, "提示", "该对象中没有图片")
            return
        storage = self.svc.get_object(obj["id"]).get("storage_path", "")
        ext_filter = "图片文件 (" + " ".join(f"*{e}" for e in SUPPORTED_FORMATS) + ")"
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", storage, ext_filter
        )
        if path:
            self.svc.update_object_cover(obj["id"], path)
            self.tags_updated.emit()