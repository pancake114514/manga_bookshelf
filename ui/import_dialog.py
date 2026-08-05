import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QProgressDialog, QApplication,
    QFrame, QListWidget, QListWidgetItem, QDialogButtonBox, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor
from config import SUPPORTED_FORMATS
from .widgets import SectionLabel, Divider, FramelessDialog, C, STYLE_MAIN
from .tag_editor import TagEditorDialog
import uuid


class ImportWorker(QThread):
    """后台导入线程（使用独立 LibraryService，避免共享 sqlite 连接）"""
    progress = pyqtSignal(int, int)
    import_finished = pyqtSignal(str, int, int)   # obj_id, 成功数, 失败数
    error = pyqtSignal(str)

    def __init__(self, db_path: str, obj_id: str, obj_name: str, tags: dict,
                 source_dir: str, storage_root: str, is_new: bool):
        super().__init__()
        self.db_path = db_path
        self.obj_id = obj_id
        self.obj_name = obj_name
        self.tags = tags
        self.source_dir = source_dir
        self.storage_root = storage_root
        self.is_new = is_new

    def run(self):
        from services.library_service import LibraryService
        svc = None
        try:
            svc = LibraryService(self.db_path)
            ok, fail = svc.import_directory(
                self.obj_id, self.obj_name, self.tags,
                self.source_dir, self.storage_root, self.is_new,
                progress_cb=lambda cur, total: self.progress.emit(cur, total),
            )
            self.import_finished.emit(self.obj_id, ok, fail)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if svc is not None:
                svc.close()


