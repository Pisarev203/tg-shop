import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent / "shop.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sort INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '',
                photo TEXT NOT NULL DEFAULT '',
                category_id INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL
            );
                        CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_user TEXT NOT NULL DEFAULT '',
                metro TEXT NOT NULL DEFAULT '',
                delivery_time TEXT NOT NULL DEFAULT '',
                items_json TEXT NOT NULL DEFAULT '[]',
                total INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )

        # Авто-сид (чтобы не было пусто)
        cur = conn.execute("SELECT COUNT(*) AS c FROM products")
        if cur.fetchone()["c"] == 0:
            # категории
            conn.execute("INSERT OR IGNORE INTO categories(name, sort) VALUES(?,?)", ("Популярное", 0))
            conn.execute("INSERT OR IGNORE INTO categories(name, sort) VALUES(?,?)", ("Новинки", 10))
            cat_id = conn.execute("SELECT id FROM categories WHERE name=?", ("Популярное",)).fetchone()["id"]

            # товары
            conn.execute(
                "INSERT INTO products(name, price, description, photo, category_id, is_active) VALUES(?,?,?,?,?,1)",
                ("Товар 1", 100, "Описание товара 1", "", cat_id),
            )
            conn.execute(
                "INSERT INTO products(name, price, description, photo, category_id, is_active) VALUES(?,?,?,?,?,1)",
                ("Товар 2", 250, "Описание товара 2", "", cat_id),
            )


# ---------- Public API ----------

def list_products(active_only: bool = True) -> List[Dict[str, Any]]:
    q = """
    SELECT p.id, p.name, p.price, p.description, p.photo,
           p.category_id, COALESCE(c.name,'') AS category,
           p.is_active
    FROM products p
    LEFT JOIN categories c ON c.id = p.category_id
    """
    args: List[Any] = []
    if active_only:
        q += " WHERE p.is_active = 1"
    q += " ORDER BY COALESCE(c.sort, 0) ASC, p.id DESC"

    with _conn() as conn:
        rows = conn.execute(q, args).fetchall()

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "price": int(r["price"] or 0),
            "description": r["description"] or "",
            "photo": r["photo"] or "",
            "category": r["category"] or "",
            "category_id": r["category_id"],
            "is_active": bool(r["is_active"]),
        }
        for r in rows
    ]


# ---------- Admin API: Categories ----------

def list_categories() -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("SELECT id, name, sort FROM categories ORDER BY sort ASC, id ASC").fetchall()
    return [{"id": r["id"], "name": r["name"], "sort": r["sort"]} for r in rows]


def create_category(name: str, sort: int = 0) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название категории пустое")
    with _conn() as conn:
        conn.execute("INSERT INTO categories(name, sort) VALUES(?,?)", (name, int(sort)))
        row = conn.execute("SELECT id, name, sort FROM categories WHERE name=?", (name,)).fetchone()
    return {"id": row["id"], "name": row["name"], "sort": row["sort"]}


def update_category(cat_id: int, name: str, sort: int = 0) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название категории пустое")
with _conn() as conn:
        conn.execute("UPDATE categories SET name=?, sort=? WHERE id=?", (name, int(sort), int(cat_id)))


def delete_category(cat_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE products SET category_id=NULL WHERE category_id=?", (int(cat_id),))
        conn.execute("DELETE FROM categories WHERE id=?", (int(cat_id),))


# ---------- Admin API: Products ----------

def create_product(
    name: str,
    price: int,
    description: str = "",
    photo: str = "",
    category_id: Optional[int] = None,
    is_active: bool = True,
) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название товара пустое")

    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO products(name, price, description, photo, category_id, is_active)
            VALUES(?,?,?,?,?,?)
            """,
            (
                name,
                int(price or 0),
                description or "",
                photo or "",
                int(category_id) if category_id else None,
                1 if is_active else 0,
            ),
        )
        pid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        row = conn.execute(
            """
            SELECT p.id, p.name, p.price, p.description, p.photo, p.category_id,
                   COALESCE(c.name,'') AS category, p.is_active
            FROM products p LEFT JOIN categories c ON c.id=p.category_id
            WHERE p.id=?
            """,
            (pid,),
        ).fetchone()

    return {
        "id": row["id"],
        "name": row["name"],
        "price": int(row["price"] or 0),
        "description": row["description"] or "",
        "photo": row["photo"] or "",
        "category": row["category"] or "",
        "category_id": row["category_id"],
        "is_active": bool(row["is_active"]),
    }


def update_product(
    pid: int,
    name: str,
    price: int,
    description: str = "",
    photo: str = "",
    category_id: Optional[int] = None,
    is_active: bool = True,
) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название товара пустое")

    with _conn() as conn:
        conn.execute(
            """
            UPDATE products
            SET name=?, price=?, description=?, photo=?, category_id=?, is_active=?
            WHERE id=?
            """,
            (
                name,
                int(price or 0),
                description or "",
                photo or "",
                int(category_id) if category_id else None,
                1 if is_active else 0,
                int(pid),
            ),
        )


def delete_product(pid: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM products WHERE id=?", (int(pid),))
