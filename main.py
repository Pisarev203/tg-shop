
from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import json
import urllib.request
import urllib.parse

import db

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent

# ---------- Init DB ----------
db.init_db()

# ---------- Static (если есть папка static) ----------
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ---------- Helpers ----------
def require_admin(req: Request):
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(500, "ADMIN_TOKEN не задан в переменных окружения Render")
    got = (req.headers.get("X-Admin-Token") or "").strip()
    if got != token:
        raise HTTPException(401, "Unauthorized")


def tg_send(text: str):
    """
    Отправка сообщения в Telegram (без сторонних библиотек).
    Нужны переменные окружения:
    TG_BOT_TOKEN и TG_CHAT_ID
    """
    bot_token = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TG_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        # Если не настроено — просто ничего не отправляем (и не ломаем заказ)
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        _ = resp.read()


def format_order_for_tg(order_id: int, data: dict) -> str:
    tg_user = (data.get("tg_user") or "").strip()
    metro = (data.get("metro") or "").strip()
    delivery_time = (data.get("time") or data.get("delivery_time") or "").strip()
    items = data.get("items") or []
    total = data.get("total") or 0

    lines = []
    lines.append(f"🛒 <b>Новый заказ</b> #{order_id}")
    if tg_user:
        lines.append(f"👤 <b>Клиент:</b> {tg_user}")
    if metro:
        lines.append(f"🚇 <b>Метро:</b> {metro}")
    if delivery_time:
        lines.append(f"⏰ <b>Время:</b> {delivery_time}")

    lines.append("")
    lines.append("📦 <b>Состав:</b>")

    if isinstance(items, list) and items:
        for it in items:
            name = (it.get("name") or "Товар").strip()
            qty = int(it.get("qty") or 1)
            price = int(it.get("price") or 0)
            lines.append(f"• {name} × {qty} = {price * qty} ₽")
    else:
        lines.append("• (пусто)")

    lines.append("")
    lines.append(f"💰 <b>Итого:</b> {total} ₽")

    return "\n".join(lines)


# ---------- Pages ----------
@app.get("/")
def index():
    return FileResponse(str(BASE_DIR / "index.html"))


@app.get("/admin")
def admin_page():
    return FileResponse(str(BASE_DIR / "admin.html"))


# ---------- Public API ----------
@app.get("/api/products")
def api_products():
    return JSONResponse(db.list_products(active_only=True))


@app.post("/api/order")
def create_order(data: dict = Body(...)):
    order_id = db.create_order(
        tg_user=data.get("tg_user", ""),
        metro=data.get("metro", ""),
        delivery_time=data.get("time", "") or data.get("delivery_time", ""),
        items=data.get("items", []),
        total=data.get("total", 0),
    )

    # Отправка в Telegram
    try:
        tg_send(format_order_for_tg(order_id, data))
    except Exception:
        # Не ломаем заказ, даже если TG упал
        pass

    return {"ok": True, "order_id": order_id}


# ---------- Admin API: Categories ----------
@app.get("/api/admin/categories")
def admin_list_categories(req: Request):
    require_admin(req)
    return JSONResponse(db.list_categories())


@app.post("/api/admin/categories")
async def admin_create_category(req: Request):
    require_admin(req)
    data = await req.json()
    try:
        return JSONResponse(db.create_category(data.get("name", ""), int(data.get("sort", 0))))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.put("/api/admin/categories/{cat_id}")
async def admin_update_category(cat_id: int, req: Request):
    require_admin(req)
    data = await req.json()
    try:
        db.update_category(cat_id, data.get("name", ""), int(data.get("sort", 0)))
        return JSONResponse({"ok": True})
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/admin/categories/{cat_id}")
def admin_delete_category(cat_id: int, req: Request):
    require_admin(req)
    db.delete_category(cat_id)
    return JSONResponse({"ok": True})


# ---------- Admin API: Products ----------
@app.get("/api/admin/products")
def admin_list_products(req: Request):
    require_admin(req)
    return JSONResponse(db.list_products(active_only=False))


@app.post("/api/admin/products")
async def admin_create_product(req: Request):
    require_admin(req)
    data = await req.json()
    try:
        p = db.create_product(
            name=data.get("name", ""),
            price=int(data.get("price", 0)),
            description=data.get("description", "") or "",
            photo=data.get("photo", "") or "",
            category_id=int(data["category_id"]) if data.get("category_id") else None,
            is_active=bool(data.get("is_active", True)),
        )
        return JSONResponse(p)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.put("/api/admin/products/{pid}")
async def admin_update_product(pid: int, req: Request):
    require_admin(req)
    data = await req.json()
    try:
        db.update_product(
            pid=pid,
            name=data.get("name", ""),
            price=int(data.get("price", 0)),
            description=data.get("description", "") or "",
            photo=data.get("photo", "") or "",
            category_id=int(data["category_id"]) if data.get("category_id") else None,
            is_active=bool(data.get("is_active", True)),
        )
        return JSONResponse({"ok": True})
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/admin/products/{pid}")
def admin_delete_product(pid: int, req: Request):
    require_admin(req)
    db.delete_product(pid)
    return JSONResponse({"ok": True})

