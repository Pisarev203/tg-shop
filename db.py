import os
import json
import psycopg
from psycopg.rows import dict_row
from datetime import datetime

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задан")

def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    sort INTEGER DEFAULT 0
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    price INTEGER NOT NULL DEFAULT 0,
                    description TEXT DEFAULT '',
                    photo TEXT DEFAULT '',
                    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                    is_active BOOLEAN DEFAULT TRUE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT NOW(),
                    tg_user TEXT DEFAULT '',
                    metro TEXT DEFAULT '',
                    delivery_time TEXT DEFAULT '',
                    items JSONB DEFAULT '[]'::jsonb,
                    total INTEGER DEFAULT 0
                );
            """)
        conn.commit()

# -------- categories --------

def list_categories():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name, sort FROM categories ORDER BY sort, id")
        return cur.fetchall()

def create_category(name: str, sort: int = 0):
    name = (name or "").strip()
    if not name:
        raise ValueError("Название категории пустое")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO categories(name, sort) VALUES (%s,%s) RETURNING id, name, sort",
            (name, int(sort)),
        )
        row = cur.fetchone()
        conn.commit()
        return row

def update_category(cat_id: int, name: str, sort: int = 0):
    name = (name or "").strip()
    if not name:
        raise ValueError("Название категории пустое")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE categories SET name=%s, sort=%s WHERE id=%s",
            (name, int(sort), int(cat_id)),
        )
        conn.commit()

def delete_category(cat_id: int):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE products SET category_id=NULL WHERE category_id=%s", (int(cat_id),))
        cur.execute("DELETE FROM categories WHERE id=%s", (int(cat_id),))
        conn.commit()

# -------- products --------

def list_products(active_only: bool = True):
    q = """
        SELECT p.id, p.name, p.price, p.description, p.photo, p.category_id, p.is_active,
               c.name AS category
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
    """
    if active_only:
        q += " WHERE p.is_active = TRUE "
    q += " ORDER BY p.id DESC"

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(q)
        return cur.fetchall()

def create_product(name: str, price: int, description: str = "", photo: str = "",
                   category_id=None, is_active: bool = True):
    name = (name or "").strip()
    if not name:
        raise ValueError("Название товара пустое")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO products (name, price, description, photo, category_id, is_active)
            VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING id, name, price, description, photo, category_id, is_active
        """, (name, int(price), description or "", photo or "", category_id, bool(is_active)))
        row = cur.fetchone()
        conn.commit()
        return row

def update_product(pid: int, name: str, price: int, description: str = "", photo: str = "",
                   category_id=None, is_active: bool = True):
    name = (name or "").strip()
    if not name:
        raise ValueError("Название товара пустое")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE products
            SET name=%s, price=%s, description=%s, photo=%s, category_id=%s, is_active=%s
            WHERE id=%s
        """, (name, int(price), description or "", photo or "", category_id, bool(is_active), int(pid)))
        conn.commit()

def delete_product(pid: int):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM products WHERE id=%s", (int(pid),))
        conn.commit()

# -------- orders --------

def create_order(tg_user: str, metro: str, delivery_time: str, items, total: int):
    # items может быть списком dict — кладём в JSONB
    items_json = json.dumps(items or [], ensure_ascii=False)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO orders (created_at, tg_user, metro, delivery_time, items, total)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id
        """, (
            datetime.utcnow(),
            (tg_user or ""),
            (metro or ""),
            (delivery_time or ""),
            items_json,
            int(total or 0),
        ))
        oid = cur.fetchone()["id"]
        conn.commit()
        return oid
