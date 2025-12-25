# src/shared/settings.py
import os
from pathlib import Path
from urllib.parse import quote


BASE_DIR = Path(os.getenv("APP_BASE_DIR", "/app"))
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
LOGS_DIR = Path(os.getenv("LOGS_DIR", str(BASE_DIR / "logs")))
CONFIG_DIR = Path(os.getenv("CONFIG_DIR", str(BASE_DIR / "config")))

# === PostgreSQL ===
DB_USER = os.getenv("DB_USER", "gh_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "gracehub")

# Автоматическое URL-кодирование пароля для безопасности
_db_password_encoded = quote(DB_PASSWORD, safe='')

# Полная DATABASE_URL (используется MasterDatabase)
DATABASE_URL = f"postgresql://{DB_USER}:{_db_password_encoded}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Альтернатива: асинхронный драйвер для FastAPI (если понадобится)
DATABASE_URL_ASYNC = f"postgresql+asyncpg://{DB_USER}:{_db_password_encoded}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


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


# === WORKER ===
WORKER_INSTANCE_ID = os.getenv("WORKER_INSTANCE_ID")
WORKER_TOKEN = os.getenv("WORKER_TOKEN")


# === ОБЩИЕ НАСТРОЙКИ ===
AUTO_CLOSE_HOURS = int(os.getenv("AUTO_CLOSE_HOURS", "12"))
GLOBAL_RATE_LIMIT = int(os.getenv("GLOBAL_RATE_LIMIT", "30"))
CHAT_RATE_LIMIT = int(os.getenv("CHAT_RATE_LIMIT", "20"))
MAX_INSTANCES_PER_USER = int(os.getenv("MAX_INSTANCES_PER_USER", "5"))

WORKER_MONITOR_INTERVAL = int(os.getenv("WORKER_MONITOR_INTERVAL", "600"))
BILLING_CRON_INTERVAL = int(os.getenv("BILLING_CRON_INTERVAL", "3600"))


WORKER_MAX_FILE_MB: int = int(os.getenv("WORKER_MAX_FILE_MB", 50))

#STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")  # sk_test_...
#STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")  # pk_test_...
#STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")  # whsec_... (для валидации сигнатур)
#STRIPE_CURRENCY = os.getenv("STRIPE_CURRENCY", "usd")  # или "rub"


ANTIFLOOD_MAX_USER_MESSAGES_PER_MINUTE = int(os.getenv("ANTIFLOOD_MAX_USER_MESSAGES_PER_MINUTE", "30"))

# === ADMIN / ROLES ===
# Пример env: GRACEHUB_SUPERADMIN_TELEGRAM_IDS="123456789,987654321"
_SUPERADMIN_RAW = os.getenv("GRACEHUB_SUPERADMIN_TELEGRAM_IDS", "").strip()

def _parse_int_list_csv(value: str) -> list[int]:
    if not value:
        return []
    out: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            # игнорируем мусор типа "abc"
            continue
    return out

SUPERADMIN_TELEGRAM_IDS: list[int] = _parse_int_list_csv(_SUPERADMIN_RAW)