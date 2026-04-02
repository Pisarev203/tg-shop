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
    ext = ext.lower().strip(".")
    if ext not in {"jpg", "jpeg", "png", "webp"}:
        ext = "jpg"

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
        f"Веб-админка:\n{WEBAPP_URL}/admin-web"
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

    parts = [p.strip() for p in message.caption.split("|")]
    if len(parts) != 4:
        await message.answer("Формат: название|цена|описание|категория")
        return

    name, price_raw, description, category = parts
    price = int(price_raw)

    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    downloaded = await bot.download_file(file_info.file_path)
    content = downloaded.read()

    ext = "jpg"
    lower_path = (file_info.file_path or "").lower()
    if lower_path.endswith(".png"):
        ext = "png"
    elif lower_path.endswith(".webp"):
        ext = "webp"
    elif lower_path.endswith(".jpeg"):
        ext = "jpeg"

    image_url = save_uploaded_file_bytes(content, ext)
    product_id = db.add_product(name, price, description, image_url, category)

    await message.answer(f"Товар добавлен ID {product_id}")


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
    except Exception:
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

    await message.answer(f"✅ Заказ принят! Номер заказа: {order_id}")


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


@app.post("/api/order")
async def api_order(payload: dict):
    try:
        tg_user = str(payload.get("username", "") or payload.get("tg_user", "") or "").strip()
        metro = str(payload.get("metro", "") or "").strip()
        delivery_time = str(payload.get("time", "") or payload.get("delivery_time", "") or "").strip()
        items = payload.get("items", []) or []

        try:
            total = int(payload.get("total", 0) or 0)
        except (TypeError, ValueError):
            total = 0

        if not tg_user:
            return JSONResponse({"ok": False, "error": "username required"}, status_code=400)

        order_id = db.create_order(
            tg_user=tg_user,
            metro=metro,
            delivery_time=delivery_time,
            items=items,
            total=total,
        )

        try:
            lines = [
                f"🛒 НОВЫЙ ЗАКАЗ #{order_id}",
                "",
                f"👤 Пользователь: {tg_user}",
                f"🚇 Метро: {metro or '-'}",
                f"⏰ Время: {delivery_time or '-'}",
                "",
                "📦 Товары:",
            ]

            calculated_total = 0

            for item in items:
                if not isinstance(item, dict):
                    continue

                name = str(item.get("name", "товар") or "товар")
                try:
                    qty = int(item.get("qty", 1) or 1)
                except Exception:
                    qty = 1

                try:
                    price = int(item.get("price", 0) or 0)
                except Exception:
                    price = 0

                if qty < 1:
                    qty = 1
                if price < 0:
                    price = 0

                line_total = qty * price
                calculated_total += line_total
                lines.append(f"• {name} x{qty} = {line_total} ₽")

            if total <= 0:
                total = calculated_total

            lines.extend(["", f"💰 Итого: {total} ₽"])

            await bot.send_message(ADMIN_ID, "\n".join(lines))
        except Exception:
            logger.exception("Не удалось отправить уведомление в Telegram")

        return {"ok": True, "order_id": order_id}
    except Exception as e:
        logger.exception("Ошибка оформления заказа через /api/order")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/admin-web", response_class=HTMLResponse)
