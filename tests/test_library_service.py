"""LibraryService 增删改查 / 导入 / 删除 / 缩略图缓存 测试（无 GUI）。"""
import os
import sqlite3
import uuid

import pytest

from services.library_service import LibraryService


def test_config_roundtrip(svc_and_root):
    svc, root = svc_and_root
    assert svc.get_config("storage_root") == root
    svc.set_config("theme", "dark")
    assert svc.get_config("theme") == "dark"
    assert svc.get_config("missing") is None


def test_create_and_import(svc_and_root, make_images, new_object_id):
    svc, root = svc_and_root
    src = os.path.join(root, "..", "src")
    src = os.path.abspath(src)
    os.makedirs(src)
    make_images(src, 3)

    ok, fail = svc.import_directory(
        new_object_id, "Alpha", {"work": ["系列A"], "r18": False},
        src, root, is_new=True,
    )
    assert (ok, fail) == (3, 0)

    objs = svc.get_all_objects(include_r18=False)
    assert len(objs) == 1
    # 批量查询装配字段（N+1 修复后）
    assert objs[0]["image_count"] == 3
    assert objs[0]["first_image"]

    obj = svc.get_object(new_object_id)
    assert obj["name"] == "Alpha"
    assert obj["tags"].get("work") == ["系列A"]
    assert svc.get_image_count(new_object_id) == 3
    assert obj.get("cover_image")                     # 自动设置封面
    assert svc.resolve_cover(obj) == obj["cover_image"]


def test_update_name_and_tags(svc_and_root, make_images, new_object_id):
    svc, root = svc_and_root
    src = os.path.join(root, "..", "src")
    src = os.path.abspath(src)
    os.makedirs(src)
    make_images(src, 1)
    svc.import_directory(new_object_id, "Alpha", {"work": ["系列A"]}, src, root, is_new=True)

    svc.update_object_name(new_object_id, "Alpha2")
    svc.set_object_tags(new_object_id, {"author": ["X"], "r18": True})
    obj = svc.get_object(new_object_id)
    assert obj["name"] == "Alpha2"
    assert obj["tags"].get("author") == ["X"]
    assert obj["tags"].get("r18") is True

    # r18 默认隐藏，显式开启后可见
    assert svc.get_all_objects(include_r18=False) == []
    assert len(svc.get_all_objects(include_r18=True)) == 1


def test_append_import_after_rename(svc_and_root, make_images, new_object_id):
    """改名后再追加导入：图片必须进入原 storage_path，而不是按新名字新建目录。"""
    svc, root = svc_and_root
    src1 = os.path.abspath(os.path.join(root, "..", "src1"))
    src2 = os.path.abspath(os.path.join(root, "..", "src2"))
    os.makedirs(src1)
    os.makedirs(src2)
    make_images(src1, 2)
    svc.import_directory(new_object_id, "Alpha", {}, src1, root, is_new=True)

    svc.update_object_name(new_object_id, "Alpha2")
    make_images(src2, 2)
    ok, fail = svc.import_directory(new_object_id, "Alpha2", {}, src2, root, is_new=False)
    assert (ok, fail) == (2, 0)
    assert svc.get_image_count(new_object_id) == 4

    # 所有图片都在原 storage_path（storage/Alpha）下
    obj = svc.get_object(new_object_id)
    storage = obj["storage_path"]
    assert os.path.basename(storage) == "Alpha"
    files = [f for f in os.listdir(storage) if not f.startswith(".")]
    assert len(files) == 4


def test_single_import(svc_and_root, make_images, new_object_id):
    svc, root = svc_and_root
    src1 = os.path.abspath(os.path.join(root, "..", "src1"))
    os.makedirs(src1)
    make_images(src1, 1)
    svc.import_directory(new_object_id, "Alpha", {}, src1, root, is_new=True)

    src2 = os.path.abspath(os.path.join(root, "..", "src2"))
    os.makedirs(src2)
    p = make_images(src2, 1)[0]
    ok, fail = svc.import_single_files(new_object_id, [p], root)
    assert (ok, fail) == (1, 0)
    assert svc.get_image_count(new_object_id) == 2


