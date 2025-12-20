from fastapi import FastAPI
from fastapi.responses import FileResponse
from pathlib import Path
import db

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent

db.init_db()

@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")

@app.get("/api/products")
def api_products():
    return db.products()
