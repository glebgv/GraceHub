# GraceHub Platform

Полнофункциональная платформа для управления Telegram‑ботами с поддержкой инстансов, билинга и веб‑панели.

## Технический стек

- **Backend**: Python (FastAPI, Hypercorn)
- **Frontend**: React 19 + TypeScript + Vite
- **Управление ботами**: Telegram Bot API
- **БД**: PostgreSQL
- **Прокси**: Nginx

## Структура проекта

```
gracehub/
├── src/
│   └── master_bot/
│       ├── main.py           # Точка входа мастер‑бота
│       ├── api_server.py     # REST API сервер
│       └── worker/           # Воркеры для инстансов
├── frontend/miniapp_frontend/ # React приложение
├── config/                    # Конфигурационные файлы
├── scripts/
│   └── launch.sh             # Скрипт запуска
└── .env                       # Переменные окружения
```

## Подготовка окружения

1. Перейдите в каталог проекта:
   ```bash
   cd /root/gracehub
   ```

2. Создайте файл окружения и заполните его:
   ```bash
   cp .env-example .env
   nano .env
   ```

3. Подгрузите переменные окружения:
   ```bash
   source .env
   ```

4. При необходимости создайте виртуальное окружение:
   ```bash
   python3 -m venv venv
   ```

## Запуск для разработки

Запуск трёх процессов (мастер‑бот, API, frontend):

- Обычный режим (с логами в терминале):
  ```bash
  ./scripts/launch.sh dev
  ```

- Фоновый режим:
  ```bash
  ./scripts/launch.sh dev --detach
  ```

## Продакшен‑деплой через systemd

Первичная настройка и деплой:

```bash
./scripts/launch.sh prod
```

После этого управление сервисами через systemd:

```bash
systemctl status gracehub-master gracehub-api gracehub-frontend
systemctl restart gracehub-master gracehub-api gracehub-frontend
systemctl stop gracehub-frontend
```

## Логи и мониторинг

### Для dev режима

Логи находятся в каталоге `logs/`:
```bash
tail -f logs/masterbot.log
tail -f logs/api_server.log
tail -f logs/frontend-dev.log
```

### Для prod режима

Просмотр логов systemd:
```bash
journalctl -u gracehub-master -n 50 --no-pager
journalctl -u gracehub-api -n 50 --no-pager
journalctl -u gracehub-frontend -n 50 --no-pager
```

## Требования

- Python 3.8+
- Node.js 20+
- PostgreSQL 12+
- Nginx (опционально)

## Лицензия

MIT
