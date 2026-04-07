import sqlite3
from typing import Any, Dict, List, Optional


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._in_transaction = False
        self._init_tables()

    def begin(self):
        if not self._in_transaction:
            self.conn.execute("BEGIN")
            self._in_transaction = True

    def commit(self):
        self.conn.commit()
        self._in_transaction = False

    def rollback(self):
        self.conn.rollback()
        self._in_transaction = False

    def _commit_if_needed(self):
        if not self._in_transaction:
            self.conn.commit()

    def _init_tables(self):
        cur = self.conn.cursor()
        cur.executescript("""
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS objects (
                id            TEXT PRIMARY KEY,
                type          TEXT NOT NULL CHECK(type IN ('directory','file')),
                name          TEXT NOT NULL,
                source_path   TEXT,
                storage_path  TEXT,
                cover_image   TEXT,
                last_read_idx INTEGER DEFAULT 0,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tags (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                object_id TEXT NOT NULL,
                category  TEXT NOT NULL,
                value     TEXT NOT NULL,
                FOREIGN KEY (object_id) REFERENCES objects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS images (
                id         TEXT PRIMARY KEY,
                object_id  TEXT NOT NULL,
                filename   TEXT NOT NULL,
                filepath   TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (object_id) REFERENCES objects(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tags_object ON tags(object_id);
            CREATE INDEX IF NOT EXISTS idx_images_object ON images(object_id);
        """)
        self._commit_if_needed()

    def get_config(self, key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM config WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_config(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO config(key,value) VALUES(?,?)", (key, value)
        )
        self._commit_if_needed()

    def create_object(self, obj_id: str, obj_type: str, name: str,
                      source_path: str, storage_path: str) -> bool:
        try:
            self.conn.execute(
                """INSERT INTO objects(id,type,name,source_path,storage_path)
                   VALUES(?,?,?,?,?)""",
                (obj_id, obj_type, name, source_path, storage_path)
            )
            self._commit_if_needed()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_all_objects(self, include_r18: bool = False) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM objects ORDER BY created_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            obj = dict(row)
            obj["tags"] = self._get_tags(obj["id"])
            if not include_r18 and obj["tags"].get("r18", False):
                continue
            result.append(obj)
        return result

    def get_object(self, obj_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM objects WHERE id=?", (obj_id,)
        ).fetchone()
        if not row:
            return None
        obj = dict(row)
        obj["tags"] = self._get_tags(obj_id)
        return obj

    def update_object_name(self, obj_id: str, name: str):
        self.conn.execute(
            "UPDATE objects SET name=? WHERE id=?", (name, obj_id)
        )
        self._commit_if_needed()

    def update_object_cover(self, obj_id: str, cover_image: str):
        self.conn.execute(
            "UPDATE objects SET cover_image=? WHERE id=?", (cover_image, obj_id)
        )
        self._commit_if_needed()

    def update_object_storage_path(self, obj_id: str, storage_path: str):
        self.conn.execute(
            "UPDATE objects SET storage_path=? WHERE id=?", (storage_path, obj_id)
        )
        self._commit_if_needed()

    def update_last_read(self, obj_id: str, idx: int):
        self.conn.execute(
            "UPDATE objects SET last_read_idx=? WHERE id=?", (idx, obj_id)
        )
        self._commit_if_needed()

    def delete_object(self, obj_id: str):
        self.conn.execute("DELETE FROM objects WHERE id=?", (obj_id,))
        self._commit_if_needed()
        self.cleanup_all_orphan_tags()

    def cleanup_all_orphan_tags(self):
        valid_objects = set(
            row["id"] for row in self.conn.execute("SELECT id FROM objects").fetchall()
        )
        all_tags = self.conn.execute(
            "SELECT id, object_id, category, value FROM tags"
        ).fetchall()

        orphan_tag_ids = []
        for tag in all_tags:
            if tag["object_id"] not in valid_objects:
                orphan_tag_ids.append(tag["id"])

        if orphan_tag_ids:
            placeholders = ",".join("?" * len(orphan_tag_ids))
            self.conn.execute(
                f"DELETE FROM tags WHERE id IN ({placeholders})", orphan_tag_ids
            )
            self._commit_if_needed()

    def _cleanup_orphan_tags(self, tags: Dict):
        self.cleanup_all_orphan_tags()

    def search_objects(self, keyword: str, include_r18: bool = False) -> List[Dict]:
        keyword = f"%{keyword}%"
        rows = self.conn.execute(
            """SELECT DISTINCT o.* FROM objects o
               LEFT JOIN tags t ON t.object_id = o.id
               WHERE o.name LIKE ? OR t.value LIKE ?
               ORDER BY o.created_at DESC""",
            (keyword, keyword)
        ).fetchall()
        result = []
        for row in rows:
            obj = dict(row)
            obj["tags"] = self._get_tags(obj["id"])
            if not include_r18 and obj["tags"].get("r18", False):
                continue
            result.append(obj)
        return result

    def filter_by_tags(self, tag_filters: Dict[str, List[str]],
                       include_r18: bool = False) -> List[Dict]:
        all_objs = self.get_all_objects(include_r18)
        if not tag_filters:
            return all_objs
        result = []
        for obj in all_objs:
            tags = obj["tags"]
            match = True
            for cat, values in tag_filters.items():
                if not values:
                    continue
                obj_vals = tags.get(cat, [])
                if isinstance(obj_vals, bool):
                    obj_vals = [obj_vals]
                if not any(v in obj_vals for v in values):
                    match = False
                    break
            if match:
                result.append(obj)
        return result

    def _get_tags(self, obj_id: str) -> Dict:
        rows = self.conn.execute(
            "SELECT category, value FROM tags WHERE object_id=?", (obj_id,)
        ).fetchall()
        tags: Dict[str, Any] = {}
        for row in rows:
            cat, val = row["category"], row["value"]
            if cat == "r18":
                tags["r18"] = val == "true"
            elif cat in tags:
                tags[cat].append(val)
            else:
                tags[cat] = [val]
        return tags

    def set_tags(self, obj_id: str, tags: Dict):
        self.conn.execute("DELETE FROM tags WHERE object_id=?", (obj_id,))
        rows = []
        for cat, val in tags.items():
            if cat == "r18":
                rows.append((obj_id, "r18", "true" if val else "false"))
            elif isinstance(val, list):
                for v in val:
                    if v:
                        rows.append((obj_id, cat, v))
            else:
                if val:
                    rows.append((obj_id, cat, str(val)))
        if rows:
            self.conn.executemany(
                "INSERT INTO tags(object_id,category,value) VALUES(?,?,?)", rows
            )
        self._commit_if_needed()

    def get_all_tag_values(self, category: str) -> List[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT value FROM tags WHERE category=? ORDER BY value",
            (category,)
        ).fetchall()
        return [r["value"] for r in rows]

    def add_image(self, img_id: str, obj_id: str, filename: str,
                  filepath: str, sort_order: int = 0):
        self.conn.execute(
            """INSERT OR IGNORE INTO images(id,object_id,filename,filepath,sort_order)
               VALUES(?,?,?,?,?)""",
            (img_id, obj_id, filename, filepath, sort_order)
        )
        self._commit_if_needed()

    def update_image_filepath(self, img_id: str, filepath: str):
        self.conn.execute(
            "UPDATE images SET filepath=? WHERE id=?", (filepath, img_id)
        )
        self._commit_if_needed()

    def get_images(self, obj_id: str) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM images WHERE object_id=? ORDER BY sort_order, filename",
            (obj_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_image_count(self, obj_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM images WHERE object_id=?", (obj_id,)
        ).fetchone()
        return row["cnt"]

    def close(self):
        self.conn.close()
