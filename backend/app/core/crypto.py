import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class SecretCipher:
    def __init__(self, secret: str | None = None) -> None:
        source = (secret or get_settings().app_encryption_key).encode("utf-8")
        key = base64.urlsafe_b64encode(hashlib.sha256(source).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("无法解密已保存的 API Key，请检查 APP_ENCRYPTION_KEY") from exc


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:3]}••••••••{value[-4:]}"