class ImportDialog(FramelessDialog):
    import_done = pyqtSignal(str)

    def __init__(self, svc, storage_root: str, parent=None):
        super().__init__("导入图片", parent)
        self.svc = svc
        self.storage_root = storage_root
        self.setMinimumWidth(480)
        self.setModal(True)
        self.setStyleSheet(STYLE_MAIN)
        self._build()
        self._install_titlebar("📥")

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(16, 16, 16, 16)  # 内容内边距，不影响边框
        cl.setSpacing(12)

        title = QLabel("选择导入方式")
        title.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {C['text']};")
        cl.addWidget(title)

        self.btn_new = QPushButton("📁  新建目录（导入文件夹）")
        self.btn_new.setMinimumHeight(52)
        self.btn_new.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['accent_bg']};
                border: 1px solid {C['accent_bd']};
                border-radius: 8px;
                color: {C['accent']};
                font-size: 14px;
                text-align: left;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background-color: {C['bg3']};
                border-color: {C['accent2']};
            }}
        """)
        self.btn_new.clicked.connect(self._import_new_directory)
        cl.addWidget(self.btn_new)

        self.btn_existing = QPushButton("🖼  导入文件夹到已有目录")
        self.btn_existing.setMinimumHeight(52)
        self.btn_existing.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['bg2']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                color: {C['blue']};
                font-size: 14px;
                text-align: left;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background-color: {C['bg3']};
                border-color: {C['border2']};
            }}
        """)
        self.btn_existing.clicked.connect(self._import_to_existing)
        cl.addWidget(self.btn_existing)

        self.btn_files = QPushButton("📄  导入单张/多张图片到已有目录")
        self.btn_files.setMinimumHeight(52)
        self.btn_files.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['bg2']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                color: {C['green']};
                font-size: 14px;
                text-align: left;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background-color: {C['bg3']};
                border-color: {C['border2']};
            }}
        """)
        self.btn_files.clicked.connect(self._import_single_files)
        cl.addWidget(self.btn_files)

        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        cl.addWidget(cancel)

        root.addWidget(content)

    def _import_new_directory(self):
        folder = QFileDialog.getExistingDirectory(
            self, "选择要导入的文件夹", "",
            QFileDialog.Option.ShowDirsOnly
        )
        if not folder:
            return

        from utils.file_utils import collect_images
        images = collect_images(folder)
        if not images:
            QMessageBox.warning(self, "提示", "所选文件夹中没有支持的图片文件")
            return

        default_name = os.path.basename(folder)
        obj_id = str(uuid.uuid4())

        dlg = TagEditorDialog({"name": default_name, "tags": {}}, self)
        dlg.setWindowTitle(f"新建目录 — 共 {len(images)} 张图片")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        name = dlg.get_name()
        tags = dlg.get_tags()

        from utils.file_utils import validate_windows_path_name
        ok, err = validate_windows_path_name(name)
        if not ok:
            QMessageBox.warning(self, "名称无效", err)
            return

        self._run_import(obj_id, name, tags, folder, is_new=True)

    def _import_to_existing(self):
        objects = self.svc.get_all_objects(include_r18=True)
        dir_objs = [o for o in objects if o["type"] == "directory"]
        if not dir_objs:
            QMessageBox.information(self, "提示", "还没有创建目录，请先新建")
            return

        sel_dlg = _SelectObjectDialog(dir_objs, self)
        if sel_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target_obj = sel_dlg.selected_object()
        if not target_obj:
            return

        folder = QFileDialog.getExistingDirectory(
            self, "选择要导入图片的文件夹", "",
            QFileDialog.Option.ShowDirsOnly
        )
        if not folder:
            return

        from utils.file_utils import collect_images
        images = collect_images(folder)
        if not images:
            QMessageBox.warning(self, "提示", "所选文件夹中没有支持的图片文件")
            return

        self._run_import(target_obj["id"], target_obj["name"], {},
                         folder, is_new=False)

    def _import_single_files(self):
        objects = self.svc.get_all_objects(include_r18=True)
        dir_objs = [o for o in objects if o["type"] == "directory"]
        if not dir_objs:
            QMessageBox.information(self, "提示", "还没有创建目录，请先新建")
            return

        sel_dlg = _SelectObjectDialog(dir_objs, self)
        if sel_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target_obj = sel_dlg.selected_object()
        if not target_obj:
            return

        from config import SUPPORTED_FORMATS
        ext_filter = "图片文件 (" + " ".join(f"*{e}" for e in SUPPORTED_FORMATS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择要导入的图片文件", "", ext_filter
        )
        if not paths:
            return

        ok, fail = self.svc.import_single_files(
            target_obj["id"], paths, self.storage_root
        )
        msg = f"成功导入 {ok} 张图片"
        if fail:
            msg += f"，{fail} 张失败"
        QMessageBox.information(self, "导入完成", msg)
        self.accept()
        self.import_done.emit(target_obj["id"])

    def _run_import(self, obj_id, name, tags, source_dir, is_new):
        prog = QProgressDialog("正在导入图片…", "取消", 0, 100, self)
        prog.setWindowTitle("导入中")
        prog.setModal(True)
        prog.setMinimumWidth(320)
        prog.show()

        self.worker = ImportWorker(self.svc.db_path, obj_id, name, tags,
                                   source_dir, self.storage_root, is_new)

        def on_progress(cur, total):
            if total > 0:
                prog.setMaximum(total)
                prog.setValue(cur)
                prog.setLabelText(f"正在导入图片… ({cur}/{total})")
            QApplication.processEvents()

        def on_finished(oid, ok, fail):
            prog.close()
            msg = f"导入完成：成功 {ok} 张图片"
            if fail:
                msg += f"，{fail} 张失败"
            QMessageBox.information(self, "导入完成", msg)
            self.accept()
            self.import_done.emit(oid)

        def on_error(msg):
            prog.close()
            QMessageBox.critical(self, "导入失败", msg)

        self.worker.progress.connect(on_progress)
        self.worker.import_finished.connect(on_finished)
        self.worker.error.connect(on_error)
        self.worker.start()


class _SelectObjectDialog(FramelessDialog):
    def __init__(self, objects: list, parent=None):
        super().__init__("选择目标目录", parent)
        self.setMinimumWidth(380)
        self.setStyleSheet(STYLE_MAIN)
        self._objects = objects
        self._selected = None
        self._build()
        self._install_titlebar()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(16, 16, 16, 16)  # 内容内边距，不影响边框
        cl.setSpacing(12)

        cl.addWidget(QLabel("请选择要导入到的目标目录："))

        self.list_widget = QListWidget()
        for obj in self._objects:
            item = QListWidgetItem(obj["name"])
            item.setData(Qt.ItemDataRole.UserRole, obj)
            self.list_widget.addItem(item)
        if self._objects:
            self.list_widget.setCurrentRow(0)
        self.list_widget.itemDoubleClicked.connect(lambda: self.accept())
        cl.addWidget(self.list_widget)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        cl.addWidget(btns)

        root.addWidget(content)

    def selected_object(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None