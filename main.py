import os
import requests
from fastapi import FastAPI, Body
import db

app = FastAPI()

db.init_db()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

def send_to_tg(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    })

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
        text += f"• {i.get('name')} × {i.get('qty')} = {i.get('price')}₽\n"

    text += f"\n💰 <b>Итого:</b> {data.get('total')}₽"

    send_to_tg(text)

    return {"ok": True, "order_id": order_id}
