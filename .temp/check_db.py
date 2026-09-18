import sqlite3, os

db = os.path.join(os.environ['APPDATA'], 'MangaShelf', 'library.db')
conn = sqlite3.connect(db)
c = conn.cursor()

print("=== OBJECTS ===")
c.execute("SELECT id, name, cover_image, storage_path FROM objects LIMIT 5")
for r in c.fetchall():
    print(r)

print("\n=== IMAGES ===")
c.execute("SELECT id, object_id, filename, filepath FROM images LIMIT 5")
for r in c.fetchall():
    print(r)

print("\n=== CONFIG (storage_root) ===")
c.execute("SELECT key, value FROM config WHERE key='storage_root'")
for r in c.fetchall():
    print(r)

conn.close()
