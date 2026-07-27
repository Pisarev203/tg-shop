import asyncio
import os
from pathlib import Path

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse

import crm
from auth_utils import TelegramAuthError, validate_telegram_init_data


router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent
API_TOKEN = (os.getenv("API_TOKEN") or "").strip()
ADMIN_ID = (os.getenv("ADMIN_ID") or "").strip()
BOT_USERNAME = (os.getenv("BOT_USERNAME") or "").strip().lstrip("@")


def _telegram_context(x_telegram_init_data: str = Header("", alias="X-Telegram-Init-Data")) -> dict:
    try:
        return validate_telegram_init_data(x_telegram_init_data, API_TOKEN)
    except TelegramAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _current_customer(context: dict = Depends(_telegram_context)) -> dict:
    return crm.upsert_customer(context["user"], context.get("start_param", ""))


def _optional_customer(x_telegram_init_data: str = Header("", alias="X-Telegram-Init-Data")) -> dict | None:
    if not x_telegram_init_data:
        return None
    try:
        context = validate_telegram_init_data(x_telegram_init_data, API_TOKEN)
        return crm.upsert_customer(context["user"], context.get("start_param", ""))
    except TelegramAuthError:
        return None


def _raise_value_error(exc: ValueError):
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _send_order_notification(order: dict, customer: dict, metro: str, delivery_time: str, comment: str):
    if not API_TOKEN or not ADMIN_ID:
        return
    name = " ".join(
        value for value in [customer.get("first_name", ""), customer.get("last_name", "")] if value
    ).strip()
    username = f"@{customer['username']}" if customer.get("username") else str(customer["telegram_id"])
    lines = [
        f"🛒 НОВЫЙ ЗАКАЗ #{order['id']}",
        f"👤 {name or username} ({username})",
        f"🚇 Метро: {metro or '-'}",
        f"⏰ Время: {delivery_time or '-'}",
        "",
    ]
    for item in order["items"]:
        variant = f" · {item['variant_name']}" if item.get("variant_name") else ""
        lines.append(f"• {item['name']}{variant} × {item['qty']} — {item['line_subtotal']} ₽")
    if order["discount_total"]:
        lines.append(f"🏷 Скидка: −{order['discount_total']} ₽")
    lines.append(f"💰 Итого: {order['total']} ₽")
    if comment:
        lines.append(f"💬 {comment[:500]}")
    try:
        requests.post(
            f"https://api.telegram.org/bot{API_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_ID, "text": "\n".join(lines)},
            timeout=10,
        ).raise_for_status()
    except Exception:
        # The order is already stored; a Telegram outage must not cancel it.
        return


@router.get("/api/v2/catalog")
async def catalog_v2():
    products = crm.get_catalog()
    return {
        "products": products,
        "categories": sorted({product["category"] for product in products if product["category"]}),
        "brands": sorted({product["brand"] for product in products if product["brand"]}),
    }


@router.get("/api/v2/session")
async def session_v2(
    ref: str = Query("", max_length=64),
    context: dict = Depends(_telegram_context),
):
    start_param = context.get("start_param", "") or ref
    customer = crm.upsert_customer(context["user"], start_param)
    return {"customer": customer}


@router.post("/api/v2/quote")
async def quote_v2(payload: dict, customer: dict | None = Depends(_optional_customer)):
    try:
        return crm.quote(
            customer["id"] if customer else None,
            payload.get("items") or [],
            payload.get("promo_code") or "",
        )
    except ValueError as exc:
        _raise_value_error(exc)


@router.post("/api/v2/orders")
async def create_order_v2(
    payload: dict,
    background_tasks: BackgroundTasks,
    customer: dict = Depends(_current_customer),
):
    metro = str(payload.get("metro") or "").strip()
    delivery_time = str(payload.get("delivery_time") or "").strip()
    comment = str(payload.get("comment") or "").strip()
    try:
        order = crm.create_order(
            customer["id"],
            payload.get("items") or [],
            payload.get("promo_code") or "",
            metro,
            delivery_time,
            comment,
        )
    except ValueError as exc:
        _raise_value_error(exc)
    background_tasks.add_task(
        _send_order_notification,
        order,
        customer,
        metro,
        delivery_time,
        comment,
    )
    return {"ok": True, "order": order}


@router.get("/api/v2/profile")
async def profile_v2(customer: dict = Depends(_current_customer)):
    try:
        return crm.get_profile(customer["id"], BOT_USERNAME)
    except ValueError as exc:
        _raise_value_error(exc)


@router.get("/admin-crm")
async def admin_crm_page():
    return FileResponse(BASE_DIR / "admin_crm.html")


@router.get("/api/admin/dashboard")
async def admin_dashboard(days: int = Query(30, ge=7, le=365)):
    return crm.dashboard(days)


@router.get("/api/admin/orders")
async def admin_orders(limit: int = Query(100, ge=1, le=500)):
    return {"orders": crm.list_orders(limit)}


@router.patch("/api/admin/orders/{order_id}/status")
async def admin_order_status(order_id: int, payload: dict):
    try:
        return crm.update_order_status(order_id, payload.get("status") or "")
    except ValueError as exc:
        _raise_value_error(exc)


@router.get("/api/admin/customers")
async def admin_customers(limit: int = Query(300, ge=1, le=1000)):
    return {"customers": crm.list_customers(limit)}


@router.patch("/api/admin/customers/{customer_id}")
async def admin_customer_update(customer_id: int, payload: dict):
    try:
        return crm.update_customer(customer_id, payload.get("label_color"), payload.get("note"))
    except ValueError as exc:
        _raise_value_error(exc)


@router.get("/api/admin/promos")
async def admin_promos():
    return {"promos": crm.list_promos()}


@router.post("/api/admin/promos")
async def admin_promo_create(payload: dict):
    try:
        return crm.create_promo(payload)
    except ValueError as exc:
        _raise_value_error(exc)


@router.patch("/api/admin/promos/{promo_id}")
async def admin_promo_toggle(promo_id: int, payload: dict):
    try:
        return crm.set_promo_active(promo_id, bool(payload.get("active")))
    except ValueError as exc:
        _raise_value_error(exc)


@router.get("/api/admin/products")
async def admin_products():
    return {"products": crm.get_catalog(include_inactive=True)}


@router.post("/api/admin/products")
async def admin_product_create(payload: dict):
    try:
        return crm.create_product(payload)
    except ValueError as exc:
        _raise_value_error(exc)


@router.patch("/api/admin/products/{product_id}")
async def admin_product_update(product_id: int, payload: dict):
    try:
        return crm.update_product(product_id, payload)
    except ValueError as exc:
        _raise_value_error(exc)


@router.post("/api/admin/products/{product_id}/variants")
async def admin_variant_create(product_id: int, payload: dict):
    try:
        return crm.create_variant(product_id, payload)
    except ValueError as exc:
        _raise_value_error(exc)


@router.patch("/api/admin/variants/{variant_id}")
async def admin_variant_update(variant_id: int, payload: dict):
    try:
        return crm.update_variant(variant_id, payload)
    except ValueError as exc:
        _raise_value_error(exc)


@router.delete("/api/admin/variants/{variant_id}")
async def admin_variant_delete(variant_id: int):
    crm.delete_variant(variant_id)
    return {"ok": True}
