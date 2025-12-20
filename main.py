from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os

import db

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent

db.init_db()

# Не падаем, если папки static нет
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

from fastapi import Form

ADMIN_TOKEN = "Sm03052604!"  # 👉 потом поменяешь

def admin_auth(request: Request):
    token = request.headers.get("x-admin-token")
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/admin")
def admin_page():
    return FileResponse("admin.html")


@app.post("/admin/add-product")
def admin_add_product(
    name: str = Form(...),
    price: int = Form(...),
    description: str = Form(""),
    image_url: str = Form(""),
    category_id: int = Form(1),
):
    db.add_product(name, price, description, image_url, category_id)
    return {"ok": True}
    
@app.post("/api/order")
def create_order(data: dict = Body(...)):
    order_id = db.create_order(
        tg_user=data.get("tg_user", ""),
        metro=data.get("metro", ""),
        delivery_time=data.get("time", ""),
        items=data.get("items", []),
        total=data.get("total", 0),
    )
    return {"ok": True, "order_id": order_id}

def require_admin(req: Request):
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        # Чтобы не забыли поставить пароль
        raise HTTPException(500, "ADMIN_TOKEN не задан в переменных окружения Render")
    got = (req.headers.get("X-Admin-Token") or "").strip()
    if got != token:
        raise HTTPException(401, "Unauthorized")


@app.get("/")
def index():
    return FileResponse(str(BASE_DIR / "index.html"))


@app.get("/admin")
def admin_page():
    return FileResponse(str(BASE_DIR / "admin.html"))


@app.get("/api/products")
def api_products():
    return JSONResponse(db.list_products(active_only=True))


# -------- Admin: categories --------

@app.get("/api/admin/categories")
def admin_list_categories(req: Request):
    require_admin(req)
    return JSONResponse(db.list_categories())


@app.post("/api/admin/categories")
async def admin_create_category(req: Request):
    require_admin(req)
    data = await req.json()
    try:
        return JSONResponse(db.create_category(data.get("name", ""), int(data.get("sort", 0))))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.put("/api/admin/categories/{cat_id}")
async def admin_update_category(cat_id: int, req: Request):
    require_admin(req)
    data = await req.json()
    try:
        db.update_category(cat_id, data.get("name", ""), int(data.get("sort", 0)))
        return JSONResponse({"ok": True})
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/admin/categories/{cat_id}")
def admin_delete_category(cat_id: int, req: Request):
    require_admin(req)
    db.delete_category(cat_id)
    return JSONResponse({"ok": True})


# -------- Admin: products --------

@app.get("/api/admin/products")
def admin_list_products(req: Request):
    require_admin(req)
    return JSONResponse(db.list_products(active_only=False))


@app.post("/api/admin/products")
async def admin_create_product(req: Request):
    require_admin(req)
    data = await req.json()
    try:
        p = db.create_product(
            name=data.get("name", ""),
            price=int(data.get("price", 0)),
            description=data.get("description", "") or "",
            photo=data.get("photo", "") or "",
            category_id=int(data["category_id"]) if data.get("category_id") else None,
            is_active=bool(data.get("is_active", True)),
        )
        return JSONResponse(p)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.put("/api/admin/products/{pid}")
async def admin_update_product(pid: int, req: Request):
    require_admin(req)
    data = await req.json()
    try:
        db.update_product(
            pid=pid,
            name=data.get("name", ""),
            price=int(data.get("price", 0)),
            description=data.get("description", "") or "",
            photo=data.get("photo", "") or "",
            category_id=int(data["category_id"]) if data.get("category_id") else None,
            is_active=bool(data.get("is_active", True)),
        )
        return JSONResponse({"ok": True})
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/admin/products/{pid}")
def admin_delete_product(pid: int, req: Request):
    require_admin(req)
    db.delete_product(pid)
    return JSONResponse({"ok": True})


