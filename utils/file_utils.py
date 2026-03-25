"""
文件操作工具
"""
import os
import shutil
import uuid
from config import SUPPORTED_FORMATS


def collect_images(directory: str) -> list[str]:
    """收集目录中所有支持格式的图片，按文件名排序"""
    result = []
    for fname in sorted(os.listdir(directory)):
        if os.path.splitext(fname)[1].lower() in SUPPORTED_FORMATS:
            result.append(os.path.join(directory, fname))
    return result


def copy_image_to_storage(src_path: str, storage_obj_dir: str) -> str | None:
    """
    将图片复制到对象存储目录。
    如文件名冲突则添加 uuid 前缀。
    返回目标路径，失败返回 None。
    """
    os.makedirs(storage_obj_dir, exist_ok=True)
    filename = os.path.basename(src_path)
    dest = os.path.join(storage_obj_dir, filename)
    if os.path.exists(dest):
        base, ext = os.path.splitext(filename)
        filename = f"{base}_{uuid.uuid4().hex[:6]}{ext}"
        dest = os.path.join(storage_obj_dir, filename)
    try:
        shutil.copy2(src_path, dest)
        return dest
    except Exception as e:
        print(f"[FileUtils] Copy error: {e}")
        return None


def import_directory_to_storage(src_dir: str, storage_obj_dir: str) -> list[tuple[str, str]]:
    """
    将源目录中的所有图片复制到存储目录。
    返回 [(filename, dest_path), ...] 列表。
    """
    images = collect_images(src_dir)
    results = []
    for src in images:
        dest = copy_image_to_storage(src, storage_obj_dir)
        if dest:
            results.append((os.path.basename(dest), dest))
    return results


def validate_windows_path_name(name: str) -> tuple[bool, str]:
    """校验是否是合法 Windows 路径名，返回 (ok, error_msg)"""
    if not name or not name.strip():
        return False, "名称不能为空"
    illegal = set(r'\/:*?"<>|')
    bad = [c for c in name if c in illegal]
    if bad:
        return False, f"包含非法字符：{''.join(set(bad))}"
    reserved = {"CON","PRN","AUX","NUL","COM1","COM2","COM3","COM4",
                 "COM5","COM6","COM7","COM8","COM9","LPT1","LPT2",
                 "LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"}
    if name.upper().split('.')[0] in reserved:
        return False, f"'{name}' 是 Windows 保留名称"
    if name != name.strip('. '):
        return False, "名称不能以点或空格开头/结尾"
    return True, ""
