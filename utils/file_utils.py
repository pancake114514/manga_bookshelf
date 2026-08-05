"""
文件操作工具
"""
import os
import shutil
import logging
from config import SUPPORTED_FORMATS

logger = logging.getLogger(__name__)


def collect_images(directory: str) -> list[str]:
    """
    收集目录中所有支持格式的图片，按文件名升序排列。
    以 '.' 开头的隐藏文件不收集。
    """
    result = []
    for fname in sorted(os.listdir(directory)):
        if fname.startswith("."):
            continue
        if os.path.splitext(fname)[1].lower() in SUPPORTED_FORMATS:
            result.append(os.path.join(directory, fname))
    return result


def next_seq_number(storage_obj_dir: str) -> int:
    """
    扫描存储目录，返回下一个可用序号（已有文件最大序号 + 1，从 1 开始）。
    只识别形如 000001.ext 的文件名（纯数字部分）。
    """
    max_seq = 0
    if os.path.isdir(storage_obj_dir):
        for fname in os.listdir(storage_obj_dir):
            if fname.startswith("."):
                continue
            base, ext = os.path.splitext(fname)
            if ext.lower() in SUPPORTED_FORMATS and base.isdigit():
                max_seq = max(max_seq, int(base))
    return max_seq + 1


def copy_image_with_seq_name(src_path: str, storage_obj_dir: str,
                              seq: int) -> tuple[str, str] | tuple[None, None]:
    """
    将图片复制到存储目录，以 7 位序号重命名（如 000001.jpg）。
    返回 (filename, dest_path)，失败返回 (None, None)。
    """
    os.makedirs(storage_obj_dir, exist_ok=True)
    ext = os.path.splitext(src_path)[1].lower()
    filename = f"{seq:07d}{ext}"
    dest = os.path.join(storage_obj_dir, filename)
    # 序号冲突时继续递增（理论上不应发生，防御性处理）
    while os.path.exists(dest):
        seq += 1
        filename = f"{seq:07d}{ext}"
        dest = os.path.join(storage_obj_dir, filename)
    try:
        shutil.copy2(src_path, dest)
        return filename, dest
    except Exception as e:
        logger.warning("图片复制失败: %s | %s", e, src_path)
        return None, None


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