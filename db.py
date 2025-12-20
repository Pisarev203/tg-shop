# db.py
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

# --- путь к базе (Render/локально одинаково нормально) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "shop.db")


def _ensure_dirs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


@contextmanager
def _conn():
    _ensure_dirs()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Создаёт таблицы, если их нет."""
    with _conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sort INTEGER NOT NULL DEFAULT 0
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '',
                photo TEXT NOT NULL DEFAULT '',
                category_id INTEGER NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                customer_name TEXT NOT NULL DEFAULT '',
                customer_phone TEXT NOT NULL DEFAULT '',
                customer_address TEXT NOT NULL DEFAULT '',
                comment TEXT NOT NULL DEFAULT '',
                items_json TEXT NOT NULL DEFAULT '[]',
                total INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'new'
            );
            """
        )


# ----------------- helpers -----------------

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row) if row is not None else {}


# ----------------- Public API -----------------

def list_public_products() -> List[Dict[str, Any]]:
    """
    Публичный список товаров для магазина.
    Возвращает только активные товары, с названием категории.
    """
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT
                p.id, p.name, p.price, p.description, p.photo,
                p.category_id,
                p.is_active,
                c.name AS category,
                COALESCE(c.sort, 0) AS cat_sort
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE p.is_active = 1
            ORDER BY cat_sort ASC, c.name ASC, p.id DESC;
            """
        ).fetchall()

    return [dict(r) for r in rows]


# ----------------- Admin API: Categories -----------------

def list_categories() -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name, sort FROM categories ORDER BY sort ASC, id ASC;"
        ).fetchall()
    return [dict(r) for r in rows]


def create_category(name: str, sort: int = 0) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название категории пустое")

    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO categories(name, sort) VALUES(?, ?);",
            (name, int(sort)),
        )
        cat_id = cur.lastrowid
        row = conn.execute(
            "SELECT id, name, sort FROM categories WHERE id=?;",
            (cat_id,),
        ).fetchone()

    return _row_to_dict(row)


def update_category(cat_id: int, name: str, sort: int = 0) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название категории пустое")

    with _conn() as conn:
        conn.execute(
            "UPDATE categories SET name=?, sort=? WHERE id=?;",
            (name, int(sort), int(cat_id)),
        )


def delete_category(cat_id: int) -> None:
    with _conn() as conn:
        # у товаров категорию обнулим
        conn.execute(
            "UPDATE products SET category_id=NULL WHERE category_id=?;",
            (int(cat_id),),
        )
        conn.execute("DELETE FROM categories WHERE id=?;", (int(cat_id),))


# ----------------- Admin API: Products -----------------

def list_products_admin() -> List[Dict[str, Any]]:
    """Список товаров для админки (все товары, включая неактивные)."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT
                p.id, p.name, p.price, p.description, p.photo,
                p.category_id,
                p.is_active,
                c.name AS category
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            ORDER BY p.id DESC;
            """
        ).fetchall()
    return [dict(r) for r in rows]


def create_product(
    name: str,
    price: int = 0,
    description: str = "",
    photo: str = "",
    category_id: Optional[int] = None,
    is_active: bool = True,
) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название товара пустое")

    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO products(name, price, description, photo, category_id, is_active)
            VALUES(?, ?, ?, ?,
