"""
缩略图生成工具
"""
import os
import hashlib
from PIL import Image
from config import THUMBNAIL_SIZE, GRID_THUMB_SIZE, SUPPORTED_FORMATS


def get_thumb_cache_dir(base_dir: str) -> str:
    cache = os.path.join(base_dir, ".thumbcache")
    os.makedirs(cache, exist_ok=True)
    return cache


def _thumb_path(cache_dir: str, source_path: str, size: tuple) -> str:
    h = hashlib.md5(f"{source_path}{size}".encode()).hexdigest()
    return os.path.join(cache_dir, f"{h}.jpg")


def generate_thumbnail(source_path: str, cache_dir: str,
                        size: tuple = THUMBNAIL_SIZE) -> str | None:
    """生成缩略图，返回缓存路径；失败返回 None"""
    if not os.path.isfile(source_path):
        return None
    ext = os.path.splitext(source_path)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        return None

    thumb_path = _thumb_path(cache_dir, source_path, size)
    if os.path.exists(thumb_path):
        return thumb_path

    try:
        img = Image.open(source_path)
        img = img.convert("RGB")
        img.thumbnail(size, Image.LANCZOS)
        # 创建带背景的缩略图（保持比例，填充黑色）
        bg = Image.new("RGB", size, (20, 20, 30))
        offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
        bg.paste(img, offset)
        bg.save(thumb_path, "JPEG", quality=85)
        return thumb_path
    except Exception as e:
        print(f"[Thumbnail] Error: {e} | {source_path}")
        return None


def generate_grid_thumbnail(source_path: str, cache_dir: str) -> str | None:
    return generate_thumbnail(source_path, cache_dir, GRID_THUMB_SIZE)


def get_first_image_in_dir(storage_path: str) -> str | None:
    """获取目录中的第一张图片"""
    if not os.path.isdir(storage_path):
        return None
    files = sorted(f for f in os.listdir(storage_path)
                   if os.path.splitext(f)[1].lower() in SUPPORTED_FORMATS)
    if files:
        return os.path.join(storage_path, files[0])
    return None