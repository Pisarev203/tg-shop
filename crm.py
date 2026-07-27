import json
import re
import secrets
from datetime import date, datetime

import db
from psycopg.errors import UniqueViolation


ORDER_STATUSES = {"new", "confirmed", "paid", "completed", "cancelled"}
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _rows(cur):
    columns = [column.name for column in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def _row(cur):
    row = cur.fetchone()
    if row is None:
        return None
    columns = [column.name for column in cur.description]
    return dict(zip(columns, row))


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _serialize_row(row):
    if not row:
        return row
    return {key: _json_safe(value) for key, value in row.items()}


def init_db():
    """Add CRM tables and columns without deleting existing shop data."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL UNIQUE,
                    username TEXT DEFAULT '',
                    first_name TEXT DEFAULT '',
                    last_name TEXT DEFAULT '',
                    photo_url TEXT DEFAULT '',
                    language_code TEXT DEFAULT '',
                    referral_code TEXT NOT NULL UNIQUE,
                    referrer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL,
                    referral_rewarded BOOLEAN NOT NULL DEFAULT FALSE,
                    referral_discount_percent INTEGER NOT NULL DEFAULT 0,
                    regular_discount_percent INTEGER NOT NULL DEFAULT 0,
                    label_color TEXT NOT NULL DEFAULT '#2AABEE',
                    note TEXT DEFAULT '',
                    orders_count INTEGER NOT NULL DEFAULT 0,
                    total_spent INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    last_seen_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS cost_price INTEGER NOT NULL DEFAULT 0;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS product_variants (
                    id BIGSERIAL PRIMARY KEY,
                    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    color TEXT DEFAULT '',
                    price_delta INTEGER NOT NULL DEFAULT 0,
                    cost_price INTEGER,
                    stock INTEGER NOT NULL DEFAULT -1,
                    image TEXT DEFAULT '',
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'new';")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS subtotal INTEGER NOT NULL DEFAULT 0;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS discount_total INTEGER NOT NULL DEFAULT 0;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS promo_code TEXT DEFAULT '';")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS comment TEXT DEFAULT '';")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;")
            cur.execute("UPDATE orders SET subtotal = total WHERE subtotal = 0 AND total > 0;")

            cur.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS product_id INTEGER;")
            cur.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS variant_id BIGINT;")
            cur.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS variant_name TEXT DEFAULT '';")
            cur.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS cost_price INTEGER NOT NULL DEFAULT 0;")
            cur.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS discount_total INTEGER NOT NULL DEFAULT 0;")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id BIGSERIAL PRIMARY KEY,
                    code TEXT NOT NULL UNIQUE,
                    discount_type TEXT NOT NULL DEFAULT 'percent',
                    value INTEGER NOT NULL DEFAULT 0,
                    min_total INTEGER NOT NULL DEFAULT 0,
                    max_uses INTEGER NOT NULL DEFAULT 0,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    one_per_customer BOOLEAN NOT NULL DEFAULT TRUE,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    starts_at TIMESTAMP,
                    ends_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS promo_usages (
                    id BIGSERIAL PRIMARY KEY,
                    promo_id BIGINT NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
                    customer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL,
                    order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
                    discount INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE (promo_id, order_id)
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS order_status_history (
                    id BIGSERIAL PRIMARY KEY,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    old_status TEXT DEFAULT '',
                    new_status TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_variants_product_id ON product_variants(product_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_customers_referrer_id ON customers(referrer_id);")
        conn.commit()


def _new_referral_code() -> str:
    return "MSV" + secrets.token_hex(4).upper()


def upsert_customer(telegram_user: dict, start_param: str = "") -> dict:
    telegram_id = int(telegram_user["id"])
    username = str(telegram_user.get("username") or "").strip()
    first_name = str(telegram_user.get("first_name") or "").strip()
    last_name = str(telegram_user.get("last_name") or "").strip()
    photo_url = str(telegram_user.get("photo_url") or "").strip()
    language_code = str(telegram_user.get("language_code") or "").strip()

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM customers WHERE telegram_id = %s;", (telegram_id,))
            customer = _row(cur)
            if customer:
                cur.execute(
                    """
                    UPDATE customers
                    SET username=%s, first_name=%s, last_name=%s, photo_url=%s,
                        language_code=%s, last_seen_at=NOW()
                    WHERE id=%s RETURNING *;
                    """,
                    (username, first_name, last_name, photo_url, language_code, customer["id"]),
                )
                customer = _row(cur)
            else:
                for _ in range(5):
                    try:
                        cur.execute(
                            """
                            INSERT INTO customers
                                (telegram_id, username, first_name, last_name, photo_url, language_code, referral_code)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            RETURNING *;
                            """,
                            (
                                telegram_id,
                                username,
                                first_name,
                                last_name,
                                photo_url,
                                language_code,
                                _new_referral_code(),
                            ),
                        )
                        customer = _row(cur)
                        break
                    except UniqueViolation:
                        conn.rollback()
                if not customer:
                    raise RuntimeError("Не удалось создать профиль клиента")

            ref_code = start_param[4:].strip().upper() if start_param.startswith("ref_") else ""
            if ref_code and not customer.get("referrer_id"):
                cur.execute(
                    "SELECT id FROM customers WHERE referral_code = %s AND id <> %s;",
                    (ref_code, customer["id"]),
                )
                referrer = cur.fetchone()
                if referrer:
                    cur.execute(
                        "UPDATE customers SET referrer_id = %s WHERE id = %s RETURNING *;",
                        (referrer[0], customer["id"]),
                    )
                    customer = _row(cur)
        conn.commit()
    return _serialize_row(customer)


def get_catalog(include_inactive: bool = False) -> list[dict]:
    active_filter = "" if include_inactive else "WHERE p.active = TRUE"
    variant_filter = "" if include_inactive else "AND active = TRUE"
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT p.id, p.name, p.price, p.cost_price, p.description, p.image,
                       p.category, p.brand, p.promo_type, p.promo_text, p.active, p.sort_order
                FROM products p
                {active_filter}
                ORDER BY p.sort_order, p.id DESC;
                """
            )
            products = _rows(cur)
            product_ids = [product["id"] for product in products]
            variants = []
            if product_ids:
                cur.execute(
                    f"""
                    SELECT id, product_id, name, color, price_delta, cost_price, stock,
                           image, active, sort_order
                    FROM product_variants
                    WHERE product_id = ANY(%s) {variant_filter}
                    ORDER BY sort_order, id;
                    """,
                    (product_ids,),
                )
                variants = _rows(cur)

    grouped = {product["id"]: [] for product in products}
    for variant in variants:
        grouped.setdefault(variant["product_id"], []).append(_serialize_row(variant))
    for product in products:
        product["variants"] = grouped.get(product["id"], [])
    return [_serialize_row(product) for product in products]


