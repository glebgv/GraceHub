# Логи и мониторинг

## В режиме разработки

Логи пишутся в каталог `logs/`:

tail -f logs/masterbot.log
tail -f logs/api_server.log
tail -f logs/frontend-dev.log

## В продакшене

Логи сервисов доступны через `journalctl`:

journalctl -u gracehub-master -n 50 --no-pager
journalctl -u gracehub-api -n 50 --no-pager
journalctl -u gracehub-frontend -n 50 --no-pager
