# src/shared/settings.py
import os
from pathlib import Path

BASE_DIR = Path(os.getenv("APP_BASE_DIR", "/app"))
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
LOGS_DIR = Path(os.getenv("LOGS_DIR", str(BASE_DIR / "logs")))
CONFIG_DIR = Path(os.getenv("CONFIG_DIR", str(BASE_DIR / "config")))

# === БАЗЫ ДАННЫХ ===
MASTER_DB_PATH = Path(
    os.getenv("MASTER_DB_PATH", os.getenv("MASTERDBPATH", str(DATA_DIR / "master.db")))
)
WORKER_DB_DIR = Path(
    os.getenv("WORKER_DB_DIR", os.getenv("WORKERDBDIR", str(DATA_DIR / "instances")))
)

# === КЛЮЧИ ===
ENCRYPTION_KEY_FILE = Path(
    os.getenv(
        "ENCRYPTION_KEY_FILE",
        os.getenv("ENCRYPTIONKEYFILE", str(DATA_DIR / "master_key.key")),
    )
)

# === ЛОГИРОВАНИЕ ===
LOG_LEVEL = os.getenv("LOG_LEVEL", os.getenv("LOGLEVEL", "INFO"))
MASTER_LOG_FILE = Path(os.getenv("MASTER_LOG_FILE", str(LOGS_DIR / "master_bot.log")))
WORKER_LOG_FILE = Path(os.getenv("WORKER_LOG_FILE", str(LOGS_DIR / "worker.log")))

# === МАСТЕР-БОТ ===
MASTER_BOT_TOKEN = os.getenv("MASTER_BOT_TOKEN", "")
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", "")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", os.getenv("WEBHOOKPORT", "9443")))

# === WORKER (ЭТО САМОЕ ВАЖНОЕ ДЛЯ ТЕКУЩЕЙ ОШИБКИ) ===
# Эти переменные использует worker/main.py
WORKER_INSTANCE_ID = os.getenv("WORKER_INSTANCE_ID")
WORKER_TOKEN = os.getenv("WORKER_TOKEN")

# === ОБЩИЕ НАСТРОЙКИ ===
AUTO_CLOSE_HOURS = int(os.getenv("AUTO_CLOSE_HOURS", "12"))
GLOBAL_RATE_LIMIT = int(os.getenv("GLOBAL_RATE_LIMIT", "30"))
CHAT_RATE_LIMIT = int(os.getenv("CHAT_RATE_LIMIT", "20"))
MAX_INSTANCES_PER_USER = int(os.getenv("MAX_INSTANCES_PER_USER", "5"))

SINGLE_TENANT_OWNER_ONLY = os.getenv("GRACEHUB_SINGLE_TENANT_OWNER_ONLY", "0") == "1"
OWNER_TELEGRAM_ID = int(os.getenv("GRACEHUB_OWNER_TELEGRAM_ID", "0")) or None
