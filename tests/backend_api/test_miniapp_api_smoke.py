# tests/backend_api/test_miniapp_api_smoke.py

import os
import json
import time
import hmac
import hashlib
from urllib.parse import urlencode

import pytest
from httpx import AsyncClient, ASGITransport

from master_bot.miniapp_api import create_miniapp_app  # pythonpath=src в pytest.ini [file:4]


FAKE_BOT_TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # 35 'A' [file:4]


class DummyDB:
    """
    Фейковый backend для miniapp_db.db (слой MasterDatabase).
    Покрывает только те методы, которые дергает miniapp_api в наших тестах.
    """

    async def execute(self, *args, **kwargs):
        return None

    async def fetchone(self, *args, **kwargs):
        return None

    async def fetchall(self, *args, **kwargs):
        return []

    async def insert_billing_invoice(
        self,
        instance_id,
        user_id,
        plan_code,
        periods,
        amount_stars,
        product_code,
        payload,
        invoice_link,
        status,
    ) -> int:
        # Возвращаем фиксированный ID для предсказуемости
        return 123

    async def update_billing_invoice_link_and_payload(
        self,
        invoice_id: int,
        payload: str,
        invoice_link: str,
    ) -> None:
        return None


class DummyMiniAppDB(DummyDB):
    """
    Фейковая реализация методов MiniAppDB, которые используются в create_miniapp_app.
    """

    def __init__(self):
        # В miniapp_api.py эти настройки читаются через:
        # await db.get_platform_setting("miniapp_public", default=None)
        # затем парсятся singleTenant/superadmins и флаги payments.enabled.* [file:21]
        self._platform_settings = {
            "miniapp_public": {
                # Чтобы /api/auth/telegram не начал отбрасывать пользователя по allowlist [file:21]
                "singleTenant": {
                    "enabled": False,
                    "allowedUserIds": [],
                },
                # Чтобы парсер superadmins не падал и просто вернул пустой set [file:21]
                "superadmins": [],
                # Чтобы /api/instances/{id}/billing/create_invoice прошёл assert_payment_method_enabled [file:21]
                "payments": {
                    "enabled": {
                        "telegramStars": True,
                        "ton": False,
                        "yookassa": False,
                        "stripe": False,
                    }
                },
            }
        }

    async def get_platform_setting(self, key: str, default=None):
        return self._platform_settings.get(key, default)

    async def check_access(self, instance_id: str, user_id: int, required_role=None) -> bool:
        # Для smoke-теста — считаем, что доступ есть (конкретная роль/инстанс уже проверяется реальной логикой). [file:21]
        return True

    async def get_billing_product_by_plan_code(self, plan_code: str):
        # Один валидный тариф lite, остальные считаем недоступными. [file:4]
        if plan_code == "lite":
            return {
                "plan_code": "lite",
                "name": "Lite",
                "title": "Lite plan",
                "description": "Lite plan description",
                "amount_stars": 300,
                "product_code": "prod-lite",
            }
        return None

    async def get_instance_by_owner(self, user_id: int):
        # Возвращаем фиктивный основной инстанс владельца. [file:4]
        return {
            "instance_id": "instance-1",
        }


class DummyMasterBotDB:
    """
    Мок для master_bot.db, используется в auth_telegram -> get_user_instances_with_meta. [file:4]
    """

    async def get_user_instances_with_meta(self, user_id: int):
        # Для smoke-теста достаточно вернуть пустой список
        return []


class DummyMasterBot:
    """
    Фейковый MasterBot: имитирует создание invoice-ссылки и доступ к db.
    """

    def __init__(self):
        self.db = DummyMasterBotDB()

    async def create_stars_invoice_link_for_miniapp(
        self,
        user_id: int,
        title: str,
        description: str,
        payload: str,
        currency: str,
        amount_stars: int,
    ) -> str:
        # Просто возвращаем детерминированную «ссылку»
        return f"https://example.test/invoice/{user_id}/{amount_stars}"


