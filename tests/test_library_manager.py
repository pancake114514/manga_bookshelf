"""library_manager 迁移功能测试（无 GUI）。"""
import os
import shutil
import uuid

from library_manager import migrate_library
from services.library_service import LibraryService


def _setup_svc(tmp_path):
    db_path = str(tmp_path / "library.db")
    old_root = str(tmp_path / "old")
    new_root = str(tmp_path / "new")
    os.makedirs(old_root)
    os.makedirs(new_root)
    svc = LibraryService(db_path)
    svc.set_config("storage_root", old_root)
    return svc, old_root, new_root


def test_migrate_updates_paths(tmp_path, make_images):
    """正常迁移：storage_path / 图片路径 / 封面路径全部更新到新根。"""
    svc, old_root, new_root = _setup_svc(tmp_path)
    try:
        src = str(tmp_path / "src")
        os.makedirs(src)
        make_images(src, 2)
        oid = str(uuid.uuid4())
        svc.import_directory(oid, "Alpha", {}, src, old_root, is_new=True)
        obj = svc.get_object(oid)

        moved, warnings = migrate_library(svc.db, new_root)
        assert moved == 1
        assert warnings == []

        obj = svc.get_object(oid)
        assert obj["storage_path"].startswith(new_root)
        assert os.path.isdir(obj["storage_path"])
        for img in svc.get_images(oid):
            assert img["filepath"].startswith(new_root)
        assert obj["cover_image"].startswith(new_root)
        assert svc.get_config("storage_root") == os.path.abspath(new_root)
    finally:
        svc.close()


def test_migrate_same_name_auto_rename(tmp_path, make_images):
    """两个同名对象（不同父目录）迁移时自动加后缀，不再中止。"""
    svc, old_root, new_root = _setup_svc(tmp_path)
    try:
        oid1, oid2 = str(uuid.uuid4()), str(uuid.uuid4())
        for oid, sub in ((oid1, "A"), (oid2, "B")):
            d = os.path.join(old_root, sub, "Alpha")
            os.makedirs(d)
            svc.db.create_object(oid, "directory", sub, "", d)
            src = os.path.join(old_root, sub, "src")
            os.makedirs(src)
            p = make_images(src, 1)[0]
            dest = os.path.join(d, "0000001.png")
            shutil.copy2(p, dest)
            svc.db.add_image(str(uuid.uuid4()), oid, "0000001.png", dest, 0)

        moved, warnings = migrate_library(svc.db, new_root)
        assert moved == 2
        o1 = svc.get_object(oid1)
        o2 = svc.get_object(oid2)
        names = {os.path.basename(o1["storage_path"]),
                 os.path.basename(o2["storage_path"])}
        assert names == {"Alpha", "Alpha (1)"}
        assert os.path.isdir(o1["storage_path"])
        assert os.path.isdir(o2["storage_path"])
        # 图片路径随新目录更新
        assert svc.get_images(oid1)[0]["filepath"] == os.path.join(
            o1["storage_path"], "0000001.png")
        assert svc.get_images(oid2)[0]["filepath"] == os.path.join(
            o2["storage_path"], "0000001.png")
    finally:
        svc.close()


def test_migrate_warns_unmapped_cover(tmp_path, make_images):
    """库外封面路径不随迁移，应出现在警告列表中。"""
    svc, old_root, new_root = _setup_svc(tmp_path)
    try:
        oid = str(uuid.uuid4())
        d = os.path.join(old_root, "Alpha")
        os.makedirs(d)
        svc.db.create_object(oid, "directory", "Alpha", "", d)
        src = os.path.join(old_root, "src")
        os.makedirs(src)
        p = make_images(src, 1)[0]
        dest = os.path.join(d, "0000001.png")
        shutil.copy2(p, dest)
        svc.db.add_image(str(uuid.uuid4()), oid, "0000001.png", dest, 0)

        outside_dir = str(tmp_path / "outside")
        os.makedirs(outside_dir)
        cover = make_images(outside_dir, 1)[0]
        svc.db.update_object_cover(oid, cover)

        moved, warnings = migrate_library(svc.db, new_root)
        assert moved == 1
        assert any("封面" in w and "库外" in w for w in warnings)
    finally:
        svc.close()