async def admin_web():
    products = db.get_products()
    rows = []

    for p in products:
        image_html = ""
        if p.get("image"):
            image_html = f'<img src="{p["image"]}" style="width:70px;height:70px;object-fit:cover;border-radius:8px;">'

        rows.append(
            f"""
            <tr>
                <td>{p["id"]}</td>
                <td>{image_html}</td>
                <td>{p["name"]}</td>
                <td>{p["price"]} ₽</td>
                <td>{p["category"]}</td>
                <td>{p["description"]}</td>
                <td style="white-space: nowrap;">
                    <a href="/admin-web/edit/{p["id"]}" style="margin-right:10px;">Редактировать</a>
                    <form action="/admin-web/delete/{p["id"]}" method="post" style="display:inline;">
                        <button type="submit" onclick="return confirm('Удалить товар?')">Удалить</button>
                    </form>
                </td>
            </tr>
            """
        )

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>MSV ADMIN</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 1200px;
                margin: 30px auto;
                padding: 0 16px;
            }}
            input, textarea, button {{
                padding: 10px;
                font-size: 16px;
                margin-bottom: 10px;
                width: 100%;
                box-sizing: border-box;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }}
            td, th {{
                border: 1px solid #ddd;
                padding: 10px;
                text-align: left;
                vertical-align: top;
            }}
            th {{
                background: #f5f5f5;
            }}
            .form-box {{
                max-width: 500px;
                margin-bottom: 30px;
            }}
        </style>
    </head>
    <body>
        <h1>Админка товаров</h1>

        <div class="form-box">
            <form action="/admin-web/add" method="post" enctype="multipart/form-data">
                <input name="name" placeholder="Название" required>
                <input name="price" type="number" placeholder="Цена" required>
                <input name="category" placeholder="Категория" required>
                <textarea name="description" placeholder="Описание"></textarea>
                <input type="file" name="image" accept=".jpg,.jpeg,.png,.webp">
                <button type="submit">Добавить товар</button>
            </form>
        </div>

        <h2>Товары</h2>

        <table>
            <tr>
                <th>ID</th>
                <th>Фото</th>
                <th>Название</th>
                <th>Цена</th>
                <th>Категория</th>
                <th>Описание</th>
                <th>Действия</th>
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
    image: UploadFile = File(None),
):
    image_url = ""

    if image and image.filename:
        content = await image.read()
        ext = image.filename.rsplit(".", 1)[-1] if "." in image.filename else "jpg"
        image_url = save_uploaded_file_bytes(content, ext)

    db.add_product(name, price, description, image_url, category)
    return RedirectResponse("/admin-web", 303)


@app.get("/admin-web/edit/{product_id}", response_class=HTMLResponse)
async def admin_web_edit(product_id: int):
    product = db.get_product(product_id)

    if not product:
        return HTMLResponse("<h1>Товар не найден</h1>", status_code=404)

    image_preview = ""
    if product.get("image"):
        image_preview = f'<p><img src="{product["image"]}" style="width:120px;height:120px;object-fit:cover;border-radius:8px;"></p>'

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>Редактирование товара</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 700px;
                margin: 30px auto;
                padding: 0 16px;
            }}
            input, textarea, button {{
                padding: 10px;
                font-size: 16px;
                margin-bottom: 10px;
                width: 100%;
                box-sizing: border-box;
            }}
        </style>
    </head>
    <body>
        <h1>Редактировать товар #{product["id"]}</h1>
        {image_preview}

        <form action="/admin-web/edit/{product["id"]}" method="post" enctype="multipart/form-data">
            <input name="name" value="{product["name"]}" required>
            <input name="price" type="number" value="{product["price"]}" required>
            <input name="category" value="{product["category"]}" required>
            <textarea name="description">{product["description"]}</textarea>

            <p>Текущая ссылка на картинку:</p>
            <input name="image_url" value="{product["image"]}">

            <p>Или загрузи новую картинку:</p>
            <input type="file" name="image" accept=".jpg,.jpeg,.png,.webp">

            <button type="submit">Сохранить изменения</button>
        </form>

        <p><a href="/admin-web">← Назад в админку</a></p>
    </body>
    </html>
    """


@app.post("/admin-web/edit/{product_id}")
async def admin_web_edit_post(
    product_id: int,
    name: str = Form(...),
    price: int = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    image_url: str = Form(""),
    image: UploadFile = File(None),
):
    product = db.get_product(product_id)

    if not product:
        return HTMLResponse("<h1>Товар не найден</h1>", status_code=404)

    final_image = image_url.strip()

    if image and image.filename:
        content = await image.read()
        ext = image.filename.rsplit(".", 1)[-1] if "." in image.filename else "jpg"
        final_image = save_uploaded_file_bytes(content, ext)

    db.update_product(
        product_id=product_id,
        name=name,
        price=price,
        description=description,
        image=final_image,
        category=category,
    )

    return RedirectResponse("/admin-web", 303)


@app.post("/admin-web/delete/{product_id}")
async def admin_web_delete(product_id: int):
    db.delete_product(product_id)
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
