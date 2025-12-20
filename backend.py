from fastapi import FastAPI
from fastapi.responses import FileResponse
import db

app = FastAPI()
db.init_db()

@app.get("/")
def index():
    return FileResponse("index.html")

@app.get("/api/products")
def api_products():
    return db.products()
