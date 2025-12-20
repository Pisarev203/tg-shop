import os
import requests

def send_telegram(text: str):
    token = os.environ.get("BOT_TOKEN", "").strip()
    chat_id = os.environ.get("ADMIN_CHAT_ID", "").strip()
    if not token or not chat_id:
        # Если не заданы переменные — просто молча не шлём
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    requests.post(url, json=payload, timeout=10)
