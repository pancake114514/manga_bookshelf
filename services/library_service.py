"""
LibraryService - 业务门面层

UI 组件只依赖本服务，不直接访问 Database。
本模块不依赖任何 Qt，可在无 GUI 环境下独立测试。

线程约定：
- 主线程使用一个 LibraryService 实例做查询/变更。
- 后台工作线程（如导入）应使用独立的 LibraryService 实例（传入同一 db_path），
  避免共享同一个 sqlite 连接对象。
"""
import logging
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
from utils.thumbnail import clear_cached_thumbs, THUMB_CACHE_DIR

logger = logging.getLogger(__name__)


ProgressCB = Callable[[int, int], None]
CancelCheck = Callable[[], bool]


class ImportCancelled(Exception):
    """导入被调用方取消；抛出前本次导入已写入的对象/图片/文件已回滚。"""


class LibraryService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = Database(db_path)

    def close(self):
        """关闭数据库连接。工作线程用完务必调用。"""
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

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

    def _storage_path_taken(self, path: str,
                            exclude_id: Optional[str] = None) -> bool:
        """检查存储路径是否已被（其他）对象占用。

        防止两个对象共享同一存储目录：删除任一对象时会级联删掉
        另一对象的全部图片。比较时做 normcase+abspath 归一化。
        """
        target = os.path.normcase(os.path.abspath(path))
        rows = self.db.conn.execute(
            "SELECT id, storage_path FROM objects"
        ).fetchall()
        for row in rows:
            sp = (row["storage_path"] or "").strip()
            if not sp:
                continue
            if os.path.normcase(os.path.abspath(sp)) == target:
                if exclude_id is None or row["id"] != exclude_id:
                    return True
        return False

    def delete_object(self, obj_id: str, delete_files: bool = False,
                      storage_root: Optional[str] = None):
        """删除对象（DB + 可选本地文件 + 缩略图缓存）。

        文件删除失败会抛出异常，由调用方（UI）提示；此时 DB 记录已删除，
        与原行为保持一致。若存储目录与其他对象共享（H1 修复前的历史数据），
        跳过物理删除，避免级联删掉其他对象的图片。
        """
        obj = self.db.get_object(obj_id)

        # 清理该对象关联的缩略图缓存；未显式传入 storage_root 时从对象的
        # storage_path 反推根目录（storage_path = <root>/<name>）
        root = storage_root
        if not root and obj and obj.get("storage_path"):
            root = os.path.dirname(obj["storage_path"])
        if obj and root:
            cache_dir = os.path.join(root, THUMB_CACHE_DIR)
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
                # 防御：历史数据可能存在多对象共享同一存储目录的情况，
                # 此时物理删除会级联删掉其他对象的全部图片，必须跳过。
                # 对象记录已删除，此处查到的均为其他对象，无需 exclude_id。
                if self._storage_path_taken(storage_path):
                    logger.warning(
                        "对象 %s 的存储目录与其他对象共享，跳过物理删除：%s",
                        obj_id, storage_path,
                    )
                else:
                    shutil.rmtree(storage_path)

    # ── 导入 ────────────────────────────────────────────────────────────────

    def _resolve_append_target_dir(self, obj: dict, storage_root: str,
                                    name_hint: str) -> str:
        """追加导入时解析目标目录：优先 DB 记录的 storage_path，
        无效时按名字重建，但必须先做占用检查并回写 DB（M3 防御）。

        重建场景：storage_path 无效（目录被移走/删除）。
        此时按对象名拼新目录，若该目录已被其他对象占用则报错，
        避免两对象共享目录→删除时级联删图；成功后回写 storage_path，
        否则后续 delete_object 拿不到路径→磁盘孤儿文件。
        """
        storage_path = (obj.get("storage_path") or "").strip()
        if storage_path and os.path.isdir(storage_path):
            return storage_path

        rebuilt = os.path.join(storage_root, obj.get("name") or name_hint)
        if self._storage_path_taken(rebuilt, exclude_id=obj.get("id")):
            raise ValueError(
                f"存储目录已被其他对象占用，无法重建：{rebuilt}"
            )
        os.makedirs(rebuilt, exist_ok=True)
        if obj.get("id"):
            self.db.update_object_storage_path(obj["id"], rebuilt)
        return rebuilt

    def import_directory(self, obj_id: str, name: str, tags: dict,
                         source_dir: str, storage_root: str,
                         is_new: bool, progress_cb: Optional[ProgressCB] = None,
                         cancel_check: Optional[CancelCheck] = None
                         ) -> tuple[int, int]:
        """导入整个目录到 storage_root 下。返回 (成功数, 失败数)。

        cancel_check 返回 True 时立即中止，并回滚本次已写入的对象/图片
        （含已复制到磁盘的文件），随后抛出 ImportCancelled——避免留下
        残缺对象、孤立图片等半成品状态。
        """
        created_object = False
        created_dir = False
        created_images: list = []   # [(img_id, dest_path)]

        if is_new:
            storage_obj_dir = os.path.join(storage_root, name)
            # 防止两个对象共享同一存储目录：删除任一对象会级联删掉
            # 另一对象的全部图片（H1），因此先检查目录是否已被占用
            if self._storage_path_taken(storage_obj_dir):
                raise ValueError(f"存储目录已被其他对象占用：{name}")
            # M4 防御：库根下已存在的同名目录（用户手工放置/上次失败残留）
            # 不属于任何对象；静默复用后删除对象会把其中的用户文件一并
            # rmtree。非空即拒绝，让用户换名或先处理该目录。
            if os.path.isdir(storage_obj_dir) and os.listdir(storage_obj_dir):
                raise ValueError(
                    f"目录已存在且非空（不属于任何对象），为避免误删其中文件"
                    f"已拒绝导入：{storage_obj_dir}"
                )
            dir_existed = os.path.isdir(storage_obj_dir)
            created_dir = not dir_existed
            os.makedirs(storage_obj_dir, exist_ok=True)
            if not self.db.create_object(obj_id, "directory", name,
                                         source_dir, storage_obj_dir):
                # create_object 失败（ID 冲突）时只清理本次新建的空目录，
                # 绝不删除预先存在的目录（可能属于其他对象）
                if created_dir:
                    shutil.rmtree(storage_obj_dir, ignore_errors=True)
                raise ValueError(f"对象 ID 冲突，创建失败：{obj_id}")
            created_object = True
            self.db.set_tags(obj_id, tags)
        else:
            # 追加导入必须使用对象 DB 中记录的目录，而不是按当前名字拼接，
            # 否则对象改名后会导致图片复制到新目录、与 DB 记录分裂。
            # storage_path 无效时重建（含占用检查 + 回写，见 M3 防御）。
            obj = self.db.get_object(obj_id) or {}
            storage_obj_dir = self._resolve_append_target_dir(
                obj, storage_root, name
            )

        try:
            images = collect_images(source_dir)
            total = len(images)
            seq = next_seq_number(storage_obj_dir)
            sort_start = self.db.get_image_count(obj_id)
            ok, fail = 0, 0
            for i, src in enumerate(images):
                if cancel_check and cancel_check():
                    raise ImportCancelled()
                filename, dest, used_seq = copy_image_with_seq_name(
                    src, storage_obj_dir, seq
                )
                if dest:
                    img_id = str(uuid.uuid4())
                    self.db.add_image(img_id, obj_id, filename, dest, sort_start + i)
                    created_images.append((img_id, dest))
                    seq = used_seq + 1
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
        except ImportCancelled:
            self._rollback_import(obj_id, created_object, created_dir,
                                  storage_obj_dir, created_images)
            raise

    def _rollback_import(self, obj_id: str, created_object: bool,
                         created_dir: bool, storage_obj_dir: str,
                         created_images: list):
        """回滚一次被取消的导入，避免留下残缺对象与孤立文件。"""
        if created_object:
            # 对象为本次创建：删除对象（CASCADE 清 tags/images），
            # 目录若也是本次新建则一并移除
            self.db.delete_object(obj_id)
            if created_dir and os.path.isdir(storage_obj_dir):
                shutil.rmtree(storage_obj_dir, ignore_errors=True)
        else:
            # 追加导入：仅移除本次新增的图片记录与对应文件
            for img_id, dest in created_images:
                self.db.delete_image(img_id)
                try:
                    if os.path.isfile(dest):
                        os.remove(dest)
                except OSError as e:
                    logger.warning("回滚导入文件失败：%s", e)

    def import_single_files(self, obj_id: str, paths: list,
                            storage_root: str) -> tuple[int, int]:
        """导入单张/多张图片到已有对象。返回 (成功数, 失败数)。"""
        obj = self.db.get_object(obj_id) or {}
        # storage_path 无效时重建（含占用检查 + 回写，见 M3 防御）
        storage_obj_dir = self._resolve_append_target_dir(
            obj, storage_root, "unnamed"
        )

        ok, fail = 0, 0
        cur_count = self.db.get_image_count(obj_id)
        seq = next_seq_number(storage_obj_dir)
        for src in sorted(paths, key=lambda p: os.path.basename(p)):
            if os.path.basename(src).startswith("."):
                continue
            filename, dest, used_seq = copy_image_with_seq_name(src, storage_obj_dir, seq)
            if dest:
                img_id = str(uuid.uuid4())
                self.db.add_image(img_id, obj_id, filename, dest, cur_count + ok)
                ok += 1
                seq = used_seq + 1
            else:
                fail += 1
        return ok, fail
