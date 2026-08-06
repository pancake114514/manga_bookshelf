"""
配置常量 - 应用全局常量（不含可变状态）

可变状态（筛选/搜索/R18）由 MainWindow 持有，见 ui/main_window.py。
"""
APP_NAME = "MangaShelf"
SUPPORTED_FORMATS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff", ".tif")
THUMBNAIL_SIZE = (220, 300)
GRID_THUMB_SIZE = (160, 160)
# 目录视图封面缩略图尺寸（clear_cached_thumbs 清理时须包含此尺寸）
COVER_THUMB_SIZE = (180, 240)

TAG_CATEGORIES = {
    "work":      "作品",
    "author":    "作者",
    "character": "角色",
    "cm":        "CM",
    "censored":  "修正",
    "r18": "R-18",
}

TAG_CATEGORY_ORDER = ["work", "author", "character", "cm", "censored", "r18"]
