#!/bin/bash

# GraceHub Platform Launch Script

set -e

echo "🚀 Starting GraceHub Platform..."

# Create directories
mkdir -p data logs data/instances ssl

# Check if config files exist
if [ ! -f "config/master_local.py" ]; then
    echo "⚠️  Creating config/master_local.py from template"
    cp config/master.py config/master_local.py
    echo "Please edit config/master_local.py with your settings"
fi

if [ ! -f "config/worker_local.py" ]; then
    echo "⚠️  Creating config/worker_local.py from template"  
    cp config/worker.py config/worker_local.py
fi

# Check environment variables
if [ -z "$MASTER_BOT_TOKEN" ]; then
    echo "❌ MASTER_BOT_TOKEN environment variable not set"
    echo "Please set your master bot token:"
    echo "export MASTER_BOT_TOKEN='your_bot_token'"
    exit 1
fi

if [ -z "$WEBHOOK_DOMAIN" ]; then
    echo "❌ WEBHOOK_DOMAIN environment variable not set"
    echo "Please set your domain:"
    echo "export WEBHOOK_DOMAIN='your-domain.com'"
    exit 1
fi

echo "✅ Configuration OK"

# Choose launch method
if [ "$1" == "docker" ]; then
    echo "🐳 Starting with Docker Compose..."
    docker-compose up --build
elif [ "$1" == "dev" ]; then
    echo "🔧 Starting in development mode..."
    export PYTHONPATH="$(pwd)/src"

    # Установка зависимостей
    pip install -r requirements.txt

    # ЗАПУСКАЕМ ТОЛЬКО МАСТЕР-БОТ! Worker-ы он создаст сам!
    python src/master_bot/main.py
else
    echo "Usage: $0 [docker|dev]"
    echo ""
    echo "  docker  - Start with Docker Compose (recommended for production)"
    echo "  dev     - Start in development mode (local Python)"
    echo ""
    echo "Example:"
    echo "  export MASTER_BOT_TOKEN='123456:ABC-DEF...'"
    echo "  export WEBHOOK_DOMAIN='yourdomain.com'"  
    echo "  $0 docker"
fi

