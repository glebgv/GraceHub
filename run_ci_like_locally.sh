#!/usr/bin/env bash
set -euo pipefail

# 1) Поднимаем временный Postgres
docker rm -f gh-ci-postgres >/dev/null 2>&1 || true
docker run -d --name gh-ci-postgres \
  -e POSTGRES_DB=gracehub \
  -e POSTGRES_USER=gh_user \
  -e POSTGRES_PASSWORD=postgres \
  -p 127.0.0.1:5432:5432 \
  postgres:16-alpine

# Ждём готовности БД
for i in $(seq 1 30); do
  docker exec gh-ci-postgres pg_isready -U gh_user -d gracehub && break
  sleep 1
done

# 2) Стартуем API (CI режим: Telegram не нужен)
export ENV=ci
export CI_TEST_LOGIN_SECRET="local-ci-secret-change-me"
export DATABASE_URL="postgresql://gh_user:postgres@127.0.0.1:5432/gracehub"

nohup python src/master_bot/api_server.py > api.log 2>&1 &
API_PID=$!

# 3) Ждём API
for i in $(seq 1 60); do
  curl -fsS http://127.0.0.1:8001/openapi.json >/dev/null && break
  sleep 1
done

# 4) Получаем токен и запускаем schemathesis
TOKEN=$(
  curl -fsS -X POST http://127.0.0.1:8001/__test__/login \
    -H 'Content-Type: application/json' \
    -d "{\"secret\":\"$CI_TEST_LOGIN_SECRET\"}" \
  | python -c "import sys,json; print(json.load(sys.stdin)['token'])"
)
export API_TOKEN="$TOKEN"

schemathesis run http://127.0.0.1:8001/openapi.json

# 5) Уборка
kill "$API_PID" || true
docker rm -f gh-ci-postgres >/dev/null 2>&1 || true

