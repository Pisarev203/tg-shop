import sqlite3
from pathlib import Path

DB_PATH = Path("shop.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        price INTEGER,
        description TEXT,
        image_url TEXT,
        category TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_user INTEGER,
        total INTEGER,
        created TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        name TEXT,
        price INTEGER,
        qty INTEGER
    )
    """)

    conn.commit()
    conn.close()

def products():
    conn = get_conn()
    items = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return [dict(i) for i in items]

def add_product(n, p, d, i, c):
    conn = get_conn()
    conn.execute(
        "INSERT INTO products VALUES (NULL,?,?,?,?,?)",
        (n,p,d,i,c)
    )
    conn.commit()
    conn.close()

def create_order(uid, total, items):
    from datetime import datetime
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO orders VALUES (NULL,?,?,?)",
                (uid,total,datetime.now().isoformat()))
    oid = cur.lastrowid
    for it in items:
        cur.execute(
            "INSERT INTO order_items VALUES (NULL,?,?,?,?)",
            (oid,it["name"],it["price"],it["qty"])
        )
    conn.commit()
    conn.close()
    return oid
