
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
            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    price INTEGER NOT NULL DEFAULT 0,
                    description TEXT DEFAULT '',
                    image TEXT DEFAULT '',
                    category TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT NOW()
                );
                '''
            )

            cur.execute(
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';"
            )
            cur.execute(
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS image TEXT DEFAULT '';"
            )
            cur.execute(
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS category TEXT DEFAULT '';"
            )

            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    tg_user TEXT NOT NULL,
                    metro TEXT DEFAULT '',
                    delivery_time TEXT DEFAULT '',
                    total INTEGER NOT NULL DEFAULT 0,
                    items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                '''
            )

            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS metro TEXT DEFAULT '';")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_time TEXT DEFAULT '';")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS total INTEGER NOT NULL DEFAULT 0;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS items_json JSONB NOT NULL DEFAULT '[]'::jsonb;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();")

            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS order_items (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    product_name TEXT NOT NULL,
                    qty INTEGER NOT NULL DEFAULT 1,
                    price INTEGER NOT NULL DEFAULT 0,
                    line_total INTEGER NOT NULL DEFAULT 0
                );
                '''
            )

        conn.commit()


def add_product(name, price, description="", image="", category=""):
    name = str(name or "").strip()
    description = str(description or "").strip()
    image = str(image or "").strip()
    category = str(category or "").strip()

    if not name:
        raise ValueError("Название товара пустое")

    price = int(price)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO products (name, price, description, image, category)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
                ''',
                (name, price, description, image, category),
            )
            product_id = cur.fetchone()[0]

        conn.commit()
        return product_id


def get_products():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    '''
                    SELECT id, name, price, description, image, category
                    FROM products
                    ORDER BY id DESC;
                    '''
                )
                rows = cur.fetchall()

        result = []
        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "price": row[2],
                    "description": row[3],
                    "image": row[4],
                    "category": row[5],
                }
            )
        return result
    except Exception as e:
        print("DB ERROR:", e)
        return []


def delete_product(product_id):
    product_id = int(product_id)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                '''
                DELETE FROM products
                WHERE id = %s;
                ''',
                (product_id,),
            )

        conn.commit()


def create_order(tg_user, metro, delivery_time, items, total):
    tg_user = str(tg_user or "").strip()
    metro = str(metro or "").strip()
    delivery_time = str(delivery_time or "").strip()

    if not isinstance(items, list):
        items = []

    normalized_items = []
    calculated_total = 0

    for item in items:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "товар")).strip() or "товар"

        try:
            qty = int(item.get("qty", 1) or 1)
        except:
            qty = 1

        try:
            price = int(item.get("price", 0) or 0)
        except:
            price = 0

        if qty < 1:
            qty = 1
        if price < 0:
            price = 0

        line_total = qty * price
        calculated_total += line_total

        normalized_items.append(
            {
                "name": name,
                "qty": qty,
                "price": price,
                "line_total": line_total,
            }
        )

    try:
        total = int(total)
    except:
        total = calculated_total

    if total <= 0 and calculated_total > 0:
        total = calculated_total

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO orders (tg_user, metro, delivery_time, total, items_json)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING id;
                ''',
                (
                    tg_user,
                    metro,
                    delivery_time,
                    total,
                    json.dumps(normalized_items, ensure_ascii=False),
                ),
            )
            order_id = cur.fetchone()[0]

            for item in normalized_items:
                cur.execute(
                    '''
                    INSERT INTO order_items (order_id, product_name, qty, price, line_total)
                    VALUES (%s, %s, %s, %s, %s);
                    ''',
                    (
                        order_id,
                        item["name"],
                        item["qty"],
                        item["price"],
                        item["line_total"],
                    ),
                )

        conn.commit()
        return order_id
