"""FastAPI 层：把 LibraryService 包装成 HTTP API，供 Web 前端使用。

设计要点：
- 每个请求创建独立 LibraryService 实例（sqlite 连接绑定创建线程，不能跨线程共享）。
- 图片/缩略图端点通过对象 id + 图片 id 在 DB 中反查真实路径，不接收任意路径参数。
- 生产模式下静态托管 frontend/dist；开发时前端走 vite dev server + proxy。
"""
import json
import os
import sys
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.responses import FileResponse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from library_manager import check_writable, migrate_library          # noqa: E402
from services.library_service import LibraryService, ImportCancelled   # noqa: E402
from utils.thumbnail import (                                        # noqa: E402
    generate_thumbnail, get_thumb_cache_dir,
    THUMBNAIL_SIZE, GRID_THUMB_SIZE, COVER_THUMB_SIZE,
)
from config import TAG_CATEGORIES, TAG_CATEGORY_ORDER                # noqa: E402

def _default_db_path() -> str:
    """与 library_manager.get_database_path 一致，但不创建目录（导入期避免副作用）。"""
    if os.name == "nt":
        data_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        data_dir = os.path.expanduser("~/.local/share")
    return os.path.join(data_dir, "MangaShelf", "library.db")


# 数据库路径：默认用户数据目录；测试/开发可用 MANGASHELF_DB 覆盖
DB_PATH = os.environ.get("MANGASHELF_DB") or _default_db_path()
FRONTEND_DIST = os.path.join(PROJECT_ROOT, "frontend", "dist")

app = FastAPI(title="MangaShelf API", docs_url=None, redoc_url=None)


def get_svc() -> LibraryService:
    return LibraryService(DB_PATH)


def _storage_root(svc: LibraryService) -> str:
    return svc.get_config("storage_root") or ""


def _serialize_object(o: dict) -> dict:
    """DB 对象 → 前端友好结构（补充 URL 字段，去掉本地绝对路径）。"""
    return {
        "id": o["id"],
        "name": o["name"],
        "type": o["type"],
        "tags": o.get("tags", {}),
        "image_count": o.get("image_count", 0),
        "last_read_idx": o.get("last_read_idx", 0),
        "created_at": o.get("created_at"),
        "cover_url": f"/api/objects/{o['id']}/cover",
    }


def _serialize_image(img: dict, obj_id: str) -> dict:
    return {
        "id": img["id"],
        "filename": img["filename"],
        "sort_order": img["sort_order"],
        "thumb_url": f"/api/objects/{obj_id}/thumb/{img['id']}",
        "image_url": f"/api/objects/{obj_id}/image/{img['id']}",
    }


class SetupBody(BaseModel):
    path: str


class PathBody(BaseModel):
    path: str


class ObjectPatch(BaseModel):
    name: str | None = None
    tags: dict | None = None
    cover_image: str | None = None


class LastReadBody(BaseModel):
    idx: int


class ImportDirectoryBody(BaseModel):
    source_dir: str
    name: str
    tags: dict = {}
    is_new: bool = True
    obj_id: str | None = None


class ImportFilesBody(BaseModel):
    obj_id: str
    paths: list[str]


class MigrateBody(BaseModel):
    new_root: str


class NameBody(BaseModel):
    name: str


class ConfigBody(BaseModel):
    key: str
    value: str


# ── 全局状态 / 初始化 ─────────────────────────────────────────────────────────

@app.get("/api/state")
def api_state():
    with get_svc() as svc:
        root = _storage_root(svc)
        valid = bool(root) and os.path.isdir(root) and check_writable(root)[0]
        return {"storage_root": root, "valid": valid}


@app.post("/api/setup")
def api_setup(body: SetupBody):
    ok, err = check_writable(body.path)
    if not ok:
        raise HTTPException(400, err)
    with get_svc() as svc:
        svc.set_config("storage_root", body.path)
    return {"ok": True}


@app.post("/api/check-writable")
def api_check_writable(body: PathBody):
    ok, err = check_writable(body.path)
    return {"ok": ok, "error": err}


@app.post("/api/validate-name")
def api_validate_name(body: NameBody):
    from utils.file_utils import validate_windows_path_name
    ok, err = validate_windows_path_name(body.name)
    return {"ok": ok, "error": err}


# ── 对象查询 ──────────────────────────────────────────────────────────────────

@app.get("/api/objects")
def api_objects(q: str = "", include_r18: bool = False, filters: str = "{}"):
    try:
        tag_filters = json.loads(filters) if filters and filters != "{}" else {}
    except json.JSONDecodeError:
        raise HTTPException(400, "filters 不是合法 JSON")
    with get_svc() as svc:
        if q:
            objs = svc.search_objects(q, include_r18=include_r18)
        elif tag_filters:
            objs = svc.filter_by_tags(tag_filters, include_r18=include_r18)
        else:
            objs = svc.get_all_objects(include_r18=include_r18)
        return [_serialize_object(o) for o in objs]


@app.get("/api/objects/{oid}")
def api_object_detail(oid: str):
    with get_svc() as svc:
        obj = svc.get_object(oid)
        if not obj:
            raise HTTPException(404, "对象不存在")
        images = svc.get_images(oid)
        data = _serialize_object(obj)
        data["storage_path"] = obj.get("storage_path")
        data["images"] = [_serialize_image(i, oid) for i in images]
        return data


