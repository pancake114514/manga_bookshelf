"""
MangaShelf - 漫画管理器
入口文件
"""
import sys
import os

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from database import Database
from config import app_state
from ui.widgets import STYLE_MAIN, SectionLabel


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
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #c8b8f8;")
        layout.addWidget(title)

        desc = QLabel(
            "请选择一个目录作为图库的存储根目录。\n"
            "所有导入的图片将会被复制到这个目录下进行管理。"
        )
        desc.setStyleSheet("color: #8a7aab; font-size: 13px; line-height: 1.6;")
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

        layout.addStretch()

        confirm_btn = QPushButton("确定并开始使用")
        confirm_btn.setObjectName("accent")
        confirm_btn.setFixedHeight(42)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background: #5c3f8a; border: 1px solid #9a7adb;
                border-radius: 8px; color: #f0e8ff;
                font-size: 14px; font-weight: 600;
            }
            QPushButton:hover { background: #7a55aa; }
            QPushButton:disabled { background: #2a2540; color: #4a3f6b; border-color: #3a2d60; }
        """)
        confirm_btn.clicked.connect(self._confirm)
        confirm_btn.setEnabled(False)
        self.confirm_btn = confirm_btn
        layout.addWidget(confirm_btn)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择图库根目录")
        if path:
            self._path = path
            self.path_input.setText(path)
            self.confirm_btn.setEnabled(True)

    def _confirm(self):
        if not self._path:
            QMessageBox.warning(self, "提示", "请先选择一个目录")
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

    # 应用全局样式
    app.setStyleSheet(STYLE_MAIN)

    # 初始化数据库
    db_path = get_config_path()
    db = Database(db_path)

    # 检查是否首次运行（需要设置存储根目录）
    storage_root = db.get_config("storage_root")
    if not storage_root or not os.path.isdir(storage_root):
        dlg = FirstRunDialog()
        dlg.setStyleSheet(STYLE_MAIN)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
        storage_root = dlg.get_path()
        db.set_config("storage_root", storage_root)

    # 初始化全局状态
    app_state.init(db)

    from ui.main_window import MainWindow
    window = MainWindow(storage_root)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
