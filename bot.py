import os, json
from aiogram import Bot, Dispatcher, executor, types
import db

TOKEN = os.getenv("API_TOKEN")
ADMIN = int(os.getenv("ADMIN_ID"))
WEBAPP = os.getenv("WEBAPP_URL")

bot = Bot(TOKEN)
dp = Dispatcher(bot)
db.init_db()

@dp.message_handler(commands=["start"])
async def start(m):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🛍 Открыть магазин",
           web_app=types.WebAppInfo(url=WEBAPP)))
    await m.answer("Открыть магазин:",reply_markup=kb)

@dp.message_handler(commands=["admin"])
async def admin(m):
    if m.from_user.id!=ADMIN: return
    await m.answer("Добавление товара:\nназвание|цена|описание|картинка|категория")

@dp.message_handler(lambda m:"|" in m.text)
async def add(m):
    if m.from_user.id!=ADMIN: return
    n,p,d,i,c=m.text.split("|")
    db.add_product(n,int(p),d,i,c)
    await m.answer("Товар добавлен")

@dp.message_handler(content_types=types.ContentType.WEB_APP_DATA)
async def order(m):
    data=json.loads(m.web_app_data.data)
    oid=db.create_order(m.from_user.id,data["total"],data["items"])
    await bot.send_message(ADMIN,f"Новый заказ #{oid}")
    await m.answer("Заказ принят")

executor.start_polling(dp)


