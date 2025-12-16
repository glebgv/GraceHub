#!/bin/bash
set -e

echo "🚀 GraceHub Platform..."

# Абсолютный путь к директории скрипта (gracehub/scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Корень репозитория (gracehub)
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

FRONTEND_DIR="$ROOT_DIR/frontend/miniapp_frontend"
VENV_DIR="$ROOT_DIR/venv"
ENV_FILE="$ROOT_DIR/.env"

MASTER_SERVICE="gracehub-master.service"
API_SERVICE="gracehub-api.service"

mkdir -p "$ROOT_DIR/data" "$ROOT_DIR/logs" "$ROOT_DIR/data/instances" "$ROOT_DIR/ssl"

cd "$ROOT_DIR"

# --- аккуратный stop в одну "динамическую" строку и строго один раз ---
_cleanup_done=0
cleanup() {
    # защита от повторного вызова (INT + EXIT, повторные сигналы, killpg и т.п.)
    if [ "${_cleanup_done}" -eq 1 ]; then
        return 0
    fi
    _cleanup_done=1

    # снимаем трапы, чтобы не было рекурсии/повторов
    trap - EXIT INT TERM

    # "динамическая" строка: \r (carriage return) + очистка до конца строки \033[K
    # это убирает спам и перерисовывает строку на месте [web:22][web:25]
    printf "\r\033[K🔻 Stopping GraceHub dev/prod stack..."
    kill -- -$$ 2>/dev/null || true
    printf "\r\033[K✅ Stopped.\n"
}

trap cleanup EXIT INT TERM

load_env() {
    if [ ! -f "$ENV_FILE" ]; then
        echo "❌ .env file not found at: $ENV_FILE"
        echo "   Create .env with at least: MASTER_BOT_TOKEN, WEBHOOK_DOMAIN, DATABASE_URL"
        exit 1
    fi

    # Загружаем пары KEY=VALUE, игнорируя комментарии и пустые строки
    set -a
    # shellcheck disable=SC1090
    source <(grep -Ev '^\s*#' "$ENV_FILE" | grep -E '^\s*[A-Za-z_][A-Za-z0-9_]*=' || true)
    set +a
}

check_required_env() {
    local missing=0

    for var in MASTER_BOT_TOKEN WEBHOOK_DOMAIN DATABASE_URL; do
        if [ -z "${!var:-}" ]; then
            echo "❌ Required variable $var is not set or empty (check $ENV_FILE)"
            missing=1
        fi
    done

    if [ "$missing" -ne 0 ]; then
        echo "   Make sure .env contains non-empty values for:"
        echo "   MASTER_BOT_TOKEN, WEBHOOK_DOMAIN, DATABASE_URL"
        exit 1
    fi
}

# --- загружаем и проверяем .env при любом запуске ---
load_env
check_required_env

echo "✅ .env loaded and required variables are set"
echo "✅ Configuration OK"

MODE="$1"
DETACH="$2"

run_dev() {
    echo "🔧 Starting in development mode..."
    export PYTHONPATH="$ROOT_DIR/src"

    # активируем venv относительно корня
    if [ ! -d "$VENV_DIR" ]; then
        echo "❌ venv not found at $VENV_DIR"
        exit 1
    fi

    source "$VENV_DIR/bin/activate"

    REQ_FILE="$ROOT_DIR/requirements.txt"
    REQ_HASH_FILE="$ROOT_DIR/.requirements.hash"

    CUR_HASH="$(md5sum "$REQ_FILE" | cut -d' ' -f1)"

    if [ ! -f "$REQ_HASH_FILE" ] || [ "$CUR_HASH" != "$(cat "$REQ_HASH_FILE")" ]; then
        echo "📦 Installing / updating Python deps (requirements changed)..."
        pip install -r "$REQ_FILE"
        echo "$CUR_HASH" > "$REQ_HASH_FILE"
    else
        echo "✅ Python deps already up to date"
    fi

    # master bot (без nohup, обычный фон)
    python src/master_bot/main.py >> logs/masterbot.log 2>&1 &

    # api backend
    python src/master_bot/api_server.py >> logs/api_server.log 2>&1 &

    # frontend dev server
    cd "$FRONTEND_DIR"
    if ! command -v npm >/dev/null 2>&1; then
        echo "❌ npm not found in PATH. Install Node.js/npm first."
        exit 1
    fi

    npm install
    npm run dev -- --host 0.0.0.0 >> "$ROOT_DIR/logs/frontend-dev.log" 2>&1 &

    echo "✅ Dev processes started (master, api, frontend)"

    if [ "$DETACH" != "--detach" ]; then
        echo "ℹ️  Press Ctrl+C to stop tailing logs (and stop all dev processes)"
        tail -F "$ROOT_DIR/logs/masterbot.log" \
               "$ROOT_DIR/logs/api_server.log" \
               "$ROOT_DIR/logs/frontend-dev.log"
    fi
}

