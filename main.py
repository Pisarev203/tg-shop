
import asyncio
import json
import logging
import os
import secrets
from contextlib import suppress
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import db


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_TOKEN = (os.getenv("API_TOKEN") or "").strip()
ADMIN_ID_RAW = (os.getenv("ADMIN_ID") or "").strip()
WEBAPP_URL = (os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
PORT = int((os.getenv("PORT") or "5000").strip())

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

DATA_DIR = Path("/data")
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

if STATIC_DIR.exists() and STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


def build_main_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        types.KeyboardButton(
            "Открыть магазин",
            web_app=types.WebAppInfo(url=WEBAPP_URL),
        )
    )
    return kb


def parse_product_caption(text: str):
    parts = [p.strip() for p in (text or "").split("|")]
    if len(parts) != 4:
        raise ValueError("Нужен формат: название|цена|описание|категория")

    name, price_raw, description, category = parts

    try:
        price = int(price_raw)
    except ValueError:
        raise ValueError("Цена должна быть числом")

    if not name:
        raise ValueError("Название пустое")

    return {
        "name": name,
        "price": price,
        "description": description,
        "category": category,
    }


def save_uploaded_file_bytes(content: bytes, ext: str) -> str:
    ext = ext.lower().strip(".")
    if ext not in {"jpg", "jpeg", "png", "webp"}:
        raise ValueError("Разрешены только jpg, jpeg, png, webp")

    filename = f"{secrets.token_hex(16)}.{ext}"
    path = UPLOADS_DIR / filename
    path.write_bytes(content)
    return f"{WEBAPP_URL}/uploads/{filename}"


@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    await message.answer("Открыть магазин:", reply_markup=build_main_keyboard())


@dp.message_handler(commands=["admin"])
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет доступа.")
        return

    await message.answer(
        "Админка:\n\n"
        "1) Текстом:\n"
        "название|цена|описание|ссылка_на_картинку|категория\n\n"
        "2) Фото + подпись:\n"
        "название|цена|описание|категория\n\n"
        f"3) Веб-админка:\n{WEBAPP_URL}/admin-web"
    )


@dp.message_handler(lambda m: m.text and "|" in m.text)
async def add_product_text_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = [p.strip() for p in message.text.split("|")]
    if len(parts) != 5:
        return

    name, price_raw, description, image, category = parts

    try:
        price = int(price_raw)
    except ValueError:
        await message.answer("Цена должна быть числом.")
        return

    try:
        product_id = db.add_product(name, price, description, image, category)
        await message.answer(f"Товар добавлен. ID: {product_id}")
    except Exception as e:
        logger.exception("Ошибка при добавлении товара")
        await message.answer(f"Ошибка при добавлении товара: {e}")


@dp.message_handler(content_types=types.ContentType.PHOTO)
async def add_product_photo_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    if not message.caption:
        return

    try:
        product = parse_product_caption(message.caption)
    except Exception as e:
        await message.answer(
            "Для фото нужен формат подписи:\n"
            "название|цена|описание|категория\n\n"
            f"Ошибка: {e}"
        )
        return

    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        downloaded = await bot.download_file(file_info.file_path)
        content = downloaded.read()

        ext = "jpg"
        file_path = (file_info.file_path or "").lower()
        if file_path.endswith(".png"):
            ext = "png"
        elif file_path.endswith(".webp"):
            ext = "webp"
        elif file_path.endswith(".jpeg"):
            ext = "jpeg"

        image_url = save_uploaded_file_bytes(content, ext)

        product_id = db.add_product(
            product["name"],
            product["price"],
            product["description"],
            image_url,
            product["category"],
        )

        await message.answer(
            f"Товар добавлен.\nID: {product_id}\nКартинка: {image_url}"
        )
    except Exception as e:
        logger.exception("Ошибка при загрузке фото товара")
        await message.answer(f"Ошибка при загрузке фото: {e}")


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
        <p><a href="/admin-web">Открыть веб-админку</a></p>
      </body>
    </html>
    """


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.get("/products")
async def products():
    return db.get_products()


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
