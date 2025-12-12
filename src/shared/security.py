import hashlib
import hmac
import os
import secrets
from typing import Optional


class SecurityManager:
    """
    Security utilities for the platform.

    Используется для:
      - хэширования токенов ботов перед сохранением (tokenhash)
      - генерации секретов для вебхуков
      - проверки подписей вебхука
      - генерации идентификаторов инстансов
    """

    def __init__(self, salt: Optional[str] = None) -> None:
        # В проде соль лучше брать из переменной окружения, в коде оставить дефолт.
        self.salt = salt or os.getenv("GRACEHUB_TOKEN_SALT") or "gracehub_platform_salt"

    def hash_token(self, token: str) -> str:
        """
        Create a secure hash of bot token for storage.

        Используем SHA-256 + соль, чтобы не хранить токены в явном виде.
        """
        data = f"{token}{self.salt}".encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    def generate_webhook_secret(self) -> str:
        """
        Generate secure webhook secret.

        Секрет используется Telegram-ботом для подписи вебхуков.
        """
        return secrets.token_urlsafe(32)

    def verify_webhook_signature(self, data: bytes, signature: str, secret: str) -> bool:
        """
        Verify webhook signature.

        data      — «сырое» тело HTTP-запроса (bytes),
        signature — строка с хэшем, пришедшая в заголовке,
        secret    — секрет, с которым настраивался вебхук.
        """
        expected = hmac.new(secret.encode("utf-8"), data, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    def generate_instance_id(self) -> str:
        """
        Generate unique instance ID.

        Используется как primary key instanceid в botinstances.
        """
        return secrets.token_urlsafe(16)
