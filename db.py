import json
import os
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

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


def create_order(tg_user: str, metro: str, delivery_time: str, items, total: int) -> int:
    items_json = json.dumps(items or [], ensure_ascii=False)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders (created_at, tg_user, metro, delivery_time, items, total)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                RETURNING id
                """,
                (datetime.utcnow(), tg_user or "", metro or "", delivery_time or "", items_json, int(total or 0)),
            )
            oid = cur.fetchone()["id"]
        conn.commit()
    return oid
