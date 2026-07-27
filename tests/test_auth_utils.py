import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import urlencode

from auth_utils import TelegramAuthError, valid_admin_basic, validate_telegram_init_data


def signed_init_data(token: str, user: dict) -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "test-query",
        "user": json.dumps(user, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class TelegramAuthTests(unittest.TestCase):
    def test_valid_signature(self):
        token = "123456:test-token"
        value = signed_init_data(token, {"id": 42, "first_name": "Test"})
        parsed = validate_telegram_init_data(value, token)
        self.assertEqual(parsed["user"]["id"], 42)

    def test_invalid_signature(self):
        value = signed_init_data("right", {"id": 42})
        with self.assertRaises(TelegramAuthError):
            validate_telegram_init_data(value, "wrong")

    def test_admin_basic(self):
        self.assertTrue(valid_admin_basic("Basic YWRtaW46c2VjcmV0", "admin", "secret"))
        self.assertFalse(valid_admin_basic("Basic YWRtaW46d3Jvbmc=", "admin", "secret"))


if __name__ == "__main__":
    unittest.main()
