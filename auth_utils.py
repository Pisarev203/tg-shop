import hashlib
import hmac
import json
import time
from base64 import b64decode, urlsafe_b64decode, urlsafe_b64encode
from urllib.parse import parse_qsl


class TelegramAuthError(ValueError):
    pass


def _fallback_secret(bot_token: str) -> bytes:
    return hashlib.sha256(f"MSVWebAuth:{bot_token}".encode("utf-8")).digest()


def create_webapp_auth(telegram_user: dict, bot_token: str, ttl_seconds: int = 604800) -> str:
    """Create a signed fallback for Telegram clients that omit WebApp initData."""
    if not bot_token or not telegram_user.get("id"):
        raise TelegramAuthError("Не удалось создать авторизацию магазина")
    now = int(time.time())
    payload = {
        "id": int(telegram_user["id"]),
        "username": str(telegram_user.get("username") or ""),
        "first_name": str(telegram_user.get("first_name") or ""),
        "last_name": str(telegram_user.get("last_name") or ""),
        "language_code": str(telegram_user.get("language_code") or ""),
        "iat": now,
        "exp": now + max(300, int(ttl_seconds)),
    }
    body = urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    signature = hmac.new(_fallback_secret(bot_token), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def validate_webapp_auth(token: str, bot_token: str) -> dict:
    if not token or "." not in token or not bot_token:
        raise TelegramAuthError("Откройте магазин новой кнопкой после команды /start")
    try:
        body, received_signature = token.rsplit(".", 1)
        expected_signature = hmac.new(
            _fallback_secret(bot_token), body.encode("ascii"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(received_signature, expected_signature):
            raise TelegramAuthError("Подпись кнопки магазина недействительна")
        padding = "=" * (-len(body) % 4)
        payload = json.loads(urlsafe_b64decode(body + padding).decode("utf-8"))
        now = int(time.time())
        if not isinstance(payload, dict) or not payload.get("id"):
            raise TelegramAuthError("В кнопке нет профиля Telegram")
        if int(payload.get("exp") or 0) < now or int(payload.get("iat") or 0) > now + 60:
            raise TelegramAuthError("Кнопка магазина устарела — отправьте боту /start")
        return payload
    except TelegramAuthError:
        raise
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TelegramAuthError("Некорректная кнопка магазина") from exc


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
