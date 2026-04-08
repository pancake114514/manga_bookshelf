import os
import time

from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QProgressDialog, QPushButton, QVBoxLayout, QWidget
)
from PyQt6.QtCore import pyqtSignal

from config import app_state
from library_manager import (
    LibraryMigrationError,
    check_writable,
    migrate_library,
)
from .widgets import C, FramelessDialog, SectionLabel, STYLE_MAIN


class LibraryDialog(FramelessDialog):
    storage_root_changed = pyqtSignal(str)

    def __init__(self, current_path: str, parent=None):
        super().__init__("库管理", parent)
        self._current_path = current_path
        self._selected_path = current_path
        self.setMinimumWidth(560)
        self.setModal(True)
        self.setStyleSheet(STYLE_MAIN)
        self._build()
        self._install_titlebar("🗃️")

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        intro = QLabel(
            "修改库路径会迁移所有已导入对象到新的根目录。迁移完成前，当前库路径不会生效。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {C['text2']}; font-size: 13px;")
        layout.addWidget(intro)

        layout.addWidget(SectionLabel("当前库路径"))

        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet(
            f"background: #ffffff; border: 1px solid {C['border']}; "
            f"border-radius: 6px; padding: 10px; color: {C['text']};"
        )
        layout.addWidget(self.path_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        browse_btn = QPushButton("选择目录")
        browse_btn.clicked.connect(self._browse)
        btn_row.addWidget(browse_btn)

        self.save_btn = QPushButton("开始迁移")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: #ede8df;
                border: 1px solid #c8bfaa;
                border-radius: 5px;
                color: #5a5040;
                padding: 5px 14px;
                font-weight: 500;
            }
            QPushButton:hover:!disabled {
                background: #BFBFBF;
                border-color: #c8bfaa;
                color: #2a2418;
            }
            QPushButton:disabled {
                background: #BFBFBF;
                border: 1px solid #c8bfaa;
                color: #d7d1c7;
            }
        """)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.warn_label = QLabel()
        self.warn_label.setWordWrap(True)
        self.warn_label.setStyleSheet("color: #8b2a2a; font-size: 12px;")
        self.warn_label.hide()
        layout.addWidget(self.warn_label)

        hint = QLabel(
            "迁移会同步更新对象目录、图片路径和封面路径。目标目录下若已存在同名对象目录，迁移会直接中止。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {C['text3']}; font-size: 12px;")
        layout.addWidget(hint)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)

        root.addWidget(content)
        self._refresh_path_label()

    def _refresh_path_label(self):
        self.path_label.setText(self._selected_path or "未设置")
        changed = os.path.normcase((self._selected_path or "").strip()) != os.path.normcase((self._current_path or "").strip())
        self.save_btn.setEnabled(changed)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择新的图库目录")
        if not path:
            return
        ok, err = check_writable(path)
        if not ok:
            self.warn_label.setText(err)
            self.warn_label.show()
            return
        self.warn_label.hide()
        self._selected_path = path
        self._refresh_path_label()

    def _save(self):
        path = (self._selected_path or "").strip()
        if not path:
            QMessageBox.warning(self, "Notice", "Please choose a directory first.")
            return
        ok, err = check_writable(path)
        if not ok:
            QMessageBox.warning(self, "Directory Unavailable", err)
            return
        if os.path.normcase(path) == os.path.normcase(self._current_path):
            self.accept()
            return

        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Icon.Warning)
        confirm.setWindowTitle("确认迁移？")
        confirm.setText("当前库将被迁移到新目录下")
        confirm.setInformativeText(
            f"当前路径:\n{self._current_path}\n\n"
            f"目标路径:\n{path}\n\n"
            "所有对象将被迁移，在完成前请不要关闭窗口"
        )
        confirm.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        confirm.button(QMessageBox.StandardButton.Yes).setText("开始迁移")
        confirm.button(QMessageBox.StandardButton.Cancel).setText("取消")
        if confirm.exec() != QMessageBox.StandardButton.Yes:
            return

        prog = QProgressDialog("准备开始迁移...", None, 0, 0, self)
        prog.setWindowTitle("转移中...")
        prog.setModal(True)
        prog.setMinimumWidth(360)
        prog.setCancelButton(None)

        started_at = time.monotonic()
        progress_visible = False

        try:
            moved_count = 0
            def on_progress(cur: int, total: int, message: str):
                nonlocal progress_visible
                prog.setMaximum(total)
                prog.setValue(cur)
                prog.setLabelText(message)
                if not progress_visible and time.monotonic() - started_at >= 0.25:
                    prog.show()
                    progress_visible = True
                if progress_visible:
                    QApplication.processEvents()

            moved_count = migrate_library(app_state.db, path, progress=on_progress)
        except LibraryMigrationError as exc:
            if progress_visible:
                prog.close()
            QMessageBox.critical(self, "Migration Failed", str(exc))
            return
        except Exception as exc:
            if progress_visible:
                prog.close()
            QMessageBox.critical(self, "Migration Failed", str(exc))
            return

        if progress_visible:
            prog.close()
        self.storage_root_changed.emit(path)
        QMessageBox.information(self, "Migration Complete", f"Moved {moved_count} objects to the new library directory.")
        self.accept()