def test_search_and_filter(svc_and_root, make_images, new_object_id):
    svc, root = svc_and_root
    src = os.path.abspath(os.path.join(root, "..", "src"))
    os.makedirs(src)
    make_images(src, 1)
    svc.import_directory(new_object_id, "Alpha", {"author": ["X"]}, src, root, is_new=True)

    assert len(svc.search_objects("X", include_r18=True)) == 1
    assert svc.search_objects("zzz", include_r18=True) == []
    assert len(svc.filter_by_tags({"author": ["X"]}, include_r18=True)) == 1
    assert svc.filter_by_tags({"work": ["不存在"]}, include_r18=True) == []


def test_search_escapes_wildcards(svc_and_root, make_images, new_object_id):
    """LIKE 通配符（_ / %）应被转义：搜 'a_b' 不应匹配 'aXb'。"""
    svc, root = svc_and_root
    src = os.path.abspath(os.path.join(root, "..", "src"))
    os.makedirs(src)
    make_images(src, 1)
    svc.import_directory(new_object_id, "aXb", {"work": ["W"]}, src, root, is_new=True)

    assert len(svc.search_objects("aXb", include_r18=True)) == 1
    assert svc.search_objects("a_b", include_r18=True) == []
    assert svc.search_objects("a%b", include_r18=True) == []


def test_search_finds_literal_underscore(svc_and_root, make_images, new_object_id):
    """含字面 _ 的名称应能被精确搜索到（转义后仍匹配自身）。"""
    svc, root = svc_and_root
    src = os.path.abspath(os.path.join(root, "..", "src"))
    os.makedirs(src)
    make_images(src, 1)
    svc.import_directory(new_object_id, "a_b", {}, src, root, is_new=True)

    assert len(svc.search_objects("a_b", include_r18=True)) == 1


def test_last_read(svc_and_root, make_images, new_object_id):
    svc, root = svc_and_root
    src = os.path.abspath(os.path.join(root, "..", "src"))
    os.makedirs(src)
    make_images(src, 1)
    svc.import_directory(new_object_id, "Alpha", {}, src, root, is_new=True)
    svc.update_last_read(new_object_id, 0)
    assert svc.get_object(new_object_id)["last_read_idx"] == 0


def test_thumbnail_and_delete(svc_and_root, make_images, new_object_id):
    """缩略图生成/清理 + 删除对象（DB、文件、缓存）。"""
    from utils.thumbnail import generate_thumbnail

    svc, root = svc_and_root
    src = os.path.abspath(os.path.join(root, "..", "src"))
    os.makedirs(src)
    make_images(src, 2)
    svc.import_directory(new_object_id, "Alpha", {"work": ["系列A"]}, src, root, is_new=True)
    obj = svc.get_object(new_object_id)

    cache_dir = os.path.join(root, ".thumbcache")
    os.makedirs(cache_dir)
    thumb = generate_thumbnail(obj["cover_image"], cache_dir)
    assert thumb and os.path.isfile(thumb)

    before = set(os.listdir(cache_dir))
    svc.delete_object(new_object_id, delete_files=True, storage_root=root)
    after = set(os.listdir(cache_dir)) if os.path.isdir(cache_dir) else set()
    assert not (before & after)          # 缩略图缓存被清理
    assert svc.get_object(new_object_id) is None
    assert not os.path.isdir(obj["storage_path"])   # 存储目录被删除


def test_thumbnail_cache_invalidated_by_mtime(svc_and_root, make_images, new_object_id):
    """源图 mtime 变化后，缩略图缓存键应失效并生成新文件。"""
    import time

    from utils.thumbnail import generate_thumbnail

    svc, root = svc_and_root
    src = os.path.abspath(os.path.join(root, "..", "src"))
    os.makedirs(src)
    make_images(src, 1)
    svc.import_directory(new_object_id, "Alpha", {}, src, root, is_new=True)
    first_img = svc.get_images(new_object_id)[0]["filepath"]

    cache_dir = os.path.join(root, ".thumbcache")
    os.makedirs(cache_dir)
    t1 = generate_thumbnail(first_img, cache_dir)

    time.sleep(0.05)
    st = os.stat(first_img)
    os.utime(first_img, (st.st_atime, st.st_mtime + 2))
    t2 = generate_thumbnail(first_img, cache_dir)
    assert t1 != t2


