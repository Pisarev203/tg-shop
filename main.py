
# FULL FIXED main.py

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

if not API_TOKEN:
    raise RuntimeError("API_TOKEN не задан")

if not ADMIN_ID_RAW:
    raise RuntimeError("ADMIN_ID не задан")

ADMIN_ID = int(ADMIN_ID_RAW)

if not WEBAPP_URL:
    raise RuntimeError("WEBAPP_URL не задан")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
app = FastAPI(title="MSV Shop")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML = BASE_DIR / "index.html"

DATA_DIR = Path("/data")
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


def build_main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        types.KeyboardButton(
            "Открыть магазин",
            web_app=types.WebAppInfo(url=WEBAPP_URL),
        )
    )
    return kb


def save_uploaded_file_bytes(content: bytes, ext: str) -> str:
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
        "Текстом:\n"
        "название|цена|описание|ссылка|категория\n\n"
        "Фото + подпись:\n"
        "название|цена|описание|категория\n\n"
        f"Веб админка:\n{WEBAPP_URL}/admin-web"
    )


@dp.message_handler(lambda m: m.text and "|" in m.text)
async def add_product_text_cmd(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    parts = [p.strip() for p in message.text.split("|")]

    if len(parts) != 5:
        return

    name, price_raw, description, image, category = parts
    price = int(price_raw)

    product_id = db.add_product(name, price, description, image, category)

    await message.answer(f"Товар добавлен ID {product_id}")


@dp.message_handler(content_types=types.ContentType.PHOTO)
async def add_product_photo_cmd(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    if not message.caption:
        return

    parts = message.caption.split("|")

    if len(parts) != 4:
        return

    name, price_raw, description, category = parts

    price = int(price_raw)

    photo = message.photo[-1]

    file_info = await bot.get_file(photo.file_id)

    downloaded = await bot.download_file(file_info.file_path)

    content = downloaded.read()

    image_url = save_uploaded_file_bytes(content, "jpg")

    product_id = db.add_product(
        name,
        price,
        description,
        image_url,
        category,
    )

    await message.answer(f"Товар добавлен ID {product_id}")


@app.get("/", response_class=HTMLResponse)
async def home():

    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)

    return "<h1>MSV SHOP работает</h1>"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/products")
async def products():
    return db.get_products()


@app.get("/api/products")
async def api_products():
    return db.get_products()


@app.get("/admin-web", response_class=HTMLResponse)
async def admin_web():

    products = db.get_products()

    rows = []

    for p in products:

        rows.append(
            f"""
<tr>
<td>{p["id"]}</td>
<td>{p["name"]}</td>
<td>{p["price"]}</td>
<td>{p["category"]}</td>
</tr>
"""
        )

    return f"""
<html>
<head>
<title>MSV ADMIN</title>
</head>
<body>

<h1>Добавить товар</h1>

<form action="/admin-web/add" method="post" enctype="multipart/form-data">

<input name="name" placeholder="Название"><br>
<input name="price" placeholder="Цена"><br>
<input name="category" placeholder="Категория"><br>
<textarea name="description"></textarea><br>

<input type="file" name="image"><br>

<button type="submit">Добавить</button>

</form>

<h2>Товары</h2>

<table border="1">

<tr>
<th>ID</th>
<th>Название</th>
<th>Цена</th>
<th>Категория</th>
</tr>

{''.join(rows)}

</table>

</body>
</html>
"""


@app.post("/admin-web/add")
async def admin_web_add(

    name: str = Form(...),
    price: int = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    image: UploadFile = File(...),

):

    content = await image.read()

    image_url = save_uploaded_file_bytes(content, "jpg")

    db.add_product(name, price, description, image_url, category)

    return RedirectResponse("/admin-web", 303)


@app.on_event("startup")
async def on_startup():

    db.init_db()

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
