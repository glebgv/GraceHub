# src/shared/billing_cron.py
import asyncio
import logging
import os

import aiohttp

from .database import MasterDatabase
from . import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

MASTER_BOT_TOKEN = os.getenv("MASTER_BOT_TOKEN")
BOT_API_URL = f"https://api.telegram.org/bot{MASTER_BOT_TOKEN}"

SQL_UPDATE_BILLING = """
UPDATE instance_billing
SET
  days_left = GREATEST(
    0,
    CAST(EXTRACT(EPOCH FROM (period_end - NOW())) / 86400 AS INTEGER)
  ),
  over_limit = (tickets_used >= tickets_limit),
  service_paused = (
    NOW() > period_end
    OR (tickets_used >= tickets_limit)
  ),
  updated_at = NOW()
;
"""

# инстансы, у которых осталось ровно 7 дней
SQL_GET_EXPIRING_7_DAYS = """
SELECT ib.instance_id,
       ib.period_end,
       ib.days_left,
       ib.tickets_used,
       ib.tickets_limit,
       bi.owner_user_id,
       bi.admin_private_chat_id,
       bi.bot_username
FROM instance_billing ib
JOIN bot_instances bi ON bi.instance_id = ib.instance_id
WHERE ib.service_paused = FALSE
  AND ib.days_left = 7;
"""

# инстансы, которые недавно ушли в паузу
SQL_GET_JUST_PAUSED = """
SELECT ib.instance_id,
       ib.period_end,
       ib.days_left,
       ib.tickets_used,
       ib.tickets_limit,
       ib.over_limit,
       bi.owner_user_id,
       bi.admin_private_chat_id,
       bi.bot_username
FROM instance_billing ib
JOIN bot_instances bi ON bi.instance_id = ib.instance_id
WHERE ib.service_paused = TRUE
  AND ib.updated_at >= (NOW() - INTERVAL '1 day');
"""


async def send_telegram_message(chat_id: int, text: str) -> None:
    if not MASTER_BOT_TOKEN:
        logger.warning("MASTER_BOT_TOKEN not set, skip telegram notifications")
        return
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{BOT_API_URL}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            ) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    logger.error("sendMessage failed: %s", data)
        except Exception as e:
            logger.exception("Failed to send telegram message: %s", e)


async def notify_expiring(db: MasterDatabase):
    rows = await db.fetchall(SQL_GET_EXPIRING_7_DAYS)
    if not rows:
        return

    logger.info("Found %d instances expiring in 7 days", len(rows))

    for r in rows:
        owner_id = r["owner_user_id"]
        admin_chat = r["admin_private_chat_id"]
        bot_username = r["bot_username"]
        days_left = r["days_left"]

        if not owner_id and not admin_chat:
            continue

        text = (
            f"🔔 <b>Напоминание по тарифу</b>\n\n"
            f"Для инстанса @{bot_username} осталось {days_left} дней до окончания периода.\n"
            f"Продлите тариф, чтобы бот продолжил работать без ограничений."
        )

        targets = set()
        if owner_id:
            targets.add(owner_id)
        if admin_chat:
            targets.add(admin_chat)

        for chat_id in targets:
            await send_telegram_message(chat_id, text)


async def notify_paused(db: MasterDatabase):
    rows = await db.fetchall(SQL_GET_JUST_PAUSED)
    if not rows:
        return

    logger.info("Found %d instances just paused", len(rows))

    for r in rows:
        owner_id = r["owner_user_id"]
        admin_chat = r["admin_private_chat_id"]
        bot_username = r["bot_username"]
        over_limit = r["over_limit"]

        if not owner_id and not admin_chat:
            continue

        if over_limit:
            reason = "превышен лимит тикетов"
        else:
            reason = "истёк срок действия тарифа"

        text = (
            f"⛔️ <b>Тариф приостановлен</b>\n\n"
            f"Обслуживание инстанса @{bot_username} приостановлено: {reason}.\n"
            f"Продлите тариф или увеличьте лимит, чтобы бот возобновил работу."
        )

        targets = set()
        if owner_id:
            targets.add(owner_id)
        if admin_chat:
            targets.add(admin_chat)

        for chat_id in targets:
            await send_telegram_message(chat_id, text)


async def main():
    # В single-tenant режиме биллинг и уведомления не нужны
    if settings.SINGLE_TENANT_OWNER_ONLY:
        logger.info("Single-tenant owner-only mode: skip billing cron")
        return

    db = MasterDatabase()
    await db.init()

    # 1) пересчитать days_left / over_limit / service_paused
    await db.execute(SQL_UPDATE_BILLING)
    logger.info("Billing flags updated")

    # 2) уведомления
    await notify_expiring(db)
    await notify_paused(db)


if __name__ == "__main__":
    asyncio.run(main())

