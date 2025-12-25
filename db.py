import os
import json
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задан")

def get_conn():
    return psycopg.connect(DATABASE_URL)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                tg_user TEXT,
                metro TEXT,
                delivery_time TEXT,
                items JSONB,
                total INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)
        conn.commit()

def create_order(tg_user, metro, delivery_time, items, total):
    items_json = json.dumps(items, ensure_ascii=False)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders (tg_user, metro, delivery_time, items, total)
                VALUES (%s, %s, %s, %s::jsonb, %s)
                RETURNING id
            """, (tg_user, metro, delivery_time, items_json, total))
            order_id = cur.fetchone()[0]
        conn.commit()

    return order_id
