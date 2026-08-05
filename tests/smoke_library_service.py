"""
冒烟测试：LibraryService 增删改查 / 导入 / 删除流程（无 GUI）。
可在项目根目录运行：python -m tests.smoke_library_service
"""
import os
import shutil
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.library_service import LibraryService

PASS = 0
FAIL = 0


def check(name: str, cond: bool):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}")


def make_images(d: str, count: int = 3) -> list:
    from PIL import Image
    paths = []
    for i in range(count):
        p = os.path.join(d, f"img{i:03d}.png")
        Image.new("RGB", (100, 150), (i * 40, 20, 20)).save(p)
        paths.append(p)
    return paths


def main():
    tmp = tempfile.mkdtemp(prefix="mangashelf_smoke_")
    try:
        db_path = os.path.join(tmp, "library.db")
        root = os.path.join(tmp, "storage")
        os.makedirs(root, exist_ok=True)

        svc = LibraryService(db_path)
        svc.set_config("storage_root", root)
        check("set/get config", svc.get_config("storage_root") == root)

        # 1. 新建对象导入
        src1 = os.path.join(tmp, "src1")
        os.makedirs(src1)
        make_images(src1, 3)
        oid1 = str(uuid.uuid4())
        svc.import_directory(oid1, "Alpha", {"work": ["系列A"], "r18": False},
                             src1, root, is_new=True)
        objs = svc.get_all_objects(include_r18=False)
        check("create + import object", len(objs) == 1)
        obj = svc.get_object(oid1)
        check("object name", obj["name"] == "Alpha")
        check("object tags", obj["tags"].get("work") == ["系列A"])
        check("images imported", svc.get_image_count(oid1) == 3)
        check("auto cover set", bool(obj.get("cover_image")))
        check("cover resolves", svc.resolve_cover(obj) == obj["cover_image"])

        # 2. 更新标签/名称
        svc.update_object_name(oid1, "Alpha2")
        svc.set_object_tags(oid1, {"author": ["X"], "r18": True})
        obj = svc.get_object(oid1)
        check("rename", obj["name"] == "Alpha2")
        check("tags replaced", obj["tags"].get("author") == ["X"] and obj["tags"].get("r18") is True)
        check("r18 hidden by default", svc.get_all_objects(include_r18=False) == [])
        check("r18 shown with flag", len(svc.get_all_objects(include_r18=True)) == 1)

        # 3. 已有对象追加导入
        src2 = os.path.join(tmp, "src2")
        os.makedirs(src2)
        make_images(src2, 2)
        svc.import_directory(oid1, "Alpha2", {}, src2, root, is_new=False)
        check("append import", svc.get_image_count(oid1) == 5)

        # 4. 单文件导入
        src3 = os.path.join(tmp, "single")
        os.makedirs(src3)
        p = make_images(src3, 1)[0]
        ok, fail = svc.import_single_files(oid1, [p], root)
        check("single import", ok == 1 and fail == 0 and svc.get_image_count(oid1) == 6)

        # 5. 搜索 / 过滤
        check("search by tag", len(svc.search_objects("X", include_r18=True)) == 1)
        check("search no match", svc.search_objects("zzz", include_r18=True) == [])
        filt = svc.filter_by_tags({"author": ["X"]}, include_r18=True)
        check("filter by tag", len(filt) == 1)

        # 6. 阅读进度
        svc.update_last_read(oid1, 4)
        check("last_read updated", svc.get_object(oid1)["last_read_idx"] == 4)

        # 7. 缩略图缓存生成 + 删除清理
        from utils.thumbnail import generate_thumbnail, clear_cached_thumbs
        cache_dir = os.path.join(root, ".thumbcache")
        os.makedirs(cache_dir, exist_ok=True)
        thumb = generate_thumbnail(obj["cover_image"], cache_dir)
        check("thumbnail generated", bool(thumb) and os.path.isfile(thumb))
        before = set(os.listdir(cache_dir)) if os.path.isdir(cache_dir) else set()
        svc.delete_object(oid1, delete_files=True, storage_root=root)
        after = set(os.listdir(cache_dir)) if os.path.isdir(cache_dir) else set()
        # 删除对象后其缩略图缓存应被清理（after 不应再包含 before 中的文件）
        check("thumb cache cleared", not (before & after))
        check("object deleted from db", svc.get_object(oid1) is None)
        # 对象实际存储目录是 storage/Alpha（改名不改变 storage_path），删除后应被移除
        check("storage dir removed", not os.path.isdir(os.path.join(root, "Alpha")))

        # 8. 多对象 / R18 混合
        oid2 = str(uuid.uuid4())
        src4 = os.path.join(tmp, "src4")
        os.makedirs(src4)
        make_images(src4, 1)
        svc.import_directory(oid2, "Beta", {"work": ["系列A"]}, src4, root, is_new=True)
        check("r18 hidden", len(svc.get_all_objects(include_r18=False)) == 1)
        # oid1（Alpha2，r18）已在第 7 步删除，因此此处只应剩 Beta 一个对象
        check("r18 shown", len(svc.get_all_objects(include_r18=True)) == 1)
        check("tag values", set(svc.get_tag_values("work")) == {"系列A"})

        svc.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'-' * 40}\nPASS: {PASS}  FAIL: {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
