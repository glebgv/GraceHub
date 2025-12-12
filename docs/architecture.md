# Архитектура и стек

## Технический стек

- Backend: Python (FastAPI, Hypercorn)  
- Frontend: React 19, TypeScript, Vite  
- Управление ботами: Telegram Bot API  
- База данных: PostgreSQL 15+  
- Прокси: Nginx  
- Версия Python: 3.11+

## Структура проекта

gracehub/
├── src/
│ └── master_bot/
│ ├── main.py # Точка входа мастер‑бота
│ ├── api_server.py # REST API сервер
│ └── worker/ # Воркеры инстансов
├── frontend/miniapp_frontend/ # React‑приложение
├── config/ # Конфигурационные файлы
├── scripts/
│ └── launch.sh # Скрипт запуска
├── logs/ # Логи
└── .env # Переменные окружения
