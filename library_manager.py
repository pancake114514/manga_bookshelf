"""Library configuration and migration helpers."""
import os
import shutil
import sys
from dataclasses import dataclass
from typing import Callable, List

from database import Database


class LibraryMigrationError(Exception):
    pass


@dataclass
class ImagePathUpdate:
    img_id: str
    old_path: str
    new_path: str


@dataclass
class ObjectMigrationPlan:
    obj_id: str
    name: str
    old_dir: str
    new_dir: str
    cover_old: str | None
    cover_new: str | None
    image_updates: List[ImagePathUpdate]


ProgressCallback = Callable[[int, int, str], None]


def check_writable(path: str) -> tuple[bool, str]:
    """Return whether the directory exists and is writable."""
    if not os.path.isdir(path):
        return False, f"目录不存在：\n{path}"
    test_file = os.path.join(path, ".manga_shelf_write_test")
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test")
        os.remove(test_file)
        return True, ""
    except PermissionError:
        return False, f"没有写入权限，请选择其他目录：\n{path}"
    except Exception as e:
        return False, f"目录不可用：{e}"


def get_database_path() -> str:
    """Return the SQLite database path used by the app."""
    if sys.platform == "win32":
        data_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        data_dir = os.path.expanduser("~/.local/share")
    app_dir = os.path.join(data_dir, "MangaShelf")
    os.makedirs(app_dir, exist_ok=True)
    return os.path.join(app_dir, "library.db")


def get_storage_root(db: Database) -> str | None:
    return db.get_config("storage_root")


def set_storage_root(db: Database, path: str):
    db.set_config("storage_root", path)


def _normalize_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _is_relative_to(path: str, parent: str) -> bool:
    try:
        common = os.path.commonpath([path, parent])
    except ValueError:
        return False
    return common == parent


def _map_path(path: str | None, old_dir: str, new_dir: str) -> str | None:
    if not path:
        return path
    normalized = _normalize_path(path)
    old_dir_normalized = _normalize_path(old_dir)
    if not _is_relative_to(normalized, old_dir_normalized):
        return path
    relative = os.path.relpath(path, old_dir)
    return os.path.join(new_dir, relative)


def prepare_library_migration(db: Database, new_root: str) -> tuple[str, str, List[ObjectMigrationPlan]]:
    old_root = get_storage_root(db)
    if not old_root:
        raise LibraryMigrationError("当前还没有已配置的图库目录。")

    old_root = os.path.abspath(old_root)
    new_root = os.path.abspath(new_root)

    if _normalize_path(old_root) == _normalize_path(new_root):
        raise LibraryMigrationError("新旧图库目录相同，无需迁移。")
    if _is_relative_to(new_root, old_root) or _is_relative_to(old_root, new_root):
        raise LibraryMigrationError("新旧图库目录不能互相包含。")

    ok, err = check_writable(new_root)
    if not ok:
        raise LibraryMigrationError(err)

    objects = db.get_all_objects(include_r18=True)
    plans: List[ObjectMigrationPlan] = []
    seen_targets: set[str] = set()

    for obj in objects:
        old_dir = (obj.get("storage_path") or "").strip()
        if not old_dir:
            raise LibraryMigrationError(f"对象“{obj['name']}”缺少存储路径，无法迁移。")
        if not os.path.isdir(old_dir):
            raise LibraryMigrationError(f"对象“{obj['name']}”的目录不存在：\n{old_dir}")

        new_dir = os.path.join(new_root, os.path.basename(old_dir))
        new_dir_key = _normalize_path(new_dir)
        if new_dir_key in seen_targets:
            raise LibraryMigrationError(f"检测到重复目标目录：\n{new_dir}")
        seen_targets.add(new_dir_key)

        if os.path.exists(new_dir):
            raise LibraryMigrationError(f"目标目录已存在，无法安全迁移：\n{new_dir}")

        images = db.get_images(obj["id"])
        image_updates = [
            ImagePathUpdate(
                img_id=img["id"],
                old_path=img["filepath"],
                new_path=_map_path(img["filepath"], old_dir, new_dir) or img["filepath"],
            )
            for img in images
        ]
        cover_old = obj.get("cover_image")
        cover_new = _map_path(cover_old, old_dir, new_dir)

        plans.append(
            ObjectMigrationPlan(
                obj_id=obj["id"],
                name=obj["name"],
                old_dir=old_dir,
                new_dir=new_dir,
                cover_old=cover_old,
                cover_new=cover_new,
                image_updates=image_updates,
            )
        )

    return old_root, new_root, plans


def migrate_library(db: Database, new_root: str, progress: ProgressCallback | None = None) -> int:
    old_root, new_root, plans = prepare_library_migration(db, new_root)
    total_steps = max(1, len(plans) * 2 + 1)
    current_step = 0
    moved_dirs: list[tuple[str, str]] = []

    def emit(message: str):
        nonlocal current_step
        current_step += 1
        if progress:
            progress(current_step, total_steps, message)

    try:
        os.makedirs(new_root, exist_ok=True)
        for plan in plans:
            emit(f"正在迁移：{plan.name}")
            shutil.move(plan.old_dir, plan.new_dir)
            moved_dirs.append((plan.old_dir, plan.new_dir))

        db.begin()
        try:
            for plan in plans:
                emit(f"正在更新数据库：{plan.name}")
                db.update_object_storage_path(plan.obj_id, plan.new_dir)
                for image in plan.image_updates:
                    db.update_image_filepath(image.img_id, image.new_path)
                if plan.cover_old != plan.cover_new and plan.cover_new is not None:
                    db.update_object_cover(plan.obj_id, plan.cover_new)
            set_storage_root(db, new_root)
            db.commit()
        except Exception:
            db.rollback()
            raise

        emit("迁移完成")
        return len(plans)
    except Exception as exc:
        for old_dir, new_dir in reversed(moved_dirs):
            try:
                if os.path.exists(new_dir) and not os.path.exists(old_dir):
                    shutil.move(new_dir, old_dir)
            except Exception:
                pass
        if isinstance(exc, LibraryMigrationError):
            raise
        raise LibraryMigrationError(str(exc)) from exc
