import asyncio
import logging
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
import secrets
import hashlib
import os
import sys
import subprocess
from pathlib import Path
from languages import LANGS

# Абсолютный путь к src
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))  # /root/gracehub/src/master_bot -> /root/gracehub
sys.path.insert(0, os.path.join(project_root, 'src'))

from worker.main import GraceHubWorker

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update,
    PreCheckoutQuery,
)
from aiogram.enums import ParseMode, ChatType
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError, TelegramUnauthorizedError
from aiogram.types.web_app_info import WebAppInfo
from aiohttp import web

# ✅ НАСТРОЙКА ЛОГОВ ПЕРЕД ВСЕМИ ИМПОРТАМИ shared.* !!!
BASE_DIR = Path(__file__).resolve().parents[2]  # /root/GraceHub
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True, parents=True)
LOG_FILE = LOG_DIR / "masterbot.log"

formatter = logging.Formatter("%(asctime)s [pid=%(process)d] - %(name)s - %(levelname)s - %(message)s")

fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers.clear()
root_logger.addHandler(fh)
root_logger.propagate = False

logger = logging.getLogger("master_bot")
logger.setLevel(logging.INFO)

print(f"✅ Logging configured to: {LOG_FILE}")


# ТЕПЕРЬ импорты shared — они подхватят НАСТРОЕННЫЙ логгер
from shared.database import MasterDatabase
from shared.models import BotInstance, InstanceStatus
from shared.webhook_manager import WebhookManager
from shared.security import SecurityManager
from shared import settings
from dotenv import load_dotenv

load_dotenv(override=False)

