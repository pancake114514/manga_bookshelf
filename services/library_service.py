"""
LibraryService - 业务门面层

UI 组件只依赖本服务，不直接访问 Database。
本模块不依赖任何 Qt，可在无 GUI 环境下独立测试。

线程约定：
- 主线程使用一个 LibraryService 实例做查询/变更。
- 后台工作线程（如导入）应使用独立的 LibraryService 实例（传入同一 db_path），
  避免共享同一个 sqlite 连接对象。
"""
import os
import shutil
import uuid
from typing import Callable, Optional

from database import Database
from utils.file_utils import (
    collect_images,
    copy_image_with_seq_name,
    next_seq_number,
)
from utils.thumbnail import clear_cached_thumbs


ProgressCB = Callable[[int, int], None]


class LibraryService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = Database(db_path)

    def close(self):
        """关闭数据库连接。工作线程用完务必调用。"""
        self.db.close()

    # ── 配置 ────────────────────────────────────────────────────────────────

    def get_config(self, key: str) -> Optional[str]:
        return self.db.get_config(key)

    def set_config(self, key: str, value: str):
        self.db.set_config(key, value)

    # ── 查询 ────────────────────────────────────────────────────────────────

    def get_all_objects(self, include_r18: bool = False):
        return self.db.get_all_objects(include_r18=include_r18)

    def search_objects(self, keyword: str, include_r18: bool = False):
        return self.db.search_objects(keyword, include_r18=include_r18)

    def filter_by_tags(self, tag_filters: dict, include_r18: bool = False):
        return self.db.filter_by_tags(tag_filters, include_r18=include_r18)

    def get_object(self, obj_id: str):
        return self.db.get_object(obj_id)

    def get_images(self, obj_id: str):
        return self.db.get_images(obj_id)

    def get_image_count(self, obj_id: str) -> int:
        return self.db.get_image_count(obj_id)

    def get_tag_values(self, category: str):
        return self.db.get_all_tag_values(category)

    def resolve_cover(self, obj: dict) -> Optional[str]:
        """返回对象封面路径；未设置封面时取第一张图片。"""
        if not obj:
            return None
        cover = obj.get("cover_image")
        if cover and os.path.isfile(cover):
            return cover
        first = obj.get("first_image")
        if first and os.path.isfile(first):
            return first
        images = self.db.get_images(obj["id"], limit=1)
        if images and os.path.isfile(images[0]["filepath"]):
            return images[0]["filepath"]
        return None

    # ── 变更 ────────────────────────────────────────────────────────────────

    def update_object_name(self, obj_id: str, name: str):
        self.db.update_object_name(obj_id, name)

    def set_object_tags(self, obj_id: str, tags: dict):
        self.db.set_tags(obj_id, tags)

    def update_object_cover(self, obj_id: str, cover_image: str):
        self.db.update_object_cover(obj_id, cover_image)

    def update_last_read(self, obj_id: str, idx: int):
        self.db.update_last_read(obj_id, idx)

    def delete_object(self, obj_id: str, delete_files: bool = False,
                      storage_root: Optional[str] = None):
        """删除对象（DB + 可选本地文件 + 缩略图缓存）。

        文件删除失败会抛出异常，由调用方（UI）提示；此时 DB 记录已删除，
        与原行为保持一致。
        """
        obj = self.db.get_object(obj_id)

        # 清理该对象关联的缩略图缓存
        if obj and storage_root:
            cache_dir = os.path.join(storage_root, ".thumbcache")
            paths = []
            if obj.get("cover_image"):
                paths.append(obj["cover_image"])
            paths.extend(img["filepath"] for img in self.db.get_images(obj_id))
            clear_cached_thumbs(cache_dir, [p for p in paths if p])

        # 删除对象（tags / images 通过外键 CASCADE 一并删除）
        self.db.delete_object(obj_id)

        if delete_files and obj:
            storage_path = obj.get("storage_path") or ""
            if storage_path and os.path.isdir(storage_path):
                shutil.rmtree(storage_path)

    # ── 导入 ────────────────────────────────────────────────────────────────

    def import_directory(self, obj_id: str, name: str, tags: dict,
                         source_dir: str, storage_root: str,
                         is_new: bool, progress_cb: Optional[ProgressCB] = None
                         ) -> tuple[int, int]:
        """导入整个目录到 storage_root 下。返回 (成功数, 失败数)。"""
        if is_new:
            storage_obj_dir = os.path.join(storage_root, name)
            os.makedirs(storage_obj_dir, exist_ok=True)
            self.db.create_object(obj_id, "directory", name,
                                  source_dir, storage_obj_dir)
            self.db.set_tags(obj_id, tags)
        else:
            # 追加导入必须使用对象 DB 中记录的目录，而不是按当前名字拼接，
            # 否则对象改名后会导致图片复制到新目录、与 DB 记录分裂。
            obj = self.db.get_object(obj_id) or {}
            storage_obj_dir = (obj.get("storage_path") or "").strip()
            if not storage_obj_dir or not os.path.isdir(storage_obj_dir):
                storage_obj_dir = os.path.join(storage_root, obj.get("name", name))
            os.makedirs(storage_obj_dir, exist_ok=True)

        images = collect_images(source_dir)
        total = len(images)
        seq = next_seq_number(storage_obj_dir)
        sort_start = self.db.get_image_count(obj_id)
        ok, fail = 0, 0
        for i, src in enumerate(images):
            filename, dest = copy_image_with_seq_name(src, storage_obj_dir, seq)
            if dest:
                img_id = str(uuid.uuid4())
                self.db.add_image(img_id, obj_id, filename, dest, sort_start + i)
                seq += 1
                ok += 1
            else:
                fail += 1
            if progress_cb:
                progress_cb(i + 1, total)

        # 新建对象默认用第一张图作为封面
        if is_new:
            obj = self.db.get_object(obj_id)
            first_img = self.db.get_images(obj_id)
            if first_img and not (obj or {}).get("cover_image"):
                self.db.update_object_cover(obj_id, first_img[0]["filepath"])

        return ok, fail

    def import_single_files(self, obj_id: str, paths: list,
                            storage_root: str) -> tuple[int, int]:
        """导入单张/多张图片到已有对象。返回 (成功数, 失败数)。"""
        obj = self.db.get_object(obj_id) or {}
        storage_obj_dir = (obj.get("storage_path") or "").strip()
        if not storage_obj_dir or not os.path.isdir(storage_obj_dir):
            storage_obj_dir = os.path.join(storage_root, obj.get("name", "unnamed"))
        os.makedirs(storage_obj_dir, exist_ok=True)

        ok, fail = 0, 0
        cur_count = self.db.get_image_count(obj_id)
        seq = next_seq_number(storage_obj_dir)
        for src in sorted(paths, key=lambda p: os.path.basename(p)):
            if os.path.basename(src).startswith("."):
                continue
            filename, dest = copy_image_with_seq_name(src, storage_obj_dir, seq)
            if dest:
                img_id = str(uuid.uuid4())
                self.db.add_image(img_id, obj_id, filename, dest, cur_count + ok)
                ok += 1
                seq += 1
            else:
                fail += 1
        return ok, fail
