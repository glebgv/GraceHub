# Master Bot Configuration
# Copy this file to config/master_local.py and customize

import os

# Master bot token from BotFather
MASTER_BOT_TOKEN = os.getenv("MASTER_BOT_TOKEN", "YOUR_MASTER_BOT_TOKEN")

# Webhook configuration
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", "your-domain.com")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))
WEBHOOK_USE_HTTPS = os.getenv("WEBHOOK_USE_HTTPS", "true").lower() == "true"

# Database configuration
#MASTER_DB_PATH = os.getenv("MASTER_DB_PATH", "data/master.db")

# Security
ENCRYPTION_KEY_FILE = os.getenv("ENCRYPTION_KEY_FILE", "data/master_key.key")

# Rate limiting
GLOBAL_RATE_LIMIT = int(os.getenv("GLOBAL_RATE_LIMIT", "30"))  # requests per second
CHAT_RATE_LIMIT = int(os.getenv("CHAT_RATE_LIMIT", "20"))     # requests per chat per 40 seconds

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/master.log")

# Instance limits per user
MAX_INSTANCES_PER_USER = int(os.getenv("MAX_INSTANCES_PER_USER", "5"))

# Health check
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "60"))  # seconds

