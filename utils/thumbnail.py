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
    """
    生成缩略图，返回缓存路径；失败返回 None。
    策略：等比缩放后居中裁剪到目标尺寸，不填充任何背景色。
    """
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
        # 处理 EXIF 旋转
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        img = img.convert("RGB")
        target_w, target_h = size
        src_w, src_h = img.size

        # 计算等比缩放后能覆盖目标尺寸的最小缩放比
        scale = max(target_w / src_w, target_h / src_h)
        new_w = round(src_w * scale)
        new_h = round(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        # 居中裁剪到目标尺寸
        left = (new_w - target_w) // 2
        top  = (new_h - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))

        img.save(thumb_path, "JPEG", quality=85)
        return thumb_path
    except Exception as e:
        print(f"[Thumbnail] Error: {e} | {source_path}")
        return None


def generate_grid_thumbnail(source_path: str, cache_dir: str) -> str | None:
    return generate_thumbnail(source_path, cache_dir, GRID_THUMB_SIZE)


def clear_cached_thumbs(cache_dir: str, source_paths: list) -> int:
    """
    删除与 source_paths 对应的缩略图缓存文件（含两种尺寸），
    返回实际删除的文件数。用于删除对象后清理缓存。
    """
    if not source_paths:
        return 0
    removed = 0
    for src in source_paths:
        for size in (THUMBNAIL_SIZE, GRID_THUMB_SIZE):
            p = _thumb_path(cache_dir, src, size)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                    removed += 1
                except OSError:
                    pass
    return removed


def get_first_image_in_dir(storage_path: str) -> str | None:
    """获取目录中的第一张图片"""
    if not os.path.isdir(storage_path):
        return None
    files = sorted(f for f in os.listdir(storage_path)
                   if os.path.splitext(f)[1].lower() in SUPPORTED_FORMATS)
    if files:
        return os.path.join(storage_path, files[0])
    return None