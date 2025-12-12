#!/usr/bin/env python3
"""
Standalone сервер Mini App API.
Запускается отдельным процессом на порту 8001.
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ==== Пути проекта ====
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # /root/gracehub
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import uvicorn  # noqa: E402

from shared.database import MasterDatabase, get_master_dsn  # noqa: E402
from master_bot.main import MasterBot  # noqa: E402
from master_bot.miniapp_api import create_miniapp_app  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Читаем bot token из .env
MASTER_BOT_TOKEN = os.getenv("GRACEHUB_BOT_TOKEN") or os.getenv("MASTER_BOT_TOKEN")
if not MASTER_BOT_TOKEN:
    logger.error("❌ MASTER_BOT_TOKEN не найден в .env")
    sys.exit(1)

logger.info("✅ MASTER_BOT_TOKEN загружен из .env")

WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN")
if not WEBHOOK_DOMAIN:
    logger.error("❌ WEBHOOK_DOMAIN не найден в .env")
    sys.exit(1)

DEBUG = bool(int(os.getenv("DEBUG", "0")))


async def main():
    """Инициализирует БД, MasterBot и запускает Mini App API сервер."""

    # Используем тот же DSN, что и master: из env DATABASE_URL (PostgreSQL)
    try:
        dsn = get_master_dsn()
    except RuntimeError as e:
        logger.error(f"❌ {e}")
        sys.exit(1)

    logger.info(f"📁 Используется БД (Postgres): {dsn}")

    # Инициализируем master БД (Postgres)
    master_db = MasterDatabase(dsn=dsn)
    await master_db.init()
    logger.info("✅ MasterDatabase инициализирована")

    # Инициализируем MasterBot, передавая уже готовую БД
    master_bot = MasterBot(
        token=MASTER_BOT_TOKEN,
        webhook_domain=WEBHOOK_DOMAIN,
        db=master_db,
    )

    # Создаём FastAPI приложение Mini App,
    # передаём и master_db, и master_bot
    app = create_miniapp_app(
        master_db=master_db,
        master_bot_instance=master_bot,
        bot_token=MASTER_BOT_TOKEN,
        webhook_domain=WEBHOOK_DOMAIN,
        debug=DEBUG,
    )

    logger.info("🚀 Mini App API запускается на 0.0.0.0:8001")

    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=8001,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Mini App API остановлена")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        sys.exit(1)
