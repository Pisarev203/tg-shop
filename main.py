import asyncio
import os
import json

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher, types
import db

API_TOKEN = os.getenv("API_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WEBAPP_URL = os.getenv("WEBAPP_URL", "")  # ссылка на твой сайт в Amvera (https://....amvera.io)

if not API_TOKEN:
    raise RuntimeError("API_TOKEN не задан")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID не задан")
if not WEBAPP_URL:
    raise RuntimeError("WEBAPP_URL не задан")
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL не задан")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

app = FastAPI()

# статика (если используешь)
app.mount("/static", StaticFiles(directory="static"), name="static")


@dp.message_handler(commands=["start"])
async def start_cmd(m: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        types.KeyboardButton(
            "🛍 Открыть магазин",
            web_app=types.WebAppInfo(url=WEBAPP_URL),
        )
    )
    await m.answer("Открыть магазин:", reply_markup=kb)


@dp.message_handler(content_types=types.ContentType.WEB_APP_DATA)
async def webapp_order(m: types.Message):
    data = json.loads(m.web_app_data.data)

    tg_user = m.from_user.username or str(m.from_user.id)
    metro = data.get("metro", "")
    delivery_time = data.get("time", "")
    items = data.get("items", [])
    total = int(data.get("total", 0))

    oid = db.create_order(tg_user=tg_user, metro=metro, delivery_time=delivery_time, items=items, total=total)

    # соберём красивое сообщение админу
    lines = [f"🛒 Новый заказ #{oid}", f"👤 TG: @{tg_user}" if m.from_user.username else f"👤 TG id: {m.from_user.id}"]
    if metro:
        lines.append(f"🚇 Метро: {metro}")
    if delivery_time:
        lines.append(f"⏰ Время: {delivery_time}")

    lines.append("\n📦 Товары:")
    for it in items:
        name = it.get("name", "товар")
        qty = it.get("qty", 1)
        price = it.get("price", 0)
        lines.append(f"• {name} x{qty} = {qty * int(price)}₽")

    lines.append(f"\n💰 Итого: {total}₽")

    await bot.send_message(ADMIN_ID, "\n".join(lines))
    await m.answer("✅ Заказ принят! Мы скоро напишем вам.")


# -------- сайт (минимально) --------
@app.get("/", response_class=HTMLResponse)
async def home():
    # если у тебя уже есть index.html в репо — лучше отдавать его,
    # но пока сделаем заглушку
    return """
    <html><body>
    <h2>MSV Shop</h2>
    <p>Сайт запущен ✅</p>
    </body></html>
    """


@app.on_event("startup")
async def on_startup():
    db.init_db()
    # запускаем бота фоном
    asyncio.create_task(dp.start_polling())
