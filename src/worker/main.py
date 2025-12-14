import asyncio
import logging
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode, ChatType
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update,
    MessageEntity,
    BufferedInputFile,
)
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

import sys
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # /root/gracehub
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from shared import settings
from shared.database import MasterDatabase
from shared.rate_limiter import BotRateLimiter
from languages import LANGS

logger = logging.getLogger("worker")


def setup_logging() -> None:
    """
    Логируем в отдельный файл на инстанс, либо в общий logs/worker.log.
    """
    # Пытаемся использовать instance_id для имени файла
    instance_id = (
        getattr(settings, "WORKER_INSTANCE_ID", None)
        or os.getenv("WORKER_INSTANCE_ID", "unknown")
    )
    default_path = Path("logs") / f"worker_{instance_id}.log"

    log_file_str = getattr(settings, "LOG_FILE", None)
    log_path = Path(log_file_str) if log_file_str else default_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(
            logging, getattr(settings, "LOG_LEVEL", "INFO").upper(), logging.INFO
        ),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


class AdminStates(StatesGroup):
    """
    FSM-состояния для админских настроек.
    """

    wait_greeting = State()
    wait_autoreply = State()
    wait_blacklist_menu = State()
    wait_blacklist_add = State()
    wait_blacklist_remove = State()
    wait_blacklist_search = State()