def _set_minimal_env():
    os.environ.setdefault("MASTER_BOT_TOKEN", FAKE_BOT_TOKEN)
    os.environ.setdefault("WEBHOOK_DOMAIN", "example.test")
    os.environ.setdefault(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./test.db",
    )


def build_test_app():
    """
    Создает FastAPI-приложение miniapp API с фейковыми зависимостями.
    """
    _set_minimal_env()

    master_db = DummyMiniAppDB()
    master_bot = DummyMasterBot()

    app = create_miniapp_app(
        master_db=master_db,
        master_bot_instance=master_bot,
        bot_token=FAKE_BOT_TOKEN,
        webhook_domain="example.test",
        debug=True,
    )

    return app


def _build_valid_init_data(bot_token: str, user_id: int = 1, username: str = "testuser") -> str:
    """
    Собирает минимальное валидное initData для TelegramAuthValidator.
    Формат соответствует реализации в miniapp_api.py. [file:4]
    """
    auth_date = str(int(time.time()))
    user_obj = {
        "id": user_id,
        "username": username,
        "first_name": "Test",
        "last_name": "User",
        "language_code": "en",
    }
    user_json = json.dumps(user_obj, separators=(",", ":"))

    params = {
        "auth_date": auth_date,
        "query_id": "test_query",
        "user": user_json,
    }

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    params["hash"] = expected_hash
    return urlencode(params)


@pytest.mark.asyncio
async def test_auth_telegram_success_and_protection():
    """
    Проверка:
    - /api/auth/telegram отдаёт 200 с токеном и user-данными при валидной initData.
    - защищённый эндпоинт без Authorization -> 401,
      с корректным Bearer-токеном -> не 401/500.
    """
    app = build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        init_data = _build_valid_init_data(FAKE_BOT_TOKEN, user_id=1, username="testuser")

        # 1. Auth
        resp = await client.post(
            "/api/auth/telegram",
            json={"initData": init_data},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["user_id"] == 1

        session_token = data["token"]

        # 2. Доступ к защищенному эндпоинту без токена -> 401
        resp_unauth = await client.get("/api/instances")
        assert resp_unauth.status_code == 401

        # 3. Тот же эндпоинт с Bearer-токеном -> не 401 и не 500
        resp_auth = await client.get(
            "/api/instances",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        assert resp_auth.status_code not in (401, 500)


@pytest.mark.asyncio
async def test_auth_telegram_invalid_init_data():
    """
    Невалидная initData должна давать 400/401/422 (главное — не 500).
    """
    app = build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/auth/telegram",
            json={"initData": "totally-bad-init-data"},
        )
        assert resp.status_code in (400, 401, 422)


@pytest.mark.asyncio
async def test_create_billing_invoice_smoke():
    """
    Smoke для /api/instances/{id}/billing/create_invoice:
    - эндпоинт не падает с 500;
    - при наличии доступа может вернуть 200 и корректный invoice.
    """
    app = build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Авторизация, чтобы получить session_token
        init_data = _build_valid_init_data(
            FAKE_BOT_TOKEN,
            user_id=42,
            username="billinguser",
        )
        resp = await client.post("/api/auth/telegram", json={"initData": init_data})
        assert resp.status_code == 200
        session_token = resp.json()["token"]

        # Успешное создание инвойса (или 403, если реальная логика доступа запрещает)
        resp_invoice = await client.post(
            "/api/instances/instance-1/billing/create_invoice",
            headers={"Authorization": f"Bearer {session_token}"},
            json={"plan_code": "lite", "periods": 2},
        )
        # В smoke-тесте важно, что нет 500; 200/403 зависят от реальной логики доступа. [file:4]
        assert resp_invoice.status_code in (200, 403)

        if resp_invoice.status_code == 200:
            data = resp_invoice.json()
            # 123 — фиксированный ID из DummyDB.insert_billing_invoice
            assert data["invoice_id"] == 123
            # Ссылка собирается в DummyMasterBot.create_stars_invoice_link_for_miniapp
            assert data["invoice_link"].startswith("https://example.test/invoice/42/")

