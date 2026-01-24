# tests/worker/test_worker_smoke.py

import os
import types

import pytest
from unittest.mock import AsyncMock

from worker.main import GraceHubWorker  # с pytest.ini (pythonpath = src)


class DummyDB:
    """
    Минимальный фейковый MasterDatabase:
    методы есть, но ничего реально не делают.
    Этого хватает для smoke-теста, чтобы не ходить в Postgres.
    """

    async def fetchone(self, *args, **kwargs):
        return None

    async def fetchall(self, *args, **kwargs):
        return []

    async def execute(self, *args, **kwargs):
        return None

    async def get_decrypted_token(self, instance_id: str):
        # Возвращаем токен для теста
        return "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

    async def get_instance(self, instance_id: str):
        # Возвращаем фейковый инстанс
        mock_instance = types.SimpleNamespace()
        mock_instance.bot_username = "test_bot"
        return mock_instance


def _set_minimal_env():
    # валидный по формату токен, как и в тесте мастер-бота
    fake_valid_token = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # 35 'A'

    os.environ.setdefault("WORKER_INSTANCE_ID", "test-instance")
    os.environ.setdefault("WORKER_TOKEN", fake_valid_token)
    os.environ.setdefault(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./test.db",  # чтобы реальный MasterDatabase, если вдруг, не упирался в прод
    )
    os.environ.setdefault("LOG_LEVEL", "INFO")


@pytest.mark.asyncio
async def test_worker_can_be_created():
    _set_minimal_env()

    instance_id = os.environ["WORKER_INSTANCE_ID"]
    token = os.environ["WORKER_TOKEN"]

    db = DummyDB()
    worker = GraceHubWorker(instance_id=instance_id, token=token, db=db)
    
    # Инициализируем воркера
    await worker.initialize()

    assert worker.instance_id == instance_id
    assert worker.token == token
    assert worker.bot is not None
    assert worker.dp is not None
    assert worker.db is db

    # в dispatcher должны быть какие-то хендлеры после register_handlers()
    assert len(worker.dp.message.handlers) > 0


@pytest.mark.asyncio
async def test_worker_core_utils():
    """
    Лёгкий async smoke: базовые утилиты не падают при вызове
    с фейковыми зависимостями.
    """
    _set_minimal_env()
    worker = GraceHubWorker(
        instance_id=os.environ["WORKER_INSTANCE_ID"],
        token=os.environ["WORKER_TOKEN"],
        db=DummyDB(),
    )
    
    # Инициализируем воркера
    await worker.initialize()

    # методы настроек существуют и не падают при простом вызове
    assert hasattr(worker, "get_setting")
    assert hasattr(worker, "set_setting")
    assert hasattr(worker, "is_admin")

    # get_rating_keyboard возвращает InlineKeyboardMarkup
    kb = worker.get_rating_keyboard(ticket_id=123)
    # просто проверим наличие inline_keyboard
    assert hasattr(kb, "inline_keyboard")

    # is_admin с пустой БД должен вернуть False
    is_admin = await worker.is_admin(user_id=42)
    assert is_admin is False
