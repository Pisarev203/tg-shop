import os
import requests
from pathlib import Path

from fastapi import FastAPI, Body, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import db

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent

# --- init DB ---
db.init_db()

# --- static ---
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# --- TG ---
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "").strip()

def send_to_tg(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }, timeout=10)

# --- pages ---
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

# --- API: create order ---
@app.post("/api/order")
def create_order(data: dict = Body(...)):
    order_id = db.create_order(
        tg_user=data.get("tg_user", ""),
        metro=data.get("metro", ""),
        delivery_time=data.get("time", ""),
        items=data.get("items", []),
        total=int(data.get("total", 0)),
    )

    text = (
        f"🛒 <b>Новый заказ #{order_id}</b>\n\n"
        f"👤 TG: {data.get('tg_user','—')}\n"
        f"🚇 Метро: {data.get('metro','—')}\n"
        f"⏰ Время: {data.get('time','—')}\n\n"
        f"📦 <b>Товары:</b>\n"
    )

    for i in data.get("items", []):
        name = i.get("name", "—")
        qty = i.get("qty", 1)
        price = i.get("price", 0)
        text += f"• {name} × {qty} = {price}₽\n"

    text += f"\n💰 <b>Итого:</b> {data.get('total', 0)}₽"

    send_to_tg(text)

    return {"ok": True, "order_id": order_id}
