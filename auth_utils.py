import hashlib
import hmac
import json
import time
from base64 import b64decode
from urllib.parse import parse_qsl


class TelegramAuthError(ValueError):
    pass


def validate_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict:
    """Validate Telegram Mini App initData and return its decoded fields."""
    if not init_data:
        raise TelegramAuthError("Откройте магазин внутри Telegram")
    if not bot_token:
        raise TelegramAuthError("Бот не настроен")

    try:
        fields = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise TelegramAuthError("Некорректные данные Telegram") from exc

    received_hash = fields.pop("hash", "")
    if not received_hash:
        raise TelegramAuthError("Telegram не передал подпись")

    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(received_hash, calculated_hash):
        raise TelegramAuthError("Подпись Telegram не прошла проверку")

    try:
        auth_date = int(fields.get("auth_date", "0"))
    except (TypeError, ValueError) as exc:
        raise TelegramAuthError("Некорректная дата авторизации") from exc

    now = int(time.time())
    if auth_date <= 0 or auth_date > now + 60 or now - auth_date > max_age_seconds:
        raise TelegramAuthError("Сессия Telegram устарела — откройте магазин заново")

    try:
        user = json.loads(fields.get("user", "{}"))
    except json.JSONDecodeError as exc:
        raise TelegramAuthError("Telegram не передал профиль пользователя") from exc

    if not isinstance(user, dict) or not user.get("id"):
        raise TelegramAuthError("Telegram не передал идентификатор пользователя")

    fields["user"] = user
    return fields


def parse_basic_authorization(header: str) -> tuple[str, str] | None:
    if not header or not header.startswith("Basic "):
        return None
    try:
        raw = b64decode(header[6:].strip(), validate=True).decode("utf-8")
        username, password = raw.split(":", 1)
        return username, password
    except (ValueError, UnicodeDecodeError):
        return None


def valid_admin_basic(header: str, expected_user: str, expected_password: str) -> bool:
    credentials = parse_basic_authorization(header)
    if not credentials or not expected_password:
        return False
    username, password = credentials
    return hmac.compare_digest(username, expected_user) and hmac.compare_digest(
        password,
        expected_password,
    )