create_systemd_units() {
    echo "📝 Creating systemd units for backend..."

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
ExecStart=$VENV_DIR/bin/python $ROOT_DIR/src/master_bot/main.py
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
ExecStart=$VENV_DIR/bin/python $ROOT_DIR/src/master_bot/api_server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
}

run_prod() {
    echo "🏭 Setting up production (backend + frontend build + nginx checks)..."

    # --- backend deps ---
    if [ ! -d "$VENV_DIR" ]; then
        echo "❌ venv not found at $VENV_DIR"
        exit 1
    fi

    source "$VENV_DIR/bin/activate"
    pip install -r "$ROOT_DIR/requirements.txt"

    # --- frontend build ---
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo "❌ FRONTEND_DIR not found: $FRONTEND_DIR"
        exit 1
    fi

    cd "$FRONTEND_DIR"

    if ! command -v npm >/dev/null 2>&1; then
        echo "❌ npm not found in PATH. Install Node.js/npm first."
        exit 1
    fi

    echo "📦 Installing frontend deps..."
    if [ -f package-lock.json ]; then
        npm ci
    else
        npm install
    fi

    echo "🏗  Building frontend (npm run build)..."
    npm run build

    # --- deploy static build ---
    BUILD_DIR="$FRONTEND_DIR/dist"   # для Vite; замени на build при CRA
    TARGET_DIR="/var/www/gracehub-frontend"

    if [ ! -d "$BUILD_DIR" ]; then
        echo "❌ Build directory not found: $BUILD_DIR"
        exit 1
    fi

    echo "📂 Deploying static files to $TARGET_DIR ..."
    mkdir -p "$TARGET_DIR"
    rsync -a --delete "$BUILD_DIR"/ "$TARGET_DIR"/

    # --- nginx checks ---
    echo "🔍 Checking nginx installation..."
    if ! command -v nginx >/dev/null 2>&1; then
        echo "❌ nginx is not installed (nginx binary not found in PATH)."
        echo "   Install nginx (e.g. apt install nginx) and configure it to serve $TARGET_DIR."
        exit 1
    fi

    echo "🔍 Checking nginx service status..."
    if ! systemctl -q is-enabled nginx >/dev/null 2>&1; then
        echo "⚠️  nginx service is not enabled (will not start on boot)."
    fi

    if ! systemctl -q is-active nginx >/dev/null 2>&1; then
        echo "⚠️  nginx service is not active. Trying to start..."
        if ! systemctl start nginx; then
            echo "❌ Failed to start nginx service. Check: systemctl status nginx"
            exit 1
        fi
    fi

    echo "🔍 Testing nginx configuration (nginx -t)..."
    if ! nginx -t >/dev/null 2>&1; then
        echo "❌ nginx configuration test failed. Fix config and run again."
        nginx -t  # показать ошибки пользователю
        exit 1
    fi

    # --- check backend listener on 8001 (или поменяй на свой) ---
    BACKEND_PORT=8001
    echo "🔍 Checking backend listener on port $BACKEND_PORT ..."
    if ! ss -tuln | grep -q ":$BACKEND_PORT"; then
        echo "⚠️  No process is listening on port $BACKEND_PORT."
        echo "   Make sure your backend (api_server) is configured to listen on this port and nginx reverse-proxy points to it."
    fi

    # --- systemd units for backend only ---
    create_systemd_units

    echo "🔁 Enabling & restarting backend services..."
    systemctl enable $MASTER_SERVICE $API_SERVICE
    systemctl restart $MASTER_SERVICE $API_SERVICE

    systemctl --no-pager status $MASTER_SERVICE $API_SERVICE
    echo "✅ Production setup finished."
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