class GraceHubWorker:
    """
    Отдельный воркер для одного инстанса бота.
    Работает через polling, хранит своё состояние в отдельной SQLite-БД.
    """

    STATUS_EMOJI: Dict[str, str] = {
        "new": "⬜️",
        "inprogress": "🟨",
        "answered": "🟩",
        "escalated": "🟥",
        "closed": "🟦",
        "spam": "⬛️",
    }

    # допустимые статусы тикетов
    ALLOWED_TICKET_STATUSES = {"new", "inprogress", "answered", "escalated", "closed", "spam"}

    # верхние лимиты
    MAX_USER_TEXT = 4096     # сообщения в Telegram
    MAX_DB_TEXT = 2000       # тексты, которые пишем в БД

    @staticmethod
    def _safe_trim(text: str, limit: int) -> str:
        if text is None:
            return text
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def __init__(self, instance_id: str, token: str, db: MasterDatabase):
        self.instance_id = instance_id
        self.token = token
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.db: MasterDatabase = db
        self.ratelimiter = BotRateLimiter(self.token)
        self.shutdown_event = asyncio.Event()
        self.lang_code = "ru"
        self.texts = LANGS[self.lang_code]

        # Лимит вложений (из .env / settings)
        self.max_file_mb: int = getattr(settings, "WORKER_MAX_FILE_MB", 50)
        self.max_file_bytes: int = self.max_file_mb * 1024 * 1024

    async def load_language(self):
        code = await self.get_setting("lang_code") or "ru"
        if code not in LANGS:
            code = "ru"
        self.lang_code = code
        self.texts = LANGS[code]


    async def _check_file_size(self, file_id: str) -> bool:
        tg_file = await self.bot.get_file(file_id)
        size = getattr(tg_file, "file_size", None) or 0
        if size > self.max_file_bytes:
            return False
        return True

    @staticmethod
    async def global_error_handler(update: Update, exception: Exception) -> bool:
        user_id = None
        try:
            if update.message and update.message.from_user:
                user_id = update.message.from_user.id
            elif update.callback_query and update.callback_query.from_user:
                user_id = update.callback_query.from_user.id
        except Exception:
            pass

        logger.exception(
            "Unhandled error in worker update_id=%s user_id=%s exc=%r",
            getattr(update, "update_id", None),
            user_id,
            exception,
        )
        return True

        logger.exception(
            "Unhandled error in worker: instance_id=%s update_id=%s user_id=%s exc=%r",
            self.instance_id,
            getattr(update, "update_id", None),
            user_id,
            exception,
        )

        if isinstance(exception, TelegramBadRequest):
            return True

        return True


    async def init_database(self) -> None:
        # master_db уже инициализирован и передан в конструктор
        # здесь только дефолты настроек для конкретного инстанса
        if await self.get_setting("admin_user_id") is None:
            await self.set_setting("admin_user_id", "0")

        if await self.get_setting("privacy_mode_enabled") is None:
            await self.set_setting("privacy_mode_enabled", "False")

        # язык по умолчанию
        if await self.get_setting("lang_code") is None:
            await self.set_setting("lang_code", "ru")

        # подгружаем выбранный язык в self.texts
        await self.load_language()

        # blacklist теперь в общей worker-схеме, отдельного CREATE не нужно
        logger.info(
            f"Worker DB initialized in Postgres for instance {self.instance_id}"
        )

    def get_rating_keyboard(self, ticket_id: int) -> InlineKeyboardMarkup:
        """
        Клавиатура для оценки работы специалиста.
        """
        emojis = ["👎🏻", "😑", "😊", "👍🏻", "🥳"]
        buttons = [
            InlineKeyboardButton(
                text=e,
                callback_data=f"rating:{ticket_id}:{e}",
            )
            for e in emojis
        ]
        return InlineKeyboardMarkup(
            inline_keyboard=[buttons]
        )


    # ====================== УТИЛИТЫ ======================
    async def handle_language_callback(self, cb: CallbackQuery, state: FSMContext) -> None:
        data = cb.data or ""

        # Открываем подменю выбора языка
        if data == "setup_language":
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=self.texts.language_ru_label,
                            callback_data="set_lang:ru",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=self.texts.language_en_label,
                            callback_data="set_lang:en",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=self.texts.language_es_label,
                            callback_data="set_lang:es",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=self.texts.language_hi_label,
                            callback_data="set_lang:hi",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=self.texts.language_zh_label,
                            callback_data="set_lang:zh",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=self.texts.back,
                            callback_data="main_menu",
                        )
                    ],
                ]
            )
            await cb.message.edit_text(
                self.texts.language_menu_title,
                reply_markup=kb,
            )
            await cb.answer()
            return

        # Обработка выбора конкретного языка
        if data.startswith("set_lang:"):
            code = data.split(":", 1)[1]

            if code not in LANGS:
                await cb.answer(self.texts.language_unknown_error, show_alert=True)
                return

            # сохраняем выбор в БД
            await self.set_setting("lang_code", code)

            # подгружаем словарь в self.texts
            await self.load_language()

            # уведомляем и возвращаем в админ-меню уже на новом языке
            await cb.answer(self.texts.language_updated_message)
            await cb.message.edit_text(
                self.texts.admin_panel_title,
                reply_markup=await self.get_admin_menu(),
            )
            return



    async def handle_forum_service_message(self, message: Message) -> None:
        """
        Удаляет сервисные сообщения вида '... изменил(а) название темы ...',
        оставляя чат чище.
        """
        # Только в супергруппах/форумных чатах
        if message.chat.type != ChatType.SUPERGROUP:
            return

        # Нас интересуют сервисные сообщения об изменении топика
        if not message.forum_topic_edited:
            return

        me = await self.bot.get_me()
        if not message.from_user or message.from_user.id != me.id:
            # Не наше системное сообщение — не трогаем
            return

        try:
            await self.bot.delete_message(
                chat_id=message.chat.id,
                message_id=message.message_id,
            )
        except Exception as e:
            # Может не хватать прав / вышло 48 часов — просто логируем
            logger.error(
                "Failed to delete forum topic edit service message %s: %s",
                message.message_id,
                e,
            )


    async def is_admin(self, user_id: int) -> bool:
        admin = await self.get_setting("admin_user_id")
        return bool(admin) and str(user_id) == admin


    async def get_setting(self, key: str) -> Optional[str]:
        row = await self.db.fetchone(
            """
            SELECT value
            FROM worker_settings
            WHERE instance_id = %s AND key = %s
            """,
            (self.instance_id, key),
        )
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self.db.execute(
            """
            INSERT INTO worker_settings (instance_id, key, value)
            VALUES (%s, %s, %s)
            ON CONFLICT (instance_id, key)
            DO UPDATE SET value = EXCLUDED.value
            """,
            (self.instance_id, key, value),
        )

    async def get_openchat_settings(self) -> Dict:
        return {
            "enabled": (await self.get_setting("openchat_enabled")) == "True",
            "chat_id": int((await self.get_setting("general_panel_chat_id")) or 0) or 0,
            "username": (await self.get_setting("openchat_username")) or "",
        }

    async def is_privacy_enabled(self) -> bool:
        return (await self.get_setting("privacy_mode_enabled")) == "True"


    # ---------- Чёрный список: утилиты ----------

    def get_blacklist_view_menu(self, page: int = 0) -> InlineKeyboardMarkup:
        buttons: list[list[InlineKeyboardButton]] = []

        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(
                InlineKeyboardButton(
                    text=self.texts.blacklist_prev_page_button,
                    callback_data=f"bl_page:{page-1}",
                )
            )

        buttons.append(
            [
                InlineKeyboardButton(
                    text=self.texts.blacklist_search_button,
                    callback_data="blacklist_search",
                )
            ]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text=self.texts.blacklist_back_to_menu_button,
                    callback_data="blacklist",
                )
            ]
        )

        if nav_row:
            buttons.insert(0, nav_row)

        return InlineKeyboardMarkup(inline_keyboard=buttons)


    async def render_blacklist_page(
        self,
        cb: CallbackQuery,
        page: int = 0,
        per_page: int = 10,
    ) -> None:
        bl = await self.get_blacklist()
        total = len(bl)

        if total == 0:
            text = self.texts.blacklist_list_empty
            text = self._safe_trim(text, self.MAX_USER_TEXT)
            kb = self.get_blacklist_menu()
            await cb.message.edit_text(text, reply_markup=kb)
            return

        start = page * per_page
        end = start + per_page
        page_items = bl[start:end]

        lines: list[str] = []
        for u in page_items:
            label = f"@{u['username']}" if u["username"] else ""
            lines.append(f"<code>{u['user_id']}</code> {label}")

        total_pages = max(1, (total + per_page - 1) // per_page)
        text = (
            self.texts.blacklist_list_title
            + "\n".join(lines)
            + self.texts.blacklist_page_suffix.format(
                current=page + 1,
                total=total_pages,
            )
        )

        text = self._safe_trim(text, self.MAX_USER_TEXT)

        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(
                InlineKeyboardButton(
                    text=self.texts.blacklist_prev_page_button,
                    callback_data=f"bl_page:{page-1}",
                )
            )
        if end < total:
            nav_row.append(
                InlineKeyboardButton(
                    text=self.texts.blacklist_next_page_button,
                    callback_data=f"bl_page:{page+1}",
                )
            )

        kb_rows: list[list[InlineKeyboardButton]] = []
        if nav_row:
            kb_rows.append(nav_row)

        kb_rows.append(
            [
                InlineKeyboardButton(
                    text=self.texts.blacklist_search_button,
                    callback_data="blacklist_search",
                )
            ]
        )
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text=self.texts.blacklist_back_to_menu_button,
                    callback_data="blacklist",
                )
            ]
        )

        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await cb.message.edit_text(text, reply_markup=kb)



    async def is_user_blacklisted(self, user_id: int) -> bool:
        row = await self.db.fetchone(
            """
            SELECT 1
            FROM autoreply_log
            WHERE instance_id = %s AND user_id = %s
            LIMIT 1
            """,
            (self.instance_id, user_id),
        )
        return row is not None


    async def add_to_blacklist(self, user_id: int, username: str) -> None:
        now = datetime.now(timezone.utc)

        # логируем факт в autoreply_log (история / совместимость)
        await self.db.execute(
            """
            INSERT INTO autoreply_log (instance_id, user_id, date)
            VALUES (%s, %s, %s)
            ON CONFLICT (instance_id, user_id, date) DO NOTHING
            """,
            (self.instance_id, user_id, now.date()),
        )

        # сохраняем пользователя в основной таблице blacklist
        await self.db.execute(
            """
            INSERT INTO blacklist (instance_id, user_id, username, added_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (instance_id, user_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                added_at = EXCLUDED.added_at
            """,
            (self.instance_id, user_id, username or None, now),
        )

        # помечаем тикеты как spam
        try:
            await self.db.execute(
                """
                UPDATE tickets
                   SET status     = 'spam',
                       updated_at = %s
                 WHERE instance_id = %s AND user_id = %s
                """,
                (now, self.instance_id, user_id),
            )
        except Exception as e:
            logger.error(
                f"Failed to mark tickets as spam for blacklisted user {user_id}: {e}"
            )


    async def remove_from_blacklist(self, user_id: int) -> None:
        if not self.db:
            return
        await self.db.execute(
            """
            DELETE FROM blacklist
            WHERE instance_id = %s AND user_id = %s
            """,
            (self.instance_id, user_id),
        )


    async def get_blacklist(self) -> List[Dict[str, Any]]:
        if not self.db:
            return []

        rows = await self.db.fetchall(
            """
            SELECT user_id, username, added_at
            FROM blacklist
            WHERE instance_id = %s
            ORDER BY added_at DESC
            """,
            (self.instance_id,),
        )

        result: List[Dict[str, Any]] = []
        for r in rows:
            result.append(
                {
                    "user_id": r[0],
                    "username": r[1],
                    "added_at": r[2],
                }
            )
        return result


    async def _send_safe_message(
        self,
        *,
        chat_id: int,
        text: str,
        **kwargs: Any,
    ) -> Message:
        return await self.bot.send_message(
            chat_id,
            text,
            protect_content=await self.is_privacy_enabled(),
            **kwargs,
        )

    async def _send_safe_photo(
        self,
        *,
        chat_id: int,
        file_id: str,
        **kwargs: Any,
    ) -> Message:
        return await self.bot.send_photo(
            chat_id,
            file_id,
            protect_content=await self.is_privacy_enabled(),
            **kwargs,
        )

    async def _send_safe_document(
        self,
        *,
        chat_id: int,
        file_id: str,
        **kwargs: Any,
    ) -> Message:
        return await self.bot.send_document(
            chat_id,
            file_id,
            protect_content=await self.is_privacy_enabled(),
            **kwargs,
        )

    async def _send_safe_video(
        self,
        *,
        chat_id: int,
        file_id: str,
        **kwargs: Any,
    ) -> Message:
        return await self.bot.send_video(
            chat_id,
            file_id,
            protect_content=await self.is_privacy_enabled(),
            **kwargs,
        )

    async def _send_safe_audio(
        self,
        *,
        chat_id: int,
        file_id: str,
        **kwargs: Any,
    ) -> Message:
        return await self.bot.send_audio(
            chat_id,
            file_id,
            protect_content=await self.is_privacy_enabled(),
            **kwargs,
        )

    async def _send_safe_voice(
        self,
        *,
        chat_id: int,
        file_id: str,
        **kwargs: Any,
    ) -> Message:
        return await self.bot.send_voice(
            chat_id,
            file_id,
            protect_content=await self.is_privacy_enabled(),
            **kwargs,
        )

    async def _send_safe_sticker(
        self,
        *,
        chat_id: int,
        file_id: str,
        **kwargs: Any,
    ) -> Message:
        return await self.bot.send_sticker(
            chat_id,
            file_id,
            protect_content=await self.is_privacy_enabled(),
            **kwargs,
        )

    async def get_admin_menu(self) -> InlineKeyboardMarkup:
        # Автоответы
        autoreply_enabled = await self.get_setting("autoreply_enabled")
        autoreply_on = autoreply_enabled == "True"
        autoreply_label = f"{self.texts.menu_autoreply}: {'🟢' if autoreply_on else '🔴'}"

        # Privacy Mode
        privacy_on = await self.is_privacy_enabled()
        privacy_label = f"Privacy Mode: {'🟢' if privacy_on else '🔴'}"

        # Язык
        lang_code = await self.get_setting("lang_code") or "ru"
        lang_label = f"{self.texts.menu_language}: {lang_code.upper()}"

        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=self.texts.menu_greeting,
                        callback_data="edit_greeting",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=autoreply_label,
                        callback_data="setup_autoreply",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=self.texts.menu_export_users,
                        callback_data="export_users",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=self.texts.menu_blacklist,
                        callback_data="blacklist",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=privacy_label,
                        callback_data="setup_privacy",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=lang_label,
                        callback_data="setup_language",
                    )
                ],
            ]
        )

    def get_blacklist_menu(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=self.texts.blacklist_btn_add,
                        callback_data="blacklist_add",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=self.texts.blacklist_btn_remove,
                        callback_data="blacklist_remove",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=self.texts.blacklist_btn_show,
                        callback_data="blacklist_show",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=self.texts.blacklist_btn_back,
                        callback_data="main_menu",
                    )
                ],
            ]
        )

    # ====================== МАППИНГ РЕПЛАЕВ ======================

    async def save_reply_mapping_v2(
        self,
        chat_id: int,
        message_id: int,
        target_user_id: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        await self.db.execute(
            """
            INSERT INTO admin_reply_map_v2 (instance_id, chat_id, admin_message_id, target_user_id, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (instance_id, chat_id, admin_message_id)
            DO UPDATE SET target_user_id = EXCLUDED.target_user_id,
                          created_at     = EXCLUDED.created_at
            """,
            (self.instance_id, chat_id, message_id, target_user_id, now),
        )


    async def get_target_user_by_admin_message(
        self,
        chat_id: int,
        admin_message_id: int,
    ) -> Optional[int]:
        row = await self.db.fetchone(
            """
            SELECT target_user_id
            FROM admin_reply_map_v2
            WHERE instance_id = %s AND chat_id = %s AND admin_message_id = %s
            """,
            (self.instance_id, chat_id, admin_message_id),
        )
        return int(row["target_user_id"]) if row else None


    # ====================== ТИКЕТЫ / OPENCHAT ======================

    def _format_ticket_title(self, ticket: Dict[str, Any]) -> str:
        """
        Собирает название темы тикета с учетом статуса и назначенного исполнителя.
        """
        status = ticket.get("status") or "new"
        emoji = self.STATUS_EMOJI.get(status, "⬜️")

        user_label = ticket.get("username") or f"user {ticket.get('user_id')}"
        assignee = ticket.get("assigned_username")

        if assignee:
            if not assignee.startswith("@"):
                assignee = f"@{assignee}"
            return f"{emoji} #{ticket.get('id')} {user_label} • {assignee}"
        return f"{emoji} #{ticket.get('id')} {user_label}"


    async def update_ticket_topic_title(self, ticket: Dict[str, Any]) -> None:
        """
        Обновляет название форумной темы по данным тикета.
        """
        thread_id = ticket.get("thread_id")   # было "threadid"
        chat_id = ticket.get("chat_id")
        if not thread_id or not chat_id:
            return

        try:
            await self.bot.edit_forum_topic(
                chat_id=chat_id,
                message_thread_id=thread_id,
                name=self._format_ticket_title(ticket),
            )
        except Exception as e:
            logger.error(
                "Failed to update topic title for ticket %s: %s",
                ticket.get("id"),
                e,
            )



    async def fetch_ticket(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        row = await self.db.fetchone(
            """
            SELECT *
            FROM tickets
            WHERE instance_id = %s AND id = %s
            """,
            (self.instance_id, ticket_id),
        )
        return dict(row) if row else None


    async def set_ticket_status(
        self,
        ticket_id: int,
        status: str,
        assigned_username: Optional[str] = None,
        assigned_user_id: Optional[int] = None,
    ) -> None:
        if status not in self.ALLOWED_TICKET_STATUSES:
            logger.warning(
                "Attempt to set invalid ticket status: %s (ticket_id=%s, instance_id=%s)",
                status,
                ticket_id,
                self.instance_id,
            )
            return

        now = datetime.now(timezone.utc)
        set_parts = ["status = %s", "updated_at = %s"]
        params: List[Any] = [status, now]

        if assigned_username is not None:
            set_parts.append("assigned_username = %s")
            params.append(assigned_username)
        if assigned_user_id is not None:
            set_parts.append("assigned_user_id = %s")
            params.append(assigned_user_id)
        if status == "closed":
            set_parts.append("closed_at = %s")
            params.append(now)

        params.extend([self.instance_id, ticket_id])

        sql = f"""
            UPDATE tickets
            SET {", ".join(set_parts)}
            WHERE instance_id = %s AND id = %s
        """
        await self.db.execute(sql, tuple(params))

        ticket = await self.fetch_ticket(ticket_id)
        if ticket:
            # обновляем заголовок темы
            await self.update_ticket_topic_title(ticket)

            # если только что закрыли — отправляем запрос оценки
            if status == "closed":
                try:
                    user_id = ticket.get("user_id")
                    if user_id:
                        await self._send_safe_message(
                            chat_id=user_id,
                            text=self.texts.ticket_closed_rating_request,
                            reply_markup=self.get_rating_keyboard(ticket_id),
                        )
                except Exception as e:
                    logger.error(
                        "Failed to send rating request for ticket %s: %s",
                        ticket_id,
                        e,
                    )

    async def handle_rating_callback(self, cb: CallbackQuery) -> None:
        data = cb.data or ""
        if not data.startswith("rating:"):
            return

        parts = data.split(":", 2)
        if len(parts) != 3:
            await cb.answer()
            return

        try:
            ticket_id = int(parts[1])
        except ValueError:
            await cb.answer()
            return

        rating_emoji = parts[2]

        ticket = await self.fetch_ticket(ticket_id)
        if not ticket:
            await cb.answer(self.texts.ticket_not_found, show_alert=True)
            return

        thread_id = ticket.get("thread_id")
        chat_id = ticket.get("chat_id")
        if not thread_id or not chat_id:
            await cb.answer()
            return

        # Пишем системное сообщение в топик
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=self.texts.rating_topic_message.format(emoji=rating_emoji),
                message_thread_id=thread_id,
            )
        except Exception as e:
            logger.error(
                "Failed to send rating message for ticket %s: %s",
                ticket_id,
                e,
            )

        # Обновляем текст сообщения с оценкой для пользователя
        try:
            if cb.message:
                await cb.message.edit_text(
                    self.texts.rating_thanks_edit,
                    reply_markup=None,
                )
        except Exception as e:
            logger.error(
                "Failed to edit rating prompt message for ticket %s: %s",
                ticket_id,
                e,
            )

        await cb.answer(self.texts.rating_thanks_alert)

    async def put_ticket_keyboard(
        self,
        ticket_id: int,
        message_id: int,
        *,
        compact: bool = True,
    ) -> None:
        ticket = await self.fetch_ticket(ticket_id)
        if not ticket or not self.db:
            return

        chat_id = ticket["chat_id"]
        status = ticket.get("status") or "new"
        is_spam = status == "spam"
        is_closed = status == "closed"
        can_close = status not in ("closed", "spam")

        if compact:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🖲",
                            callback_data=f"ticket:menu:{ticket_id}",
                        )
                    ]
                ]
            )
        else:
            kb = self._build_full_ticket_keyboard(
                ticket_id,
                can_close,
                is_spam=is_spam,
                is_closed=is_closed,
            )

        try:
            await self.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=kb,
            )
        except Exception as e:
            if "message is not modified" in str(e).lower():
                return
            logger.error(
                "Failed to attach ticket keyboard to message %s: %s",
                message_id,
                e,
            )

    def _build_full_ticket_keyboard(
        self,
        ticket_id: int,
        can_close: bool,
        *,
        is_spam: bool = False,
        is_closed: bool = False,
    ) -> InlineKeyboardMarkup:
        """
        Строит полное меню тикета.
        Для spam: 'Не спам' + 'Свернуть'.
        Для closed: 'Переоткрыть' + 'Свернуть'.
        Для обычного: Себе / Назначить / Спам / Закрыть + 'Свернуть'.
        """
        buttons: List[List[InlineKeyboardButton]] = []

        if is_spam:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=self.texts.ticket_btn_not_spam,
                        callback_data=f"ticket:not_spam:{ticket_id}",
                    )
                ]
            )
        elif is_closed:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=self.texts.ticket_btn_reopen,
                        callback_data=f"ticket:reopen:{ticket_id}",
                    )
                ]
            )
        else:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=self.texts.ticket_btn_self,
                        callback_data=f"ticket:self:{ticket_id}",
                    ),
                    InlineKeyboardButton(
                        text=self.texts.ticket_btn_assign,
                        callback_data=f"ticket:assign:{ticket_id}",
                    ),
                ]
            )
            row_spam: List[InlineKeyboardButton] = [
                InlineKeyboardButton(
                    text=self.texts.ticket_btn_spam,
                    callback_data=f"ticket:spam:{ticket_id}",
                )
            ]
            if can_close:
                row_spam.append(
                    InlineKeyboardButton(
                        text=self.texts.ticket_btn_close,
                        callback_data=f"ticket:close:{ticket_id}",
                    )
                )
            buttons.append(row_spam)

        # Кнопка свернуть назад в 🖲
        buttons.append(
            [
                InlineKeyboardButton(
                    text=self.texts.ticket_btn_compact,
                    callback_data=f"ticket:compact:{ticket_id}",
                )
            ]
        )

        return InlineKeyboardMarkup(inline_keyboard=buttons)


    async def fetch_ticket_by_chat(
        self,
        chat_id: int,
        username: str,
        user_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Найти существующий тикет для пользователя в привязанном чате.
        """
        if not self.db:
            return None

        if username:
            row = await self.db.fetchone(
                """
                SELECT *
                FROM tickets
                WHERE instance_id = %s AND chat_id = %s AND username = %s
                """,
                (self.instance_id, chat_id, username),
            )
        else:
            row = await self.db.fetchone(
                """
                SELECT *
                FROM tickets
                WHERE instance_id = %s AND chat_id = %s AND user_id = %s
                """,
                (self.instance_id, chat_id, user_id),
            )

        if not row:
            return None

        # row уже DictCursor, можно просто dict(row)
        return dict(row)


    async def ensure_ticket_for_user(
        self,
        chat_id: int,
        user_id: int,
        username: str,
    ) -> Dict[str, Any]:
        """
        Гарантирует наличие тикета в OpenChat для данного пользователя.
        Если тикет уже есть — возвращает его, иначе создаёт новый и топик.
        """

        # Пытаемся найти существующий тикет для этого пользователя в данном чате
        ticket = await self.fetch_ticket_by_chat(chat_id, username, user_id)
        if ticket:
            return ticket

        # === БИЛЛИНГ: проверяем лимит тикетов ===
        ok, reason = await self.db.increment_tickets_used(self.instance_id)
        if not ok:
            # здесь можно дифференцировать сообщения, пока сделаем простой лог
            logger.warning(
                "Ticket creation blocked by billing: instance=%s reason=%s user_id=%s",
                self.instance_id,
                reason,
                user_id,
            )
            # Ничего не создаём. Выше по стеку ты можешь отреагировать:
            # либо отправить пользователю поясняющее сообщение, либо тихо игнорировать.
            # Для совместимости вернём пустой словарь.
            return {
                "id": None,
                "user_id": user_id,
                "username": username,
                "chat_id": chat_id,
                "thread_id": None,
                "status": "billing_blocked",
                "assigned_username": None,
                "assigned_user_id": None,
                "billing_reason": reason,
            }

        now = datetime.now(timezone.utc)

        # Создаём базовый тикет в Postgres
        row = await self.db.fetchone(
            """
            INSERT INTO tickets (
                instance_id,
                user_id,
                username,
                chat_id,
                status,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, 'new', %s, %s)
            RETURNING id
            """,
            (self.instance_id, user_id, username, chat_id, now, now),
        )
        ticket_id = row["id"]

        # Пытаемся создать форумный топик под этого пользователя
        thread_id = None
        user_label = username or f"user {user_id}"
        title = f"{ticket_id} · {user_label}"

        try:
            ft = await self.bot.create_forum_topic(chat_id, name=title)
            thread_id = ft.message_thread_id
            await self.db.execute(
                """
                UPDATE tickets
                   SET thread_id = %s, updated_at = %s
                 WHERE instance_id = %s AND id = %s
                """,
                (thread_id, now, self.instance_id, ticket_id),
            )
        except Exception as e:
            logger.error(f"Failed to create forum topic for ticket {ticket_id}: {e}")
            thread_id = None

        ticket = {
            "id": ticket_id,
            "user_id": user_id,
            "username": username,
            "chat_id": chat_id,
            "thread_id": thread_id,
            "status": "new",
            "assigned_username": None,
            "assigned_user_id": None,
        }

        return ticket


    # ====================== НОВАЯ ЛОГИКА: КЛАВА ТОЛЬКО НА ПОСЛЕДНЕМ ======================

    async def _clear_ticket_keyboards_for_user(
        self,
        chat_id: int,
        user_id: int,
        exclude_message_id: int,
    ) -> None:
        """
        Убирает reply_markup у всех сообщений этого пользователя в данном OpenChat,
        кроме exclude_message_id. Использует таблицу messages, если она есть.
        """
        if not self.db:
            return

        try:
            rows = await self.db.fetchall(
                """
                SELECT message_id
                FROM messages
                WHERE instance_id = %s
                AND chat_id = %s
                AND user_id = %s
                AND direction = 'user_to_openchat'
                AND message_id <> %s
                """,
                (self.instance_id, chat_id, user_id, exclude_message_id),
            )

        except Exception as e:
            logger.error(f"Failed to fetch messages for clearing keyboards: {e}")
            return

        for (mid,) in rows:
            try:
                await self.bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=mid,
                    reply_markup=None,
                )
            except Exception:
                # Сообщения могли быть удалены/недоступны — игнорируем
                continue

    async def store_forwarded_message(self, chat_id: int, message: Message, user_id: int) -> None:
        text_content = None
        if message.text:
            text_content = self._safe_trim(message.text, self.MAX_DB_TEXT)
        elif message.caption:
            text_content = self._safe_trim(message.caption, self.MAX_DB_TEXT)

        try:
            await self.db.execute(
                """
                INSERT INTO messages (
                    instance_id, chat_id, message_id, user_id, direction, content
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (self.instance_id, chat_id, message.message_id, user_id, "user_to_openchat", text_content),
            )
        except Exception as e:
            logger.error(f"Failed to insert message into messages table: {e}")


    async def forward_to_openchat(self, message: Message) -> None:
        """
        Отправка входящего сообщения пользователя в привязанный OpenChat (в его топик)
        с сохранением маппинга для последующих реплеев администратора.
        """
        # Админа в OpenChat не форвардим
        if message.from_user and await self.is_admin(message.from_user.id):
            return

        # Чёрный список: если пользователь заблокирован — игнорируем
        if message.from_user and await self.is_user_blacklisted(message.from_user.id):
            try:
                await self._send_safe_message(
                    chat_id=message.chat.id,
                    text="❌ Вы заблокированы и не можете отправлять сообщения в поддержку.",
                )
            except Exception as e:
                logger.error(f"Failed to notify blacklisted user {message.from_user.id}: {e}")
            return

        oc = await self.get_openchat_settings()
        if not (oc["enabled"] and oc["chat_id"]):
            return

        if not self.db:
            return

        user_id = message.from_user.id
        username = message.from_user.username or ""
        chat_id = oc["chat_id"]

        # --- БИЛЛИНГ / ЛИМИТЫ ---
        ticket = await self.ensure_ticket_for_user(chat_id, user_id, username)

        # Если ensure_ticket_for_user вернул спец-статус блокировки биллингом
        if ticket.get("status") == "billing_blocked":
            reason = ticket.get("billing_reason")

            # Выбираем тексты для пользователя и владельцев по причине
            if reason == "limit_reached":
                user_text = getattr(
                    self.texts,
                    "billing_user_limit_reached_message",
                    "⚠️ Лимит обращений по текущему тарифу исчерпан. Попробуйте связаться с владельцами бота другими способами.",
                )
                owner_text = getattr(
                    self.texts,
                    "billing_owner_limit_reached_message",
                    "⚠️ Лимит тикетов по текущему тарифу исчерпан. Новые обращения не попадают в систему поддержки.",
                )
            elif reason == "expired":
                user_text = getattr(
                    self.texts,
                    "billing_user_demo_expired_message",
                    "⏳ Тестовый тариф этого бота закончился, новые обращения временно не принимаются.",
                )
                owner_text = getattr(
                    self.texts,
                    "billing_owner_demo_expired_message",
                    "⏳ Демо‑период бота закончился. Новые тикеты не создаются.",
                )
            else:  # 'no_billing' или иное
                user_text = getattr(
                    self.texts,
                    "billing_user_no_plan_message",
                    "⚠️ Для этого бота ещё не настроен тариф поддержки, новые обращения временно не принимаются.",
                )
                owner_text = getattr(
                    self.texts,
                    "billing_owner_no_plan_message",
                    "⚠️ Для этого бота не настроен активный тариф, обращения пользователей не доходят до системы поддержки.",
                )

            # Сообщение пользователю (обезличенное про владельцев)
            try:
                await self._send_safe_message(
                    chat_id=message.chat.id,
                    text=user_text,
                )
            except Exception as e:
                logger.error(
                    "Failed to notify user %s about billing limit (%s): %s",
                    user_id,
                    reason,
                    e,
                )

            # Сообщение владельцам/операторам в General‑топик
            try:
                if oc["enabled"] and oc["chat_id"]:
                    await self.bot.send_message(
                        oc["chat_id"],
                        owner_text,
                    )
            except Exception as e:
                logger.error(
                    "Failed to notify owners in General about billing limit for instance %s: %s",
                    self.instance_id,
                    e,
                )

            return

        thread_id = ticket.get("thread_id")
        header = username or f"user {user_id}"

        now = datetime.now(timezone.utc)

        sent: Optional[Message] = None

        async def _send_into_thread(thread: int) -> Message:
            if message.text:
                body = f"{header}:\n{message.text}"
                return await self.bot.send_message(
                    chat_id,
                    body,
                    message_thread_id=thread,
                )
            elif message.photo:
                caption = message.caption or ""
                cap = f"{header}:\n{caption}" if caption else header
                return await self.bot.send_photo(
                    chat_id,
                    message.photo[-1].file_id,
                    caption=cap,
                    message_thread_id=thread,
                )
            elif message.video:
                caption = message.caption or ""
                cap = f"{header}:\n{caption}" if caption else header
                return await self.bot.send_video(
                    chat_id,
                    message.video.file_id,
                    caption=cap,
                    message_thread_id=thread,
                )
            elif message.document:
                caption = message.caption or ""
                cap = f"{header}:\n{caption}" if caption else header
                return await self.bot.send_document(
                    chat_id,
                    message.document.file_id,
                    caption=cap,
                    message_thread_id=thread,
                )
            elif message.audio:
                caption = message.caption or ""
                cap = f"{header}:\n{caption}" if caption else header
                return await self.bot.send_audio(
                    chat_id,
                    message.audio.file_id,
                    caption=cap,
                    message_thread_id=thread,
                )
            elif message.voice:
                return await self.bot.send_voice(
                    chat_id,
                    message.voice.file_id,
                    caption=header,
                    message_thread_id=thread,
                )
            elif message.sticker:
                return await self.bot.send_sticker(
                    chat_id,
                    message.sticker.file_id,
                    message_thread_id=thread,
                )
            else:
                body = f"{header}: [{message.content_type}]"
                return await self.bot.send_message(
                    chat_id,
                    body,
                    message_thread_id=thread,
                )

        # Пытаемся отправить в текущий thread_id
        try:
            sent = await _send_into_thread(thread_id)
        except Exception as e:
            err_text = str(e).lower()
            if "message thread not found" in err_text or "message thread not found" in getattr(
                getattr(e, "message", ""), "lower", lambda: ""
            )():
                # Топик удалён — создаём новый и обновляем тикет
                try:
                    ft = await self.bot.create_forum_topic(
                        chat_id,
                        name=self._format_ticket_title(ticket),
                    )
                    new_thread_id = ft.message_thread_id
                    await self.db.execute(
                        """
                        UPDATE tickets
                           SET thread_id = %s, updated_at = %s
                         WHERE instance_id = %s AND id = %s
                        """,
                        (new_thread_id, now, self.instance_id, ticket["id"]),
                    )
                    ticket["thread_id"] = new_thread_id
                    thread_id = new_thread_id

                    sent = await _send_into_thread(new_thread_id)
                except Exception as e2:
                    logger.error(f"Failed to recreate forum topic for ticket {ticket['id']}: {e2}")
                    return
            else:
                logger.error(f"Failed to forward to OpenChat: Telegram server says - {e}")
                return

        # Сохраняем связь для корректного реплея админа клиенту
        if sent:
            # маппинг admin_message -> user
            await self.save_reply_mapping_v2(chat_id, sent.message_id, user_id)

            # сохраняем запись в messages о сообщении пользователя в OpenChat
            await self.store_forwarded_message(
                chat_id=chat_id,
                message=sent,
                user_id=user_id,
            )

            # сначала убираем клавиатуру со всех предыдущих сообщений этого пользователя
            await self._clear_ticket_keyboards_for_user(
                chat_id=chat_id,
                user_id=user_id,
                exclude_message_id=sent.message_id,
            )

            # затем вешаем компактную кнопку-меню только на последнее сообщение клиента
            await self.put_ticket_keyboard(ticket["id"], sent.message_id, compact=True)

        # Обновляем тайминги тикета
        try:
            await self.db.execute(
                """
                UPDATE tickets
                   SET last_user_msg_at = %s,
                       updated_at       = %s
                 WHERE instance_id = %s
                   AND id          = %s
                """,
                (now, now, self.instance_id, ticket["id"]),
            )

            current_status = ticket.get("status") or "new"
            if current_status in ("answered", "closed"):
                await self.set_ticket_status(ticket["id"], "inprogress")
        except Exception as e:
            logger.error(f"Failed to update ticket timestamps: {e}")



    # ====================== КОМАНДЫ ======================

    async def cmd_start(self, message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id

        admin_id = await self.get_setting("admin_user_id")
        # Автоматически назначаем первого пользователя админом (если ещё не задан)
        if not admin_id or admin_id in ("0", ""):
            await self.set_setting("admin_user_id", str(user_id))
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.you_are_admin_now,
            )

        # Общие настройки OpenChat для статуса
        oc = await self.get_openchat_settings()
        if oc["enabled"] and oc["chat_id"]:
            status_line_admin = self.texts.openchat_status_line_on
            status_line_user = self.texts.openchat_status_line_on
        else:
            status_line_admin = self.texts.openchat_status_line_off
            status_line_user = self.texts.openchat_status_line_off

        # Ветка для админа
        if await self.is_admin(user_id):
            me = await self.bot.get_me()
            bot_username = me.username or "bot"

            if not oc["enabled"]:
                # Для незанастроенного OpenChat показываем статус + подсказку по привязке
                await self._send_safe_message(
                    chat_id=message.chat.id,
                    text=(
                        f"{status_line_admin}\n"
                        f"{self.texts.menu_you_are_admin}\n\n"
                        + self.texts.openchat_setup_hint.format(
                            bot_username=bot_username
                        )
                    ),
                )
            else:
                # Основное админское сообщение с клавиатурой
                await self._send_safe_message(
                    chat_id=message.chat.id,
                    text=(
                        f"{status_line_admin}\n"
                        f"{self.texts.menu_you_are_admin}\n"
                        f"{self.texts.admin_panel_choose_section}"
                    ),
                    reply_markup=await self.get_admin_menu(),
                )
        else:
            # Ветка для обычного пользователя

            # Проверка на blacklist
            if await self.is_user_blacklisted(user_id):
                await self._send_safe_message(
                    chat_id=message.chat.id,
                    text=self.texts.you_are_blocked,
                )
                return

            # Пытаемся взять кастомное приветствие из настроек
            greeting = await self.get_setting("greeting_text")
            if not greeting or not greeting.strip():
                # Если админ ещё не задал приветствие — используем дефолтное из языковых текстов
                # (убедись, что такое поле есть в self.texts, либо поменяй имя)
                greeting = self.texts.default_greeting

            # Отправляем пользователю приветствие
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=greeting,
            )

    async def cmd_admin(self, message: Message, state: FSMContext) -> None:
        if not await self.is_admin(message.from_user.id):
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.access_denied,
            )
            return

        await state.clear()
        await self._send_safe_message(
            chat_id=message.chat.id,
            text=self.texts.admin_panel_title,
            reply_markup=await self.get_admin_menu(),
        )


    async def cmd_openchat_off(self, message: Message, state: FSMContext) -> None:
        """
        Отключение OpenChat из приватного чата.
        """
        if not await self.is_admin(message.from_user.id):
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.access_denied,
            )
            return

        # Гасим в worker settings
        await self.set_setting("openchat_enabled", "False")
        await self.set_setting("general_panel_chat_id", "")
        await self.set_setting("openchat_username", "")

        try:
            await self.db.execute(
                """
                INSERT INTO instance_meta (
                    instance_id,
                    openchat_username,
                    general_panel_chat_id,
                    openchat_enabled,
                    updated_at
                )
                VALUES (%s, NULL, NULL, %s, NOW())
                ON CONFLICT (instance_id) DO UPDATE
                SET openchat_username     = NULL,
                    general_panel_chat_id = NULL,
                    openchat_enabled      = EXCLUDED.openchat_enabled,
                    updated_at            = NOW()
                """,
                (
                    self.instance_id,
                    False,
                ),
            )
        except Exception as e:
            logger.error(f"Failed to update instance_meta (openchat off) for {self.instance_id}: {e}")

        await self._send_safe_message(
            chat_id=message.chat.id,
            text=self.texts.openchat_off_confirm,
        )

    async def cmd_bind_openchat(self, message: Message, state: FSMContext) -> None:
        """
        Привязка OpenChat из самого группового чата:
        /bind @bot_name_bot
        """
        user_id = message.from_user.id

        # Только админ инстанса может привязывать OpenChat
        if not await self.is_admin(user_id):
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.openchat_bind_only_owner,
            )
            return

        parts = (message.text or "").split()
        if len(parts) > 1:
            arg = parts[1].lstrip("@")
            me = await self.bot.get_me()
            if arg.lower() != (me.username or "").lower():
                await self._send_safe_message(
                    chat_id=message.chat.id,
                    text=self.texts.openchat_bind_usage_error,
                )
                return

        chat = message.chat

        # 1. Чат должен быть супергруппой
        if chat.type != ChatType.SUPERGROUP:
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.openchat_not_supergroup,
            )
            return

        # 2. Не должен иметь username
        if chat.username:
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.openchat_has_username.format(
                    chat_username=chat.username
                ),
            )
            return

        # 3. Должен быть включен форумный режим (topics)
        if not chat.is_forum:
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.openchat_no_forum,
            )
            return

        # Сохраняем в worker settings (как было)
        await self.set_setting("openchat_enabled", "True")
        await self.set_setting("general_panel_chat_id", str(chat.id))
        await self.set_setting("openchat_username", chat.username or "")

        # Дополнительно синхронизируем в master Postgres для mini-app (instance_meta)
        try:
            await self.db.execute(
                """
                INSERT INTO instance_meta (
                    instance_id,
                    openchat_username,
                    general_panel_chat_id,
                    openchat_enabled,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (instance_id) DO UPDATE
                  SET openchat_username     = EXCLUDED.openchat_username,
                      general_panel_chat_id = EXCLUDED.general_panel_chat_id,
                      openchat_enabled      = EXCLUDED.openchat_enabled,
                      updated_at            = NOW()
                """,
                (
                    self.instance_id,           # или self.instanceid, как у тебя реально называется
                    chat.username or None,
                    chat.id,
                    True,
                ),
            )
        except Exception as e:
            logger.error(
                f"Failed to upsert instance_meta for instance {self.instance_id}: {e}"
            )

        await self._send_safe_message(
            chat_id=message.chat.id,
            text=self.texts.openchat_bound_ok.format(chat_title=chat.title),
        )

    # ====================== CALLBACKS (ТИКЕТЫ) ======================

    async def handle_ticket_callback(self, cb: CallbackQuery) -> None:
        """
        Обработка callback'ов от клавиатуры тикетов:
        меню / Себе / Назначить / Спам / Не спам / Закрыть / Переоткрыть.
        """
        data = cb.data or ""
        if not data.startswith("ticket:"):
            return

        parts = data.split(":")
        if len(parts) < 3:
            await cb.answer()
            return

        action = parts[1]

        # Открыть полное меню из компактной кнопки 🖲
        if action == "menu":
            try:
                ticket_id = int(parts[2])
            except ValueError:
                await cb.answer()
                return

            ticket = await self.fetch_ticket(ticket_id)
            if not ticket:
                await cb.answer("Тикет не найден", show_alert=True)
                return

            status = ticket.get("status") or "new"
            can_close = status not in ("closed", "spam")
            is_spam = status == "spam"
            is_closed = status == "closed"

            kb = self._build_full_ticket_keyboard(
                ticket_id,
                can_close,
                is_spam=is_spam,
                is_closed=is_closed,
            )
            if cb.message:
                await cb.message.edit_reply_markup(reply_markup=kb)

            await cb.answer()
            return

        # Свернуть полное меню обратно в одну кнопку 🖲
        if action == "compact":
            try:
                ticket_id = int(parts[2])
            except ValueError:
                await cb.answer()
                return

            if cb.message:
                await self.put_ticket_keyboard(
                    ticket_id,
                    cb.message.message_id,
                    compact=True,
                )

            await cb.answer()
            return

        # Ниже — действия, требующие ticket_id и самого тикета
        try:
            ticket_id = int(parts[2])
        except ValueError:
            await cb.answer()
            return

        ticket = await self.fetch_ticket(ticket_id)
        if not ticket:
            await cb.answer("Тикет не найден", show_alert=True)
            return

        message = cb.message
        if not message:
            await cb.answer()
            return

        user = cb.from_user
        assignee_username = user.username or f"id{user.id}"

        # 1) "Себе"
        if action == "self":
            current_status = ticket.get("status") or "new"
            new_status = current_status
            if current_status == "new":
                new_status = "inprogress"

            await self.set_ticket_status(
                ticket_id,
                new_status,
                assigned_username=assignee_username,
                assigned_user_id=user.id,
            )
            # после действия сворачиваем меню
            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer("Тикет взят в работу")
            return

        # 2) "Назначить" — показать список других участников (админов) чата
        if action == "assign":
            members = await self.bot.get_chat_administrators(ticket["chat_id"])
            rows: List[List[InlineKeyboardButton]] = []

            for m in members:
                if m.user.is_bot or m.user.id == user.id:
                    continue
                label = (
                    f"@{m.user.username}"
                    if m.user.username
                    else m.user.full_name
                )
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=label,
                            callback_data=f"ticket:assign_to:{ticket_id}:{m.user.id}",
                        )
                    ]
                )
            if not rows:
                await cb.answer("Некого назначать", show_alert=True)
                return

            rows.append(
                [
                    InlineKeyboardButton(
                        text="Отмена",
                        callback_data=f"ticket:cancel_assign:{ticket_id}",
                    )
                ]
            )

            await message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
            )
            await cb.answer()
            return

        # 2a) Выбор конкретного исполнителя
        if action == "assign_to" and len(parts) == 4:
            try:
                assignee_id = int(parts[3])
            except ValueError:
                await cb.answer()
                return

            member = await self.bot.get_chat_member(ticket["chat_id"], assignee_id)
            target_username = member.user.username or f"id{member.user.id}"

            current_status = ticket.get("status") or "new"
            new_status = current_status
            if current_status == "new":
                new_status = "inprogress"

            await self.set_ticket_status(
                ticket_id,
                new_status,
                assigned_username=target_username,
                assigned_user_id=assignee_id,
            )
            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer(f"Назначено {target_username}")
            return

        # 2b) Отмена назначения
        if action == "cancel_assign":
            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer("Отменено")
            return

        # 3) "Спам" — пометить тикет как спам,
        # убрать возможность "Себе"/"Назначить", показать "Не спам"
        if action == "spam":
            await self.set_ticket_status(
                ticket_id,
                "spam",
                assigned_username=None,
                assigned_user_id=None,
            )
            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer("Отмечено как спам")
            return

        # 3a) "Не спам" — вернуть тикет из спама в работу с текущим админом
        if action == "not_spam":
            await self.set_ticket_status(
                ticket_id,
                "inprogress",
                assigned_username=assignee_username,
                assigned_user_id=user.id,
            )
            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer("Тикет возвращён из спама")
            return

        # 4) "Закрыть"
        if action == "close":
            await self.set_ticket_status(
                ticket_id,
                "closed",
                assigned_username=ticket.get("assigned_username"),
                assigned_user_id=ticket.get("assigned_user_id"),
            )
            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer("Тикет закрыт")
            return

        # 4a) "Переоткрыть"
        if action == "reopen":
            await self.set_ticket_status(
                ticket_id,
                "inprogress",
                assigned_username=assignee_username,
                assigned_user_id=user.id,
            )
            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer("Тикет переоткрыт")
            return

        await cb.answer()


    # ====================== CALLBACKS АДМИН-ПАНЕЛИ ======================

    async def handle_callback(self, cb: CallbackQuery, state: FSMContext) -> None:
        if not await self.is_admin(cb.from_user.id):
            await cb.answer(self.texts.access_denied, show_alert=True)
            return

        data = cb.data or ""

        if data == "edit_greeting":
            await state.set_state(AdminStates.wait_greeting)
            await cb.message.edit_text(
                self.texts.greeting_edit_prompt,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=self.texts.back,
                                callback_data="main_menu",
                            )
                        ]
                    ]
                ),
            )

        elif data == "setup_autoreply":
            await state.set_state(AdminStates.wait_autoreply)
            enabled = (
                self.texts.autoreply_state_on.format(
                    state=self.texts.autoreply_enabled_label
                    if await self.get_setting("autoreply_enabled") == "True"
                    else self.texts.autoreply_disabled_label
                )
            )
            await cb.message.edit_text(
                enabled,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=self.texts.back,
                                callback_data="main_menu",
                            )
                        ]
                    ]
                ),
            )

        elif data == "setup_openchat":
            openchat = await self.get_openchat_settings()
            status = self.texts.openchat_status_on if openchat["enabled"] else self.texts.openchat_status_off

            if openchat["chat_id"]:
                current = self.texts.openchat_current_chat_id.format(
                    chat_id=openchat["chat_id"]
                )
            else:
                current = self.texts.openchat_not_bound

            me = await self.bot.get_me()
            bot_username = me.username or "bot"
            await cb.message.edit_text(
                self.texts.openchat_now_status.format(
                    status=status,
                    current=current,
                    bot_username=bot_username,
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=self.texts.back,
                                callback_data="main_menu",
                            )
                        ]
                    ]
                ),
            )

        elif data == "setup_privacy":
            enabled = self.texts.privacy_state_on if await self.is_privacy_enabled() else self.texts.privacy_state_off
            await cb.message.edit_text(
                self.texts.privacy_screen.format(state=enabled),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=self.texts.privacy_toggle_btn,
                                callback_data="toggle_privacy",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text=self.texts.back,
                                callback_data="main_menu",
                            )
                        ],
                    ]
                ),
            )

        elif data == "toggle_privacy":
            current = await self.is_privacy_enabled()
            await self.set_setting("privacy_mode_enabled", "False" if current else "True")
            new_state = (
                self.texts.privacy_state_on if not current else self.texts.privacy_state_off
            )
            await cb.answer(
                self.texts.privacy_toggled.format(state=new_state),
                show_alert=False,
            )

            enabled = (
                self.texts.privacy_state_on if await self.is_privacy_enabled() else self.texts.privacy_state_off
            )
            await cb.message.edit_text(
                self.texts.privacy_screen.format(state=enabled),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=self.texts.privacy_toggle_btn,
                                callback_data="toggle_privacy",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text=self.texts.back,
                                callback_data="main_menu",
                            )
                        ],
                    ]
                ),
            )

        elif data == "blacklist":
            await state.set_state(AdminStates.wait_blacklist_menu)
            await cb.message.edit_text(
                self.texts.blacklist_title,
                reply_markup=self.get_blacklist_menu(),
            )

        elif data == "blacklist_add":
            await state.set_state(AdminStates.wait_blacklist_add)
            await cb.message.edit_text(
                self.texts.blacklist_add_prompt,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=self.texts.back,
                                callback_data="blacklist",
                            )
                        ]
                    ]
                ),
            )

        elif data == "blacklist_remove":
            await state.set_state(AdminStates.wait_blacklist_remove)
            await cb.message.edit_text(
                self.texts.blacklist_remove_prompt,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=self.texts.back,
                                callback_data="blacklist",
                            )
                        ]
                    ]
                ),
            )

        elif data == "blacklist_show":
            await self.render_blacklist_page(cb, page=0)

        elif data.startswith("bl_page:"):
            try:
                page = int(data.split(":", 1)[1])
            except ValueError:
                await cb.answer()
                return
            await self.render_blacklist_page(cb, page=page)

        elif data == "blacklist_search":
            await state.set_state(AdminStates.wait_blacklist_search)
            await cb.message.edit_text(
                self.texts.blacklist_search_prompt,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=self.texts.back,
                                callback_data="blacklist_show",
                            )
                        ]
                    ]
                ),
            )

        elif data == "export_users":
            await cb.answer(self.texts.export_preparing, show_alert=False)

            rows = await self.db.fetchall(
                """
                SELECT DISTINCT user_id, username, created_at
                FROM tickets
                WHERE instance_id = %s
                ORDER BY created_at ASC
                """,
                (self.instance_id,),
            )

            if not rows:
                await cb.message.answer(self.texts.export_no_users)
                return

            import io
            import csv
            from datetime import datetime as _dt

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["user_id", "username", "first_seen"])
            for r in rows:
                created = r["created_at"]
                if isinstance(created, _dt):
                    created = created.isoformat()
                writer.writerow([r["user_id"], r["username"] or "", created])

            data_bytes = buf.getvalue().encode("utf-8")
            file = BufferedInputFile(file=data_bytes, filename="users_export.csv")

            await cb.message.answer_document(
                document=file,
                caption=self.texts.export_users_caption,
            )

        elif data == "main_menu":
            await state.clear()

            openchat = await self.get_openchat_settings()
            if openchat["enabled"] and openchat["chat_id"]:
                status_line_admin = self.texts.openchat_status_line_on
            else:
                status_line_admin = self.texts.openchat_status_line_off

            me = await self.bot.get_me()
            bot_username = me.username or "bot"

            if not openchat["enabled"]:
                text = (
                    f"{status_line_admin}\n"
                    f"{self.texts.menu_you_are_admin}\n\n"
                    + self.texts.openchat_setup_hint.format(bot_username=bot_username)
                )
                reply_markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=self.texts.openchat_setup_button,
                                callback_data="setup_openchat",
                            )
                        ]
                    ]
                )
            else:
                text = (
                    f"{status_line_admin}\n"
                    f"{self.texts.menu_you_are_admin}\n"
                    f"{self.texts.admin_panel_choose_section}"
                )
                reply_markup = await self.get_admin_menu()

            await cb.message.edit_text(text, reply_markup=reply_markup)

        else:
            await cb.answer()


    # ====================== ОБРАБОТКА СОСТОЯНИЙ АДМИНА ======================

    async def handle_admin_blacklist_search(self, message: Message, state: FSMContext) -> None:
        if not await self.is_admin(message.from_user.id):
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="❌ Доступ запрещён",
            )
            return

        if not message.text:
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="Требуется текст для поиска.",
            )
            return

        query = message.text.strip().lstrip("@").lower()

        bl = await self.get_blacklist()
        results = [
            u
            for u in bl
            if (u["username"] or "").lower().find(query) != -1
        ]

        if not results:
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="Ничего не найдено в чёрном списке.",
            )
            return

        lines = []
        for u in results[:50]:
            label = f"@{u['username']}" if u["username"] else ""
            lines.append(f"<code>{u['user_id']}</code> {label}")

        text = (
            f"🔍 Результаты поиска по \"{query}\":\n"
            + "\n".join(lines)
        )
        if len(results) > 50:
            text += f"\n\nПоказаны первые 50 из {len(results)} записей."

        await state.set_state(AdminStates.wait_blacklist_menu)
        await self._send_safe_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=self.get_blacklist_menu(),
        )


    async def handle_admin_greeting(self, message: Message, state: FSMContext) -> None:
        if not await self.is_admin(message.from_user.id):
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="❌ Доступ запрещён",
            )
            return

        if message.text and message.text.strip() == "/clear_greeting":
            await self.set_setting("greeting_text", "")
            await state.clear()
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="✅ Приветствие удалено.",
            )
            return

        if not message.text:
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="Требуется текстовое сообщение с приветствием.",
            )
            return

        greeting = self._safe_trim(message.text, self.MAX_DB_TEXT)
        await self.set_setting("greeting_text", greeting)
        await state.clear()
        await self._send_safe_message(
            chat_id=message.chat.id,
            text="✅ Новое приветствие сохранено.",
        )

    async def handle_admin_autoreply(self, message: Message, state: FSMContext) -> None:
        if not await self.is_admin(message.from_user.id):
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="❌ Доступ запрещён",
            )
            return

        if message.text and message.text.strip() == "/autoreply_off":
            await self.set_setting("autoreply_enabled", "False")
            await self.set_setting("autoreply_text", "")
            await state.clear()
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="✅ Автоответы отключены.",
            )
            return

        if not message.text:
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="Отправьте текст автоответа или /autoreply_off.",
            )
            return

        autoreply = self._safe_trim(message.text, self.MAX_DB_TEXT)
        await self.set_setting("autoreply_enabled", "True")
        await self.set_setting("autoreply_text", autoreply)
        await state.clear()
        await self._send_safe_message(
            chat_id=message.chat.id,
            text="✅ Автоответ сохранён и включён.",
        )

    async def handle_admin_blacklist_add(self, message: Message, state: FSMContext) -> None:
        if not await self.is_admin(message.from_user.id):
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="❌ Доступ запрещён",
            )
            return

        if not message.text:
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="Требуется ID пользователя или username.",
            )
            return

        parts = message.text.strip().split()

        user_id: Optional[int] = None
        username: str = ""

        # Вариант 1: указан числовой ID (с опциональным username вторым аргументом)
        try:
            user_id = int(parts[0])
            if len(parts) > 1:
                username = parts[1].lstrip("@")
        except ValueError:
            # Вариант 2: нет ID, только username
            username = parts[0].lstrip("@")

        if user_id is None:
            # Пытаемся найти user_id по username в таблице tickets
            row = await self.db.fetchone(
                """
                SELECT DISTINCT user_id
                FROM tickets
                WHERE instance_id = %s AND username = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (self.instance_id, username),
            )
            if not row:
                await self._send_safe_message(
                    chat_id=message.chat.id,
                    text=f"Не удалось найти пользователя с username @{username} "
                         f"среди тикетов. Укажи numeric ID или верный username.",
                )
                return
            user_id = row["user_id"]

        await self.add_to_blacklist(user_id, username)

        await state.set_state(AdminStates.wait_blacklist_menu)
        await self._send_safe_message(
            chat_id=message.chat.id,
            text=f"✅ Пользователь <code>{user_id}</code> добавлен в чёрный список.",
            reply_markup=self.get_blacklist_menu(),
        )


    async def handle_admin_blacklist_remove(self, message: Message, state: FSMContext) -> None:
        if not await self.is_admin(message.from_user.id):
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="❌ Доступ запрещён",
            )
            return

        if not message.text:
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="Отправьте ID пользователя для удаления из чёрного списка.",
            )
            return

        try:
            user_id = int(message.text.strip())
        except ValueError:
            await self._send_safe_message(
                chat_id=message.chat.id,
                text="Некорректный формат. Укажите числовой ID пользователя.",
            )
            return

        if not await self.is_user_blacklisted(user_id):
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=f"Пользователь <code>{user_id}</code> не найден в чёрном списке.",
            )
            return

        await self.remove_from_blacklist(user_id)
        await state.set_state(AdminStates.wait_blacklist_menu)
        await self._send_safe_message(
            chat_id=message.chat.id,
            text=f"✅ Пользователь <code>{user_id}</code> удалён из чёрного списка.",
            reply_markup=self.get_blacklist_menu(),
        )

    # ====================== ОБРАБОТКА ПРИВАТНЫХ СООБЩЕНИЙ ======================

    @staticmethod
    def _has_bot_command(message: Message) -> bool:
        """
        Детектим наличие любой bot_command в entities,
        чтобы не эхоить /start, /admin и прочие команды.
        """
        if not message.entities:
            return False
        for ent in message.entities:
            if isinstance(ent, MessageEntity) and ent.type == "bot_command":
                return True
            if not isinstance(ent, MessageEntity) and getattr(ent, "type", None) == "bot_command":
                return True
        return False

    async def handle_private_message(self, message: Message, state: FSMContext) -> None:
        """
        Общий обработчик приватных сообщений пользователя.
        Команды игнорирует (их ловят cmd_start/cmd_admin).
        """
        # Не трогаем команды, чтобы не эхоить /admin и т.п.
        if self._has_bot_command(message):
            return

        user_id = message.from_user.id

        # Чёрный список
        if await self.is_user_blacklisted(user_id) and not await self.is_admin(user_id):
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.you_are_blocked,
            )
            return

        # Rate-limit на отправку ответов
        if not await self.ratelimiter.can_send(chat_id=message.chat.id):
            wait_for = await self.ratelimiter.wait_for_send()
            await asyncio.sleep(wait_for)

        # Если это админ
        if await self.is_admin(user_id):
            # Показываем админ-панель
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.admin_panel_title,
                reply_markup=await self.get_admin_menu(),
            )
            return

        # Валидация размеров вложений
        too_big = False
        max_bytes = self.max_file_bytes  # задаётся в __init__ из settings.WORKER_MAX_FILE_MB

        # Фото (берём максимально крупное)
        if message.photo:
            photo = message.photo[-1]
            if photo.file_size and photo.file_size > max_bytes:
                too_big = True

        # Документы
        if message.document and message.document.file_size and message.document.file_size > max_bytes:
            too_big = True

        # Видео
        if message.video and message.video.file_size and message.video.file_size > max_bytes:
            too_big = True

        # Аудио
        if message.audio and message.audio.file_size and message.audio.file_size > max_bytes:
            too_big = True

        # Голосовые
        if message.voice and message.voice.file_size and message.voice.file_size > max_bytes:
            too_big = True

        # Видео-заметки
        if message.video_note and message.video_note.file_size and message.video_note.file_size > max_bytes:
            too_big = True

        # Стикеры (если хочешь ограничивать и их)
        if message.sticker and message.sticker.file_size and message.sticker.file_size > max_bytes:
            too_big = True

        if too_big:
            logger.warning(
                "Attachment too large from user %s in private chat %s (limit %s bytes)",
                user_id,
                message.chat.id,
                max_bytes,
            )
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.attachment_too_big,  # строка должна быть в языковых файлах
            )
            return

        oc = await self.get_openchat_settings()

        # Если включён OpenChat и есть привязанный чат — шлём в топики
        if oc["enabled"] and oc["chat_id"]:
            try:
                await self.forward_to_openchat(message)
            except Exception as e:
                logger.error(f"Failed to forward to OpenChat: {e}")
            # Можно дополнительно прислать автоответ пользователю
            if await self.get_setting("autoreply_enabled") == "True":
                text = await self.get_setting("autoreply_text") or ""
                if text:
                    await self._send_safe_message(
                        chat_id=message.chat.id,
                        text=text,
                    )
            else:
                await self._send_safe_message(
                    chat_id=message.chat.id,
                    text=self.texts.message_forwarded_to_support,
                )
            return

        # Если OpenChat не настроен — информируем пользователя
        await self._send_safe_message(
            chat_id=message.chat.id,
            text=self.texts.support_not_configured,
        )


    # ====================== OPENCHAT: СОБЩЕНИЯ И РЕПЛАИ ======================

    async def handle_openchat_message(self, message: Message) -> None:
        """
        Обработка сообщений в чате OpenChat (супергруппа с темами).
        Интересуют только реплаи внутри привязанного чата.
        """
        oc = await self.get_openchat_settings()
        if not (oc["enabled"] and oc["chat_id"] and message.chat.id == oc["chat_id"]):
            return

        # Берём только ответы на сообщения (reply) — это сигнал ответа клиенту
        if not message.reply_to_message:
            return

        # Не обрабатываем собственные сообщения бота, чтобы не зациклиться
        if message.from_user and message.from_user.is_bot:
            return

        # Валидация размеров вложений от админов/операторов в OpenChat
        too_big = False
        max_bytes = self.max_file_bytes  # задаётся в __init__ из settings.WORKER_MAX_FILE_MB

        # Фото
        if message.photo:
            photo = message.photo[-1]
            if photo.file_size and photo.file_size > max_bytes:
                too_big = True

        # Документы
        if message.document and message.document.file_size and message.document.file_size > max_bytes:
            too_big = True

        # Видео
        if message.video and message.video.file_size and message.video.file_size > max_bytes:
            too_big = True

        # Аудио
        if message.audio and message.audio.file_size and message.audio.file_size > max_bytes:
            too_big = True

        # Голосовые
        if message.voice and message.voice.file_size and message.voice.file_size > max_bytes:
            too_big = True

        # Видео-заметки
        if message.video_note and message.video_note.file_size and message.video_note.file_size > max_bytes:
            too_big = True

        # Стикеры (если тоже ограничиваем)
        if message.sticker and message.sticker.file_size and message.sticker.file_size > max_bytes:
            too_big = True

        if too_big:
            logger.warning(
                "Attachment too large from openchat user %s in chat %s (limit %s bytes)",
                message.from_user.id if message.from_user else None,
                message.chat.id,
                max_bytes,
            )
            # В OpenChat обычно отвечаем только оператору, без текста пользователю
            # Можно отправить сервисное сообщение в этот же топик
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.attachment_too_big,
            )
            return

        await self.handle_openchat_reply(message, message.reply_to_message, oc)


    async def handle_openchat_reply(
        self, message: Message, reply_msg: Message, oc: Dict[str, Any]
    ) -> None:
        """
        Реплай админа в теме OpenChat → ответ клиенту в личку.
        """
        if not self.db:
            return

        # Находим, кому отвечаем, по сохранённому маппингу
        target_user_id = await self.get_target_user_by_admin_message(
            reply_msg.chat.id, reply_msg.message_id
        )
        if not target_user_id:
            # Нет маппинга — не знаем, кому отправлять
            return

        # Если пользователь в чёрном списке — сообщения к нему не отправляем
        if await self.is_user_blacklisted(target_user_id):
            return

        # Уважим rate limit перед исходящим
        if not await self.ratelimiter.can_send(chat_id=target_user_id):
            wait_for = await self.ratelimiter.wait_for_send()
            await asyncio.sleep(wait_for)

        # Пересылаем по типу контента с учётом Privacy Mode
        try:
            if message.text:
                await self._send_safe_message(
                    chat_id=target_user_id,
                    text=message.text,
                )
            elif message.photo:
                await self._send_safe_photo(
                    chat_id=target_user_id,
                    file_id=message.photo[-1].file_id,
                    caption=message.caption,
                )
            elif message.document:
                await self._send_safe_document(
                    chat_id=target_user_id,
                    file_id=message.document.file_id,
                    caption=message.caption,
                )
            elif message.video:
                await self._send_safe_video(
                    chat_id=target_user_id,
                    file_id=message.video.file_id,
                    caption=message.caption,
                )
            elif message.audio:
                await self._send_safe_audio(
                    chat_id=target_user_id,
                    file_id=message.audio.file_id,
                    caption=message.caption,
                )
            elif message.voice:
                await self._send_safe_voice(
                    chat_id=target_user_id,
                    file_id=message.voice.file_id,
                    caption=message.caption,
                )
            elif message.sticker:
                await self._send_safe_sticker(
                    chat_id=target_user_id,
                    file_id=message.sticker.file_id,
                )
            else:
                await self._send_safe_message(
                    chat_id=target_user_id,
                    text=f"[{message.content_type}]",
                )
        except Exception as e:
            logger.error(
                f"Failed to send OpenChat reply to user {target_user_id}: {e}"
            )
            return

        # Обновляем тайминги/статус тикета
        try:
            now = datetime.now(timezone.utc)

            ticket = await self.fetch_ticket_by_chat(
                oc["chat_id"], "", target_user_id
            )
            if not ticket:
                ticket = await self.ensure_ticket_for_user(
                    oc["chat_id"], target_user_id, ""
                )

            # Обновляем временные метки ответа админа
            await self.db.execute(
                """
                UPDATE tickets
                   SET last_admin_reply_at = %s,
                       updated_at          = %s
                 WHERE instance_id = %s
                   AND id          = %s
                """,
                (now, now, self.instance_id, ticket["id"]),
            )

            # Фиксируем статус "сотрудник ответил" (🟩)
            await self.set_ticket_status(ticket["id"], "answered")
        except Exception as e:
            logger.error(f"Failed to update ticket after admin reply: {e}")


    # ====================== АВТО-ЗАКРЫТИЕ ТИКЕТОВ ======================

    async def auto_close_tickets_loop(self) -> None:
        hours = int(getattr(settings, "AUTOCLOSE_HOURS", 24))
        while not self.shutdown_event.is_set():
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                rows = await self.db.fetchall(
                    """
                    SELECT id
                    FROM tickets
                    WHERE instance_id = %s
                      AND status IN ('inprogress', 'answered')
                      AND last_admin_reply_at IS NOT NULL
                      AND (
                          last_user_msg_at IS NULL
                          OR last_user_msg_at < %s
                      )
                    """,
                    (self.instance_id, cutoff),
                )
                if rows:
                    for ticket_id, in rows:
                        await self.set_ticket_status(ticket_id, "closed")
                    logger.info(f"Auto-closed {len(rows)} tickets")
            except Exception as e:
                logger.error(f"Auto-close error: {e}")
            await asyncio.sleep(3600)


    # ====================== РЕГИСТРАЦИЯ ХЭНДЛЕРОВ ======================
    def register_handlers(self) -> None:
        # Сервиска про изменение темы
        self.dp.message.register(
            self.handle_forum_service_message,
            F.forum_topic_edited,
        )

        # Callback'и тикетной клавиатуры
        self.dp.callback_query.register(
            self.handle_ticket_callback,
            F.data.startswith("ticket:"),
        )

        # Оценка
        self.dp.callback_query.register(
            self.handle_rating_callback,
            F.data.startswith("rating:"),
        )

        # Команды в приватке
        self.dp.message.register(
            self.cmd_start,
            CommandStart(),
            F.chat.type == ChatType.PRIVATE,
        )
        self.dp.message.register(
            self.cmd_admin,
            Command("admin"),
            F.chat.type == ChatType.PRIVATE,
        )
        self.dp.message.register(
            self.cmd_openchat_off,
            Command("openchat_off"),
            F.chat.type == ChatType.PRIVATE,
        )

        # Привязка OpenChat из группы/супергруппы
        self.dp.message.register(
            self.cmd_bind_openchat,
            Command("bind"),
            (F.chat.type == ChatType.SUPERGROUP) | (F.chat.type == ChatType.GROUP),
        )

        # Задаём язык (ИСПОЛЬЗУЕМ self.dp)
        self.dp.callback_query.register(
            self.handle_language_callback,
            F.data.in_(["setup_language"]) | F.data.startswith("set_lang:"),
        )

        # OpenChat: обработка сообщений в супергруппе (для реплеев)
        self.dp.message.register(
            self.handle_openchat_message,
            F.chat.type == ChatType.SUPERGROUP,
        )

        # Callback'и админ-панели
        self.dp.callback_query.register(self.handle_callback)

        # Состояния админ-панели
        self.dp.message.register(
            self.handle_admin_blacklist_search,
            StateFilter(AdminStates.wait_blacklist_search),
            F.chat.type == ChatType.PRIVATE,
        )
        self.dp.message.register(
            self.handle_admin_greeting,
            StateFilter(AdminStates.wait_greeting),
            F.chat.type == ChatType.PRIVATE,
        )
        self.dp.message.register(
            self.handle_admin_autoreply,
            StateFilter(AdminStates.wait_autoreply),
            F.chat.type == ChatType.PRIVATE,
        )
        self.dp.message.register(
            self.handle_admin_blacklist_add,
            StateFilter(AdminStates.wait_blacklist_add),
            F.chat.type == ChatType.PRIVATE,
        )
        self.dp.message.register(
            self.handle_admin_blacklist_remove,
            StateFilter(AdminStates.wait_blacklist_remove),
            F.chat.type == ChatType.PRIVATE,
        )

        # Общий обработчик приватных сообщений
        self.dp.message.register(
            self.handle_private_message,
            F.chat.type == ChatType.PRIVATE,
        )
        # Общий для ошибок
        self.dp.errors.register(GraceHubWorker.global_error_handler)

    # ====================== ЗАПУСК / ИНТЕГРАЦИЯ ======================

    async def process_update(self, update: Update) -> None:
        """
        Доп. метод, если вдруг захочется кормить воркер апдейтами вручную.
        В polling-режиме, по сути, не нужен, но оставлен для совместимости.
        """
        await self.dp.feed_update(self.bot, update)

    async def run(self) -> None:
        """
        Старт воркера: инициализация БД, запуск автозакрытия и polling.
        """
        await self.init_database()
        self.register_handlers()  # <<< ВОТ ЭТОГО СЕЙЧАС НЕ ХВАТАЕТ
        logger.info(f"Worker started for instance {self.instance_id}")

        asyncio.create_task(self.auto_close_tickets_loop())

        try:
            await self.bot.delete_webhook(drop_pending_updates=True)
        except Exception as e:
            logger.warning(f"Failed to delete webhook: {e}")

        try:
            await self.dp.start_polling(self.bot)
        finally:
            self.shutdown_event.set()
            await self.bot.session.close()
            if self.db:
                self.db.close()



async def main() -> None:
    setup_logging()

    instance_id = getattr(settings, "WORKER_INSTANCE_ID", None) or os.getenv("WORKERINSTANCEID")
    token = getattr(settings, "WORKER_TOKEN", None) or os.getenv("WORKERTOKEN")

    if not instance_id or not token:
        logger.error("WORKER_INSTANCE_ID and WORKER_TOKEN must be set")
        return

    db = MasterDatabase()
    # ВАЖНО: инициализируем соединение и схемы
    await db.init()

    worker = GraceHubWorker(instance_id=instance_id, token=token, db=db)

    try:
        await worker.run()
    except asyncio.CancelledError:
        logger.info("Worker cancelled, shutting down...")
    except Exception as e:
        logger.exception(f"Worker crashed: {e}")



if __name__ == "__main__":
    asyncio.run(main())