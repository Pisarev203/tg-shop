import os
import requests

def send(text: str):
    token = (os.getenv("BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("ADMIN_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return  # не настроено

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    requests.post(url, json=payload, timeout=10)
