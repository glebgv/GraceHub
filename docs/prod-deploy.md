# Продакшен‑деплой через systemd

## Первичная настройка и деплой

./scripts/launch.sh prod


## Управление сервисами

systemctl status gracehub-master gracehub-api gracehub-frontend
systemctl restart gracehub-master gracehub-api gracehub-frontend
systemctl stop gracehub-frontend


