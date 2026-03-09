
# db.py (final version)

import json
import os
from contextlib import contextmanager
import psycopg

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

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

            cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name TEXT,
                price INTEGER,
                description TEXT,
                image TEXT,
                category TEXT
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                tg_user TEXT,
                metro TEXT,
                delivery_time TEXT,
                total INTEGER,
                items_json JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)

        conn.commit()


def add_product(name, price, description="", image="", category=""):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO products (name, price, description, image, category)
            VALUES (%s,%s,%s,%s,%s)
            RETURNING id
            """, (name, price, description, image, category))

            pid = cur.fetchone()[0]

        conn.commit()
        return pid


def get_products():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT id,name,price,description,image,category
            FROM products
            ORDER BY id DESC
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
            "category": r[5],
        })

    return result


def create_order(tg_user, metro, delivery_time, items, total):

    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
            INSERT INTO orders (tg_user, metro, delivery_time, total, items_json)
            VALUES (%s,%s,%s,%s,%s::jsonb)
            RETURNING id
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