@app.get("/api/tag-values")
def api_tag_values():
    with get_svc() as svc:
        return {
            cat: svc.get_tag_values(cat)
            for cat in TAG_CATEGORY_ORDER if cat != "r18"
        }


# ── 图片 / 缩略图 ─────────────────────────────────────────────────────────────

_THUMB_SIZES = {"card": THUMBNAIL_SIZE, "grid": GRID_THUMB_SIZE, "cover": COVER_THUMB_SIZE}


def _serve_image(path: str, kind: str = "") -> FileResponse:
    if kind and kind in _THUMB_SIZES:
        with get_svc() as svc:
            root = _storage_root(svc)
        if not root:
            raise HTTPException(404, "图库未配置")
        thumb = generate_thumbnail(path, get_thumb_cache_dir(root), _THUMB_SIZES[kind])
        if thumb:
            return FileResponse(thumb, media_type="image/jpeg")
    if not os.path.isfile(path):
        raise HTTPException(404, "文件不存在")
    return FileResponse(path)


@app.get("/api/objects/{oid}/cover")
def api_object_cover(oid: str, kind: str = "card"):
    with get_svc() as svc:
        obj = svc.get_object(oid)
        if not obj:
            raise HTTPException(404, "对象不存在")
        cover = svc.resolve_cover(obj)
    if not cover:
        raise HTTPException(404, "无封面")
    return _serve_image(cover, kind)


@app.get("/api/objects/{oid}/image/{img_id}")
def api_object_image(oid: str, img_id: str, kind: str = ""):
    with get_svc() as svc:
        images = {i["id"]: i["filepath"] for i in svc.get_images(oid)}
    path = images.get(img_id)
    if not path:
        raise HTTPException(404, "图片不存在")
    return _serve_image(path, kind)


@app.get("/api/objects/{oid}/thumb/{img_id}")
def api_object_thumb(oid: str, img_id: str, kind: str = "grid"):
    return api_object_image(oid, img_id, kind)


# ── 对象变更 ──────────────────────────────────────────────────────────────────

@app.put("/api/objects/{oid}")
def api_update_object(oid: str, body: ObjectPatch):
    with get_svc() as svc:
        if not svc.get_object(oid):
            raise HTTPException(404, "对象不存在")
        if body.name is not None:
            svc.update_object_name(oid, body.name)
        if body.tags is not None:
            svc.set_object_tags(oid, body.tags)
        if body.cover_image is not None:
            svc.update_object_cover(oid, body.cover_image)
    return {"ok": True}


@app.post("/api/objects/{oid}/last-read")
def api_last_read(oid: str, body: LastReadBody):
    with get_svc() as svc:
        svc.update_last_read(oid, body.idx)
    return {"ok": True}


@app.delete("/api/objects/{oid}")
def api_delete_object(oid: str, delete_files: bool = False):
    with get_svc() as svc:
        svc.delete_object(oid, delete_files=delete_files,
                          storage_root=_storage_root(svc) or None)
    return {"ok": True}


# ── 导入 ──────────────────────────────────────────────────────────────────────

@app.post("/api/import/directory")
def api_import_directory(body: ImportDirectoryBody):
    if not os.path.isdir(body.source_dir):
        raise HTTPException(400, f"源目录不存在：{body.source_dir}")
    obj_id = body.obj_id or str(uuid.uuid4())
    with get_svc() as svc:
        try:
            ok, fail = svc.import_directory(
                obj_id, body.name, body.tags, body.source_dir,
                _storage_root(svc), is_new=body.is_new,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        except ImportCancelled:
            raise HTTPException(400, "导入已取消")
    return {"ok": True, "obj_id": obj_id, "success": ok, "failed": fail}


@app.post("/api/import/files")
def api_import_files(body: ImportFilesBody):
    missing = [p for p in body.paths if not os.path.isfile(p)]
    if missing:
        raise HTTPException(400, f"文件不存在：{missing[0]}")
    with get_svc() as svc:
        try:
            ok, fail = svc.import_single_files(body.obj_id, body.paths, _storage_root(svc))
        except ValueError as e:
            raise HTTPException(400, str(e))
    return {"ok": True, "success": ok, "failed": fail}


# ── 库管理 ────────────────────────────────────────────────────────────────────

@app.post("/api/migrate")
def api_migrate(body: MigrateBody):
    with get_svc() as svc:
        try:
            moved, warnings = migrate_library(svc.db, body.new_root)
        except Exception as e:
            raise HTTPException(400, str(e))
    return {"ok": True, "moved": moved, "warnings": warnings}


# ── 配置 ──────────────────────────────────────────────────────────────────────

@app.get("/api/config/{key}")
def api_get_config(key: str):
    with get_svc() as svc:
        return {"key": key, "value": svc.get_config(key)}


@app.put("/api/config")
def api_set_config(body: ConfigBody):
    with get_svc() as svc:
        svc.set_config(body.key, body.value)
    return {"ok": True}


# ── 静态托管前端（生产模式） ──────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def api_index():
    """index.html 不缓存：资源文件名带 hash 可长缓存，但入口页必须实时生效。"""
    return FileResponse(
        os.path.join(FRONTEND_DIST, "index.html"),
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
