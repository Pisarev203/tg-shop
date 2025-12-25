import os
import psycopg
from psycopg.rows import dict_row
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")

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
                price INTEGER NOT NULL,
                description TEXT,
                photo TEXT,
                category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                is_active BOOLEAN DEFAULT TRUE
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP,
                tg_user TEXT,
                metro TEXT,
                delivery_time TEXT,
                items JSONB,
                total INTEGER
            );
            """)

def list_categories():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM categories ORDER BY sort, id")
            return cur.fetchall()

def create_category(name, sort=0):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO categories (name, sort) VALUES (%s,%s) RETURNING *",
                (name.strip(), sort)
            )
            return cur.fetchone()

def update_category(cat_id, name, sort=0):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE categories SET name=%s, sort=%s WHERE id=%s",
                (name.strip(), sort, cat_id)
            )

def delete_category(cat_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM categories WHERE id=%s", (cat_id,))

def list_products(active_only=True):
    q = "SELECT * FROM products"
    if active_only:
        q += " WHERE is_active=TRUE"
    q += " ORDER BY id DESC"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(q)
            return cur.fetchall()

def create_product(name, price, description="", photo="", category_id=None, is_active=True):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO products
                (name, price, description, photo, category_id, is_active)
                VALUES (%s,%s,%s,%s,%s,%s)
                RETURNING *
            """, (name, price, description, photo, category_id, is_active))
            return cur.fetchone()

def update_product(pid, name, price, description="", photo="", category_id=None, is_active=True):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET name=%s, price=%s, description=%s, photo=%s,
                    category_id=%s, is_active=%s
                WHERE id=%s
            """, (name, price, description, photo, category_id, is_active, pid))

def delete_product(pid):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM products WHERE id=%s", (pid,))

def create_order(tg_user, metro, delivery_time, items, total):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders
                (created_at, tg_user, metro, delivery_time, items, total)
                VALUES (%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (
                datetime.utcnow(),
                tg_user,
                metro,
                delivery_time,
                items,
                total
            ))
            return cur.fetchone()["id"]