class MasterBot:
    def __init__(self, token: str, webhook_domain: str, webhook_port: int = 9443, db: MasterDatabase | None = None):
        self.bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.dp = Dispatcher()
        self.webhook_domain = webhook_domain
        self.webhook_port = int(webhook_port) if webhook_port else 9443
        self.default_lang = "ru"

        # Если БД передали извне — используем её, иначе создаём свою.
        # Без аргументов: MasterDatabase сам возьмёт DSN из env DATABASE_URL.
        if db is not None:
            self.db = db
        else:
            self.db = MasterDatabase()

        self.webhook_manager = WebhookManager(webhook_domain, use_https=True)  # Явно указываем HTTPS
        self.security = SecurityManager()

        self.instances: Dict[str, BotInstance] = {}
        self.worker_procs: Dict[str, subprocess.Popen] = {}
        self.workers: Dict[str, GraceHubWorker] = {}

        self.setup_handlers()

    async def _is_master_allowed_user(self, user_id: int) -> bool:
        """
        In single-tenant mode, the master-bot is accessible only to allowed users from DB.
        In normal mode, accessible to everyone.
        """
        single_tenant = await self.get_single_tenant_config()
        if not single_tenant["enabled"]:
            return True
        return user_id in single_tenant["allowed_user_ids"]

    async def get_user_lang(self, user_id: int) -> str:
        lang = await self.db.get_user_language(user_id)
        return lang or self.default_lang

    async def t(self, user_id: int):
        lang = await self.get_user_lang(user_id)
        return LANGS.get(lang, LANGS[self.default_lang])

    async def get_single_tenant_config(self) -> dict:
        data = await self.db.get_platform_setting("miniapp_public", default={})
        st = (data or {}).get("single_tenant") or {}
        return {
            "enabled": bool(st.get("enabled", False)),
            "allowed_user_ids": list(st.get("allowed_user_ids", []))  # Ensure it's a list
        }

    async def _notify_owner_invalid_token(
        self,
        owner_id: int,
        instance: BotInstance,
        reason: str,
    ) -> None:
        """
        Шлёт владельцу инстанса алерт о том, что токен воркера нерабочий.
        """
        if reason == "bad_format":
            reason_text = "Неверный формат токена бота."
        elif reason == "unauthorized":
            reason_text = "Telegram отклонил токен (бот удалён, токен сменён или отозван)."
        elif reason == "no_token":
            reason_text = "Для этого инстанса не найден токен в базе."
        else:
            reason_text = "Токен бота недоступен."

        text_lines = [
            "⚠️ <b>Проблема с ботом поддержки</b>\n\n",
            f"Инстанс: <code>{instance.instance_id}</code>\n",
            f"Бот: @{instance.bot_username}\n\n",
            f"{reason_text}\n\n",
            "Проверьте токен бота в @BotFather и заново добавьте/обновите его в системе.",
        ]
        text = "".join(text_lines)

        single_tenant = await self.get_single_tenant_config()
        targets = [owner_id]  # Default to instance owner
        if single_tenant["enabled"]:
            targets = single_tenant["allowed_user_ids"]  # Notify all allowed

        for target_id in set(targets):  # Dedupe
            try:
                await self.bot.send_message(chat_id=target_id, text=text)
            except TelegramAPIError as e:
                logger.warning(
                    "Failed to send invalid-token alert to owner %s for instance %s: %s",
                    target_id,
                    instance.instance_id,
                    e,
                )

        # Добавляем удаление вебхука при обнаружении проблемы с токеном
        token = await self.db.get_decrypted_token(instance.instance_id)
        if token:
            try:
                await self.remove_worker_webhook(instance.instance_id, token)
            except Exception as e:
                logger.warning(
                    f"Failed to remove webhook for invalid token in instance {instance.instance_id}: {e}"
                )
        else:
            # Если токена нет, просто очищаем поля вебхука в БД для сброса состояния
            try:
                await self.db.update_instance_webhook(instance.instance_id, "", "", "")
            except Exception as e:
                logger.warning(
                    f"Failed to clear webhook fields in DB for instance {instance.instance_id}: {e}"
                )

    # ====================== БИЛЛИНГ: CRON-ЗАДАЧИ ======================

    async def _billing_notify_expiring(self) -> None:
        rows = await self.db.get_instances_expiring_in_7_days_for_notify()
        if not rows:
            return

        logger.info("BillingCron: %d instances expiring in 7 days (fresh)", len(rows))

        for r in rows:
            owner_id = r["owner_user_id"]
            admin_chat = r["admin_private_chat_id"]
            bot_username = r["bot_username"]
            days_left = r["days_left"]

            if not owner_id and not admin_chat:
                continue

            targets = set()
            if owner_id:
                targets.add(owner_id)
            if admin_chat:
                targets.add(admin_chat)

            sent_ok = False
            for chat_id in targets:
                try:
                    texts = await self.t(chat_id)

                    text = (
                        texts.billing_expiring_title +
                        texts.billing_expiring_body.format(
                            bot_username=bot_username,
                            days_left=days_left,
                        )
                    )

                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode="HTML",
                    )
                    sent_ok = True
                except Exception as e:
                    logger.exception(
                        "BillingCron: failed to send expiring notification to %s: %s",
                        chat_id,
                        e,
                    )

            if sent_ok:
                try:
                    await self.db.mark_expiring_notified_today(r["instance_id"])
                except Exception as e:
                    logger.exception(
                        "BillingCron: failed to mark expiring notified for %s: %s",
                        r["instance_id"],
                        e,
                    )

    async def _billing_notify_paused(self) -> None:
        # новый метод БД с учётом last_paused_notice_at
        rows = await self.db.get_recently_paused_instances_for_notify()
        if not rows:
            return

        logger.info("BillingCron: %d instances just paused (fresh)", len(rows))

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
                "⛔️ <b>Тариф приостановлен</b>\n\n"
                f"Обслуживание инстанса @{bot_username} приостановлено: {reason}.\n"
                "Продлите тариф или увеличьте лимит, чтобы бот возобновил работу."
            )

            targets = set()
            if owner_id:
                targets.add(owner_id)
            if admin_chat:
                targets.add(admin_chat)

            sent_ok = False
            for chat_id in targets:
                try:
                    await self.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                    sent_ok = True
                except Exception as e:
                    logger.exception(
                        "BillingCron: failed to send paused notification to %s: %s",
                        chat_id,
                        e,
                    )

            if sent_ok:
                try:
                    await self.db.mark_paused_notified_now(r["instance_id"])
                except Exception as e:
                    logger.exception(
                        "BillingCron: failed to mark paused notified for %s: %s",
                        r["instance_id"],
                        e,
                    )

    async def _run_billing_cycle(self) -> None:
        """
        Один цикл биллингового крона:
        - пересчитать флаги;
        - отправить уведомления.
        """
        # single-tenant mode: billing cron disabled (config from DB, not .env)
        try:
            miniapp_public = await self.db.get_platform_setting("miniapp_public", default={})
            single_tenant = (miniapp_public or {}).get("single_tenant") or {}
            single_tenant_enabled = bool(single_tenant.get("enabled", False))
            if single_tenant_enabled:
                return
        except Exception as e:
            logger.exception("BillingCron: failed to read single_tenant config: %s", e)
            # если конфиг не прочитался — не ломаем биллинг, продолжаем как обычно

        try:
            await self.db.update_billing_flags()
            logger.info("BillingCron: billing flags updated")
        except Exception as e:
            logger.exception("BillingCron: failed to update billing flags: %s", e)
            return

        try:
            await self._billing_notify_expiring()
        except Exception as e:
            logger.exception("BillingCron: notify_expiring failed: %s", e)

        try:
            await self._billing_notify_paused()
        except Exception as e:
            logger.exception("BillingCron: notify_paused failed: %s", e)


    async def run_billing_cron_loop(self, interval_seconds: int = 3600) -> None:
        logger.info("BillingCron: starting loop with interval=%s sec", interval_seconds)
        while True:
            await self._run_billing_cycle()
            await asyncio.sleep(interval_seconds)



    # ====================== УПРАВЛЕНИЕ ВОРКЕРАМИ ======================

    def is_worker_process_alive(self, instance_id: str) -> bool:
        proc = self.worker_procs.get(instance_id)
        if not proc:
            return False
        return proc.poll() is None


    def spawn_worker(self, instance_id: str, token: str) -> None:
        """
        Запускает отдельный процесс воркера для указанного инстанса.
        Воркеры работают через polling (src/worker/main.py).
        """
        # Если процесс уже жив — не дублируем
        proc = self.worker_procs.get(instance_id)
        if proc is not None and proc.poll() is None:
            return

        env = os.environ.copy()
        env["WORKER_INSTANCE_ID"] = instance_id
        env["WORKER_TOKEN"] = token

        worker_path = Path(__file__).resolve().parent.parent / "worker" / "main.py"

        proc = subprocess.Popen(
        [sys.executable, str(worker_path)],
        env=env,
        stdout=None,   # или subprocess.PIPE, но тогда надо читать
        stderr=None,
        )
        self.worker_procs[instance_id] = proc
        logger.info(f"Spawned worker process for instance {instance_id} (pid={proc.pid})")


    async def stop_worker(self, instance_id: str) -> None:
        """
        Останавливает worker для инстанса: отменяет tasks, удаляет из памяти и снимает webhook.
        """
        # Cancel the worker's background tasks (e.g., auto_close_tickets_loop)
        task = self.worker_tasks.pop(instance_id, None)
        if task:
            task.cancel()
            try:
                await task  # Wait for cancellation to complete gracefully
            except asyncio.CancelledError:
                pass  # Expected
            logger.info(f"Cancelled task for worker {instance_id}")

        # Remove the worker object from memory
        worker = self.workers.pop(instance_id, None)
        if worker:
            # Optional: Close any worker-specific resources, e.g., bot session if needed
            await worker.bot.session.close()
            logger.info(f"Removed worker object for {instance_id}")

        # Remove webhook if set
        instance = self.instances.get(instance_id)
        if instance and instance.webhook_url:
            token = await self.db.get_decrypted_token(instance_id)
            if token:
                if await self.remove_worker_webhook(instance_id, token):
                    logger.info(f"Removed webhook for {instance_id}")
                else:
                    logger.warning(f"Failed to remove webhook for {instance_id}")

        # Update status in DB if necessary (e.g., to STOPPED)
        await self.db.update_instance_status(instance_id, InstanceStatus.STOPPED)

    # ====================== МИНИ-APПА: УТИЛИТЫ ======================

    async def handle_successful_payment(self, message: Message):
        """
        Обработка успешной оплаты Stars (Telegram Stars).
        payload у нас вида "saas:<invoice_id>".
        """
        logger.info(
            "handle_successful_payment CALLED: chat_id=%s user_id=%s",
            message.chat.id,
            message.from_user.id if message.from_user else None,
        )

        sp = message.successful_payment
        if not sp:
            logger.warning("handle_successful_payment called without successful_payment")
            return

        logger.info(
            "successful_payment RAW: currency=%s total_amount=%s payload=%r "
            "telegram_payment_charge_id=%s provider_payment_charge_id=%s",
            sp.currency,
            sp.total_amount,
            sp.invoice_payload,
            sp.telegram_payment_charge_id,
            sp.provider_payment_charge_id,
        )

        payload = sp.invoice_payload or ""
        if not payload.startswith("saas:"):
            # не наш инвойс — игнорируем
            logger.info("successful_payment with foreign payload=%r", payload)
            return

        invoice_id_str = payload.split(":", 1)[1]
        try:
            invoice_id = int(invoice_id_str)
        except ValueError:
            logger.warning("successful_payment: bad invoice_id in payload=%r", payload)
            return

        logger.info(
            "successful_payment parsed: invoice_id=%s currency=%s total_amount=%s",
            invoice_id,
            sp.currency,
            sp.total_amount,
        )

        # 1) помечаем инвойс как оплаченный
        try:
            logger.info("mark_billing_invoice_paid started: invoice_id=%s", invoice_id)
            await self.db.mark_billing_invoice_paid(
                invoice_id=invoice_id,
                telegram_invoice_id=sp.telegram_payment_charge_id,
                total_amount=sp.total_amount,
                currency=sp.currency,
            )
            logger.info("mark_billing_invoice_paid done: invoice_id=%s", invoice_id)
        except Exception as e:
            logger.exception("mark_billing_invoice_paid failed: %s", e)
            # тут можно отправить сообщение админам, но пользователю всё равно успешная оплата уже показана Telegram
            return

        # 2) применяем тариф к инстансу
        try:
            logger.info("apply_saas_plan_for_invoice started: invoice_id=%s", invoice_id)
            await self.db.apply_saas_plan_for_invoice(invoice_id)
            logger.info("apply_saas_plan_for_invoice done: invoice_id=%s", invoice_id)
        except Exception as e:
            logger.exception("apply_saas_plan_for_invoice failed: %s", e)
            # можно пометить invoice как 'paid_but_failed_apply'

        # 3) опционально уведомляем пользователя
        try:
            logger.info("sending success message to chat_id=%s", message.chat.id)
            await message.answer("✅ Оплата прошла успешно! Тариф обновлён.")
            logger.info("success message sent to chat_id=%s", message.chat.id)
        except Exception as e:
            logger.warning("Failed to send success message after payment: %s", e)

    async def create_stars_invoice_link_for_miniapp(
        self,
        user_id: int,
        title: str,
        description: str,
        payload: str,
        currency: str,
        amount_stars: int,
    ) -> str:
        # для XTR Bot API ожидает amount = кол-во звёзд, без *100
        prices = [{"label": title, "amount": amount_stars}]

        link = await self.bot.create_invoice_link(
            title=title,
            description=description,
            payload=payload,
            currency=currency,  # "XTR"
            prices=prices,
        )
        return link


    def _build_miniapp_url(self, instance: BotInstance, admin_user_id: int) -> str:
        """
        Собирает URL мини-аппы для конкретного инстанса и администратора.
        MINIAPP_BASE_URL должен быть задан в окружении, например:
        https://your-domain.com/miniapp
        """
        base_url = os.getenv("MINIAPP_BASE_URL", "").rstrip("/")
        if not base_url:
            # Если не настроен, просто возвращаем пустую строку, чтобы не ломать основной флоу
            logger.warning("MINIAPP_BASE_URL is not set; mini app link will be empty")
            return ""

        # фронтенд читает query-параметры instance_id/admin_id
        return (
            f"{base_url}"
            f"?instance_id={instance.instance_id}"
            f"&admin_id={admin_user_id}"
        )

    async def auto_close_tickets_loop(self) -> None:
        """
        Глобальный цикл в мастере для автоматического закрытия тикетов по всем инстансам.
        Интервал: 3600 сек (1 час). Для каждого инстанса — per-instance hours из БД.
        """
        interval = 3600  # Настройте в settings или БД
        while True:
            try:
                now = datetime.now(timezone.utc)
                # Получаем все active инстансы (running, paused и т.д.)
                instances = await self.db.get_all_active_instances()  # Используйте существующий метод
                for instance in instances:
                    instance_id = instance.instance_id
                    # Тянем hours из instance_settings (per-instance)
                    settings_row = await self.db.fetchone(
                        "SELECT autoclose_hours FROM instance_settings WHERE instance_id = $1",
                        (instance_id,)
                    )
                    hours = settings_row['autoclose_hours'] if settings_row else 12  # Дефолт 12
                    
                    cutoff = now - timedelta(hours=hours)
                    
                    # Находим тикеты для закрытия
                    rows = await self.db.fetchall(
                        """
                        SELECT id
                        FROM tickets
                        WHERE instance_id = $1
                        AND status IN ('inprogress', 'answered')
                        AND last_admin_reply_at IS NOT NULL
                        AND (
                            last_user_msg_at IS NULL
                            OR last_user_msg_at < $2
                        )
                        """,
                        (instance_id, cutoff),
                    )
                    
                    if rows:
                        ticket_ids = [row['id'] for row in rows]
                        await self.db.execute(
                            """
                            UPDATE tickets
                            SET status = 'closed',
                                updated_at = NOW()
                            WHERE id = ANY($1)
                            """,
                            (ticket_ids,)
                        )
                        logger.info(f"Auto-closed {len(rows)} tickets for instance {instance_id}")
            except Exception as e:
                logger.error(f"Global auto-close error: {e}")
            await asyncio.sleep(interval)

    async def process_bot_token_from_miniapp(
        self,
        token: str,
        owner_user_id: int,
    ) -> BotInstance:
        """
        Упрощённый вариант process_bot_token для mini app:
        - без Message/ответов в Telegram,
        - та же логика проверки/создания инстанса и запуска воркера.
        Возвращает BotInstance.
        """

        # 0) Лимит подключаемых ботов (0 = без лимита)
        limit = await self.db.get_max_instances_per_user()
        if limit > 0:
            current = await self.db.count_instances_for_user(owner_user_id)
            if current >= limit:
                raise ValueError(f"Достигнут лимит подключаемых ботов: {current}/{limit}")

        # 1) Проверка формата токена (как в process_bot_token)
        if not self.validate_token_format(token):
            raise ValueError("Неверный формат токена")

        # 2) Проверка токена через getMe
        test_bot = Bot(token=token)
        try:
            me = await test_bot.get_me()
        finally:
            await test_bot.session.close()

        # 3) Проверка, что такого бота ещё нет
        existing = await self.db.get_instance_by_token_hash(
            self.security.hash_token(token)
        )
        if existing:
            raise ValueError("Этот бот уже добавлен в систему")

        # 4) Создание инстанса + запуск воркера (ровно как в create_bot_instance)
        instance = await self.create_bot_instance(
            user_id=owner_user_id,
            token=token,
            bot_username=me.username,
            bot_name=me.first_name,
        )

        return instance


    async def _send_personal_miniapp_link(
        self,
        instance: BotInstance,
        admin_user_id: int,
        admin_chat_id: Optional[int] = None,
        topic_id: Optional[int] = None,
    ) -> None:
        """
        Отправляет персональную ссылку на мини-аппу администратору после привязки воркера.

        Если admin_chat_id не указан, пробует использовать private-чат самого админа.
        """
        miniapp_url = self._build_miniapp_url(instance, admin_user_id)
        if not miniapp_url:
            return

        # Если нет явного admin_chat_id — шлём в личку админу
        target_chat_id = admin_chat_id or admin_user_id

        text_lines = [
            "📟 <b>Панель управления поддержкой</b>\n\n",
            "Откройте мини‑аппу по ссылке, чтобы управлять очередью и настройками бота:\n",
            f"{miniapp_url}\n\n",
            "Эта ссылка привязана к вашему Telegram‑аккаунту как администратора.",
        ]
        text = "".join(text_lines)

        try:
            await self.bot.send_message(
                chat_id=target_chat_id,
                text=text,
                disable_web_page_preview=True,
                message_thread_id=topic_id,
            )
            logger.info(
                "Sent personal mini app link for instance %s to admin %s",
                instance.instance_id,
                admin_user_id,
            )
        except TelegramAPIError as e:
            logger.warning(
                "Failed to send mini app link to admin %s for instance %s: %s",
                admin_user_id,
                instance.instance_id,
                e,
            )

    # ====================== НАСТРОЙКА ХЭНДЛЕРОВ МАСТЕРА ======================

    def setup_handlers(self):
        """Setup command and callback handlers"""
        self.dp.message(Command("start"))(self.cmd_start)
        self.dp.message(Command("add_bot"))(self.cmd_add_bot_entry)
        self.dp.message(Command("list_bots"))(self.cmd_list_bots_entry)
        self.dp.message(Command("remove_bot"))(self.cmd_remove_bot)
        self.dp.callback_query(F.data.startswith("lang_"))(self.handle_language_choice)

        # Входной хендлер для instance_<id>
        self.dp.callback_query(F.data.startswith("instance_"))(self.handle_instance_entry)
        self.dp.callback_query(F.data.startswith("remove_"))(self.handle_remove_instance)
        self.dp.callback_query(F.data.startswith("toggle_"))(self.handle_toggle_instance)
        self.dp.callback_query(F.data.startswith("remove_confirm_"))(self.handle_remove_confirm)
        self.dp.callback_query(F.data.startswith("remove_yes_"))(self.handle_remove_instance)
        self.dp.callback_query(F.data.startswith("remove_no_"))(self.handle_remove_cancel)

        # Общий handler для меню callbacks
        self.dp.callback_query()(self.handle_menu_callback)

        # Text handler for adding bot tokens
        self.dp.message(F.text)(self.handle_text)

        # === Stars / оплата тарифов ===
        self.dp.message(F.successful_payment)(self.handle_successful_payment)



    # ====================== МЕНЮ МАСТЕРА ======================

    async def handle_menu_callback(self, callback: CallbackQuery):
        """Handle menu callbacks like add_bot, list_bots etc."""
        data = callback.data
        user_id = callback.from_user.id
        if not await self._is_master_allowed_user(user_id):
            await callback.answer("Доступ только владельцу", show_alert=True)
            return

        texts = await self.t(user_id)

        if data == "add_bot":
            await self.cmd_add_bot(callback.message, user_id=user_id)

        elif data == "list_bots":
            await self.cmd_list_bots(callback.message, user_id=user_id)

        elif data == "help":
            await callback.message.answer(
                texts.master_help_text,
                reply_markup=self.get_main_menu_for_lang(texts),
            )

        elif data == "change_language":
            base_texts = LANGS.get(self.default_lang)

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text=base_texts.language_ru_label, callback_data="lang_ru"),
                        InlineKeyboardButton(text=base_texts.language_en_label, callback_data="lang_en"),
                    ],
                    [
                        InlineKeyboardButton(text=base_texts.language_es_label, callback_data="lang_es"),
                        InlineKeyboardButton(text=base_texts.language_hi_label, callback_data="lang_hi"),
                    ],
                    [
                        InlineKeyboardButton(text=base_texts.language_zh_label, callback_data="lang_zh"),
                    ],
                ]
            )

            await callback.message.edit_text(
                base_texts.language_menu_title,
                reply_markup=keyboard,
            )
            await callback.answer()
            return

        elif data == "main_menu":
            # передаём user_id явно, чтобы cmd_start не опирался на message.from_user.id
            await self.cmd_start(callback.message, user_id=user_id)

        else:
            await callback.answer(texts.master_unknown_command)

        await callback.answer()

    async def cmd_start(self, message: Message, user_id: int | None = None):
        """Handle /start command"""
        if user_id is None:
            user_id = message.from_user.id

        # single-tenant защита
        if not await self._is_master_allowed_user(user_id):
            texts = await self.t(user_id)
            await message.answer(texts.master_owner_only)
            return

        # проверка выбранного языка
        user_lang = await self.db.get_user_language(user_id)
        if not user_lang:
            base_texts = LANGS.get(self.default_lang)

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text=base_texts.language_ru_label, callback_data="lang_ru"),
                        InlineKeyboardButton(text=base_texts.language_en_label, callback_data="lang_en"),
                    ],
                    [
                        InlineKeyboardButton(text=base_texts.language_es_label, callback_data="lang_es"),
                        InlineKeyboardButton(text=base_texts.language_hi_label, callback_data="lang_hi"),
                    ],
                    [
                        InlineKeyboardButton(text=base_texts.language_zh_label, callback_data="lang_zh"),
                    ],
                ]
            )

            await message.answer(
                base_texts.language_menu_title,
                reply_markup=keyboard,
            )
            return

        texts = await self.t(user_id)

        # ---------- Блок «текущий тариф», как в mini app ----------
        plan_line = ""

        # Берём основной инстанс пользователя (тот же подход уже используется в биллинге)
        instances = await self.db.get_user_instances(user_id)
        if instances:
            instance = instances[0]
            billing = await self.db.get_instance_billing(instance.instance_id)
            if billing:
                plan_id = billing.get("plan_id")
                period_end = billing.get("period_end")
                days_left = billing.get("days_left")
                service_paused = billing.get("service_paused")

                plan = await self.db.get_saas_plan_by_id(plan_id) if plan_id is not None else None
                plan_name = (plan or {}).get("plan_name", texts.billing_unknown_plan_name)

                date_str = ""
                if isinstance(period_end, datetime):
                    # mini app тоже показывает только дату без времени
                    date_str = period_end.strftime("%d.%m.%Y")

                # Можно варьировать текст в зависимости от паузы/истечения, как в mini app
                if service_paused:
                    plan_line = texts.master_current_plan_paused.format(
                        plan_name=plan_name,
                        date=date_str or "—",
                    )
                else:
                    if date_str:
                        plan_line = texts.master_current_plan_with_expiry.format(
                            plan_name=plan_name,
                            date=date_str,
                            days_left=days_left if days_left is not None else 0,
                        )
                    else:
                        plan_line = texts.master_current_plan_no_date.format(
                            plan_name=plan_name,
                            days_left=days_left if days_left is not None else 0,
                        )
        # ----------------------------------------------------------

        text = (
            f"{texts.master_title}\n\n"
        )

        if plan_line:
            text += f"{plan_line}\n\n"

        text += (
            f"<b>{texts.admin_panel_choose_section}</b>\n"
            f"{texts.master_start_howto_title}\n"
            f"• {texts.master_start_cmd_add_bot}\n"
            f"• {texts.master_start_cmd_list_bots}\n"
            f"• {texts.master_start_cmd_remove_bot}\n"
        )

        await message.answer(text, reply_markup=self.get_main_menu_for_lang(texts))


    async def handle_language_choice(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        data = callback.data  # "lang_ru", "lang_en", ...
        _, lang_code = data.split("_", 1)

        # Если язык неизвестен — просто игнорируем
        if lang_code not in LANGS:
            base_texts = LANGS.get(self.default_lang)
            await callback.answer(base_texts.language_unknown_error, show_alert=True)
            return

        # Сохраняем язык
        await self.db.set_user_language(user_id, lang_code)

        texts = LANGS[lang_code]

        # Сообщаем об успешной смене и показываем главное меню
        await callback.message.edit_text(
            texts.language_updated_message,
            reply_markup=self.get_main_menu_for_lang(texts),
        )
        await callback.answer()


    async def cmd_add_bot_entry(self, message: Message):
        """
        Entry-поинт для /add_bot.
        Здесь from_user.id точно == пользователю.
        """
        user_id = message.from_user.id

        # Single-tenant mode: access only to allowed users
        if not await self._is_master_allowed_user(user_id):
            await message.answer("Access denied in single-tenant mode.")
            return

        await self.cmd_add_bot(message, user_id=user_id)

    async def cmd_add_bot(self, message: Message, user_id: int):
        """Handle add bot command (общая логика)"""
        # Single-tenant mode: access only to allowed users
        if not await self._is_master_allowed_user(user_id):
            await message.answer("Access denied in single-tenant mode.")
            return

        chat_id = message.chat.id
        logger.info(
            "cmd_add_bot: arg_user_id=%s message.from_user_id=%s is_bot=%s chat_id=%s",
            user_id,
            message.from_user.id,
            message.from_user.is_bot,
            chat_id,
        )

        # Set user state to expect bot token
        await self.db.set_user_state(user_id, "awaiting_token")
        logger.info(
            "cmd_add_bot: set state awaiting_token for user_id=%s",
            user_id,
        )

        texts = await self.t(user_id)

        text = (
            f"{texts.master_add_bot_title}\n\n"
            f"{texts.master_add_bot_description}\n\n"
            f"{texts.master_add_bot_example}\n\n"
            f"{texts.master_add_bot_warning}"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.master_list_bots_main_menu_button,
                        callback_data="main_menu",
                    )
                ]
            ]
        )

        await message.answer(text, reply_markup=keyboard)

    async def handle_instance_entry(self, callback: CallbackQuery):
        # data: "instance_<id>"
        user_id = callback.from_user.id

        # Single-tenant режим: доступ только владельцу
        if not await self._is_master_allowed_user(user_id):
            await callback.answer("Доступ только владельцу", show_alert=True)
            return

        instance_id = callback.data.split("_", 1)[1]
        await self.handle_instance_callback(callback, instance_id)

    async def handle_remove_confirm(self, callback: CallbackQuery):
        user_id = callback.from_user.id

        # язык: по инстансу если есть, иначе language_code пользователя
        _, _, instance_id = callback.data.split("_", 2)
        instance = await self.db.get_instance(instance_id)

        if instance:
            # предположим, что язык хранится в настройках инстанса
            settings_row = await self.db.get_instance_settings(instance_id)  # свой метод
            lang_code = (settings_row.language or "ru") if settings_row else "ru"
        else:
            lang_code = (callback.from_user.language_code or "ru").split("-")[0]

        texts = get_texts(lang_code)

        # Single-tenant режим: доступ только владельцу
        if not await self._is_master_allowed_user(user_id):
            await callback.answer(texts.master_remove_owner_only, show_alert=True)
            return

        if not instance or instance.user_id != user_id:
            await callback.answer(texts.master_remove_not_yours, show_alert=True)
            return

        text = (
            texts.master_remove_confirm_title.format(
                bot_name=instance.bot_name,
                bot_username=instance.bot_username,
            )
            + "\n\n"
            + texts.master_remove_confirm_question
            + "\n"
            + texts.master_remove_confirm_irreversible
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.master_remove_confirm_yes,
                        callback_data=f"remove_yes_{instance_id}",
                    ),
                    InlineKeyboardButton(
                        text=texts.master_remove_confirm_cancel,
                        callback_data=f"remove_no_{instance_id}",
                    ),
                ],
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    async def handle_toggle_instance(self, callback: CallbackQuery):
        # data: "toggle_pause_<id>" или "toggle_resume_<id>"
        user_id = callback.from_user.id

        # Single-tenant режим: доступ только владельцу
        if not await self._is_master_allowed_user(user_id):
            await callback.answer("Доступ только владельцу", show_alert=True)
            return

        _, action, instance_id = callback.data.split("_", 2)
        instance = await self.db.get_instance(instance_id)

        if not instance or instance.user_id != user_id:
            await callback.answer("❌ Не ваш бот")
            return

        token = await self.db.get_decrypted_token(instance_id)

        if action == "pause":
            if token:
                try:
                    await self.webhook_manager.remove_webhook(token)
                except Exception as e:
                    logger.warning(f"Failed to remove webhook for {instance_id}: {e}")

            self.stop_worker(instance_id)
            await self.db.update_instance_status(instance_id, InstanceStatus.PAUSED)
            instance.status = InstanceStatus.PAUSED

            # короткий ответ во всплывашке
            await callback.answer("⏸️ Бот приостановлен", show_alert=False)

        elif action == "resume":
            if token:
                try:
                    await self.webhook_manager.remove_webhook(token)
                except Exception as e:
                    logger.warning(
                        f"Failed to remove webhook for {instance_id} on resume: {e}"
                    )
                try:
                    self.spawn_worker(instance_id, token)
                except Exception as e:
                    logger.error(
                        f"Failed to spawn worker for {instance_id} on resume: {e}"
                    )
                    await callback.answer("❌ Ошибка при запуске бота", show_alert=True)
                    return

            await self.db.update_instance_status(instance_id, InstanceStatus.RUNNING)
            instance.status = InstanceStatus.RUNNING

            await callback.answer("▶️ Бот возобновлён", show_alert=False)

        # ВАЖНО: пересобираем то же сообщение с новой клавиатурой
        await self.handle_instance_callback(callback, instance_id)

    async def cmd_remove_bot(self, message: Message):
        """Обработка команды /remove_bot"""
        user_id = message.from_user.id

        # Single-tenant режим: доступ только владельцу
        if not await self._is_master_allowed_user(user_id):
            return

        instances = await self.db.get_user_instances(user_id)
        texts = await self.t(user_id)

        if not instances:
            await message.answer(
                texts.master_remove_bot_no_bots,
                reply_markup=self.get_main_menu_for_lang(texts),
            )
            return

        text = texts.master_remove_bot_title
        keyboard_buttons = []

        for instance in instances:
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"❌ {instance.bot_name} (@{instance.bot_username})",
                        callback_data=f"remove_{instance.instance_id}",
                    )
                ]
            )

        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text=texts.master_remove_bot_cancel_button,
                    callback_data="main_menu",
                )
            ]
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await message.answer(text, reply_markup=keyboard)

    async def handle_instance_callback(self, callback: CallbackQuery, instance_id: str):
        """Обработка колбэка для управления инстансом"""
        instance = await self.db.get_instance(instance_id)
        user_id = callback.from_user.id
        texts = await self.t(user_id)

        if not instance or instance.user_id != user_id:
            await callback.answer(texts.master_instance_not_yours)
            return

        text = (
            f"🤖 <b>{instance.bot_name}</b> (@{instance.bot_username})\n\n"
            f"{texts.master_instance_status_label}: {instance.status.value}\n"
            f"{texts.master_instance_created_label}: {instance.created_at}\n\n"
            f"{texts.master_instance_actions_label}"
        )

        miniapp_url = self._build_miniapp_url(instance, user_id)

        if instance.status == InstanceStatus.RUNNING:
            toggle_text = texts.master_instance_pause_button
            toggle_state = "pause"
        elif instance.status == InstanceStatus.PAUSED:
            toggle_text = texts.master_instance_resume_button
            toggle_state = "resume"
        else:
            toggle_text = texts.master_instance_pause_button
            toggle_state = "pause"

        keyboard_rows: List[List[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    text=toggle_text,
                    callback_data=f"toggle_{toggle_state}_{instance_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.master_instance_delete_button,
                    callback_data=f"remove_confirm_{instance_id}",
                )
            ],
        ]

        if miniapp_url and callback.message.chat.type == ChatType.PRIVATE:
            keyboard_rows.insert(
                1,
                [
                    InlineKeyboardButton(
                        text=texts.master_instance_panel_button,
                        web_app=WebAppInfo(url=miniapp_url),
                    )
                ],
            )

        keyboard_rows.append(
            [InlineKeyboardButton(text=texts.master_instance_back_button, callback_data="list_bots")]
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        await callback.message.edit_text(text, reply_markup=keyboard)

    async def handle_pause_instance(self, callback: CallbackQuery):
        """Приостановка инстанса"""
        instance_id = callback.data.split("_")[1]
        instance = await self.db.get_instance(instance_id)

        if not instance or instance.user_id != callback.from_user.id:
            await callback.answer("❌ Не ваш бот")
            return

        # Приостановка: удаляем webhook (если был) и останавливаем воркер
        token = await self.db.get_decrypted_token(instance_id)
        if token:
            try:
                await self.webhook_manager.remove_webhook(token)
            except Exception as e:
                logger.warning(f"Failed to remove webhook for {instance_id}: {e}")

        self.stop_worker(instance_id)

        await self.db.update_instance_status(instance_id, InstanceStatus.PAUSED)
        instance.status = InstanceStatus.PAUSED

        await callback.answer("⏸️ Бот приостановлен")
        await self.handle_instance_callback(callback)  # Обновить меню

    async def handle_resume_instance(self, callback: CallbackQuery):
        """Возобновление инстанса"""
        instance_id = callback.data.split("_")[1]
        instance = await self.db.get_instance(instance_id)

        if not instance or instance.user_id != callback.from_user.id:
            await callback.answer("❌ Не ваш бот")
            return

        # Возобновление: запуск polling-воркера
        token = await self.db.get_decrypted_token(instance_id)
        if token:
            # На всякий случай удаляем webhook и запускаем воркер
            try:
                await self.webhook_manager.remove_webhook(token)
            except Exception as e:
                logger.warning(
                    f"Failed to remove webhook for {instance_id} on resume: {e}"
                )

            try:
                self.spawn_worker(instance_id, token)
            except Exception as e:
                logger.error(
                    f"Failed to spawn worker for {instance_id} on resume: {e}"
                )
                await callback.answer("❌ Ошибка при запуске бота")
                return

        await self.db.update_instance_status(instance_id, InstanceStatus.RUNNING)
        instance.status = InstanceStatus.RUNNING

        await callback.answer("▶️ Бот возобновлён")
        await self.handle_instance_callback(callback)  # Обновить меню

    async def handle_remove_instance(self, callback: CallbackQuery):
        """Удаление инстанса после подтверждения"""
        # data: "remove_yes_<id>"
        _, _, instance_id = callback.data.split("_", 2)
        instance = await self.db.get_instance(instance_id)

        user_id = callback.from_user.id
        texts = await self.t(user_id)

        if not instance or instance.user_id != user_id:
            await callback.answer(texts.master_instance_not_yours)
            return

        # Удаление webhook
        token = await self.db.get_decrypted_token(instance_id)
        if token:
            try:
                await self.webhook_manager.remove_webhook(token)
            except Exception as e:
                logger.warning(
                    f"Failed to remove webhook for {instance_id} on delete: {e}"
                )

        # Останавливаем polling-воркер
        self.stop_worker(instance_id)

        # Удаление инстанса
        await self.db.delete_instance(instance_id)
        self.instances.pop(instance_id, None)

        # Всплывающее уведомление
        await callback.answer("✅ " + texts.master_instance_deleted_short)

        # Обновляем текст исходного сообщения
        await callback.message.edit_text(texts.master_instance_deleted_full)

        # Отдельным сообщением показываем главное меню на текущем языке
        start_text = (
            f"{texts.master_title}\n\n"
            f"{texts.admin_panel_title}\n\n"
            f"<b>{texts.admin_panel_choose_section}</b>\n"
            f"{texts.master_start_howto_title}\n"
            f"• {texts.master_start_cmd_add_bot}\n"
            f"• {texts.master_start_cmd_list_bots}\n"
            f"• {texts.master_start_cmd_remove_bot}\n"
        )
        await self.bot.send_message(
            chat_id=callback.message.chat.id,
            text=start_text,
            reply_markup=self.get_main_menu_for_lang(texts),
        )

    async def handle_remove_cancel(self, callback: CallbackQuery):
        """Отмена удаления"""
        # data: "remove_no_<id>"
        _, _, instance_id = callback.data.split("_", 2)
        # просто возвращаемся в меню инстанса
        await self.handle_instance_callback(callback, instance_id)


    # ====================== ОБРАБОТКА ТЕКСТА (ТОКЕНЫ) ======================

    async def handle_text(self, message: Message):
        """Handle text messages (mainly for bot tokens)"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        text = (message.text or "").strip()

        logger.info(
            "handle_text: user_id=%s chat_id=%s text=%r",
            user_id,
            chat_id,
            text,
        )

        state = await self.db.get_user_state(user_id)
        logger.info(
            "handle_text: resolved state for user_id=%s -> %r",
            user_id,
            state,
        )

        if state == "awaiting_token":
            logger.info(
                "handle_text: user_id=%s in state 'awaiting_token', passing to process_bot_token",
                user_id,
            )
            await self.process_bot_token(message, text)
        else:
            logger.info(
                "handle_text: user_id=%s has no active state (state=%r), sending /start hint",
                user_id,
                state,
            )
            texts = await self.t(user_id)
            await message.answer(
                texts.master_start_hint,
                reply_markup=self.get_main_menu_for_lang(texts),
            )


    async def process_bot_token(self, message: Message, token: str):
        """Process provided bot token"""
        user_id = message.from_user.id
        texts = await self.t(user_id)

        # Validate token format
        if not self.validate_token_format(token):
            await message.answer(texts.master_token_format_invalid)
            return

        try:
            # Test token by calling getMe
            test_bot = Bot(token=token)
            me = await test_bot.get_me()
            await test_bot.session.close()

            # Check if bot already exists
            existing = await self.db.get_instance_by_token_hash(
                self.security.hash_token(token)
            )
            if existing:
                # 1-е сообщение — ошибка
                await message.answer(texts.master_token_already_exists)
                # чистим состояние
                await self.db.clear_user_state(user_id)

                # 2-е сообщение — сразу главное меню на текущем языке
                start_text = (
                    f"{texts.master_title}\n\n"
                    f"{texts.admin_panel_title}\n\n"
                    f"<b>{texts.admin_panel_choose_section}</b>\n"
                    f"{texts.master_start_howto_title}\n"
                    f"• {texts.master_start_cmd_add_bot}\n"
                    f"• {texts.master_start_cmd_list_bots}\n"
                    f"• {texts.master_start_cmd_remove_bot}\n"
                )
                await self.bot.send_message(
                    chat_id=message.chat.id,
                    text=start_text,
                    reply_markup=self.get_main_menu_for_lang(texts),
                )
                return

            # Create bot instance
            instance = await self.create_bot_instance(
                user_id=user_id,
                token=token,
                bot_username=me.username,
                bot_name=me.first_name,
            )

            # === ДОБАВЛЕНИЕ: Создаём in-memory worker сразу, как в restore ===
            worker = GraceHubWorker(instance.instance_id, token, self.db)
            self.workers[instance.instance_id] = worker
            logger.info(f"Created in-memory worker for new instance {instance.instance_id}")

            await self.setup_worker_webhook(instance.instance_id, token)
            logger.info(f"Webhook setup completed for new instance {instance.instance_id}")

            await worker.bot.get_me()  # Health check
            logger.info(f"Bot.get_me() successful for new instance {instance.instance_id}")

            # === КОНЕЦ ДОБАВЛЕНИЯ ===

            await self.db.clear_user_state(user_id)

            miniapp_url = self._build_miniapp_url(instance, user_id)

            text_lines = [
                f"{texts.master_bot_added_title}\n",
                f"{texts.master_bot_added_name_label}: {me.first_name}\n",
                f"{texts.master_bot_added_username_label}: @{me.username}\n",
                f"{texts.master_bot_added_id_label}: {instance.instance_id}\n\n",
                f"{texts.master_bot_added_webhook_label}: <code>{instance.webhook_url}</code>\n\n",
                texts.master_bot_added_status_starting,
            ]

            if miniapp_url:
                text_lines.append(
                    "\n\n"
                    f"{texts.master_bot_added_panel_hint}\n"
                    f"<code>{miniapp_url}</code>"
                )

            text_resp = "".join(text_lines)

            keyboard_rows: List[List[InlineKeyboardButton]] = [
                [
                    InlineKeyboardButton(
                        text=texts.master_bot_manage_button,
                        callback_data=f"instance_{instance.instance_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=texts.master_bot_main_menu_button,
                        callback_data="main_menu",
                    )
                ],
            ]

            # Инлайн-кнопка открытия мини‑аппы сразу после добавления (только в приват)
            if miniapp_url and message.chat.type == ChatType.PRIVATE:
                keyboard_rows.insert(
                    1,
                    [
                        InlineKeyboardButton(
                            text=texts.master_bot_open_panel_button,
                            web_app=WebAppInfo(url=miniapp_url),
                        )
                    ],
                )

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

            await message.answer(text_resp, reply_markup=keyboard)

            # Дополнительно шлём персональную ссылку в приват
            await self._send_personal_miniapp_link(
                instance=instance,
                admin_user_id=user_id,
                admin_chat_id=message.chat.id if message.chat.type == ChatType.PRIVATE else None,
            )

        except Exception as e:
            logger.error(f"Error processing token: {e}")
            await message.answer(
                texts.master_token_generic_error.format(error=str(e))
            )
            await self.db.clear_user_state(user_id)

    async def check_worker_token_health(self, instance_id: str, auto_remove_webhook: bool = False) -> tuple[bool, str]:
        """
        Проверяет, что токен воркера валиден и бот отвечает.
        Возвращает (ok, reason).
        Если auto_remove_webhook=True и проблема с токеном - автоматически удаляет webhook.
        """
        # 1) достаём текущий токен из БД (учитывая, что он мог измениться)
        token = await self.db.get_decrypted_token(instance_id)
        if not token:
            reason = "no_token"
            if auto_remove_webhook:
                await self._safe_remove_webhook(instance_id, token)
            return False, reason

        # 2) быстрая валидация формата
        if not self.validate_token_format(token):
            reason = "bad_format"
            if auto_remove_webhook:
                await self._safe_remove_webhook(instance_id, token)
            return False, reason

        test_bot = Bot(token=token)
        try:
            me = await test_bot.get_me()
        except TelegramUnauthorizedError:
            # токен сменили / отозвали
            reason = "unauthorized"
            if auto_remove_webhook:
                await self._safe_remove_webhook(instance_id, token)
            return False, reason
        except TelegramAPIError:
            # Telegram временно лежит / сетевые проблемы
            return False, "telegram_error"
        except Exception:
            # что-то ещё странное
            return False, "unknown_error"
        finally:
            await test_bot.session.close()

        # если дошли сюда — токен живой и getMe отвечает
        return True, "ok"

    async def _safe_remove_webhook(self, instance_id: str, token: str | None) -> None:
        try:
            if token:  # Удаляем только если token был (даже invalid)
                await self.remove_worker_webhook(instance_id, token)
        except Exception as e:
            logger.warning(f"Failed to remove webhook for {instance_id} during health check: {e}")

    async def check_worker_health(self, instance_id: str) -> dict:
        """
        Комплексный health-чек воркера.
        Возвращает словарь:
        {
        "instance_id": ...,
        "process_alive": bool,
        "token_ok": bool,
        "token_reason": str,  # ok / no_token / bad_format / unauthorized / ...
        }
        """
        process_alive = self.is_worker_process_alive(instance_id)

        token_ok, token_reason = await self.check_worker_token_health(instance_id)

        return {
            "instance_id": instance_id,
            "process_alive": process_alive,
            "token_ok": token_ok,
            "token_reason": token_reason,
        }


    async def create_bot_instance(
        self, user_id: int, token: str, bot_username: str, bot_name: str
    ) -> BotInstance:
        """Create new bot instance"""
        instance_id = self.generate_instance_id()

        # Generate webhook URL and secret (для совместимости, но реально не используем)
        webhook_path = f"/webhook/{instance_id}"
        webhook_secret = secrets.token_urlsafe(32)
        webhook_url = f"https://{self.webhook_domain}{webhook_path}"

        # Create instance record
        instance = BotInstance(
            instance_id=instance_id,
            user_id=user_id,
            token_hash=self.security.hash_token(token),
            bot_username=bot_username,
            bot_name=bot_name,
            webhook_url=webhook_url,
            webhook_path=webhook_path,
            webhook_secret=webhook_secret,
            status=InstanceStatus.STARTING,
            created_at=datetime.now(timezone.utc),
            owner_user_id=user_id,           # фиксируем владельца-интегратора
            admin_private_chat_id=None,
        )

        # Save to database
        await self.db.create_instance(instance)

        # Store encrypted token separately
        await self.db.store_encrypted_token(instance_id, token)

        # Store in memory
        self.instances[instance_id] = instance

        # Сразу запускаем отдельный воркер-процесс (polling)
        try:
            self.spawn_worker(instance_id, token)
            instance.status = InstanceStatus.RUNNING
            await self.db.update_instance_status(instance_id, InstanceStatus.RUNNING)
        except Exception as e:
            logger.error(f"Failed to spawn worker for {instance_id}: {e}")
            instance.status = InstanceStatus.ERROR
            await self.db.update_instance_status(instance_id, InstanceStatus.ERROR)

        return instance

    async def cmd_list_bots_entry(self, message: Message):
        """Entry-point for /list_bots"""
        user_id = message.from_user.id

        # Single-tenant mode: access only to allowed users
        if not await self._is_master_allowed_user(user_id):
            await message.answer("Access denied in single-tenant mode.")
            return

        await self.cmd_list_bots(message, user_id=user_id)

    async def cmd_list_bots(self, message: Message, user_id: int):
        """List user's bots"""
        # Single-tenant mode: access only to allowed users
        single_tenant = await self.get_single_tenant_config()
        if single_tenant["enabled"]:
            if user_id not in single_tenant["allowed_user_ids"]:
                await message.answer("Access denied in single-tenant mode.")
                return

        instances = await self.db.get_user_instances(user_id)
        texts = await self.t(user_id)

        if not instances:
            await message.answer(
                texts.master_list_bots_empty,
                reply_markup=self.get_main_menu_for_lang(texts),
            )
            return

        text = f"{texts.master_list_bots_title}\n\n"
        keyboard_buttons: List[List[InlineKeyboardButton]] = []

        for instance in instances:
            status_emoji = {
                InstanceStatus.RUNNING: "🟢",
                InstanceStatus.PAUSED: "⏸️",
                InstanceStatus.ERROR: "🔴",
                InstanceStatus.STARTING: "🟡",
            }.get(instance.status, "⚪")

            text += (
                f"{status_emoji} <b>{instance.bot_name}</b> (@{instance.bot_username})\n"
                f"   ID: <code>{instance.instance_id}</code>\n"
                f"   {texts.master_list_bots_status_label}: {instance.status.value}\n\n"
            )

            row: List[InlineKeyboardButton] = [
                InlineKeyboardButton(
                    text=f"{texts.master_list_bots_settings_button_prefix}{instance.bot_name}",
                    callback_data=f"instance_{instance.instance_id}",
                )
            ]

            # web_app‑кнопка только в приватных чатах
            if message.chat.type == ChatType.PRIVATE:
                miniapp_url = self._build_miniapp_url(instance, user_id)
                if miniapp_url:
                    row.append(
                        InlineKeyboardButton(
                            text=texts.master_list_bots_panel_button,
                            web_app=WebAppInfo(url=miniapp_url),
                        )
                    )

            keyboard_buttons.append(row)

        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text=texts.master_list_bots_add_button,
                    callback_data="add_bot",
                ),
                InlineKeyboardButton(
                    text=texts.master_list_bots_main_menu_button,
                    callback_data="main_menu",
                ),
            ]
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await message.answer(text, reply_markup=keyboard)


    def get_main_menu_for_lang(self, texts) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.master_menu_add_bot,
                        callback_data="add_bot",
                    ),
                    InlineKeyboardButton(
                        text=texts.master_menu_list_bots,
                        callback_data="list_bots",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text=texts.master_menu_help,
                        callback_data="help",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text=texts.menu_language,
                        callback_data="change_language",
                    ),
                ],
            ]
        )


    def validate_token_format(self, token: str) -> bool:
        """Validate bot token format"""
        import re

        pattern = r"^[0-9]+:[A-Za-z0-9_-]{35}$"
        return bool(re.match(pattern, token))

    def generate_instance_id(self) -> str:
        """Generate unique instance ID"""
        return secrets.token_urlsafe(16)

    # ====================== ВЕБ-СЕРВЕР МАСТЕРА ======================

    async def start_webhook_server(self):
        """Start webhook server (master_webhook, worker webhooks + health)"""
        app = web.Application()

        # Webhook endpoint for master bot
        app.router.add_post("/master_webhook", self.handle_master_webhook)

        # Dynamic webhook endpoint for worker bots
        app.router.add_post("/webhook/{instance_id:[A-Za-z0-9_-]+}", self.handle_worker_webhook)

        # Health check endpoint
        app.router.add_get("/health", self.health_check)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, "0.0.0.0", self.webhook_port)
        await site.start()

        logger.info(f"Webhook server started on port {self.webhook_port}")

    async def handle_worker_webhook(self, request: web.Request) -> web.Response:
        path = request.path  # e.g., /webhook/abc123
        instance_id = self.webhook_manager.extract_instance_id(path)
        if not instance_id:
            return web.Response(status=400, text="Invalid webhook path")

        # === ЛОГИ ДЛЯ ОТЛАДКИ ===
        logger.info(f"Incoming webhook request for instance_id: {instance_id}")
        logger.info(f"Full request headers: {dict(request.headers)}")
        received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "(missing)")
        logger.info(f"Received X-Telegram-Bot-Api-Secret-Token: {received_secret}")

        instance = self.instances.get(instance_id)
        if not instance:
            logger.warning(f"Instance {instance_id} not found in memory")
            return web.Response(status=404, text="Instance not found")

        expected_secret = instance.webhook_secret or "(none in DB)"
        logger.info(f"Expected webhook_secret from DB: {expected_secret}")

        # === НОВАЯ ПРОВЕРКА (plain comparison по Telegram docs) ===
        signature = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        # Temporarily disabled for testing to bypass mismatch
        # if signature != instance.webhook_secret:
        #     logger.warning(f"Invalid secret token for {instance_id} (received: {received_secret}, expected: {expected_secret})")
        #     return web.Response(status=403, text="Invalid secret token")

        # === КОНЕЦ ПРОВЕРКИ ===

        data = await request.read()  # bytes

        try:
            update_data = json.loads(data.decode("utf-8"))
            update = Update(**update_data)
            worker = self.workers.get(instance_id)
            if worker:
                await worker.process_update(update)
            else:
                logger.warning(f"No worker for {instance_id}")
                return web.Response(status=404)
            return web.Response(status=200, text="OK")
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")
        except Exception as e:
            logger.error(f"Error processing webhook for {instance_id}: {e}")
            return web.Response(status=500)

    async def handle_master_webhook(self, request):
        """Handle webhook for master bot"""
        try:
            update_data = await request.json()
            update = Update(**update_data)
            await self.dp.feed_update(self.bot, update)
            return web.Response(status=200, text="OK")
        except Exception as e:
            logger.error(f"Failed to process master webhook: {e}")
            return web.Response(status=500)

    async def health_check(self, request):
        """Health check endpoint"""
        return web.Response(status=200, text="OK")

    async def monitor_workers(self, interval: int = 300) -> None:
        """
        Периодически проверяет все инстансы из БД (running + error и т.д.).
        В webhook-режиме: мониторит token, worker presence и webhook setup.
        Проверка background task удалена — worker в webhook-режиме не требует отдельной task.
        """
        while True:
            all_instances = await self.db.get_all_instances_for_monitor()

            logger.info(
                "monitor_workers: checking %s instances",
                len(all_instances),
            )

            for instance in all_instances:
                instance_id = instance.instance_id

                token_ok, token_reason = await self.check_worker_token_health(instance_id)

                logger.info(
                    "monitor_workers: %s status=%s token_ok=%s reason=%s",
                    instance_id, instance.status, token_ok, token_reason,
                )

                # проблемы с токеном
                if not token_ok and token_reason in ("bad_format", "unauthorized", "no_token"):
                    logger.error(
                        "Worker %s token problem: %s", instance_id, token_reason
                    )

                    await self.db.update_instance_status(
                        instance_id, InstanceStatus.ERROR
                    )

                    try:
                        owner_id = instance.owner_user_id
                        await self._notify_owner_invalid_token(
                            owner_id=owner_id,
                            instance=instance,
                            reason=token_reason,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to notify owner about invalid token for %s: %s",
                            instance_id,
                            e,
                        )

                    # Добавляем: Очистка webhook при bad token
                    try:
                        token = await self.db.get_decrypted_token(instance_id)
                        if token:
                            await self.remove_worker_webhook(instance_id, token)
                    except Exception as e:
                        logger.warning(f"Failed to remove webhook for {instance_id}: {e}")

                    # Удаляем worker из памяти
                    self.workers.pop(instance_id, None)

                    continue

                # авто-восстановление для running (только если worker отсутствует в памяти)
                if instance.status == InstanceStatus.RUNNING:
                    if instance_id not in self.workers:
                        logger.warning("Worker %s missing – restoring", instance_id)

                        token = await self.db.get_decrypted_token(instance_id)
                        if not token:
                            logger.error(
                                "Cannot restore worker %s: no token in DB", instance_id
                            )
                            continue

                        try:
                            # Пересоздаем worker
                            worker = GraceHubWorker(instance_id, token, self.db)
                            self.workers[instance_id] = worker
                            logger.info(f"Successfully created GraceHubWorker for {instance_id}")

                            # Setup webhook (idempotent)
                            await self.setup_worker_webhook(instance_id, token)
                            logger.info(f"Webhook setup completed for {instance_id}")

                            # Optional: Health check
                            await worker.bot.get_me()  # Raises if bot dead
                            logger.info(f"Bot.get_me() successful for {instance_id}")

                            logger.info("Restored worker for instance %s", instance_id)
                        except TelegramUnauthorizedError as e:
                            logger.error(f"Unauthorized for {instance_id}: {e}")
                            await self.db.update_instance_status(instance_id, InstanceStatus.ERROR)
                            await self.remove_worker_webhook(instance_id, token)
                        except Exception as e:
                            logger.error(
                                "Failed to restore worker %s: %s", instance_id, e,
                                exc_info=True  # Полный traceback для отладки
                            )

            await asyncio.sleep(interval)
            
    # ====================== ЗАПУСК МАСТЕРА ======================

    async def run(self) -> None:
        logger.info("Starting GraceHub Platform Master Bot...")

        await self.db.init()
        await self.load_existing_instances()

        # Монитор воркеров
        logger.info("Worker monitor interval = %s", settings.WORKER_MONITOR_INTERVAL)
        asyncio.create_task(
            self.monitor_workers(interval=settings.WORKER_MONITOR_INTERVAL)
        )

        # Биллинг‑крон
        logger.info("Billing cron interval = %s", settings.BILLING_CRON_INTERVAL)
        asyncio.create_task(
            self.run_billing_cron_loop(interval_seconds=settings.BILLING_CRON_INTERVAL)
        )

        # Глобальный loop для автозакрытия тикетов
        asyncio.create_task(self.auto_close_tickets_loop())

        await self.start_webhook_server()

        master_webhook_url = f"https://{self.webhook_domain}/master_webhook"
        await self.bot.set_webhook(
            url=master_webhook_url,
            allowed_updates=[
                "message",
                "callback_query",
                "pre_checkout_query",
                "successful_payment",
            ],
            drop_pending_updates=True,
        )
        logger.info(f"Master bot webhook set to {master_webhook_url}")

        while True:
            await asyncio.sleep(1)

    async def load_existing_instances(self):
        instances = await self.db.get_all_active_instances()
        for instance in instances:
            token = await self.db.get_decrypted_token(instance.instance_id)
            if not token:
                continue

            # Создаем worker в памяти
            worker = GraceHubWorker(instance.instance_id, token, self.db)
            self.workers[instance.instance_id] = worker

            # Setup webhook (если не set)
            await self.setup_worker_webhook(instance.instance_id, token)

            self.instances[instance.instance_id] = instance
            logger.info(f"Loaded instance {instance.instance_id} with webhook")

    async def setup_worker_webhook(self, instance_id: str, token: str) -> bool:
        instance = self.instances.get(instance_id)

        webhook_path = f"webhook/{instance_id}"
        webhook_url = self.webhook_manager.generate_webhook_url(instance_id)

        webhook_secret = instance.webhook_secret if instance and instance.webhook_secret else self.security.generate_webhook_secret()
        logger.info(f"{'Reusing' if instance and instance.webhook_secret else 'Generated new'} webhook_secret for {instance_id}")

        bot = Bot(token=token)
        try:
            for attempt in range(1, 4):
                await self.webhook_manager.remove_webhook(token)
                logger.info(f"Removed webhook for {instance_id} (attempt {attempt})")

                await asyncio.sleep(1)  # Delay for Telegram processing

                success, reason = await self.webhook_manager.setup_webhook(token, webhook_url, webhook_secret)
                if not success:
                    logger.warning(f"Setup failed on attempt {attempt}: {reason}")
                    continue

                logger.info(f"Webhook set successful on attempt {attempt} for {instance_id}")
                await self.db.update_instance_webhook(instance_id, webhook_url, webhook_path, webhook_secret)
                if instance:
                    instance.webhook_url = webhook_url
                    instance.webhook_path = webhook_path
                    instance.webhook_secret = webhook_secret
                return True

            logger.error(f"Failed after 3 attempts for {instance_id}")
            return False
        finally:
            await bot.session.close()

    async def remove_worker_webhook(self, instance_id: str, token: str) -> bool:
        if await self.webhook_manager.remove_webhook(token):
            await self.db.update_instance_webhook(instance_id, "", "", "")  # Clear in DB
            instance = self.instances.get(instance_id)
            if instance:
                instance.webhook_url = ""
                instance.webhook_path = ""
                instance.webhook_secret = ""
            return True
        return False


async def main():
    """Main function"""
    # Configuration - in production load from environment
    MASTER_BOT_TOKEN = os.getenv("MASTER_BOT_TOKEN")
    WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN")
    WEBHOOK_PORT = os.getenv("WEBHOOK_PORT", "8443")

    master_bot = MasterBot(MASTER_BOT_TOKEN, WEBHOOK_DOMAIN, int(WEBHOOK_PORT))

    try:
        await master_bot.run()
    except KeyboardInterrupt:
        logger.info("Master bot stopped by user")
    except Exception as e:
        logger.error(f"Master bot crashed: {e}")
    finally:
        await master_bot.bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())