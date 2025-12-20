from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI()

# Подключаем static
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def index():
    return FileResponse("index.html")

# тестовый API
@app.get("/api/products")
def get_products():
    return JSONResponse([
        {"id": 1, "name": "Товар 1", "price": 100},
        {"id": 2, "name": "Товар 2", "price": 200}
    ])
