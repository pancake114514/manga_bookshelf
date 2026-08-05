"""pytest 公共配置与 fixtures。"""
import os
import sys
import uuid

import pytest

# 项目根目录加入 sys.path（运行 pytest 时保证 services/ utils/ 可导入）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.library_service import LibraryService  # noqa: E402


@pytest.fixture
def make_images():
    """生成指定数量的小 PNG 图片，返回路径列表。"""
    from PIL import Image

    def _make(d: str, count: int = 3, size: tuple = (100, 150)) -> list:
        os.makedirs(d, exist_ok=True)
        paths = []
        for i in range(count):
            p = os.path.join(d, f"img{i:03d}.png")
            Image.new("RGB", size, (i * 40, 20, 20)).save(p)
            paths.append(p)
        return paths

    return _make


@pytest.fixture
def svc_and_root(tmp_path):
    """创建独立 LibraryService + 图库根目录；测试结束后关闭连接。"""
    db_path = str(tmp_path / "library.db")
    root = str(tmp_path / "storage")
    os.makedirs(root)
    svc = LibraryService(db_path)
    svc.set_config("storage_root", root)
    yield svc, root
    svc.close()


@pytest.fixture
def new_object_id() -> str:
    return str(uuid.uuid4())
