import os
import requests
from pathlib import Path

from fastapi import FastAPI, Body, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import db

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent

# ---------- DB ----------
db.init_db()

# ---------- Static ----------
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ---------- Admin auth ----------
def require_admin(req: Request):
    token = (os.environ.get("ADMIN_TOKEN") or "").strip()
    if not token:
        raise HTTPException(500, "ADMIN_TOKEN не задан в переменных окружения Railway")
    got = (req.headers.get("X-Admin-Token") or "").strip()
    if got != token:
        raise HTTPException(401, "Unauthorized")

# ---------- TG ----------
TG_BOT_TOKEN = (os.getenv("TG_BOT_TOKEN") or "").strip()
TG_CHAT_ID = (os.getenv("TG_CHAT_ID") or "").strip()

def send_to_tg(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        json={
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=10,
    )

# ---------- Pages ----------
@app.get("/")
def index():
    f = BASE_DIR / "index.html"
    if not f.exists():
        raise HTTPException(404, "index.html не найден рядом с main.py")
    return FileResponse(str(f))

@app.get("/admin")
def admin_page():
    f = BASE_DIR / "admin.html"
    if not f.exists():
        raise HTTPException(404, "admin.html не найден рядом с main.py")
    return FileResponse(str(f))

# ---------- Public API ----------
@app.get("/api/products")
def api_products():
    return JSONResponse(db.list_products(active_only=True))

# ---------- Orders ----------
@app.post("/api/order")
def create_order(data: dict = Body(...)):
    items = data.get("items", [])
    order_id = db.create_order(
        tg_user=data.get("tg_user", ""),
        metro=data.get("metro", ""),
        delivery_time=data.get("time", ""),
        items=items,
        total=int(data.get("total", 0)),
    )

    text = (
        f"🛒 <b>Новый заказ #{order_id}</b>\n\n"
        f"👤 TG: {data.get('tg_user','—')}\n"
        f"🚇 Метро: {data.get('metro','—')}\n"
        f"⏰ Время: {data.get('time','—')}\n\n"
        f"📦 <b>Товары:</b>\n"
    )
    for i in items:
        name = i.get("name", "—")
        qty = i.get("qty", 1)
        price = i.get("price", 0)
        text += f"• {name} × {qty} = {price}₽\n"
    text += f"\n💰 <b>Итого:</b> {data.get('total', 0)}₽"

    send_to_tg(text)

    return {"ok": True, "order_id": order_id}

# ---------- Admin: categories ----------
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

# ---------- Admin: products ----------
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
