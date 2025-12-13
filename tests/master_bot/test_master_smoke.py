# tests/master_bot/test_master_smoke.py

import os

import pytest

from master_bot.main import MasterBot  # с pytest.ini (pythonpath = src)


def _set_minimal_env():
    # 35 символов после двоеточия – чтобы validate_token_format вернул True
    fake_valid_token = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # 35 'A'

    os.environ.setdefault("MASTER_BOT_TOKEN", fake_valid_token)
    os.environ.setdefault("WEBHOOK_DOMAIN", "example.test")
    os.environ.setdefault("WEBHOOK_PORT", "8443")
    os.environ.setdefault(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./test.db",
    )


def test_master_bot_can_be_created():
    _set_minimal_env()

    token = os.environ["MASTER_BOT_TOKEN"]
    domain = os.environ["WEBHOOK_DOMAIN"]
    port = int(os.environ["WEBHOOK_PORT"])

    bot = MasterBot(token=token, webhook_domain=domain, webhook_port=port)

    assert bot.bot is not None
    assert bot.dp is not None
    assert bot.webhook_domain == domain
    assert bot.webhook_port == port
    assert len(bot.dp.message.handlers) > 0


@pytest.mark.asyncio
async def test_master_bot_has_core_methods():
    _set_minimal_env()
    bot = MasterBot(
        token=os.environ["MASTER_BOT_TOKEN"],
        webhook_domain=os.environ["WEBHOOK_DOMAIN"],
        webhook_port=int(os.environ["WEBHOOK_PORT"]),
    )

    assert hasattr(bot, "validate_token_format")
    assert hasattr(bot, "generate_instance_id")
    assert hasattr(bot, "spawn_worker")
    assert hasattr(bot, "stop_worker")

    # тут тот же валидный по формату токен
    assert (
        bot.validate_token_format("123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
        is True
    )
    assert bot.validate_token_format("bad_token") is False

    instance_id = bot.generate_instance_id()
    assert isinstance(instance_id, str)
    assert instance_id

    try:
        bot.spawn_worker(instance_id="test-instance", token="FAKE_TOKEN_FOR_WORKER")
        bot.stop_worker(instance_id="test-instance")
    except Exception as e:
        pytest.fail(f"spawn_worker/stop_worker raised unexpected exception: {e}")

