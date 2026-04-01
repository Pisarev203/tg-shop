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
                    promo_type TEXT NOT NULL DEFAULT 'none',
                    promo_text TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT NOW()
                );
                '''
            )

            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS image TEXT DEFAULT '';")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS category TEXT DEFAULT '';")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS promo_type TEXT NOT NULL DEFAULT 'none';")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS promo_text TEXT DEFAULT '';")

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


def _normalize_promo_type(value: str) -> str:
    value = str(value or "none").strip().lower()
    if value not in {"none", "bogo", "gift"}:
        return "none"
    return value


def add_product(name, price, description="", image="", category="", promo_type="none", promo_text=""):
    name = str(name or "").strip()
    description = str(description or "").strip()
    image = str(image or "").strip()
    category = str(category or "").strip()
    promo_type = _normalize_promo_type(promo_type)
    promo_text = str(promo_text or "").strip()

    if not name:
        raise ValueError("Название товара пустое")

    price = int(price)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO products (name, price, description, image, category, promo_type, promo_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                ''',
                (name, price, description, image, category, promo_type, promo_text),
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
                    SELECT id, name, price, description, image, category, promo_type, promo_text
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
                    "promo_type": row[6],
                    "promo_text": row[7],
                }
            )
        return result
    except Exception as e:
        print("DB ERROR:", e)
        return []


def get_product(product_id):
    product_id = int(product_id)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                '''
                SELECT id, name, price, description, image, category, promo_type, promo_text
                FROM products
                WHERE id = %s;
                ''',
                (product_id,),
            )
            row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "name": row[1],
        "price": row[2],
        "description": row[3],
        "image": row[4],
        "category": row[5],
        "promo_type": row[6],
        "promo_text": row[7],
    }


def update_product(product_id, name, price, description="", image="", category="", promo_type="none", promo_text=""):
    product_id = int(product_id)
    name = str(name or "").strip()
    description = str(description or "").strip()
    image = str(image or "").strip()
    category = str(category or "").strip()
    promo_type = _normalize_promo_type(promo_type)
    promo_text = str(promo_text or "").strip()

    if not name:
        raise ValueError("Название товара пустое")

    price = int(price)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                '''
                UPDATE products
                SET name = %s,
                    price = %s,
                    description = %s,
                    image = %s,
                    category = %s,
                    promo_type = %s,
                    promo_text = %s
                WHERE id = %s;
                ''',
                (name, price, description, image, category, promo_type, promo_text, product_id),
            )
        conn.commit()


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


def apply_promotions(items):
    normalized_items = []
    calculated_total = 0

    for item in items:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "товар")).strip() or "товар"

        try:
            qty = int(item.get("qty", 1) or 1)
        except Exception:
            qty = 1

        try:
            price = int(item.get("price", 0) or 0)
        except Exception:
            price = 0

        promo_type = _normalize_promo_type(item.get("promo_type", "none"))
        promo_text = str(item.get("promo_text", "") or "").strip()

        if qty < 1:
            qty = 1
        if price < 0:
            price = 0

        free_qty = 0
        gift_items = []
        chargeable_qty = qty
        promo_note = ""

        if promo_type == "bogo":
            free_qty = qty // 2
            chargeable_qty = qty - free_qty
            promo_note = promo_text or "Акция 1+1"
        elif promo_type == "gift":
            gift_name = promo_text or "Подарок"
            gift_qty = qty
            gift_items.append({
                "name": gift_name,
                "qty": gift_qty,
                "price": 0,
                "line_total": 0,
                "is_gift": True,
                "promo_note": f"Подарок к {name}",
            })
            promo_note = f"Подарок: {gift_name}"

        line_total = chargeable_qty * price
        calculated_total += line_total

        normalized_items.append(
            {
                "name": name,
                "qty": qty,
                "price": price,
                "line_total": line_total,
                "chargeable_qty": chargeable_qty,
                "free_qty": free_qty,
                "promo_type": promo_type,
                "promo_text": promo_text,
                "promo_note": promo_note,
            }
        )
        normalized_items.extend(gift_items)

    return normalized_items, calculated_total


def create_order(tg_user, metro, delivery_time, items, total):
    tg_user = str(tg_user or "").strip()
    metro = str(metro or "").strip()
    delivery_time = str(delivery_time or "").strip()

    if not isinstance(items, list):
        items = []

    normalized_items, calculated_total = apply_promotions(items)

    try:
        total = int(total)
    except Exception:
        total = calculated_total

    if total != calculated_total:
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
