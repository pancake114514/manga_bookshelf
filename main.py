"""
MangaShelf - 二次元图片管理器
入口文件
"""
import sys
import os

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from database import Database
from config import app_state
from ui.widgets import STYLE_MAIN, SectionLabel


def check_writable(path: str) -> tuple[bool, str]:
    """检查目录是否存在且有写权限"""
    if not os.path.isdir(path):
        return False, f"目录不存在：\n{path}"
    test_file = os.path.join(path, ".manga_shelf_write_test")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True, ""
    except PermissionError:
        return False, f"没有写入权限，请选择其他目录：\n{path}"
    except Exception as e:
        return False, f"目录不可用：{e}"


class FirstRunDialog(QDialog):
    """首次运行时选择图库根目录"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("欢迎使用 MangaShelf")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._path = ""
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        title = QLabel("首次启动设置")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #6b3a2a; font-family: 'Georgia', serif;")
        layout.addWidget(title)

        desc = QLabel(
            "请选择一个目录作为图库的存储根目录。\n"
            "所有导入的图片将会被复制到这个目录下进行管理。\n"
            "注意：请选择有写入权限的目录（避免 Program Files 等系统目录）。"
        )
        desc.setStyleSheet("color: #5a5040; font-size: 13px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addWidget(SectionLabel("图库根目录"))

        row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("选择目录…")
        self.path_input.setReadOnly(True)
        row.addWidget(self.path_input)

        browse_btn = QPushButton("浏览…")
        browse_btn.setFixedWidth(72)
        browse_btn.clicked.connect(self._browse)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        self.warn_label = QLabel()
        self.warn_label.setStyleSheet("color: #8b2a2a; font-size: 12px;")
        self.warn_label.setWordWrap(True)
        self.warn_label.hide()
        layout.addWidget(self.warn_label)

        layout.addStretch()

        self.confirm_btn = QPushButton("确定并开始使用")
        self.confirm_btn.setObjectName("accent")
        self.confirm_btn.setFixedHeight(42)
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background: #6b3a2a; border: 1px solid #8b4a35;
                border-radius: 8px; color: #f5ede8;
                font-size: 14px; font-weight: 600;
            }
            QPushButton:hover { background: #8b4a35; }
            QPushButton:disabled {
                background: #e0d8cc; color: #a09080; border-color: #c8bfaa;
            }
        """)
        self.confirm_btn.clicked.connect(self._confirm)
        self.confirm_btn.setEnabled(False)
        layout.addWidget(self.confirm_btn)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择图库根目录")
        if not path:
            return
        ok, err = check_writable(path)
        if not ok:
            self.warn_label.setText("⚠ " + err)
            self.warn_label.show()
            self.confirm_btn.setEnabled(False)
            self._path = ""
            self.path_input.setText("")
            return
        self._path = path
        self.path_input.setText(path)
        self.warn_label.hide()
        self.confirm_btn.setEnabled(True)

    def _confirm(self):
        if not self._path:
            QMessageBox.warning(self, "提示", "请先选择一个目录")
            return
        ok, err = check_writable(self._path)
        if not ok:
            QMessageBox.warning(self, "目录不可用", err)
            return
        self.accept()

    def get_path(self) -> str:
        return self._path


def get_config_path() -> str:
    """获取配置数据库路径（存放在用户数据目录）"""
    if sys.platform == "win32":
        data_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        data_dir = os.path.expanduser("~/.local/share")
    app_dir = os.path.join(data_dir, "MangaShelf")
    os.makedirs(app_dir, exist_ok=True)
    return os.path.join(app_dir, "library.db")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MangaShelf")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE_MAIN)

    db_path = get_config_path()
    db = Database(db_path)

    # 检查存储根目录是否有效（不存在或没有写权限则重新选择）
    storage_root = db.get_config("storage_root")
    need_setup = False
    if not storage_root:
        need_setup = True
    elif not os.path.isdir(storage_root):
        need_setup = True
    else:
        ok, _ = check_writable(storage_root)
        if not ok:
            need_setup = True

    if need_setup:
        dlg = FirstRunDialog()
        dlg.setStyleSheet(STYLE_MAIN)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
        storage_root = dlg.get_path()
        db.set_config("storage_root", storage_root)

    app_state.init(db)

    from ui.main_window import MainWindow
    window = MainWindow(storage_root)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()