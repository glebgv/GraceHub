import asyncio
import logging
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
import secrets
import hashlib
import os
import subprocess
from pathlib import Path
from languages import LANGS
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

# Import shared utilities
from shared.database import MasterDatabase
from shared.models import BotInstance, InstanceStatus
from shared.webhook_manager import WebhookManager
from shared.security import SecurityManager
from shared import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("master_bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("master_bot")


class MasterBot:
    def __init__(self, token: str, webhook_domain: str, webhook_port: int = 8443, db: MasterDatabase | None = None):
        self.bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.dp = Dispatcher()
        self.webhook_domain = webhook_domain
        self.webhook_port = int(webhook_port) if webhook_port else 8443
        self.default_lang = "ru"

        # Если БД передали извне — используем её, иначе создаём свою.
        # Без аргументов: MasterDatabase сам возьмёт DSN из env DATABASE_URL.
        if db is not None:
            self.db = db
        else:
            self.db = MasterDatabase()

        self.webhook_manager = WebhookManager(webhook_domain)
        self.security = SecurityManager()

        self.instances: Dict[str, BotInstance] = {}
        self.worker_procs: Dict[str, subprocess.Popen] = {}

        self.setup_handlers()


    def _is_master_allowed_user(self, user_id: int) -> bool:
        """
        В single-tenant режиме мастер-бот доступен только OWNER_TELEGRAM_ID.
        В обычном режиме — всем.
        """
        if not settings.SINGLE_TENANT_OWNER_ONLY:
            return True
        return settings.OWNER_TELEGRAM_ID is not None and user_id == settings.OWNER_TELEGRAM_ID

    async def get_user_lang(self, user_id: int) -> str:
        lang = await self.db.get_user_language(user_id)
        return lang or self.default_lang

    async def t(self, user_id: int):
        lang = await self.get_user_lang(user_id)
        return LANGS.get(lang, LANGS[self.default_lang])


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

        try:
            await self.bot.send_message(chat_id=owner_id, text=text)
        except TelegramAPIError as e:
            logger.warning(
                "Failed to send invalid-token alert to owner %s for instance %s: %s",
                owner_id,
                instance.instance_id,
                e,
            )


    # ====================== БИЛЛИНГ: CRON-ЗАДАЧИ ======================

    async def _billing_notify_expiring(self) -> None:
        rows = await self.db.get_instances_expiring_in_7_days()
        if not rows:
            return

        logger.info("BillingCron: %d instances expiring in 7 days", len(rows))

        for r in rows:
            owner_id = r["owner_user_id"]
            admin_chat = r["admin_private_chat_id"]
            bot_username = r["bot_username"]
            days_left = r["days_left"]

            if not owner_id and not admin_chat:
                continue

            text = (
                "🔔 <b>Напоминание по тарифу</b>\n\n"
                f"Для инстанса @{bot_username} осталось {days_left} дней до окончания периода.\n"
                "Продлите тариф, чтобы бот продолжил работать без ограничений."
            )

            targets = set()
            if owner_id:
                targets.add(owner_id)
            if admin_chat:
                targets.add(admin_chat)

            for chat_id in targets:
                try:
                    await self.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                except Exception as e:
                    logger.exception(
                        "BillingCron: failed to send expiring notification to %s: %s",
                        chat_id,
                        e,
                    )

    async def _billing_notify_paused(self) -> None:
        rows = await self.db.get_recently_paused_instances()
        if not rows:
            return

        logger.info("BillingCron: %d instances just paused", len(rows))

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

            for chat_id in targets:
                try:
                    await self.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                except Exception as e:
                    logger.exception(
                        "BillingCron: failed to send paused notification to %s: %s",
                        chat_id,
                        e,
                    )

    async def _run_billing_cycle(self) -> None:
        """
        Один цикл биллингового крона:
        - пересчитать флаги;
        - отправить уведомления.
        """
        if settings.SINGLE_TENANT_OWNER_ONLY:
            return

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

        proc = subprocess.Popen(
            ["python", "src/worker/main.py"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        self.worker_procs[instance_id] = proc
        logger.info(f"Spawned worker process for instance {instance_id} (pid={proc.pid})")

    def stop_worker(self, instance_id: str) -> None:
        """
        Останавливает воркер-процесс для инстанса, если он запущен.
        """
        proc = self.worker_procs.get(instance_id)
        if not proc:
            return

        if proc.poll() is None:
            try:
                proc.terminate()
                logger.info(f"Sent terminate to worker {instance_id} (pid={proc.pid})")
            except Exception as e:
                logger.warning(f"Failed to terminate worker {instance_id}: {e}")

        self.worker_procs.pop(instance_id, None)

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

        # 1. Проверка формата токена (как в process_bot_token)
        if not self.validate_token_format(token):
            raise ValueError("Неверный формат токена")

        # 2. Проверка токена через getMe
        test_bot = Bot(token=token)
        try:
            me = await test_bot.get_me()
        finally:
            await test_bot.session.close()

        # 3. Проверка, что такого бота ещё нет
        existing = await self.db.get_instance_by_token_hash(
            self.security.hash_token(token)
        )
        if existing:
            raise ValueError("Этот бот уже добавлен в систему")

        # 4. Создание инстанса + запуск воркера (ровно как в create_bot_instance)
        instance = await self.create_bot_instance(
            user_id=owner_user_id,
            token=token,
            bot_username=me.username,
            bot_name=me.first_name,
        )

        return instance

    async def handle_billing_main_menu(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
                await callback.answer("Доступ только владельцу", show_alert=True)
                return

        texts = await self.t(user_id)

        # берём все публичные планы (как для мини‑аппы)
        plans = await self.db.get_saas_plans_for_billing()

        if not plans:
            await callback.message.edit_text(
                "Тарифы пока не настроены.",
                reply_markup=self.get_main_menu_for_lang(texts),
            )
            await callback.answer()
            return

        text = "Выберите тариф для вашего аккаунта:\n\n"
        keyboard_rows: list[list[InlineKeyboardButton]] = []

        for p in plans:
            text += (
                f"• <b>{p['plan_name']}</b>: {p['price_stars']} ⭐ / {p['period_days']} д., "
                f"лимит {p['tickets_limit']} тикетов\n"
            )
            if p["product_code"]:
                keyboard_rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"{p['plan_name']} — {p['price_stars']} ⭐",
                            callback_data=f"billing_choose_plan_{p['plan_code']}",
                        )
                    ]
                )

        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=texts.master_list_bots_main_menu_button,
                    callback_data="main_menu",
                )
            ]
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()



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
        
        # === Биллинг из мастер-бота ===
        self.dp.callback_query(F.data.startswith("billing_choose_plan_"))(
            self.handle_billing_choose_plan
        )
        self.dp.callback_query(F.data.startswith("billing_confirm_plan_"))(
            self.handle_billing_confirm_plan
        )

        # Общий handler для меню callbacks
        self.dp.callback_query()(self.handle_menu_callback)

        # Text handler for adding bot tokens
        self.dp.message(F.text)(self.handle_text)

        # === Stars / оплата тарифов ===
        self.dp.pre_checkout_query()(self.handle_pre_checkout_query)
        self.dp.message(F.successful_payment)(self.handle_successful_payment)



    # ====================== МЕНЮ МАСТЕРА ======================

    async def handle_menu_callback(self, callback: CallbackQuery):
        """Handle menu callbacks like add_bot, list_bots etc."""
        data = callback.data
        user_id = callback.from_user.id
        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
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
        elif data == "billing_menu":
            await self.handle_billing_main_menu(callback)

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
        # если user_id не передан, берём из message
        if user_id is None:
            user_id = message.from_user.id

        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
                texts = await self.t(user_id)
                await message.answer(texts.master_owner_only)
                return

        # Проверяем, выбран ли язык
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

        text = (
            f"{texts.master_title}\n\n"
            f"{texts.admin_panel_title}\n\n"
            f"<b>{texts.admin_panel_choose_section}</b>\n"
            f"{texts.master_start_howto_title}\n"
            f"• {texts.master_start_cmd_add_bot}\n"
            f"• {texts.master_start_cmd_list_bots}\n"
            f"• {texts.master_start_cmd_remove_bot}\n"
        )
        await message.answer(text, reply_markup=self.get_main_menu_for_lang(texts))


    async def handle_billing_choose_plan(self, callback: CallbackQuery):
        user_id = callback.from_user.id

        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
                await callback.answer("Доступ только владельцу", show_alert=True)
                return

        plan_code = callback.data.split("billing_choose_plan_", 1)[1]
        plan = await self.db.get_saas_plan_with_product_by_code(plan_code)
        if not plan or not plan["product_code"]:
            await callback.answer("Тариф недоступен", show_alert=True)
            return

        # пока один период = 1x
        periods = 1

        text = (
            f"Тариф аккаунта: <b>{plan['plan_name']}</b>\n"
            f"Период: {plan['period_days']} дней, лимит {plan['tickets_limit']} тикетов.\n"
            f"Стоимость: <b>{plan['price_stars'] * periods} ⭐</b>\n\n"
            "Оплатить за 1 период?"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Оплатить",
                        callback_data=f"billing_confirm_plan_{plan_code}_{periods}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="billing_menu",
                    )
                ],
            ]
        )

        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()


    async def handle_billing_confirm_plan(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        # язык пользователя/инстанса
        instances = await self.db.get_user_instances(user_id)
        if instances:
            instance_id = instances[0].instance_id
            instance_settings = await self.db.get_instance_settings(instance_id)  # свой метод
            lang_code = instance_settings.language or "ru"
        else:
            lang_code = (callback.from_user.language_code or "ru").split("-")[0]

        texts = get_texts(lang_code)

        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
                await callback.answer(texts.billing_owner_only, show_alert=True)
                return

        # billing_confirm_plan_<plan_code>_<periods>
        payload_part = callback.data.split("billing_confirm_plan_", 1)[1]
        plan_code, periods_str = payload_part.rsplit("_", 1)
        periods = int(periods_str)

        plan = await self.db.get_saas_plan_with_product_by_code(plan_code)
        if not plan or not plan["product_code"]:
            await callback.answer(texts.billing_plan_unavailable, show_alert=True)
            return

        base_amount = plan["price_stars"]
        total_amount = base_amount * periods

        if not instances:
            await callback.answer(texts.billing_need_instance_first, show_alert=True)
            return

        instance_id = instances[0].instance_id

        invoice_id = await self.db.insert_billing_invoice(
            instance_id=instance_id,
            user_id=user_id,
            plan_code=plan_code,
            periods=periods,
            amount_stars=total_amount,
            product_code=plan["product_code"],
            payload="",
            invoice_link="",
            status="pending",
        )

        payload = f"saas:{invoice_id}"

        try:
            invoice_link = await self.create_stars_invoice_link_for_miniapp(
                user_id=user_id,
                title=plan["plan_name"],
                description=f"SaaS тариф аккаунта {plan_code} на {periods} период(ов)",  # при желании тоже вынести в Texts
                payload=payload,
                currency="XTR",
                amount_stars=total_amount,
            )
        except Exception:
            logger.exception("handle_billing_confirm_plan: create_invoice_link error")
            await callback.answer(texts.billing_invoice_create_error, show_alert=True)
            return

        await self.db.update_billing_invoice_link_and_payload(
            invoice_id=invoice_id,
            payload=payload,
            invoice_link=invoice_link,
        )

        text = (
            texts.billing_confirm_title.format(plan_name=plan["plan_name"]) + "\n"
            + texts.billing_confirm_periods.format(periods=periods) + "\n"
            + texts.billing_confirm_total.format(total_amount=total_amount) + "\n\n"
            + texts.billing_confirm_pay_hint + "\n"
            + texts.billing_confirm_after_pay
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.billing_button_pay_stars,
                        url=invoice_link,
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=texts.billing_button_back_plans,
                        callback_data="billing_menu",
                    )
                ],
            ]
        )

        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()



    async def handle_pre_checkout_query(self, pre_checkout_query: PreCheckoutQuery):
        """
        Обязательный шаг для Telegram Payments:
        бот должен подтвердить pre_checkout_query за несколько секунд,
        иначе платёж будет отменён с ошибкой "Время ожидания ответа от бота истекло".
        """
        logger.info(
            "PRE_CHECKOUT: id=%s from=%s total_amount=%s currency=%s payload=%r",
            pre_checkout_query.id,
            pre_checkout_query.from_user.id if pre_checkout_query.from_user else None,
            pre_checkout_query.total_amount,
            pre_checkout_query.currency,
            pre_checkout_query.invoice_payload,
        )
        try:
            # здесь можно делать дополнительные проверки (валидность payload, сумма и т.п.)
            await self.bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=True,
            )
            logger.info("PRE_CHECKOUT answered OK: id=%s", pre_checkout_query.id)
        except Exception as e:
            logger.exception("Failed to answer pre_checkout_query: %s", e)
            # в случае ошибки можно явно отклонить
            try:
                await self.bot.answer_pre_checkout_query(
                    pre_checkout_query.id,
                    ok=False,
                    error_message="Оплата сейчас недоступна, попробуйте позже.",
                )
            except Exception:
                pass

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

        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
                return

        await self.cmd_add_bot(message, user_id=user_id)

    async def cmd_add_bot(self, message: Message, user_id: int):
        """Handle add bot command (общая логика)"""
        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
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
        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
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
        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
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
        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
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
        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
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


    async def check_worker_token_health(self, instance_id: str) -> tuple[bool, str]:
        """
        Проверяет, что токен воркера валиден и бот отвечает.
        Возвращает (ok, reason).
        """
        # 1) достаём текущий токен из БД (учитывая, что он мог измениться)
        token = await self.db.get_decrypted_token(instance_id)
        if not token:
            return False, "no_token"

        # 2) быстрая валидация формата
        if not self.validate_token_format(token):
            return False, "bad_format"

        test_bot = Bot(token=token)
        try:
            me = await test_bot.get_me()
        except TelegramUnauthorizedError:
            # токен сменили / отозвали
            return False, "unauthorized"
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
        """Entry-поинт для /list_bots"""
        user_id = message.from_user.id

        # Single-tenant режим: доступ только владельцу
        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
                return

        await self.cmd_list_bots(message, user_id=user_id)

    async def cmd_list_bots(self, message: Message, user_id: int):
        """List user's bots"""
        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
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
                        text=texts.master_menu_billing,
                        callback_data="billing_menu",
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
        """Start webhook server (только master_webhook + health)"""
        app = web.Application()

        # Webhook endpoint for master bot
        app.router.add_post("/master_webhook", self.handle_master_webhook)

        # Health check endpoint
        app.router.add_get("/health", self.health_check)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, "0.0.0.0", self.webhook_port)
        await site.start()

        logger.info(f"Webhook server started on port {self.webhook_port}")

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

    async def monitor_workers(self, interval: int = 600) -> None:
        """
        Периодически проверяет все инстансы из БД (running + error и т.д.).
        """
        while True:
            all_instances = await self.db.get_all_instances_for_monitor()

            logger.info(
                "monitor_workers: checking %s instances",
                len(all_instances),
            )

            for instance in all_instances:
                instance_id = instance.instance_id

                process_alive = self.is_worker_process_alive(instance_id)
                token_ok, token_reason = await self.check_worker_token_health(instance_id)

                logger.info(
                    "monitor_workers: %s status=%s process_alive=%s token_ok=%s reason=%s",
                    instance_id, instance.status, process_alive, token_ok, token_reason,
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

                    continue

                # авторестарт только для running
                if instance.status == InstanceStatus.RUNNING and not process_alive:
                    logger.error("Worker %s process is dead", instance_id)

                    token = await self.db.get_decrypted_token(instance_id)
                    if not token:
                        logger.error(
                            "Cannot respawn worker %s: no token in DB", instance_id
                        )
                        continue

                    try:
                        self.spawn_worker(instance_id, token)
                        logger.info(
                            "Respawned worker process for instance %s", instance_id
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to respawn worker %s: %s", instance_id, e
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
        """Load existing instances from database и запустить polling-воркеры"""
        instances = await self.db.get_all_active_instances()

        for instance in instances:
            token = await self.db.get_decrypted_token(instance.instance_id)
            if not token:
                logger.warning(f"Skipping instance {instance.instance_id} - no token")
                continue

            # На всякий случай удаляем старый webhook, если он был
            try:
                await self.webhook_manager.remove_webhook(token)
            except Exception as e:
                logger.warning(
                    f"Failed to remove webhook for {instance.instance_id}: {e}"
                )

            # Храним инстанс в памяти
            self.instances[instance.instance_id] = instance

            # Запускаем отдельный воркер-процесс
            try:
                self.spawn_worker(instance.instance_id, token)
                logger.info(
                    f"Loaded instance {instance.instance_id} ({instance.bot_username}) with polling worker"
                )
            except Exception as e:
                logger.error(
                    f"Failed to spawn worker for {instance.instance_id}: {e}"
                )
                instance.status = InstanceStatus.ERROR
                await self.db.update_instance_status(
                    instance.instance_id, InstanceStatus.ERROR
                )
                continue

        logger.info(f"Loaded {len(instances)} active instances")


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
