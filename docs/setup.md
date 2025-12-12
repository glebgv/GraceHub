# Подготовка окружения
cd /root/gracehub
cp .env-example .env
nano .env
source .env
python3 -m venv venv
source venv/bin/activate

Переменные окружения задают параметры подключения к БД, токены ботов и режим работы инстанса.