def test_r18_mixed_and_tag_values(svc_and_root, make_images):
    svc, root = svc_and_root
    # 两个非 r18 对象 + 一个 r18 对象
    for name in ("Beta", "Gamma"):
        src = os.path.abspath(os.path.join(root, "..", f"src_{name}"))
        os.makedirs(src)
        make_images(src, 1)
        oid = str(uuid.uuid4())
        svc.import_directory(oid, name, {"work": ["系列A"]}, src, root, is_new=True)

    oid_r18 = str(uuid.uuid4())
    src = os.path.abspath(os.path.join(root, "..", "src_r18"))
    os.makedirs(src)
    make_images(src, 1)
    svc.import_directory(oid_r18, "Hidden", {"r18": True}, src, root, is_new=True)

    assert len(svc.get_all_objects(include_r18=False)) == 2
    assert len(svc.get_all_objects(include_r18=True)) == 3
    assert set(svc.get_tag_values("work")) == {"系列A"}


def test_import_rejects_duplicate_storage_dir(svc_and_root, make_images):
    """同名新建导入应被拒绝，防止两个对象共享目录导致级联删除。"""
    svc, root = svc_and_root
    src1 = os.path.abspath(os.path.join(root, "..", "src1"))
    os.makedirs(src1)
    make_images(src1, 2)
    oid1 = str(uuid.uuid4())
    svc.import_directory(oid1, "Alpha", {}, src1, root, is_new=True)

    src2 = os.path.abspath(os.path.join(root, "..", "src2"))
    os.makedirs(src2)
    make_images(src2, 1)
    oid2 = str(uuid.uuid4())
    with pytest.raises(ValueError):
        svc.import_directory(oid2, "Alpha", {}, src2, root, is_new=True)
    # 第一个对象不受影响
    assert svc.get_image_count(oid1) == 2
    assert svc.get_object(oid2) is None


def test_delete_shared_dir_skips_file_removal(svc_and_root, make_images):
    """历史共享目录（手工构造两个对象指向同一目录）：
    删除一个对象不物理删除共享目录，最后一个共享者删除时才删。"""
    svc, root = svc_and_root
    src = os.path.abspath(os.path.join(root, "..", "src"))
    os.makedirs(src)
    make_images(src, 1)
    oid1 = str(uuid.uuid4())
    svc.import_directory(oid1, "Alpha", {}, src, root, is_new=True)
    shared_dir = svc.get_object(oid1)["storage_path"]

    # 手工构造第二个对象指向同一目录（模拟 H1 修复前的历史数据）
    oid2 = str(uuid.uuid4())
    svc.db.create_object(oid2, "directory", "Legacy", "", shared_dir)
    svc.db.add_image(str(uuid.uuid4()), oid2, "0000001.png",
                     os.path.join(shared_dir, "0000001.png"), 0)

    svc.delete_object(oid1, delete_files=True, storage_root=root)
    assert os.path.isdir(shared_dir)          # 物理删除被跳过
    assert svc.get_object(oid1) is None
    assert svc.get_object(oid2) is not None

    svc.delete_object(oid2, delete_files=True, storage_root=root)
    assert not os.path.isdir(shared_dir)      # 最后一个共享者删除时才删
    assert svc.get_object(oid2) is None


def test_unique_tag_index(svc_and_root, make_images, new_object_id):
    """tags 唯一索引：直接插入重复标签应被拒绝。"""
    svc, root = svc_and_root
    src = os.path.abspath(os.path.join(root, "..", "src"))
    os.makedirs(src)
    make_images(src, 1)
    svc.import_directory(new_object_id, "Alpha", {"work": ["系列A"]}, src, root, is_new=True)

    with pytest.raises(sqlite3.IntegrityError):
        svc.db.conn.execute(
            "INSERT INTO tags(object_id,category,value) VALUES(?,?,?)",
            (new_object_id, "work", "系列A"),
        )
        svc.db.conn.execute(
            "INSERT INTO tags(object_id,category,value) VALUES(?,?,?)",
            (new_object_id, "work", "系列A"),
        )
