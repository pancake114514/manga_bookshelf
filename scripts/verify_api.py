"""联调验证脚本：走完整 API 链路（初始化 → 导入 → 查询 → 缩略图 → 筛选 → 删除回滚）。

用法：先启动 backend/server.py --serve --port 8765（MANGASHELF_DB 指向临时库），
然后运行本脚本。
"""
import io
import json
import os
import time
import urllib.request

BASE = "http://127.0.0.1:8765"
DEMO = os.path.join(os.environ.get("TEMP", "/tmp"), "ms_demo")


def call(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            ct = r.headers.get("content-type", "")
            data = r.read()
            return r.status, (json.loads(data) if "json" in ct else f"<{len(data)} bytes {ct}>")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def make_png(path: str, color: tuple, size=(120, 180)):
    from PIL import Image
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, color).save(path)


def main():
    results = []

    def check(name, cond, extra=""):
        results.append((name, "PASS" if cond else "FAIL", extra))

    # 0. 服务就绪
    for _ in range(20):
        try:
            st, data = call("GET", "/api/state")
            break
        except Exception:
            time.sleep(0.5)
    check("GET /api/state", st == 200, f"root={data.get('storage_root')!r}")

    # 1. setup：设置图库根目录
    root = os.path.join(DEMO, "storage")
    os.makedirs(root, exist_ok=True)
    st, data = call("POST", "/api/setup", {"path": root})
    check("POST /api/setup", st == 200, str(data))

    # 2. 造 3 个源文件夹共 12 张图（其中一个含 20 张的 r18 库）
    src_dirs = []
    palettes = [(61, 90, 128), (92, 64, 51), (123, 45, 67)]
    for i, pal in enumerate(palettes):
        d = os.path.join(DEMO, f"src{i}")
        for j in range(4 if i < 2 else 20):
            make_png(os.path.join(d, f"p{j:03d}.png"),
                     (pal[0] + j * 5 % 60, pal[1], pal[2]))
        src_dirs.append(d)

    # 3. 新建导入两个对象
    st, a = call("POST", "/api/import/directory", {
        "source_dir": src_dirs[0], "name": "星海航路",
        "tags": {"work": ["星海航路"], "author": ["水濑叶月"], "r18": False},
        "is_new": True,
    })
    check("import 新建对象A", st == 200 and a.get("success") == 4, str(a))

    st, b = call("POST", "/api/import/directory", {
        "source_dir": src_dirs[1], "name": "深夜食堂画集",
        "tags": {"work": ["深夜食堂"], "r18": False},
        "is_new": True,
    })
    check("import 新建对象B", st == 200 and b.get("success") == 4, str(b))

    # r18 对象（默认应被隐藏）
    st, c = call("POST", "/api/import/directory", {
        "source_dir": src_dirs[2], "name": "秘密の部屋",
        "tags": {"r18": True}, "is_new": True,
    })
    check("import 新建对象C(r18)", st == 200 and c.get("success") == 20, str(c))

    # 4. 查询：默认不含 r18
    st, objs = call("GET", "/api/objects?include_r18=false&filters=%7B%7D")
    names = {o["name"] for o in objs}
    check("查询默认隐藏 r18", st == 200 and names == {"星海航路", "深夜食堂画集"}, str(names))
    check("image_count 正确", all(o["image_count"] == 4 for o in objs), str([o["image_count"] for o in objs]))

    st, objs_r = call("GET", "/api/objects?include_r18=true&filters=%7B%7D")
    check("include_r18 可见 3 个", len(objs_r) == 3, str(len(objs_r)))

    # 5. 搜索
    st, hits = call("GET", "/api/objects?q=%E6%B7%B1%E5%A4%9C&include_r18=true&filters=%7B%7D")
    check("搜索「深夜」", len(hits) == 1 and hits[0]["name"] == "深夜食堂画集")

    # 6. 标签筛选
    filters = json.dumps({"author": ["水濑叶月"]})
    st, hits = call("GET", f"/api/objects?include_r18=true&filters={urllib.request.quote(filters)}")
    check("按作者筛选", len(hits) == 1 and hits[0]["name"] == "星海航路")

    # 7. 标签值聚合
    st, tv = call("GET", "/api/tag-values")
    check("tag-values", st == 200 and "星海航路" in tv.get("work", []), str(tv.get("work")))

    # 8. 详情 + 图片 + 缩略图 + 原图
    oid = objs_r[0]["id"]
    st, detail = call("GET", f"/api/objects/{oid}")
    check("对象详情", st == 200 and len(detail["images"]) == objs_r[0]["image_count"])
    img0 = detail["images"][0]
    st, head = call("GET", img0["thumb_url"] + "?kind=card")
    check("缩略图 card", st == 200 and "image" in str(head))
    st, head = call("GET", img0["image_url"])
    check("原图", st == 200 and "image" in str(head))
    st, head = call("GET", f"/api/objects/{oid}/cover?kind=card")
    check("封面缩略图", st == 200 and "image" in str(head))

    # 9. 阅读进度
    st, _ = call("POST", f"/api/objects/{oid}/last-read", {"idx": 2})
    st, detail = call("GET", f"/api/objects/{oid}")
    check("last-read 落库", detail["last_read_idx"] == 2, str(detail["last_read_idx"]))

    # 10. 编辑名称/标签
    st, _ = call("PUT", f"/api/objects/{oid}", {"name": "星海航路 01-03"})
    st, detail = call("GET", f"/api/objects/{oid}")
    check("改名", detail["name"] == "星海航路 01-03")

    # 11. 非法名称校验
    st, v = call("POST", "/api/validate-name", {"name": "a/b"})
    check("validate-name 拒绝非法字符", st == 200 and v["ok"] is False)

    # 12. 删除对象（含文件）
    st, _ = call("DELETE", f"/api/objects/{oid}?delete_files=true")
    st, objs_r = call("GET", "/api/objects?include_r18=true&filters=%7B%7D")
    check("删除对象", len(objs_r) == 2)
    check("存储目录已删除", not os.path.isdir(os.path.join(root, "星海航路 01-03")))

    # 13. 前端静态托管
    st, html = call("GET", "/")
    check("前端 index.html", st == 200 and isinstance(html, str) and "index" not in html)

    fails = [r for r in results if r[1] == "FAIL"]
    print("=" * 46)
    for name, status, extra in results:
        print(f"[{status}] {name}  {extra[:80]}")
    print("=" * 46)
    print(f"TOTAL {len(results)} | PASS {len(results) - len(fails)} | FAIL {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
