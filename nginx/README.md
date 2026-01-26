# GraceHub Nginx Конфигурации

Эта директория содержит примеры конфигурационных файлов для Nginx, используемых в проекте GraceHub.

## Файлы:

- **dev-example.conf**  
  Конфигурация для **разработки**.  
  - Проксирует frontend на Vite dev-сервер (127.0.0.1:5173) с поддержкой HMR (Hot Module Replacement).  
  - Отключено кэширование для удобства разработки.  
  - Подходит для локальной отладки в реальном времени.

- **prd-example.conf**  
  Конфигурация для **продакшена**.  
  - Обслуживает статические файлы frontend напрямую (из `/var/www/gracehub/frontend/dist`).  
  - Включено кэширование статики (CSS, JS, изображения и шрифты на 30 дней).  
  - Подходит для production-деплоя с высокой производительностью.

## Как использовать:

1. Выберите нужный конфиг в зависимости от окружения.  
2. Скопируйте файл в `/etc/nginx/sites-available/` или `/etc/nginx/conf.d/`.  
3. Создайте симлинк в `sites-enabled/`:  
   ```bash
   ln -s /etc/nginx/sites-available/prd-example.conf /etc/nginx/sites-enabled/
   ```
4. Замените you-domain.ru на ваш домен.
5. Убедитесь, что сертификаты Let’s Encrypt установлены (через Certbot), и укажите правильные пути к SSL сертификатам в конфигурационном файле (например, /etc/letsencrypt/live/you-domain.ru/fullchain.pem и /etc/letsencrypt/live/you-domain.ru/privkey.pem).
6. Перезапустите Nginx:
   ```bash
   nginx -t && systemctl reload nginx
   ```

