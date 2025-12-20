import sqlite3
from typing import List, Dict, Any, Optional
from pathlib import Path

DB_PATH = Path("shop.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sort INTEGER DEFAULT 0
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            category_id INTEGER,
            description TEXT,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        )
        """)


# ---------- Categories ----------

def get_categories() -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name, sort FROM categories ORDER BY sort, id"
        ).fetchall()
    return [dict(r) for r in rows]


def create_category(name: str, sort: int = 0) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название категории пустое")

    with _conn() as conn:
        conn.execute(
            "INSERT INTO categories(name, sort) VALUES (?, ?)",
            (name, int(sort))
        )
        row = conn.execute(
            "SELECT id, name, sort FROM categories WHERE name=?",
            (name,)
        ).fetchone()

    return dict(row)


def update_category(cat_id: int, name: str, sort: int = 0) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название категории пустое")

    with _conn() as conn:
        conn.execute(
            "UPDATE categories SET name=?, sort=? WHERE id=?",
            (name, int(sort), int(cat_id))
        )


def delete_category(cat_id: int) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE products SET category_id=NULL WHERE category_id=?",
            (int(cat_id),)
        )
        conn.execute(
            "DELETE FROM categories WHERE id=?",
            (int(cat_id),)
        )


# ---------- Products ----------

def get_products() -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT p.id, p.name, p.price, p.description,
                   c.id as category_id, c.name as category_name
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            ORDER BY p.id DESC
        """).fetchall()
    return [dict(r) for r in rows]


def create_product(
    name: str,
    price: int,
    category_id: Optional[int] = None,
    description: str = ""
) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название товара пустое")

    with _conn() as conn:
        conn.execute("""
            INSERT INTO products(name, price, category_id, description)
            VALUES (?, ?, ?, ?)
        """, (name, int(price), category_id, description))

        row = conn.execute(
            "SELECT * FROM products ORDER BY id DESC LIMIT 1"
        ).fetchone()

    return dict(row)


def delete_product(product_id: int) -> None:
    with _conn() as conn:
        conn.execute(
            "DELETE FROM products WHERE id=?",
            (int(product_id),)
        )
