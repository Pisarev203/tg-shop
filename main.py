import os
import requests
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import db

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent

# init db
db.init_db()

# статика (если есть папка static)
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# токен админки: берём из ENV, если нет — используем дефолт (чтобы не было 500)
DEFAULT_ADMIN_TOKEN = "Sm03052604!"
def get_admin_token():
    return (os.getenv("ADMIN_TOKEN") or DEFAULT_ADMIN_TOKEN).strip()

def require_admin(req: Request):
    got = (req.headers.get("X-Admin-Token") or "").strip()
    if got != get_admin_token():
        raise HTTPException(401, "Unauthorized")

# Telegram notify
TG_BOT_TOKEN = (os.getenv("TG_BOT_TOKEN") or "").strip()
TG_CHAT_ID = (os.getenv("TG_CHAT_ID") or "").strip()

def send_to_tg(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return  # просто молча, если не настроено
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
    except Exception:
        pass

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/")
def index():
    p = BASE_DIR / "index.html"
    if not p.exists():
        raise HTTPException(404, "index.html not found")
    return FileResponse(str(p))

@app.get("/admin")
def admin_page():
    p = BASE_DIR / "admin.html"
    if not p.exists():
        raise HTTPException(404, "admin.html not found")
    return FileResponse(str(p))

# -------- public api --------

@app.get("/api/products")
def api_products():
    return JSONResponse(db.list_products(active_only=True))

@app.post("/api/order")
async def create_order(req: Request):
    data = await req.json()

    tg_user = data.get("tg_user", "")
    metro = data.get("metro", "")
    delivery_time = data.get("time", "") or data.get("delivery_time", "")
    items = data.get("items", [])
    total = data.get("total", 0)

    order_id = db.create_order(
        tg_user=tg_user,
        metro=metro,
        delivery_time=delivery_time,
        items=items,
        total=total,
    )

    # текст в TG
    lines = [f"🛒 Новый заказ #{order_id}"]
    if tg_user: lines.append(f"👤 TG: {tg_user}")
    if metro: lines.append(f"🚇 Метро: {metro}")
    if delivery_time: lines.append(f"⏰ Время: {delivery_time}")
    lines.append("")
    lines.append("📦 Товары:")
    for it in (items or []):
        try:
            name = it.get("name", "товар")
            qty = it.get("qty", 1)
            price = it.get("price", 0)
            lines.append(f"• {name} x{qty} = {int(price)*int(qty)}₽")
        except Exception:
            lines.append(f"• {str(it)}")
    lines.append("")
    lines.append(f"💰 Итого: {total}₽")

    send_to_tg("\n".join(lines))

    return JSONResponse({"ok": True, "order_id": order_id})

# -------- admin api: categories --------

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

# -------- admin api: products --------

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
