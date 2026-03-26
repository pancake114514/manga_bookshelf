"""
导入对话框
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QProgressDialog, QApplication,
    QFrame, QListWidget, QListWidgetItem, QRadioButton,
    QButtonGroup, QWidget, QGroupBox, QComboBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from config import app_state, SUPPORTED_FORMATS
from .widgets import SectionLabel, Divider, FramelessDialog, C
from .tag_editor import TagEditorDialog
import uuid


class ImportWorker(QThread):
    """后台导入线程"""
    progress = pyqtSignal(int, int)   # current, total
    finished = pyqtSignal(str)         # obj_id
    error = pyqtSignal(str)

    def __init__(self, obj_id: str, obj_name: str, tags: dict,
                 source_dir: str, storage_root: str, is_new: bool):
        super().__init__()
        self.obj_id = obj_id
        self.obj_name = obj_name
        self.tags = tags
        self.source_dir = source_dir
        self.storage_root = storage_root
        self.is_new = is_new

    def run(self):
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from utils.file_utils import (
                collect_images, copy_image_with_seq_name, next_seq_number
            )
            db = app_state.db

            storage_obj_dir = os.path.join(self.storage_root, self.obj_name)
            os.makedirs(storage_obj_dir, exist_ok=True)

            if self.is_new:
                db.create_object(self.obj_id, "directory", self.obj_name,
                                 self.source_dir, storage_obj_dir)
                db.set_tags(self.obj_id, self.tags)

            images = collect_images(self.source_dir)
            total = len(images)
            # 接续已有文件的序号
            seq = next_seq_number(storage_obj_dir)
            sort_start = db.get_image_count(self.obj_id)
            for i, src in enumerate(images):
                filename, dest = copy_image_with_seq_name(src, storage_obj_dir, seq)
                if dest:
                    img_id = str(uuid.uuid4())
                    db.add_image(img_id, self.obj_id, filename, dest, sort_start + i)
                    seq += 1
                self.progress.emit(i + 1, total)

            # 自动设置封面为第一张（仅新建对象时）
            if self.is_new:
                first_img = db.get_images(self.obj_id)
                if first_img and not db.get_object(self.obj_id).get("cover_image"):
                    db.update_object_cover(self.obj_id, first_img[0]["filepath"])

            self.finished.emit(self.obj_id)
        except Exception as e:
            self.error.emit(str(e))


class ImportDialog(FramelessDialog):
    """
    导入对话框：
    - 新建目录对象（选择文件夹）
    - 导入到已存在的目录对象（选择文件后复制）
    """
    import_done = pyqtSignal(str)   # 导入完成，传 obj_id

    def __init__(self, storage_root: str, parent=None):
        super().__init__("导入图片", parent)
        self.storage_root = storage_root
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build()
        self._install_titlebar("📥")

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("选择导入方式")
        title.setStyleSheet("font-size: 16px; font-weight: 600; color: #e8e0f0;")
        layout.addWidget(title)

        # 选项卡
        self.btn_new = QPushButton("📁  新建目录对象（导入文件夹）")
        self.btn_new.setObjectName("accent")
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
        layout.addWidget(self.btn_new)

        self.btn_existing = QPushButton("🖼  导入文件夹到已有目录对象")
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
        layout.addWidget(self.btn_existing)

        self.btn_files = QPushButton("📄  导入单张/多张图片到已有目录对象")
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
        layout.addWidget(self.btn_files)

        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def _import_new_directory(self):
        folder = QFileDialog.getExistingDirectory(
            self, "选择要导入的文件夹", "",
            QFileDialog.Option.ShowDirsOnly
        )
        if not folder:
            return

        # 统计图片数量
        from utils.file_utils import collect_images
        images = collect_images(folder)
        if not images:
            QMessageBox.warning(self, "提示", "所选文件夹中没有支持的图片文件")
            return

        default_name = os.path.basename(folder)
        obj_id = str(uuid.uuid4())

        dlg = TagEditorDialog({"name": default_name, "tags": {}}, self)
        dlg.setWindowTitle(f"新建目录对象 — 共 {len(images)} 张图片")
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
        db = app_state.db
        objects = db.get_all_objects(include_r18=True)
        dir_objs = [o for o in objects if o["type"] == "directory"]
        if not dir_objs:
            QMessageBox.information(self, "提示", "还没有目录对象，请先新建")
            return

        # 选择目标对象
        sel_dlg = _SelectObjectDialog(dir_objs, self)
        if sel_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target_obj = sel_dlg.selected_object()
        if not target_obj:
            return

        # 选择文件夹
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
        """选择单张或多张图片文件，复制到已存在的目录对象"""
        db = app_state.db
        objects = db.get_all_objects(include_r18=True)
        dir_objs = [o for o in objects if o["type"] == "directory"]
        if not dir_objs:
            QMessageBox.information(self, "提示", "还没有目录对象，请先新建")
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

        storage_obj_dir = (target_obj.get("storage_path") or "").strip()
        if not storage_obj_dir or not os.path.isdir(storage_obj_dir):
            storage_obj_dir = os.path.join(self.storage_root, target_obj["name"])
        os.makedirs(storage_obj_dir, exist_ok=True)

        from utils.file_utils import copy_image_with_seq_name, next_seq_number
        ok, fail = 0, 0
        cur_count = db.get_image_count(target_obj["id"])
        # 按文件名排序后导入，接续已有序号
        seq = next_seq_number(storage_obj_dir)
        for src in sorted(paths, key=lambda p: os.path.basename(p)):
            if os.path.basename(src).startswith("."):
                continue
            filename, dest = copy_image_with_seq_name(src, storage_obj_dir, seq)
            if dest:
                img_id = str(uuid.uuid4())
                db.add_image(img_id, target_obj["id"],
                             filename, dest, cur_count + ok)
                ok += 1
                seq += 1
            else:
                fail += 1

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

        self.worker = ImportWorker(obj_id, name, tags, source_dir,
                                   self.storage_root, is_new)

        def on_progress(cur, total):
            if total > 0:
                prog.setMaximum(total)
                prog.setValue(cur)
                prog.setLabelText(f"正在导入图片… ({cur}/{total})")
            QApplication.processEvents()

        def on_finished(oid):
            prog.close()
            self.accept()
            self.import_done.emit(oid)

        def on_error(msg):
            prog.close()
            QMessageBox.critical(self, "导入失败", msg)

        self.worker.progress.connect(on_progress)
        self.worker.finished.connect(on_finished)
        self.worker.error.connect(on_error)
        self.worker.start()


class _SelectObjectDialog(FramelessDialog):
    def __init__(self, objects: list, parent=None):
        super().__init__("选择目标目录对象", parent)
        self.setMinimumWidth(360)
        self._objects = objects
        self._selected = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 20, 20)
        layout.setSpacing(12)
        self._install_titlebar()

        layout.addWidget(QLabel("请选择要导入到的目录对象："))

        self.list_widget = QListWidget()
        for obj in objects:
            item = QListWidgetItem(obj["name"])
            item.setData(Qt.ItemDataRole.UserRole, obj)
            self.list_widget.addItem(item)
        self.list_widget.setCurrentRow(0)
        self.list_widget.itemDoubleClicked.connect(lambda: self.accept())
        layout.addWidget(self.list_widget)

        from PyQt6.QtWidgets import QDialogButtonBox
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_object(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None