def _customer_discount(customer: dict | None, first_order_eligible: bool = True) -> tuple[int, list[str]]:
    if not customer:
        return 0, []
    regular = max(0, int(customer.get("regular_discount_percent") or 0))
    referral = max(0, int(customer.get("referral_discount_percent") or 0))
    first_order = (
        5
        if first_order_eligible
        and customer.get("referrer_id")
        and int(customer.get("orders_count") or 0) == 0
        else 0
    )
    percent = min(20, regular + referral + first_order)
    labels = []
    if regular:
        labels.append(f"Постоянный покупатель: {regular}%")
    if referral:
        labels.append(f"Реферальная скидка: {referral}%")
    if first_order:
        labels.append("Скидка друга на первый заказ: 5%")
    return percent, labels


def _load_quote(cur, customer: dict | None, raw_items: list, promo_code: str = "", lock: bool = False) -> dict:
    if not isinstance(raw_items, list):
        raise ValueError("Корзина имеет неверный формат")
    if len(raw_items) > 50:
        raise ValueError("Слишком много позиций в корзине")

    aggregated = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        try:
            product_id = int(raw.get("product_id") or raw.get("id"))
            variant_id = int(raw["variant_id"]) if raw.get("variant_id") else None
            qty = min(99, max(1, int(raw.get("qty") or 1)))
        except (TypeError, ValueError, KeyError):
            continue
        key = (product_id, variant_id)
        aggregated[key] = min(99, aggregated.get(key, 0) + qty)

    requested = [(product_id, variant_id, qty) for (product_id, variant_id), qty in aggregated.items()]

    product_ids = sorted({item[0] for item in requested})
    variant_ids = sorted({item[1] for item in requested if item[1] is not None})
    products = {}
    variants = {}
    products_with_variants = set()
    if product_ids:
        product_lock_sql = " FOR SHARE" if lock else ""
        cur.execute(
            f"""
            SELECT id, name, price, cost_price, image, active
            FROM products WHERE id = ANY(%s){product_lock_sql};
            """,
            (product_ids,),
        )
        products = {row["id"]: row for row in _rows(cur)}
        cur.execute(
            "SELECT DISTINCT product_id FROM product_variants WHERE product_id = ANY(%s) AND active=TRUE;",
            (product_ids,),
        )
        products_with_variants = {row[0] for row in cur.fetchall()}
    if variant_ids:
        lock_sql = " FOR UPDATE" if lock else ""
        cur.execute(
            f"""
            SELECT id, product_id, name, color, price_delta, cost_price, stock, image, active
            FROM product_variants WHERE id = ANY(%s){lock_sql};
            """,
            (variant_ids,),
        )
        variants = {row["id"]: row for row in _rows(cur)}

    lines = []
    subtotal = 0
    for product_id, variant_id, qty in requested:
        product = products.get(product_id)
        if not product or not product["active"]:
            raise ValueError("Один из товаров больше недоступен")
        variant = None
        if variant_id is not None:
            variant = variants.get(variant_id)
            if not variant or variant["product_id"] != product_id or not variant["active"]:
                raise ValueError(f"Вариант товара «{product['name']}» недоступен")
        elif product_id in products_with_variants:
            raise ValueError(f"Выберите вариант товара «{product['name']}»")

        if variant and variant["stock"] >= 0 and qty > variant["stock"]:
            raise ValueError(f"Недостаточно товара «{product['name']} — {variant['name']}»")

        price = int(product["price"] or 0)
        if variant:
            price += int(variant["price_delta"] or 0)
        price = max(0, price)
        cost_price = int(product["cost_price"] or 0)
        if variant and variant["cost_price"] is not None:
            cost_price = max(0, int(variant["cost_price"]))
        line_subtotal = price * qty
        subtotal += line_subtotal
        lines.append(
            {
                "product_id": product_id,
                "variant_id": variant_id,
                "name": product["name"],
                "variant_name": variant["name"] if variant else "",
                "color": variant["color"] if variant else "",
                "image": (variant["image"] if variant and variant["image"] else product["image"]),
                "qty": qty,
                "price": price,
                "cost_price": cost_price,
                "line_subtotal": line_subtotal,
            }
        )

    if not lines:
        raise ValueError("Корзина пуста")

    first_order_eligible = True
    if customer and customer.get("referrer_id"):
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM orders WHERE customer_id=%s AND status <> 'cancelled');",
            (customer["id"],),
        )
        first_order_eligible = not cur.fetchone()[0]
    discount_percent, discount_labels = _customer_discount(customer, first_order_eligible)
    customer_discount = subtotal * discount_percent // 100
    remaining = subtotal - customer_discount
    promo = None
    promo_discount = 0
    normalized_code = str(promo_code or "").strip().upper()
    if normalized_code:
        promo_lock_sql = " FOR UPDATE" if lock else ""
        cur.execute(
            f"""
            SELECT * FROM promo_codes
            WHERE UPPER(code) = %s AND active = TRUE
              AND (starts_at IS NULL OR starts_at <= NOW())
              AND (ends_at IS NULL OR ends_at >= NOW()){promo_lock_sql};
            """,
            (normalized_code,),
        )
        promo = _row(cur)
        if not promo:
            raise ValueError("Промокод не найден или уже не действует")
        if promo["max_uses"] > 0 and promo["used_count"] >= promo["max_uses"]:
            raise ValueError("Лимит использований промокода закончился")
        if subtotal < promo["min_total"]:
            raise ValueError(f"Промокод действует от {promo['min_total']} ₽")
        if promo["one_per_customer"] and customer:
            cur.execute(
                "SELECT 1 FROM promo_usages WHERE promo_id=%s AND customer_id=%s LIMIT 1;",
                (promo["id"], customer["id"]),
            )
            if cur.fetchone():
                raise ValueError("Вы уже использовали этот промокод")
        if promo["discount_type"] == "fixed":
            promo_discount = min(remaining, max(0, int(promo["value"])))
        else:
            promo_discount = min(remaining, remaining * min(100, max(0, int(promo["value"]))) // 100)
        discount_labels.append(f"Промокод {promo['code']}")

    discount_total = customer_discount + promo_discount
    return {
        "items": lines,
        "subtotal": subtotal,
        "discount_percent": discount_percent,
        "customer_discount": customer_discount,
        "promo_discount": promo_discount,
        "discount_total": discount_total,
        "total": max(0, subtotal - discount_total),
        "discount_labels": discount_labels,
        "promo": promo,
    }


def quote(customer_id: int | None, items: list, promo_code: str = "") -> dict:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            customer = None
            if customer_id:
                cur.execute("SELECT * FROM customers WHERE id=%s;", (customer_id,))
                customer = _row(cur)
            result = _load_quote(cur, customer, items, promo_code)
    return _public_quote(result)


def _public_quote(result: dict) -> dict:
    return {
        "items": [
            {key: value for key, value in line.items() if key != "cost_price"}
            for line in result["items"]
        ],
        "subtotal": result["subtotal"],
        "discount_percent": result["discount_percent"],
        "customer_discount": result["customer_discount"],
        "promo_discount": result["promo_discount"],
        "discount_total": result["discount_total"],
        "total": result["total"],
        "discount_labels": result["discount_labels"],
        "promo_code": result["promo"]["code"] if result.get("promo") else "",
    }


def create_order(customer_id: int, items: list, promo_code: str, metro: str, delivery_time: str, comment: str) -> dict:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM customers WHERE id=%s FOR UPDATE;", (customer_id,))
            customer = _row(cur)
            if not customer:
                raise ValueError("Профиль клиента не найден")
            result = _load_quote(cur, customer, items, promo_code, lock=True)
            public_items = _public_quote(result)["items"]
            tg_user = f"@{customer['username']}" if customer["username"] else str(customer["telegram_id"])
            cur.execute(
                """
                INSERT INTO orders
                    (tg_user, metro, delivery_time, total, items_json, customer_id, status,
                     subtotal, discount_total, promo_code, comment, updated_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, 'new', %s, %s, %s, %s, NOW())
                RETURNING id, created_at;
                """,
                (
                    tg_user,
                    str(metro or "").strip(),
                    str(delivery_time or "").strip(),
                    result["total"],
                    json.dumps(public_items, ensure_ascii=False),
                    customer_id,
                    result["subtotal"],
                    result["discount_total"],
                    result["promo"]["code"] if result.get("promo") else "",
                    str(comment or "").strip()[:1000],
                ),
            )
            order = _row(cur)

            remaining_discount = result["discount_total"]
            for index, line in enumerate(result["items"]):
                if index == len(result["items"]) - 1:
                    line_discount = remaining_discount
                else:
                    line_discount = round(result["discount_total"] * line["line_subtotal"] / result["subtotal"])
                    line_discount = min(remaining_discount, line_discount)
                remaining_discount -= line_discount
                cur.execute(
                    """
                    INSERT INTO order_items
                        (order_id, product_name, qty, price, line_total, product_id, variant_id,
                         variant_name, cost_price, discount_total)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        order["id"],
                        line["name"],
                        line["qty"],
                        line["price"],
                        line["line_subtotal"] - line_discount,
                        line["product_id"],
                        line["variant_id"],
                        line["variant_name"],
                        line["cost_price"],
                        line_discount,
                    ),
                )
                if line["variant_id"] is not None:
                    cur.execute(
                        """
                        UPDATE product_variants
                        SET stock = CASE WHEN stock >= 0 THEN stock - %s ELSE stock END
                        WHERE id=%s;
                        """,
                        (line["qty"], line["variant_id"]),
                    )

            if result.get("promo"):
                promo = result["promo"]
                cur.execute("UPDATE promo_codes SET used_count=used_count+1 WHERE id=%s;", (promo["id"],))
                cur.execute(
                    """
                    INSERT INTO promo_usages (promo_id, customer_id, order_id, discount)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (promo["id"], customer_id, order["id"], result["promo_discount"]),
                )
            cur.execute(
                "INSERT INTO order_status_history(order_id, old_status, new_status) VALUES (%s, '', 'new');",
                (order["id"],),
            )
        conn.commit()

    return {
        "id": order["id"],
        "created_at": _json_safe(order["created_at"]),
        **_public_quote(result),
    }


def get_profile(customer_id: int, bot_username: str = "") -> dict:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM customers WHERE id=%s;", (customer_id,))
            customer = _row(cur)
            if not customer:
                raise ValueError("Профиль не найден")
            cur.execute(
                """
                SELECT id, status, subtotal, discount_total, total, promo_code, metro,
                       delivery_time, comment, items_json, created_at, completed_at
                FROM orders WHERE customer_id=%s ORDER BY id DESC LIMIT 30;
                """,
                (customer_id,),
            )
            orders = [_serialize_row(row) for row in _rows(cur)]
            cur.execute(
                "SELECT COUNT(*) FROM customers WHERE referrer_id=%s AND referral_rewarded=TRUE;",
                (customer_id,),
            )
            successful_referrals = cur.fetchone()[0]

    next_tier = None
    tiers = [(3, 3), (5, 5), (10, 7), (20, 10)]
    for required_orders, percent in tiers:
        if customer["orders_count"] < required_orders:
            next_tier = {"orders": required_orders, "percent": percent}
            break
    username = bot_username.lstrip("@").strip()
    referral_link = (
        f"https://t.me/{username}?start=ref_{customer['referral_code']}" if username else ""
    )
    return {
        "customer": _serialize_row(customer),
        "orders": orders,
        "successful_referrals": successful_referrals,
        "next_tier": next_tier,
        "referral_link": referral_link,
    }


def _regular_discount(orders_count: int) -> int:
    if orders_count >= 20:
        return 10
    if orders_count >= 10:
        return 7
    if orders_count >= 5:
        return 5
    if orders_count >= 3:
        return 3
    return 0


def _refresh_customer_metrics(cur, customer_id: int):
    cur.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(total), 0)
        FROM orders WHERE customer_id=%s AND status='completed';
        """,
        (customer_id,),
    )
    orders_count, total_spent = cur.fetchone()
    cur.execute(
        """
        UPDATE customers SET orders_count=%s, total_spent=%s, regular_discount_percent=%s
        WHERE id=%s;
        """,
        (orders_count, total_spent, _regular_discount(orders_count), customer_id),
    )


def update_order_status(order_id: int, status: str) -> dict:
    status = str(status or "").strip().lower()
    if status not in ORDER_STATUSES:
        raise ValueError("Неизвестный статус заказа")
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE id=%s FOR UPDATE;", (order_id,))
            order = _row(cur)
            if not order:
                raise ValueError("Заказ не найден")
            old_status = order["status"]
            if old_status == "cancelled" and status != "cancelled":
                raise ValueError("Отменённый заказ нельзя открыть повторно — создайте новый")

            if status == "cancelled" and old_status != "cancelled":
                cur.execute(
                    """
                    UPDATE product_variants v
                    SET stock = CASE WHEN v.stock >= 0 THEN v.stock + oi.qty ELSE v.stock END
                    FROM order_items oi
                    WHERE oi.order_id=%s AND oi.variant_id=v.id;
                    """,
                    (order_id,),
                )
                cur.execute("SELECT promo_id FROM promo_usages WHERE order_id=%s;", (order_id,))
                promo_usage = cur.fetchone()
                if promo_usage:
                    cur.execute(
                        "UPDATE promo_codes SET used_count=GREATEST(0, used_count-1) WHERE id=%s;",
                        (promo_usage[0],),
                    )
                    cur.execute("DELETE FROM promo_usages WHERE order_id=%s;", (order_id,))

            cur.execute(
                """
                UPDATE orders
                SET status=%s,
                    updated_at=NOW(),
                    completed_at=CASE
                        WHEN %s='completed' THEN COALESCE(completed_at, NOW())
                        ELSE NULL
                    END
                WHERE id=%s;
                """,
                (status, status, order_id),
            )
            if old_status != status:
                cur.execute(
                    "INSERT INTO order_status_history(order_id, old_status, new_status) VALUES (%s, %s, %s);",
                    (order_id, old_status, status),
                )
            customer_id = order.get("customer_id")
            if customer_id:
                _refresh_customer_metrics(cur, customer_id)
                if status == "completed" and old_status != "completed":
                    cur.execute("SELECT referrer_id, referral_rewarded FROM customers WHERE id=%s;", (customer_id,))
                    referral = cur.fetchone()
                    if referral and referral[0] and not referral[1]:
                        cur.execute("UPDATE customers SET referral_rewarded=TRUE WHERE id=%s;", (customer_id,))
                        cur.execute(
                            """
                            UPDATE customers
                            SET referral_discount_percent=LEAST(10, referral_discount_percent+1)
                            WHERE id=%s;
                            """,
                            (referral[0],),
                        )
            cur.execute("SELECT * FROM orders WHERE id=%s;", (order_id,))
            updated = _row(cur)
        conn.commit()
    return _serialize_row(updated)


def dashboard(days: int = 30) -> dict:
    days = min(365, max(7, int(days)))
    day_expr = "(created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date"
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH cogs AS (
                    SELECT order_id, COALESCE(SUM(cost_price * qty), 0) AS amount
                    FROM order_items GROUP BY order_id
                )
                SELECT
                    COALESCE(SUM(o.total), 0) AS revenue,
                    COALESCE(SUM(o.total - COALESCE(c.amount, 0)), 0) AS profit,
                    COUNT(*) AS orders,
                    COUNT(DISTINCT o.customer_id) AS customers,
                    COALESCE(ROUND(AVG(o.total)), 0)::int AS average_check
                FROM orders o LEFT JOIN cogs c ON c.order_id=o.id
                WHERE o.status='completed' AND {day_expr.replace('created_at', 'o.created_at')} =
                    (NOW() AT TIME ZONE 'Europe/Moscow')::date;
                """
            )
            today = _row(cur)
            cur.execute(
                f"""
                WITH calendar AS (
                    SELECT generate_series(
                        (NOW() AT TIME ZONE 'Europe/Moscow')::date - (%s - 1),
                        (NOW() AT TIME ZONE 'Europe/Moscow')::date,
                        interval '1 day'
                    )::date AS day
                ),
                cogs AS (
                    SELECT order_id, COALESCE(SUM(cost_price * qty), 0) AS amount
                    FROM order_items GROUP BY order_id
                ),
                sales AS (
                    SELECT {day_expr.replace('created_at', 'o.created_at')} AS day,
                           SUM(o.total) AS revenue,
                           SUM(o.total - COALESCE(c.amount, 0)) AS profit,
                           COUNT(*) AS orders,
                           COUNT(DISTINCT o.customer_id) AS customers
                    FROM orders o LEFT JOIN cogs c ON c.order_id=o.id
                    WHERE o.status='completed'
                      AND {day_expr.replace('created_at', 'o.created_at')} >=
                          (NOW() AT TIME ZONE 'Europe/Moscow')::date - (%s - 1)
                    GROUP BY 1
                )
                SELECT calendar.day, COALESCE(sales.revenue,0) AS revenue,
                       COALESCE(sales.profit,0) AS profit, COALESCE(sales.orders,0) AS orders,
                       COALESCE(sales.customers,0) AS customers
                FROM calendar LEFT JOIN sales USING(day) ORDER BY calendar.day;
                """,
                (days, days),
            )
            daily = [_serialize_row(row) for row in _rows(cur)]
            cur.execute("SELECT COUNT(*) FROM customers;")
            total_customers = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM orders WHERE status='new';")
            new_orders = cur.fetchone()[0]
    return {
        "today": today,
        "daily": daily,
        "total_customers": total_customers,
        "new_orders": new_orders,
        "timezone": "Europe/Moscow",
    }


