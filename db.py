# db.py
import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "shop.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        sort INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price INTEGER NOT NULL,
        description TEXT,
        photo TEXT,
        category_id INTEGER,
        is_active INTEGER DEFAULT 1
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT,
        tg_user TEXT,
        metro TEXT,
        delivery_time TEXT,
        items TEXT,
        total INTEGER
    )
    """)

    conn.commit()
    conn.close()


# ---------- Categories ----------

def list_categories():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, sort FROM categories ORDER BY sort ASC, id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_category(name: str, sort: int = 0):
    name = name.strip()
    if not name:
        raise ValueError("Название категории пустое")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO categories (name, sort) VALUES (?, ?)",
        (name, sort)
    )
    conn.commit()

    row = cur.execute(
        "SELECT id, name, sort FROM categories WHERE id=?",
        (cur.lastrowid,)
    ).fetchone()

    conn.close()
    return dict(row)


def update_category(cat_id: int, name: str, sort: int = 0):
    conn = get_conn()
    conn.execute(
        "UPDATE categories SET name=?, sort=? WHERE id=?",
        (name.strip(), sort, cat_id)
    )
    conn.commit()
    conn.close()


def delete_category(cat_id: int):
    conn = get_conn()
    conn.execute("UPDATE products SET category_id=NULL WHERE category_id=?", (cat_id,))
    conn.execute("DELETE FROM categories WHERE id=?", (cat_id,))
    conn.commit()
    conn.close()


# ---------- Products ----------

def list_products(active_only: bool = True):
    conn = get_conn()
    if active_only:
        rows = conn.execute(
            "SELECT * FROM products WHERE is_active=1 ORDER BY id DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM products ORDER BY id DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_product(name, price, description, image_url, category_id):
    conn = get_conn()
    conn.execute("""
        INSERT INTO products (name, price, description, photo, category_id, is_active)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (name, price, description, image_url, category_id))
    conn.commit()
    conn.close()


def create_product(name, price, description="", photo="", category_id=None, is_active=True):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO products (name, price, description, photo, category_id, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, price, description, photo, category_id, int(is_active)))
    conn.commit()

    row = cur.execute(
        "SELECT * FROM products WHERE id=?",
        (cur.lastrowid,)
    ).fetchone()

    conn.close()
    return dict(row)


def update_product(pid, name, price, description="", photo="", category_id=None, is_active=True):
    conn = get_conn()
    conn.execute("""
        UPDATE products
        SET name=?, price=?, description=?, photo=?, category_id=?, is_active=?
        WHERE id=?
    """, (name, price, description, photo, category_id, int(is_active), pid))
    conn.commit()
    conn.close()


def delete_product(pid):
    conn = get_conn()
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()


# ---------- Orders ----------

def create_order(tg_user, metro, delivery_time, items, total):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders (created_at, tg_user, metro, delivery_time, items, total)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        tg_user,
        metro,
        delivery_time,
        str(items),
        total
    ))
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id
