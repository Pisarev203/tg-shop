
# main.py (final version)

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
ADMIN_ID = int((os.getenv("ADMIN_ID") or "0").strip())
WEBAPP_URL = (os.getenv("WEBAPP_URL") or "").strip().rstrip("/")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
app = FastAPI(title="MSV Shop")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path("/data")
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


def save_uploaded_file_bytes(content: bytes, ext: str) -> str:
    filename = f"{secrets.token_hex(16)}.{ext}"
    path = UPLOADS_DIR / filename
    path.write_bytes(content)
    return f"{WEBAPP_URL}/uploads/{filename}"


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
        tg_user = str(payload.get("username", "")).strip()
        metro = str(payload.get("metro", "")).strip()
        delivery_time = str(payload.get("time", "")).strip()
        items = payload.get("items", [])
        total = int(payload.get("total", 0))

        order_id = db.create_order(
            tg_user=tg_user,
            metro=metro,
            delivery_time=delivery_time,
            items=items,
            total=total,
        )

        return {"ok": True, "order_id": order_id}

    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.on_event("startup")
async def startup():
    db.init_db()
    asyncio.create_task(dp.start_polling())


@app.on_event("shutdown")
async def shutdown():
    session = await bot.get_session()
    await session.close()