def list_orders(limit: int = 100) -> list[dict]:
    limit = min(500, max(1, int(limit)))
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.id, o.status, o.tg_user, o.metro, o.delivery_time, o.comment,
                       o.subtotal, o.discount_total, o.total, o.promo_code, o.items_json,
                       o.created_at, o.completed_at, c.id AS customer_id, c.first_name,
                       c.last_name, c.username, c.label_color
                FROM orders o LEFT JOIN customers c ON c.id=o.customer_id
                ORDER BY o.id DESC LIMIT %s;
                """,
                (limit,),
            )
            return [_serialize_row(row) for row in _rows(cur)]


def list_customers(limit: int = 300) -> list[dict]:
    limit = min(1000, max(1, int(limit)))
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.*, MAX(o.created_at) AS last_order_at,
                       COUNT(o.id) FILTER (WHERE o.status <> 'cancelled') AS all_orders
                FROM customers c LEFT JOIN orders o ON o.customer_id=c.id
                GROUP BY c.id ORDER BY last_order_at DESC NULLS LAST, c.created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            return [_serialize_row(row) for row in _rows(cur)]


def update_customer(customer_id: int, label_color: str, note: str) -> dict:
    color = str(label_color or "").strip()
    if not COLOR_RE.match(color):
        raise ValueError("Цвет должен быть в формате #RRGGBB")
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE customers SET label_color=%s, note=%s WHERE id=%s RETURNING *;",
                (color.upper(), str(note or "").strip()[:2000], customer_id),
            )
            customer = _row(cur)
            if not customer:
                raise ValueError("Клиент не найден")
        conn.commit()
    return _serialize_row(customer)


def list_promos() -> list[dict]:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM promo_codes ORDER BY id DESC;")
            return [_serialize_row(row) for row in _rows(cur)]


def create_promo(payload: dict) -> dict:
    code = str(payload.get("code") or "").strip().upper()
    if not re.match(r"^[A-ZА-Я0-9_-]{3,24}$", code):
        raise ValueError("Промокод: 3–24 буквы, цифры, _ или -")
    discount_type = str(payload.get("discount_type") or "percent").lower()
    if discount_type not in {"percent", "fixed"}:
        raise ValueError("Неизвестный тип скидки")
    value = max(0, int(payload.get("value") or 0))
    if discount_type == "percent" and value > 100:
        raise ValueError("Процент не может быть больше 100")
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO promo_codes
                    (code, discount_type, value, min_total, max_uses, one_per_customer, active, starts_at, ends_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *;
                """,
                (
                    code,
                    discount_type,
                    value,
                    max(0, int(payload.get("min_total") or 0)),
                    max(0, int(payload.get("max_uses") or 0)),
                    bool(payload.get("one_per_customer", True)),
                    bool(payload.get("active", True)),
                    payload.get("starts_at") or None,
                    payload.get("ends_at") or None,
                ),
            )
            promo = _row(cur)
        conn.commit()
    return _serialize_row(promo)


