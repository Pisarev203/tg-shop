
import json
import os
from contextlib import contextmanager
import psycopg

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задан")


@contextmanager
def get_conn():
    conn = psycopg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:

            # create table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    price INTEGER NOT NULL DEFAULT 0,
                    description TEXT DEFAULT '',
                    image TEXT DEFAULT '',
                    category TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # auto add missing columns (fix old DB)
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS image TEXT DEFAULT '';")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS category TEXT DEFAULT '';")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    tg_user TEXT NOT NULL,
                    metro TEXT DEFAULT '',
                    delivery_time TEXT DEFAULT '',
                    total INTEGER NOT NULL DEFAULT 0,
                    items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    product_name TEXT NOT NULL,
                    qty INTEGER NOT NULL DEFAULT 1,
                    price INTEGER NOT NULL DEFAULT 0,
                    line_total INTEGER NOT NULL DEFAULT 0
                );
            """)

        conn.commit()


def add_product(name, price, description="", image="", category=""):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO products (name, price, description, image, category)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
            """, (name, price, description, image, category))

            product_id = cur.fetchone()[0]

        conn.commit()
        return product_id


def get_products():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, price, description, image, category
                    FROM products
                    ORDER BY id DESC;
                """)
                rows = cur.fetchall()

        result = []
        for r in rows:
            result.append({
                "id": r[0],
                "name": r[1],
                "price": r[2],
                "description": r[3],
                "image": r[4],
                "category": r[5]
            })

        return result

    except Exception as e:
        print("DB ERROR:", e)
        return []


def delete_product(product_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM products WHERE id=%s", (product_id,))
        conn.commit()


def create_order(tg_user, metro, delivery_time, items, total):
    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                INSERT INTO orders (tg_user, metro, delivery_time, total, items_json)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING id;
            """, (
                tg_user,
                metro,
                delivery_time,
                total,
                json.dumps(items, ensure_ascii=False)
            ))

            order_id = cur.fetchone()[0]

        conn.commit()
        return order_id


def get_orders(limit=50):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, tg_user, metro, delivery_time, total, items_json, created_at
                FROM orders
                ORDER BY id DESC
                LIMIT %s;
            """, (limit,))

            rows = cur.fetchall()

    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "tg_user": r[1],
            "metro": r[2],
            "delivery_time": r[3],
            "total": r[4],
            "items": r[5],
            "created_at": str(r[6])
        })

    return result
