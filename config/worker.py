# Worker Configuration
# Copy this file to config/worker_local.py and customize

import os

# Database configuration
WORKER_DB_DIR = os.getenv("WORKER_DB_DIR", "data/instances/")

# Rate limiting
BOT_RATE_LIMIT = int(os.getenv("BOT_RATE_LIMIT", "30"))      # requests per second per bot
CHAT_RATE_LIMIT = int(os.getenv("CHAT_RATE_LIMIT", "20"))    # requests per chat per 40 seconds

# Auto-close tickets after N hours of inactivity
AUTO_CLOSE_HOURS = int(os.getenv("AUTO_CLOSE_HOURS", "12"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/worker.log")

# Feature flags
ENABLE_METRICS = os.getenv("ENABLE_METRICS", "false").lower() == "true"
METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))