def set_promo_active(promo_id: int, active: bool) -> dict:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE promo_codes SET active=%s WHERE id=%s RETURNING *;", (active, promo_id))
            promo = _row(cur)
            if not promo:
                raise ValueError("Промокод не найден")
        conn.commit()
    return _serialize_row(promo)


def create_product(payload: dict) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Введите название товара")
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO products
                    (name, price, cost_price, description, image, category, brand, active, sort_order)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id;
                """,
                (
                    name,
                    max(0, int(payload.get("price") or 0)),
                    max(0, int(payload.get("cost_price") or 0)),
                    str(payload.get("description") or "").strip(),
                    str(payload.get("image") or "").strip(),
                    str(payload.get("category") or "").strip(),
                    str(payload.get("brand") or "").strip(),
                    bool(payload.get("active", True)),
                    int(payload.get("sort_order") or 0),
                ),
            )
            product_id = cur.fetchone()[0]
        conn.commit()
    return next(product for product in get_catalog(True) if product["id"] == product_id)


def update_product(product_id: int, payload: dict) -> dict:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM products WHERE id=%s;", (product_id,))
            current = _row(cur)
            if not current:
                raise ValueError("Товар не найден")
            values = {
                "name": str(payload.get("name", current["name"]) or "").strip(),
                "price": max(0, int(payload.get("price", current["price"]) or 0)),
                "cost_price": max(0, int(payload.get("cost_price", current["cost_price"]) or 0)),
                "description": str(payload.get("description", current["description"]) or "").strip(),
                "image": str(payload.get("image", current["image"]) or "").strip(),
                "category": str(payload.get("category", current["category"]) or "").strip(),
                "brand": str(payload.get("brand", current["brand"]) or "").strip(),
                "active": bool(payload.get("active", current["active"])),
                "sort_order": int(payload.get("sort_order", current["sort_order"]) or 0),
            }
            if not values["name"]:
                raise ValueError("Название товара не может быть пустым")
            cur.execute(
                """
                UPDATE products SET name=%s, price=%s, cost_price=%s, description=%s,
                    image=%s, category=%s, brand=%s, active=%s, sort_order=%s
                WHERE id=%s;
                """,
                (*values.values(), product_id),
            )
        conn.commit()
    return next(product for product in get_catalog(True) if product["id"] == product_id)


def create_variant(product_id: int, payload: dict) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Введите название варианта")
    color = str(payload.get("color") or "").strip()
    if color and not COLOR_RE.match(color):
        raise ValueError("Цвет варианта должен быть в формате #RRGGBB")
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO product_variants
                    (product_id,name,color,price_delta,cost_price,stock,image,active,sort_order)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *;
                """,
                (
                    product_id,
                    name,
                    color,
                    int(payload.get("price_delta") or 0),
                    int(payload["cost_price"]) if payload.get("cost_price") not in (None, "") else None,
                    int(payload.get("stock", -1)),
                    str(payload.get("image") or "").strip(),
                    bool(payload.get("active", True)),
                    int(payload.get("sort_order") or 0),
                ),
            )
            variant = _row(cur)
        conn.commit()
    return _serialize_row(variant)


