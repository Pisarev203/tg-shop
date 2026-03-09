Wert, [09.03.2026 19:58]
import asyncio
import json
import logging
import os
from contextlib import suppress
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import db


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_TOKEN = (os.getenv("API_TOKEN") or "").strip()
ADMIN_ID_RAW = (os.getenv("ADMIN_ID") or "").strip()
WEBAPP_URL = (os.getenv("WEBAPP_URL") or "").strip()

if not API_TOKEN:
    raise RuntimeError("API_TOKEN не задан")

if not ADMIN_ID_RAW:
    raise RuntimeError("ADMIN_ID не задан")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError as e:
    raise RuntimeError("ADMIN_ID должен быть числом") from e

if not WEBAPP_URL:
    raise RuntimeError("WEBAPP_URL не задан")

if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL не задан")


bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
app = FastAPI(title="MSV Shop")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML = BASE_DIR / "index.html"

if STATIC_DIR.exists() and STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def build_main_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        types.KeyboardButton(
            "Открыть магазин",
            web_app=types.WebAppInfo(url=WEBAPP_URL),
        )
    )
    return kb


@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    await message.answer("Открыть магазин:", reply_markup=build_main_keyboard())


@dp.message_handler(commands=["admin"])
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет доступа.")
        return

    await message.answer(
        "Добавление товара:\n"
        "название|цена|описание|картинка|категория"
    )


@dp.message_handler(lambda m: m.text and "|" in m.text)
async def add_product_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = [p.strip() for p in message.text.split("|")]
    if len(parts) != 5:
        await message.answer(
            "Неверный формат.\n"
            "Используй:\n"
            "название|цена|описание|картинка|категория"
        )
        return

    name, price_raw, description, image, category = parts

    try:
        price = int(price_raw)
    except ValueError:
        await message.answer("Цена должна быть числом.")
        return

    if not hasattr(db, "add_product"):
        await message.answer(
            "Функция add_product пока отсутствует в db.py. "
            "Сначала нужно дописать её."
        )
        return

    try:
        db.add_product(name, price, description, image, category)
        await message.answer("Товар добавлен.")
    except Exception as e:
        logger.exception("Ошибка при добавлении товара")
        await message.answer(f"Ошибка при добавлении товара: {e}")


@dp.message_handler(content_types=types.ContentType.WEB_APP_DATA)
async def webapp_order(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
    except Exception:
        await message.answer("Не удалось обработать данные заказа.")
        return

    tg_user = message.from_user.username or str(message.from_user.id)
    metro = str(data.get("metro", "") or "")
    delivery_time = str(data.get("time", "") or "")
    items = data.get("items", []) or []

    try:
        total = int(data.get("total", 0) or 0)
    except (TypeError, ValueError):
        total = 0

    try:
        order_id = db.create_order(
            tg_user=tg_user,
            metro=metro,
            delivery_time=delivery_time,
            items=items,
            total=total,
        )
    except Exception as e:
        logger.exception("Ошибка при сохранении заказа")
        await message.answer(f"Ошибка при сохранении заказа: {e}")
        return
    lines = [f"Новый заказ #{order_id}"]

    if message.from_user.username:
        lines.append(f"TG: @{message.from_user.username}")
    else:
        lines.append(f"TG id: {message.from_user.id}")

    if metro:
        lines.append(f"Метро: {metro}")

    if delivery_time:
        lines.append(f"Время: {delivery_time}")

    lines.append("")
    lines.append("Товары:")

    for item in items:
        name = item.get("name", "товар")
        qty = item.get("qty", 1)
        price = item.get("price", 0)

        try:
            qty = int(qty)
        except (TypeError, ValueError):
            qty = 1

        try:
            price = int(price)
        except (TypeError, ValueError):
            price = 0

        lines.append(f"• {name} x{qty} = {qty * price}₽")

    lines.append("")
    lines.append(f"Итого: {total}₽")

    try:
        await bot.send_message(ADMIN_ID, "\n".join(lines))
    except Exception:
        logger.exception("Не удалось отправить сообщение админу")

    await message.answer("✅ Заказ принят! Мы скоро напишем вам.")


@app.get("/", response_class=HTMLResponse)
async def home():
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)

    return """
    <html>
      <head>
        <meta charset="utf-8">
        <title>MSV Shop</title>
      </head>
      <body>
        <h1>MSV Shop</h1>
        <p>Сайт запущен ✅</p>
      </body>
    </html>
    """


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.on_event("startup")
async def on_startup():
    logger.info("Инициализация базы данных...")
    db.init_db()

    logger.info("Запуск Telegram-бота...")
    app.state.bot_polling_task = asyncio.create_task(dp.start_polling())


@app.on_event("shutdown")
async def on_shutdown():
    task = getattr(app.state, "bot_polling_task", None)

    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    session = await bot.get_session()
    await session.close()

    logger.info("Приложение остановлено")
