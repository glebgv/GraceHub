#!/bin/bash
set -e

echo "🚀 GraceHub Platform..."

ROOT_DIR="/root/gracehub"
FRONTEND_DIR="$ROOT_DIR/frontend/miniapp_frontend"
VENV_DIR="$ROOT_DIR/venv"

MASTER_SERVICE="gracehub-master.service"
API_SERVICE="gracehub-api.service"
FRONT_SERVICE="gracehub-frontend.service"

mkdir -p "$ROOT_DIR/data" "$ROOT_DIR/logs" "$ROOT_DIR/data/instances" "$ROOT_DIR/ssl"

cd "$ROOT_DIR"

# Проверка env
if [ -z "$MASTER_BOT_TOKEN" ]; then
    echo "❌ MASTER_BOT_TOKEN not set"
    exit 1
fi

if [ -z "$WEBHOOK_DOMAIN" ]; then
    echo "❌ WEBHOOK_DOMAIN not set"
    exit 1
fi

echo "✅ Configuration OK"

MODE="$1"
DETACH="$2"

run_dev() {
    echo "🔧 Starting in development mode..."
    export PYTHONPATH="$ROOT_DIR/src"

    source "$VENV_DIR/bin/activate"
    pip install -r requirements.txt

    # master bot
    nohup python src/master_bot/main.py >> logs/masterbot.log 2>&1 &

    # api backend
    nohup python src/master_bot/api_server.py >> logs/api_server.log 2>&1 &

    # frontend
    cd "$FRONTEND_DIR"
    npm install
    nohup npm run dev -- --host 0.0.0.0 >> "$ROOT_DIR/logs/frontend-dev.log" 2>&1 &

    echo "✅ Dev processes started (master, api, frontend)"

    if [ "$DETACH" != "--detach" ]; then
        echo "ℹ️  Press Ctrl+C to stop tailing logs"
        tail -F "$ROOT_DIR/logs/masterbot.log" \
               "$ROOT_DIR/logs/api_server.log" \
               "$ROOT_DIR/logs/frontend-dev.log"
    fi
}

create_systemd_units() {
    echo "📝 Creating systemd units..."

    cat >/etc/systemd/system/$MASTER_SERVICE <<EOF
[Unit]
Description=GraceHub Master Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
Environment=PYTHONPATH=$ROOT_DIR/src
Environment=MASTER_BOT_TOKEN=$MASTER_BOT_TOKEN
Environment=WEBHOOK_DOMAIN=$WEBHOOK_DOMAIN
ExecStart=$VENV_DIR/bin/python src/master_bot/main.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    cat >/etc/systemd/system/$API_SERVICE <<EOF
[Unit]
Description=GraceHub API Server
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
Environment=PYTHONPATH=$ROOT_DIR/src
Environment=MASTER_BOT_TOKEN=$MASTER_BOT_TOKEN
Environment=WEBHOOK_DOMAIN=$WEBHOOK_DOMAIN
ExecStart=$VENV_DIR/bin/python src/master_bot/api_server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    cat >/etc/systemd/system/$FRONT_SERVICE <<EOF
[Unit]
Description=GraceHub Frontend Dev Server
After=network.target

[Service]
Type=simple
WorkingDirectory=$FRONTEND_DIR
ExecStart=/usr/bin/npm run dev -- --host 0.0.0.0
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
}

run_prod() {
    echo "🏭 Setting up production services..."

    source "$VENV_DIR/bin/activate"
    pip install -r requirements.txt

    cd "$FRONTEND_DIR"
    npm install

    create_systemd_units

    systemctl enable $MASTER_SERVICE $API_SERVICE $FRONT_SERVICE
    systemctl restart $MASTER_SERVICE $API_SERVICE $FRONT_SERVICE

    systemctl --no-pager status $MASTER_SERVICE $API_SERVICE $FRONT_SERVICE
}

case "$MODE" in
  dev)
    run_dev
    ;;
  prod)
    run_prod
    ;;
  *)
    echo "Usage: $0 [dev|prod] [--detach]"
    echo ""
    echo "Examples:"
    echo "  $0 dev"
    echo "  $0 dev --detach"
    echo "  $0 prod"
    ;;
esac