def update_variant(variant_id: int, payload: dict) -> dict:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM product_variants WHERE id=%s;", (variant_id,))
            current = _row(cur)
            if not current:
                raise ValueError("Вариант не найден")
            name = str(payload.get("name", current["name"]) or "").strip()
            color = str(payload.get("color", current["color"]) or "").strip()
            if not name:
                raise ValueError("Название варианта не может быть пустым")
            if color and not COLOR_RE.match(color):
                raise ValueError("Цвет варианта должен быть в формате #RRGGBB")
            cost_raw = payload.get("cost_price", current["cost_price"])
            cur.execute(
                """
                UPDATE product_variants SET name=%s,color=%s,price_delta=%s,cost_price=%s,
                    stock=%s,image=%s,active=%s,sort_order=%s WHERE id=%s RETURNING *;
                """,
                (
                    name,
                    color,
                    int(payload.get("price_delta", current["price_delta"]) or 0),
                    int(cost_raw) if cost_raw not in (None, "") else None,
                    int(payload.get("stock", current["stock"])),
                    str(payload.get("image", current["image"]) or "").strip(),
                    bool(payload.get("active", current["active"])),
                    int(payload.get("sort_order", current["sort_order"]) or 0),
                    variant_id,
                ),
            )
            variant = _row(cur)
        conn.commit()
    return _serialize_row(variant)


def delete_variant(variant_id: int):
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM product_variants WHERE id=%s;", (variant_id,))
        conn.commit()
