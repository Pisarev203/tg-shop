
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path("shop.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL;")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sort INTEGER NOT NULL DEFAULT 0
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL DEFAULT 0,
            description TEXT NOT NULL DEFAULT "",
            photo_url TEXT NOT NULL DEFAULT "",
            category_id INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            sort INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            tg_user_id INTEGER,
            tg_username TEXT,
            metro TEXT NOT NULL DEFAULT "",
            delivery_time TEXT NOT NULL DEFAULT "",
            comment TEXT NOT NULL DEFAULT "",
            items_json TEXT NOT NULL DEFAULT "[]",
            total_price INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT "new"
        );
        """)


# -------------------- Categories --------------------

def categories_list() -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name, sort FROM categories ORDER BY sort, id"
        ).fetchall()
    return [dict(r) for r in rows]


def category_create(name: str, sort: int = 0) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название категории пустое")

    with _conn() as conn:
        conn.execute("INSERT INTO categories(name, sort) VALUES(?,?)", (name, int(sort)))
        row = conn.execute(
            "SELECT id, name, sort FROM categories ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row)


def category_update(cat_id: int, name: str, sort: int = 0) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название категории пустое")

    with _conn() as conn:
        conn.execute(
            "UPDATE categories SET name=?, sort=? WHERE id=?",
            (name, int(sort), int(cat_id))
        )


def category_delete(cat_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE products SET category_id=NULL WHERE category_id=?", (int(cat_id),))
        conn.execute("DELETE FROM categories WHERE id=?", (int(cat_id),))


# -------------------- Products --------------------

def products_list(active_only: bool = False) -> List[Dict[str, Any]]:
    q = """
    SELECT p.id, p.name, p.price, p.description, p.photo_url, p.category_id,
           p.is_active, p.sort,
           c.name AS category_name
    FROM products p
    LEFT JOIN categories c ON c.id = p.category_id
    """
    if active_only:
        q += " WHERE p.is_active=1 "
    q += " ORDER BY p.sort, p.id DESC"

    with _conn() as conn:
        rows = conn.execute(q).fetchall()
    return [dict(r) for r in rows]


def product_create(
    name: str,
    price: int,
    description: str = "",
    photo_url: str = "",
    category_id: Optional[int] = None,
    is_active: int = 1,
    sort: int = 0
) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название товара пустое")

    with _conn() as conn:
        conn.execute("""
            INSERT INTO products(name, price, description, photo_url, category_id, is_active, sort)
            VALUES(?,?,?,?,?,?,?)

""", (name, int(price), description or "", photo_url or "", category_id, int(is_active), int(sort)))

        row = conn.execute("SELECT * FROM products ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row)


def product_update(
    product_id: int,
    name: str,
    price: int,
    description: str = "",
    photo_url: str = "",
    category_id: Optional[int] = None,
    is_active: int = 1,
    sort: int = 0
) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название товара пустое")

    with _conn() as conn:
        conn.execute("""
            UPDATE products
            SET name=?, price=?, description=?, photo_url=?, category_id=?, is_active=?, sort=?
            WHERE id=?
        """, (name, int(price), description or "", photo_url or "", category_id, int(is_active), int(sort), int(product_id)))


def product_delete(product_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM products WHERE id=?", (int(product_id),))


# -------------------- Orders --------------------

def order_create(
    tg_user_id: Optional[int],
    tg_username: str,
    metro: str,
    delivery_time: str,
    comment: str,
    items_json: str,
    total_price: int
) -> Dict[str, Any]:
    with _conn() as conn:
        conn.execute("""
            INSERT INTO orders(tg_user_id, tg_username, metro, delivery_time, comment, items_json, total_price)
            VALUES(?,?,?,?,?,?,?)
        """, (tg_user_id, tg_username or "", metro or "", delivery_time or "", comment or "", items_json or "[]", int(total_price)))

        row = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row)


def orders_list(limit: int = 200) -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ?",
            (int(limit),)
        ).fetchall()
    return [dict(r) for r in rows)


def order_update_status(order_id: int, status: str) -> None:
    status = (status or "").strip() or "new"
    with _conn() as conn:
        conn.execute("UPDATE orders SET status=? WHERE id=?", (status, int(order_id)))
