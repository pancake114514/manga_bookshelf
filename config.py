"""
配置管理 - 应用全局状态
"""
import os
import uuid
from database import Database

APP_NAME = "MangaShelf"
SUPPORTED_FORMATS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff", ".tif")
THUMBNAIL_SIZE = (220, 300)
GRID_THUMB_SIZE = (160, 160)

TAG_CATEGORIES = {
    "work":      "作品",
    "author":    "作者",
    "character": "角色",
    "cm":        "CM",
    "r18":       "R-18",
    "censored":  "修正",
}

TAG_CATEGORY_ORDER = ["work", "author", "character", "cm", "r18", "censored"]


class AppState:
    """全局应用状态单例"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def init(self, db: Database):
        if self._initialized:
            return
        self.db = db
        self.show_r18 = False
        self.tag_filters: dict = {}
        self.search_keyword: str = ""
        self._initialized = True

    def generate_id(self) -> str:
        return str(uuid.uuid4())

    def sanitize_dirname(self, name: str) -> str:
        """Windows 路径名校验 - 移除非法字符"""
        illegal = r'\/:*?"<>|'
        for ch in illegal:
            name = name.replace(ch, "_")
        name = name.strip(". ")
        return name or "unnamed"


app_state = AppState()
