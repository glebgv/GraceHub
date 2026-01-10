# creator GraceHub Tg: @Gribson_Micro

import asyncio
import logging
import os
import sys
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    Update,
)

from languages import LANGS
from shared import settings
from shared.database import MasterDatabase
from shared.rate_limiter import BotRateLimiter

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # /root/gracehub
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

logger = logging.getLogger("worker")


def setup_logging():
    """🔥 НОВЫЙ setup_logging - НЕ использует ENV токены!"""
    # 🔥 Парсим instance_id ИЗ HOSTNAME (даже при импорте)
    import os
    hostname = os.uname().nodename
    import re
    match = re.match(r"gracehub-worker-([a-zA-Z0-9_-]+)", hostname)
    instance_id = match.group(1) if match else 'unknown'
    
    default_path = Path('logs') / f"worker-{instance_id}.log"
    log_file_str = getattr(settings, 'LOGFILE', None)
    log_path = Path(log_file_str) if log_file_str else default_path
    
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, getattr(settings, 'LOGLEVEL', 'INFO').upper(), logging.INFO),
        format='%(asctime)s pid=%(process)d - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler(),
        ],
    )


async def run_worker():
    """🔥 Главная функция воркера БЕЗ retry - ПРЯМОЙ старт!"""
    import os, sys, re, asyncio, socket
    
    print(f"🔥 DEBUG: WORKER START - hostname={socket.gethostname()}")
    
    logger.info("🔥 WORKER START - DIRECT mode (no retry loop)")
    
    # 1. Парсинг instance_id
    instance_id = os.getenv("WORKER_INSTANCE_ID")
    if not instance_id:
        hostname = socket.gethostname()
        logger.info(f"🔍 Parsing hostname: {hostname}")
        match = re.match(r"gracehub-worker-([a-zA-Z0-9_-]+)", hostname)
        if match:
            instance_id = match.group(1)
            logger.info(f"✅ Parsed instance_id: '{instance_id}'")
        else:
            logger.error(f"❌ Cannot parse instance_id from '{hostname}'!")
            sys.exit(1)
    
    logger.info(f"🎯 TARGET instance_id: '{instance_id}'")
    logger.info(f"🔍 Environment check: WORKER_INSTANCE_ID={os.getenv('WORKER_INSTANCE_ID')}, DATABASE_URL={'SET' if os.getenv('DATABASE_URL') else 'NOT SET'}")

    # 2. Database URL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("❌ DATABASE_URL env var required!")
        sys.exit(1)
    
    logger.info(f"✅ Using DATABASE_URL={database_url[:50]}...")
    
    # 🔥 3. MasterDatabase - ОДНА попытка! (НЕ retry!)
    try:
        from shared.database import MasterDatabase
        db = MasterDatabase(database_url)
        await db.init()
        logger.info("✅ Database + Cipher ready")
    except Exception as e:
        logger.error(f"❌ Database init FAILED: {e}")
        sys.exit(1)
    
    # 🔥 4. GraceHubWorker - ПРЯМОЙ вызов!
    logger.info("🔄 Creating GraceHubWorker...")
    worker = GraceHubWorker(db=db, instance_id=instance_id)
    
    logger.info("🔄 Starting worker.initialize()...")
    await worker.initialize()
    
    logger.info(f"✅ Worker '{instance_id}' FULLY ready!")
    logger.info(f"✅ Bot ready: @{worker.bot_username}")
    
    # 🆕 5. Автоматическая настройка Mini App кнопки
    try:
        logger.info(f"🔄 [Instance {instance_id}] Setting up Mini App button...")
        miniapp_success = await worker.setup_dynamic_miniapp()
        if miniapp_success:
            logger.info(f"✅ [Instance {instance_id}] Mini App button configured")
        else:
            logger.warning(f"⚠️ [Instance {instance_id}] Running without Mini App button")
    except Exception as e:
        logger.error(f"❌ [Instance {instance_id}] Mini App setup failed: {e}", exc_info=True)
        # Продолжаем работу без Mini App
    
    # 🆕 6. Запускаем обработчик команд от API в фоне
    try:
        logger.info(f"🔄 [Instance {instance_id}] Starting bot commands processor...")
        asyncio.create_task(worker.process_bot_commands_loop())
        logger.info(f"✅ [Instance {instance_id}] Bot commands processor started")
    except Exception as e:
        logger.error(f"❌ [Instance {instance_id}] Failed to start commands processor: {e}", exc_info=True)
        # Продолжаем работу без обработчика команд
    
    # 7. Webhook server + infinite loop
    logger.info("🚀 Starting webhook server...")
    logger.info("⏳ Waiting for updates...")
    
    # Запуск webhook сервера (если есть)
    if hasattr(worker, 'start_webhook_server'):
        asyncio.create_task(worker.start_webhook_server())
    
    # Infinite loop
    await asyncio.Event().wait()


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


class PlatformInstanceDefaultsCache:
    def __init__(self, db: MasterDatabase, ttl_seconds: int = 15):
        self.db = db
        self.ttl_seconds = ttl_seconds
        self._cached_at: datetime | None = None
        self._cached_value: tuple[int, int] | None = None
        self.ticket_keyboard_anchor: Dict[int, Dict[str, Any]] = {}

    async def get(self) -> tuple[int, int]:
        now = datetime.now(timezone.utc)

        if self._cached_at and self._cached_value:
            age = (now - self._cached_at).total_seconds()
            if age < self.ttl_seconds:
                return self._cached_value

        # ВАЖНО: тут используй реальный метод твоей MasterDatabase.
        # нужно привести к одному правильному имени.
        try:
            data = await self.db.get_platform_setting("miniapp_public", default={})
        except AttributeError:
            data = await self.db.get_platform_setting("miniapp_public", default={})

        instance_defaults = (data or {}).get("instanceDefaults") or {}

        # Совместимость:
        # - старые/ожидаемые воркером имена: antiflood_limit_per_min / max_file_mb
        # - реальные в БД (по твоему platform_settings.value): antifloodMaxUserMessagesPerMinute / workerMaxFileMb
        antiflood = int(
            instance_defaults.get("antifloodMaxUserMessagesPerMinute")
            or instance_defaults.get("antiflood_limit_per_min")
            or 0
        )
        max_file_mb = int(
            instance_defaults.get("workerMaxFileMb") or instance_defaults.get("max_file_mb") or 10
        )

        self._cached_at = now
        self._cached_value = (antiflood, max_file_mb)
        return self._cached_value


class GraceHubWorker:
    """
    Отдельный воркер для одного инстанса бота.
    """

    STATUS_EMOJI: Dict[str, str] = {
        "new": "⬜️",
        "inprogress": "🟨",
        "answered": "🟩",
        "escalated": "🟥",
        "closed": "🟦",
        "spam": "⬛️",
    }

    ALLOWED_TICKET_STATUSES = {"new", "inprogress", "answered", "escalated", "closed", "spam"}

    MAX_USER_TEXT = 4096
    MAX_DB_TEXT = 2000

    @staticmethod
    def _safe_trim(text: str, limit: int) -> str:
        if text is None:
            return text
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def __init__(self, instance_id: str, db: MasterDatabase, token: str = None):
        self.instance_id = instance_id
        self.db: MasterDatabase = db
        
        # 🔥 token загружается АСИНХРОННО в initialize()!
        self.token = token  # Может быть None
        self.bot = None
        self.bot_username = None
        self.ratelimiter = None  
        
        self.dp = Dispatcher()
        self.shutdown_event = asyncio.Event()
        self.lang_code = "ru"
        self.texts = LANGS[self.lang_code]

        # --- глобальные дефолты ---
        self._platform_defaults = PlatformInstanceDefaultsCache(self.db, ttl_seconds=15)

        self.antiflood_limit_per_min: int = 0
        self.max_file_mb: int = 10
        self.max_file_bytes: int = self.max_file_mb * 1024 * 1024

        self.user_msg_timestamps: dict[int, deque[datetime]] = {}
        self.user_session_messages: Dict[int, int] = {}
        self.ticket_keyboard_anchor: Dict[int, Dict[str, Any]] = {}


    async def initialize(self) -> None:
        """
        🔥 Полная асинхронная инициализация с GRACEFUL FALLBACK
        """
        logger.info(f"🔄 Initializing worker for instance {self.instance_id}")
        
        # 🔥 1. Проверяем инстанс (с fallback!)
        instance = await self.db.get_instance(self.instance_id)
        if not instance:
            logger.warning(f"⚠️ Instance '{self.instance_id}' NOT FOUND in DB - MINIMAL MODE")
            # 🔥 Создаём fake instance для минимальной работы
            instance = type('FakeInstance', (), {
                'bot_username': 'unknown-bot',
                'instance_id': self.instance_id
            })()
        
        # 🔥 2. Загружаем токен (может не быть)
        self.token = await self.db.get_decrypted_token(self.instance_id)
        if not self.token:
            logger.error(f"❌ FATAL: No token for {self.instance_id} - cannot initialize bot!")
            return  # Graceful fallback
        
        logger.info(f"✅ Token loaded for @{instance.bot_username}")
        
        # 🔥 3. Создаём Bot и ratelimiter
        self.bot = Bot(
            token=self.token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.ratelimiter = BotRateLimiter(self.token)
        self.bot_username = instance.bot_username
        
        # 🔥 4. Регистрируем handlers
        self.register_handlers()
        
        # 🔥 5. Существующий код
        await self.init_database()
        await self.load_language()
        
        logger.info(f"✅ Worker FULLY initialized: @{self.bot_username}")


    async def _is_attachment_too_big(self, message: Message) -> bool:
        await (
            self.refresh_limits_from_db()
        )  # если у тебя так называется; у тебя есть refreshlimitsfromdb [file:4]
        maxbytes = self.maxfilebytes

        # Собираем file_id для всех поддерживаемых типов
        file_id = None

        if message.photo:
            file_id = message.photo[-1].file_id
            size = message.photo[-1].file_size
            if size and size > maxbytes:
                return True
        elif message.document:
            file_id = message.document.file_id
            size = message.document.file_size
            if size and size > maxbytes:
                return True
        elif message.video:
            file_id = message.video.file_id
            size = message.video.file_size
            if size and size > maxbytes:
                return True
        elif message.audio:
            file_id = message.audio.file_id
            size = message.audio.file_size
            if size and size > maxbytes:
                return True
        elif message.voice:
            file_id = message.voice.file_id
            size = message.voice.file_size
            if size and size > maxbytes:
                return True
        elif message.video_note:
            file_id = message.video_note.file_id
            size = message.video_note.file_size
            if size and size > maxbytes:
                return True
        elif message.sticker:
            file_id = message.sticker.file_id
            size = message.sticker.file_size
            if size and size > maxbytes:
                return True

        # Если size нет — проверяем через get_file()
        if file_id:
            ok = await self.check_file_size(file_id)  # True если <= maxbytes [file:4]
            return not ok

        return False

    async def _refresh_limits_from_db(self) -> None:
        antiflood, max_file_mb = await self._platform_defaults.get()

        self.antiflood_limit_per_min = antiflood

        if max_file_mb != self.max_file_mb:
            self.max_file_mb = max_file_mb
            self.max_file_bytes = self.max_file_mb * 1024 * 1024

    async def _is_user_flooding(self, userid: int) -> bool:
        await self._refresh_limits_from_db()

        limit = self.antiflood_limit_per_min
        if not limit or limit <= 0:
            return False

        now = datetime.now(timezone.utc)
        window = timedelta(seconds=60)

        dq = self.user_msg_timestamps.get(userid)
        if dq is None:
            dq = deque()
            self.user_msg_timestamps[userid] = dq

        while dq and now - dq[0] > window:
            dq.popleft()

        dq.append(now)

        return len(dq) > limit

    async def load_language(self):
        code = await self.get_setting("lang_code") or "ru"
        if code not in LANGS:
            code = "ru"
        self.lang_code = code
        self.texts = LANGS[code]

    async def _check_file_size(self, file_id: str) -> bool:
        # гарантируем, что лимит актуальный (с TTL)
        await self._refresh_limits_from_db()

        tg_file = await self.bot.get_file(file_id)
        size = getattr(tg_file, "file_size", None) or 0
        return size <= self.max_file_bytes

    async def global_error_handler(self, exception: Exception) -> bool:
        """
        Глобальный обработчик ошибок aiogram.
        В error-middleware сюда прилетает только exception.
        """
        user_id = None
        update = getattr(exception, "update", None)

        try:
            if update:
                if getattr(update, "message", None) and update.message.from_user:
                    user_id = update.message.from_user.id
                elif getattr(update, "callback_query", None) and update.callback_query.from_user:
                    user_id = update.callback_query.from_user.id
        except Exception:
            pass

        logger.exception(
            "Unhandled error in worker update_id=%s user_id=%s exc=%r",
            getattr(update, "update_id", None) if update else None,
            user_id,
            exception,
        )

        if isinstance(exception, TelegramBadRequest):
            return True

        return True

    async def get_operators_keyboard(
        self,
        ticket_id: int,
        page: int = 0,
        per_page: int = 10,
    ) -> InlineKeyboardMarkup:
        offset = page * per_page
        rows = await self.db.fetchall(
            """
            SELECT user_id, username, last_seen
            FROM operators
            WHERE instance_id = $1
            ORDER BY last_seen DESC
            LIMIT $2 OFFSET $3
            """,
            (self.instance_id, per_page, offset),
        )

        buttons: List[List[InlineKeyboardButton]] = []
        for r in rows:
            uid = r["user_id"]
            uname = r["username"] or ""
            label = f"@{uname}" if uname else f"id{uid}"
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"ticket:assign_to:{ticket_id}:{uid}",
                    )
                ]
            )

        # Если пусто — вернём пустую клаву, выше ты это проверяешь и шлёшь ticket_no_assignees
        if not buttons:
            return InlineKeyboardMarkup(inline_keyboard=[])

        # Отмена
        buttons.append(
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"ticket:cancel_assign:{ticket_id}",
                )
            ]
        )

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    async def init_database(self) -> None:
        """Инициализация дефолтных настроек только для СУЩЕСТВУЮЩИХ инстансов"""
        
        logger.info(f"🔍 Checking instance '{self.instance_id}'...")
        
        # 🔥 ПРАВИЛЬНЫЙ PostgreSQL asyncpg синтаксис!
        try:
            instance_exists = await self.db.fetchone(
                "SELECT 1 FROM bot_instances WHERE instance_id = $1 LIMIT 1",  
                (self.instance_id,)
            )
        except Exception as e:
            logger.error(f"❌ DB check failed: {e}")
            instance_exists = None
        
        if not instance_exists:
            logger.warning(f"⚠️  Instance '{self.instance_id}' NOT FOUND - skipping settings")
            await self.load_language()
            logger.info("✅ Worker ready (minimal mode)")
            return
        
        logger.info(f"✅ Instance '{self.instance_id}' OK - init settings...")
        
        # Безопасная инициализация настроек
        try:
            settings_defaults = {
                "admin_user_id": "0",
                "privacy_mode_enabled": "False",
                "lang_code": "ru",
                "rating_enabled": "True"
            }
            
            for key, default_value in settings_defaults.items():
                current = await self.get_setting(key)
                if current is None:
                    await self.set_setting(key, default_value)
                    logger.info(f"Set default {key}={default_value}")
            
            await self.load_language()
            logger.info(f"✅ Worker DB FULLY initialized: {self.instance_id}")
            
        except Exception as e:
            logger.error(f"❌ Settings init failed: {e}")
            logger.info("Worker continues in minimal mode")
        
        logger.info(f"✅ Worker READY: {self.instance_id}")

    async def setup_dynamic_miniapp(self) -> bool:
        """
        Настраивает кнопку Menu Button (Mini App) ТОЛЬКО для владельца бота.
        Для всех остальных пользователей устанавливает обычное меню команд.
        """
        try:
            from aiogram.types import MenuButtonWebApp, WebAppInfo, MenuButtonCommands
            
            # 1. Получаем ID владельца из таблицы bot_instances
            # Используем user_id так как в вашей схеме он NOT NULL
            row = await self.db.fetchone(
                """
                SELECT user_id 
                FROM bot_instances 
                WHERE instance_id = $1
                """,
                (self.instance_id,)
            )
            
            if not row:
                logger.warning(f"⚠️ [Instance {self.instance_id}] Owner not found in bot_instances, skipping Menu Button setup")
                return False
                
            owner_id = int(row['user_id'])
            
            # Ссылка для админского дашборда ОБЯЗАТЕЛЬНО ЗАМЕНИТЬ ХАРДКОД НА ENV!!!
            helpdesk_url = f"https://app.gracehub.ru/helpdesk/?instance={self.instance_id}"

            # 2. СНАЧАЛА: Сбрасываем меню для ВСЕХ (глобально)
            # Чтобы обычные юзеры видели просто кнопку "Меню" (команды)
            await self.bot.set_chat_menu_button(
                chat_id=None,
                menu_button=MenuButtonCommands() 
            )

            # 3. ПОТОМ: Ставим кнопку Helpdesk персонально ВЛАДЕЛЬЦУ
            await self.bot.set_chat_menu_button(
                chat_id=owner_id,
                menu_button=MenuButtonWebApp(
                    text="🖲 Helpdesk",
                    web_app=WebAppInfo(url=helpdesk_url)
                )
            )
            
            logger.info(f"✅ [Instance {self.instance_id}] Helpdesk button set ONLY for owner {owner_id}")
            
            # Сохраняем флаг настройки (опционально, как у вас было)
            await self.db.execute("""
                INSERT INTO worker_settings (instance_id, key, value)
                VALUES ($1, 'miniapp_configured', 'true')
                ON CONFLICT (instance_id, key) DO UPDATE SET value = EXCLUDED.value
            """, self.instance_id)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ [Instance {self.instance_id}] Failed to set Mini App button: {e}")
            return False
        
    async def process_bot_commands_loop(self):
        """
        Фоновая задача: проверяет очередь команд от API и выполняет их.
        """
        logger.info(f"🔄 [Instance {self.instance_id}] Bot commands processor started")
        
        while True:
            try:
                commands = await self.db.fetchall("""
                    SELECT id, command, payload
                    FROM bot_commands
                    WHERE instance_id = $1 AND status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 10
                """, (self.instance_id,)) 

                for cmd in commands:
                    cmd_id = cmd['id']
                    command = cmd['command']
                    payload = json.loads(cmd['payload']) if cmd['payload'] else {}
                    
                    try:
                        await self.execute_bot_command(command, payload)
                        
                        # ✅ ИСПРАВЛЕНО: snake_case
                        await self.db.execute("""
                            UPDATE bot_commands
                            SET status = 'completed', completed_at = NOW()
                            WHERE id = $1
                        """, cmd_id)
                        
                        logger.info(f"✅ [Instance {self.instance_id}] Command '{command}' executed (id={cmd_id})")
                        
                    except Exception as e:
                        logger.error(f"❌ [Instance {self.instance_id}] Command '{command}' failed (id={cmd_id}): {e}")
                        
                        await self.db.execute("""
                            UPDATE bot_commands
                            SET status = 'failed', error = $1
                            WHERE id = $2
                        """, str(e)[:500], cmd_id)
                
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"❌ [Instance {self.instance_id}] Command loop error: {e}")
                await asyncio.sleep(5)

    
    async def execute_bot_command(self, command: str, payload: dict):
        """Выполняет команду от API"""
        
        if command == 'create_operator_topic':
            await self.handle_create_operator_topic(payload)
        
        elif command == 'close_ticket':
            ticket_id = payload.get('ticket_id')
            if ticket_id:
                await self.close_ticket(ticket_id)
        
        else:
            logger.warning(f"⚠️ [Instance {self.instance_id}] Unknown command: {command}")
    
    async def handle_create_operator_topic(self, payload: dict):
        """
        Создает топик в личном чате оператора с историей тикета.
        """
        ticket_id = payload.get('ticket_id')
        operator_id = payload.get('operator_id')
        username = payload.get('username', 'User')
        user_id = payload.get('user_id')
        history = payload.get('history', [])
        
        if not ticket_id or not operator_id:
            logger.error(f"❌ Invalid payload for create_operator_topic: {payload}")
            return
        
        logger.info(f"🎫 [Instance {self.instance_id}] Creating topic for ticket #{ticket_id}, operator {operator_id}")
        
        try:
            topic_name = f"#{ticket_id}: @{username}" if username != 'User' else f"#{ticket_id}: User {user_id}"
            
            ft = await self.bot.create_forum_topic(
                chat_id=operator_id,
                name=topic_name[:128]
            )
            
            thread_id = ft.message_thread_id
            
            # ✅ ИСПРАВЛЕНО: snake_case (проверьте вашу схему таблицы tickets!)
            await self.db.execute("""
                UPDATE tickets
                SET thread_id = $1, updated_at = NOW()
                WHERE id = $2 AND instance_id = $3
            """, thread_id, ticket_id, self.instance_id)
            
            # Отправка истории...
            if history:
                history_text = self._format_history_messages(history, limit=10)
                
                await self.bot.send_message(
                    chat_id=operator_id,
                    message_thread_id=thread_id,
                    text=f"📋 **История обращения #{ticket_id}**\n\n{history_text}\n\n"
                        f"✍️ _Напишите ваш ответ в этот топик_",
                    parse_mode="Markdown"
                )
            else:
                await self.bot.send_message(
                    chat_id=operator_id,
                    message_thread_id=thread_id,
                    text=f"✅ Тикет #{ticket_id} взят в работу\n\n"
                        f"✍️ _Напишите ваш ответ здесь_"
                )
            
            logger.info(f"✅ [Instance {self.instance_id}] Topic {thread_id} created for ticket #{ticket_id}")
            
        except Exception as e:
            logger.error(f"❌ [Instance {self.instance_id}] Failed to create topic for ticket #{ticket_id}: {e}")
            raise

    
    def _format_history_messages(self, messages: list, limit: int = 10) -> str:
        """Форматирует последние N сообщений для отображения"""
        recent = messages[-limit:] if len(messages) > limit else messages
        
        lines = []
        if len(messages) > limit:
            lines.append(f"_...показаны последние {limit} из {len(messages)} сообщений_\n")
        
        for msg in recent:
            direction_emoji = "👤" if msg.get('direction') == 'usertoopenchat' else "👨‍💼"
            direction_text = "Клиент" if msg.get('direction') == 'usertoopenchat' else "Оператор"
            content = msg.get('content', '_медиа_')
            
            # Обрезаем длинные сообщения
            if len(content) > 200:
                content = content[:200] + "..."
            
            lines.append(f"{direction_emoji} {direction_text}:\n{content}\n")
        
        return "\n".join(lines)

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
        return InlineKeyboardMarkup(inline_keyboard=[buttons])

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
            WHERE instance_id = $1 AND key = $2
            """,
            (self.instance_id, key),
        )
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self.db.execute(
            """
            INSERT INTO worker_settings (instance_id, key, value)
            VALUES ($1, $2, $3)
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
                    callback_data=f"bl_page:{page - 1}",
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
                    callback_data=f"bl_page:{page - 1}",
                )
            )
        if end < total:
            nav_row.append(
                InlineKeyboardButton(
                    text=self.texts.blacklist_next_page_button,
                    callback_data=f"bl_page:{page + 1}",
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
            FROM blacklist
            WHERE instance_id = $1 AND user_id = $2
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
            VALUES ($1, $2, $3)
            ON CONFLICT (instance_id, user_id, date) DO NOTHING
            """,
            (self.instance_id, user_id, now.date()),
        )

        # сохраняем пользователя в основной таблице blacklist
        await self.db.execute(
            """
            INSERT INTO blacklist (instance_id, user_id, username, added_at)
            VALUES ($1, $2, $3, $4)
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
                       updated_at = $1
                 WHERE instance_id = $2 AND user_id = $3
                """,
                (now, self.instance_id, user_id),
            )
        except Exception as e:
            logger.error(f"Failed to mark tickets as spam for blacklisted user {user_id}: {e}")

    async def remove_from_blacklist(self, user_id: int) -> None:
        if not self.db:
            return
        await self.db.execute(
            """
            DELETE FROM blacklist
            WHERE instance_id = $1 AND user_id = $2
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
            WHERE instance_id = $1
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

        # Фидбек при закрытии тикета
        rating_enabled = await self.get_setting("rating_enabled")
        rating_on = rating_enabled == "True"
        rating_label = f"{self.texts.menu_rating}: {'🟢' if rating_on else '🔴'}"

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
                        text=rating_label,
                        callback_data="setup_rating",
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
            VALUES ($1, $2, $3, $4, $5)
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
            WHERE instance_id = $1 AND chat_id = $2 AND admin_message_id = $3
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
        thread_id = ticket.get("thread_id") 
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
            WHERE instance_id = $1 AND id = $2
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
        set_parts = ["status = $1", "updated_at = $2"]
        params: List[Any] = [status, now]
        counter = 3

        if assigned_username is not None:
            set_parts.append(f"assigned_username = ${counter}")
            params.append(assigned_username)
            counter += 1
        if assigned_user_id is not None:
            set_parts.append(f"assigned_user_id = ${counter}")
            params.append(assigned_user_id)
            counter += 1
        if status == "closed":
            set_parts.append(f"closed_at = ${counter}")
            params.append(now)
            counter += 1

        params.append(self.instance_id)
        params.append(ticket_id)

        sql = f"""
            UPDATE tickets
            SET {", ".join(set_parts)}
            WHERE instance_id = ${counter} AND id = ${counter + 1}
        """
        await self.db.execute(sql, tuple(params))

        ticket = await self.fetch_ticket(ticket_id)
        if ticket:
            # обновляем заголовок темы
            await self.update_ticket_topic_title(ticket)

            # если только что закрыли — и включен запрос оценки, отправляем запрос
            if status == "closed":
                try:
                    rating_enabled = (await self.get_setting("rating_enabled")) == "True"
                    if rating_enabled:
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
        target_user_id: int | None = None,  # НОВЫЙ аргумент
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
        except TelegramBadRequest as e:
            err = str(e).lower()
            if "message is not modified" in err:
                return

            logger.warning(
                "Failed to edit ticket keyboard for ticket %s message %s: %s; sending new message",
                ticket_id,
                message_id,
                e,
            )
            try:
                sent = await self._send_safe_message(
                    chat_id=chat_id,
                    text=self.texts.ticket_admin_prompt,
                    reply_markup=kb,
                )
                if target_user_id is not None:
                    try:
                        await self.save_reply_mapping_v2(
                            chat_id=chat_id,
                            message_id=sent.message_id,
                            target_user_id=target_user_id,
                        )
                    except Exception as e3:
                        logger.error(
                            "Failed to update reply mapping for ticket %s new message %s: %s",
                            ticket_id,
                            sent.message_id,
                            e3,
                        )
            except Exception as e2:
                logger.error(
                    "Failed to send fallback ticket keyboard message for ticket %s: %s",
                    ticket_id,
                    e2,
                )
        except Exception as e:
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
                WHERE instance_id = $1 AND chat_id = $2 AND username = $3
                """,
                (self.instance_id, chat_id, username),
            )
        else:
            row = await self.db.fetchone(
                """
                SELECT *
                FROM tickets
                WHERE instance_id = $1 AND chat_id = $2 AND user_id = $3
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
            VALUES ($1, $2, $3, $4, 'new', $5, $6)
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
                   SET thread_id = $1, updated_at = $2
                 WHERE instance_id = $3 AND id = $4
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
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                (
                    self.instance_id,
                    chat_id,
                    message.message_id,
                    user_id,
                    "user_to_openchat",
                    text_content,
                ),
            )
        except Exception as e:
            logger.error(f"Failed to insert message into messages table: {e}")

    async def ensure_ticket_for_user(
        self,
        chat_id: int,
        user_id: int,
        username: str,
    ) -> Dict[str, Any]:
        """
        Гарантирует наличие тикета для данного пользователя.
        Если тикет уже есть — возвращает его, иначе создаёт новый и топик в личном чате админа.
        """
        # Пытаемся найти существующий тикет для этого пользователя
        ticket = await self.fetch_ticket_by_chat(chat_id, username, user_id)
        if ticket:
            return ticket

        # === БИЛЛИНГ: проверяем лимит тикетов ===
        ok, reason = await self.db.increment_tickets_used(self.instance_id)
        if not ok:
            logger.warning(
                "Ticket creation blocked by billing: instance=%s reason=%s user_id=%s",
                self.instance_id,
                reason,
                user_id,
            )
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
            VALUES ($1, $2, $3, $4, 'new', $5, $6)
            RETURNING id
            """,
            (self.instance_id, user_id, username, chat_id, now, now),
        )
        ticket_id = row["id"]

        # Создаём топик в личном чате админа
        thread_id = None
        user_label = username or f"user {user_id}"
        title = f"{ticket_id} · {user_label}"
        try:
            ft = await self.bot.create_forum_topic(chat_id, name=title)
            thread_id = ft.message_thread_id
            await self.db.execute(
                """
                UPDATE tickets
                SET thread_id = $1, updated_at = $2
                WHERE instance_id = $3 AND id = $4
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
            else:
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

            # Сообщение пользователю
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
                return await self.bot.send_message(chat_id, body, message_thread_id=thread)

            if message.photo:
                caption = message.caption or ""
                cap = f"{header}:\n{caption}" if caption else header
                return await self.bot.send_photo(
                    chat_id,
                    message.photo[-1].file_id,
                    caption=cap,
                    message_thread_id=thread,
                )

            if message.video:
                caption = message.caption or ""
                cap = f"{header}:\n{caption}" if caption else header
                return await self.bot.send_video(
                    chat_id,
                    message.video.file_id,
                    caption=cap,
                    message_thread_id=thread,
                )

            if message.document:
                caption = message.caption or ""
                cap = f"{header}:\n{caption}" if caption else header
                return await self.bot.send_document(
                    chat_id,
                    message.document.file_id,
                    caption=cap,
                    message_thread_id=thread,
                )

            if message.audio:
                caption = message.caption or ""
                cap = f"{header}:\n{caption}" if caption else header
                return await self.bot.send_audio(
                    chat_id,
                    message.audio.file_id,
                    caption=cap,
                    message_thread_id=thread,
                )

            if message.voice:
                return await self.bot.send_voice(
                    chat_id,
                    message.voice.file_id,
                    caption=header,
                    message_thread_id=thread,
                )

            if message.sticker:
                return await self.bot.send_sticker(
                    chat_id,
                    message.sticker.file_id,
                    message_thread_id=thread,
                )

            body = f"{header}: [{message.content_type}]"
            return await self.bot.send_message(chat_id, body, message_thread_id=thread)

        # Rate-limit перед отправкой в OpenChat
        if not await self.ratelimiter.can_send(chat_id=chat_id):
            wait_for = await self.ratelimiter.wait_for_send()
            logger.info(f"Rate limit wait for OpenChat chat {chat_id}: {wait_for}s")
            await asyncio.sleep(wait_for)

        # Пытаемся отправить в текущий thread_id
        try:
            sent = await _send_into_thread(thread_id)
        except Exception as e:
            err_text = str(e).lower()

            # Flood control: Too Many Requests
            if "too many requests" in err_text or "flood control exceeded" in err_text:
                retry_sec = 5
                for token in err_text.split():
                    if token.isdigit():
                        retry_sec = int(token)
                        break

                logger.warning(
                    "Flood control in forward_to_openchat, sleep %s sec (chat %s, ticket %s)",
                    retry_sec,
                    chat_id,
                    ticket["id"],
                )
                await asyncio.sleep(retry_sec)

                try:
                    sent = await _send_into_thread(thread_id)
                except Exception as e2:
                    logger.error(
                        "Failed to forward to OpenChat after retry for ticket %s: %s",
                        ticket["id"],
                        e2,
                    )
                    return

            elif (
                "message thread not found" in err_text
                or "message thread not found"
                in getattr(getattr(e, "message", ""), "lower", lambda: "")()
            ):
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
                        SET thread_id = $1, updated_at = $2
                        WHERE instance_id = $3 AND id = $4
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

        # Сохраняем связь для корректного реплея админа клиенту + сообщения в БД
        if sent:
            await self.save_reply_mapping_v2(chat_id, sent.message_id, user_id)

            await self.store_forwarded_message(
                chat_id=chat_id,
                message=sent,
                user_id=user_id,
            )

            # ------------------------------------------------------------
            # КЛАВИАТУРА: переносим НЕ чаще чем раз в 60 минут на тикет
            #
            # Требование: в __init__ должен быть кеш:
            # self.ticket_keyboard_anchor: Dict[int, Dict[str, Any]] = {}
            # где ticket_id -> {"message_id": int, "moved_at": datetime}
            # ------------------------------------------------------------
            move_window = timedelta(minutes=60)
            ticket_id = ticket["id"]

            anchor = getattr(self, "ticket_keyboard_anchor", None)
            if anchor is None:
                # На случай если ещё не добавил в __init__
                self.ticket_keyboard_anchor = {}
                anchor = self.ticket_keyboard_anchor

            anchor_rec = anchor.get(ticket_id)
            should_move = False
            if not anchor_rec:
                should_move = True
            else:
                moved_at = anchor_rec.get("moved_at")
                if not moved_at or (now - moved_at) >= move_window:
                    should_move = True

            if should_move:
                # затем вешаем компактную кнопку-меню на "якорное" (текущее) сообщение
                await self.put_ticket_keyboard(ticket_id, sent.message_id, compact=True)

                # запоминаем якорь
                anchor[ticket_id] = {"message_id": sent.message_id, "moved_at": now}
            else:
                # не переносим, чтобы не биться в editMessageReplyMarkup при флуде
                pass

        # Обновляем тайминги тикета
        try:
            await self.db.execute(
                """
                UPDATE tickets
                SET last_user_msg_at = $1,
                    updated_at       = $2
                WHERE instance_id = $3
                AND id          = $4
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
            # Сохраняем admin_private_chat_id в БД
            # ✅ ИСПРАВЛЕНО: WHERE instance_id = $2
            await self.db.execute(
                """
                UPDATE bot_instances
                SET admin_private_chat_id = $1
                WHERE instance_id = $2
                """,
                (message.chat.id, self.instance_id),
            )
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.you_are_admin_now,
            )

        # Ветка для админа
        if await self.is_admin(user_id):
            # 1. Обновляем admin_private_chat_id при каждом /start
            # ✅ ИСПРАВЛЕНО: WHERE instance_id = $2
            await self.db.execute(
                """
                UPDATE bot_instances
                SET admin_private_chat_id = $1
                WHERE instance_id = $2
                """,
                (message.chat.id, self.instance_id),
            )
            
            # 2. ПРИНУДИТЕЛЬНО (БЕЗ УСЛОВИЙ) включаем OpenChat и пишем ID чата
            # Это исправит вашу проблему с пустой базой
            await self.set_setting("openchat_enabled", "True")
            await self.set_setting("general_panel_chat_id", str(message.chat.id))
            
            # Синхронизируем в instance_meta
            try:
                await self.db.execute(
                    """
                    INSERT INTO instance_meta (
                        instance_id,
                        general_panel_chat_id,
                        openchat_enabled,
                        updated_at
                    )
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (instance_id) DO UPDATE
                    SET general_panel_chat_id = EXCLUDED.general_panel_chat_id,
                        openchat_enabled = EXCLUDED.openchat_enabled,
                        updated_at = NOW()
                    """,
                    (self.instance_id, message.chat.id, True),
                )
            except Exception as e:
                logger.error(
                    f"Failed to update instance_meta for {self.instance_id}: {e}"
                )

            # Основное админское сообщение
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=(
                    f"🟢 Топики активированы в этом чате\n"
                    f"{self.texts.menu_you_are_admin}\n"
                    f"{self.texts.admin_panel_choose_section}"
                ),
                reply_markup=await self.get_admin_menu(),
            )
        else:
            # Ветка для обычного пользователя
            if await self.is_user_blacklisted(user_id):
                await self._send_safe_message(
                    chat_id=message.chat.id,
                    text=self.texts.you_are_blocked,
                )
                return

            greeting = await self.get_setting("greeting_text")
            if not greeting or not greeting.strip():
                greeting = self.texts.default_greeting

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
                VALUES ($1, NULL, NULL, $2, NOW())
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
            logger.error(
                f"Failed to update instance_meta (openchat off) for {self.instance_id}: {e}"
            )

        await self._send_safe_message(
            chat_id=message.chat.id,
            text=self.texts.openchat_off_confirm,
        )

    # ====================== CALLBACKS (ТИКЕТЫ) ======================

    async def handle_ticket_callback(self, cb: CallbackQuery) -> None:
        """
        Обработка callback'ов от клавиатуры тикетов:
        меню / Себе / Назначить / Спам(+подтверждение блокировки) / Не спам / Закрыть / Переоткрыть.
        """
        data = cb.data or ""
        if not data.startswith("ticket:"):
            return

        parts = data.split(":")
        if len(parts) < 3:
            await cb.answer()
            return

        action = parts[1]

        # --- helpers (локально, чтобы не разносить по классу) ---
        def _spam_confirm_kb(ticket_id: int):
            return InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=self.texts.spam_confirm_only_spam,
                            callback_data=f"ticket:spam_only:{ticket_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=self.texts.spam_confirm_spam_and_block,
                            callback_data=f"ticket:spam_block:{ticket_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=self.texts.spam_confirm_cancel,
                            callback_data=f"ticket:menu:{ticket_id}",
                        )
                    ],
                ]
            )

        # Открыть полное меню из компактной кнопки 🖲
        if action == "menu":
            try:
                ticket_id = int(parts[2])
            except ValueError:
                await cb.answer()
                return

            ticket = await self.fetch_ticket(ticket_id)
            if not ticket:
                await cb.answer(self.texts.ticket_not_found, show_alert=True)
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
                try:
                    await cb.message.edit_reply_markup(reply_markup=kb)
                except TelegramBadRequest as e:
                    err = str(e).lower()
                    if "message is not modified" in err:
                        await cb.answer()
                        return
                    # сообщение протухло → шлём новое
                    try:
                        await self._send_safe_message(
                            chat_id=cb.message.chat.id,
                            text=self.texts.ticket_admin_prompt,
                            reply_markup=kb,
                        )
                    except Exception as e2:
                        logger.error(
                            "Failed to send fallback ticket menu message for ticket %s: %s",
                            ticket_id,
                            e2,
                        )
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
                # put_ticket_keyboard внутри уже умеет делать fallback
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
            await cb.answer(self.texts.ticket_not_found, show_alert=True)
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
            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer(self.texts.ticket_taken_self)
            return

        # 2) "Назначить" — показать список операторов из БД
        if action == "assign":
            kb = await self.get_operators_keyboard(ticket_id, page=0)
            if not kb.inline_keyboard:
                await cb.answer(self.texts.ticket_no_assignees, show_alert=True)
                return

            try:
                await message.edit_reply_markup(reply_markup=kb)
            except TelegramBadRequest as e:
                err = str(e).lower()
                if "message is not modified" not in err:
                    try:
                        await self._send_safe_message(
                            chat_id=message.chat.id,
                            text=self.texts.ticket_admin_prompt,
                            reply_markup=kb,
                        )
                    except Exception as e2:
                        logger.error(
                            "Failed to send fallback assign keyboard for ticket %s: %s",
                            ticket_id,
                            e2,
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

            target_username = f"id{assignee_id}"
            try:
                member = await self.bot.get_chat_member(ticket["chat_id"], assignee_id)
                if member and member.user:
                    target_username = member.user.username or f"id{member.user.id}"
            except Exception:
                pass

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
            await cb.answer(self.texts.ticket_assigned_to.format(username=target_username))
            return

        # 2b) Отмена назначения
        if action == "cancel_assign":
            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer(self.texts.ticket_assignment_cancelled)
            return

        # 3) "Спам" -> показать подтверждение (блокировать ли пользователя)
        if action == "spam":
            kb = _spam_confirm_kb(ticket_id)
            try:
                await message.edit_reply_markup(reply_markup=kb)
            except TelegramBadRequest:
                # сообщение протухло → шлём новое
                try:
                    await self._send_safe_message(
                        chat_id=message.chat.id,
                        text=self.texts.ticket_admin_prompt,
                        reply_markup=kb,
                    )
                except Exception as e2:
                    logger.error(
                        "Failed to send fallback spam confirm keyboard for ticket %s: %s",
                        ticket_id,
                        e2,
                    )
            await cb.answer()
            return

        # 3.1) "Только спам" (без блокировки)
        if action == "spam_only":
            await self.set_ticket_status(
                ticket_id,
                "spam",
                assigned_username=None,
                assigned_user_id=None,
            )
            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer(self.texts.ticket_marked_spam)
            return

        # 3.2) "Спам + блокировка"
        if action == "spam_block":
            # В твоём коде add_to_blacklist() уже помечает все тикеты пользователя как spam.
            target_user_id = ticket.get("userid") or ticket.get("user_id")
            target_username = ticket.get("username") or ""

            if target_user_id:
                await self.add_to_blacklist(int(target_user_id), str(target_username))

            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer("Пользователь заблокирован")
            return

        # 3a) "Не спам"
        if action == "not_spam":
            await self.set_ticket_status(
                ticket_id,
                "inprogress",
                assigned_username=assignee_username,
                assigned_user_id=user.id,
            )
            await self.put_ticket_keyboard(ticket_id, message.message_id, compact=True)
            await cb.answer(self.texts.ticket_unspammed)
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
            await cb.answer(self.texts.ticket_closed)
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
            await cb.answer(self.texts.ticket_reopened)
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
            enabled = self.texts.autoreply_state_on.format(
                state=self.texts.autoreply_enabled_label
                if await self.get_setting("autoreply_enabled") == "True"
                else self.texts.autoreply_disabled_label
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
            # Просто сообщаем статус
            openchat = await self.get_openchat_settings()
            
            if openchat["enabled"]:
                status_text = "🟢 OpenChat активен (сообщения приходят сюда в топики)."
            else:
                status_text = "🔴 OpenChat выключен. Нажмите /start для включения."

            # Кнопка назад
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=self.texts.back,
                            callback_data="main_menu",
                        )
                    ]
                ]
            )
            
            await cb.message.edit_text(status_text, reply_markup=kb)

        elif data == "setup_privacy":
            enabled = (
                self.texts.privacy_state_on
                if await self.is_privacy_enabled()
                else self.texts.privacy_state_off
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

        elif data == "toggle_privacy":
            current = await self.is_privacy_enabled()
            await self.set_setting("privacy_mode_enabled", "False" if current else "True")
            new_state = self.texts.privacy_state_on if not current else self.texts.privacy_state_off
            await cb.answer(
                self.texts.privacy_toggled.format(state=new_state),
                show_alert=False,
            )

            enabled = (
                self.texts.privacy_state_on
                if await self.is_privacy_enabled()
                else self.texts.privacy_state_off
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

        elif data == "setup_rating":
            rating_enabled = (await self.get_setting("rating_enabled")) == "True"
            enabled_text = (
                self.texts.rating_state_on if rating_enabled else self.texts.rating_state_off
            )
            await cb.message.edit_text(
                self.texts.rating_screen.format(state=enabled_text),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=self.texts.rating_toggle_btn,
                                callback_data="toggle_rating",
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

        elif data == "toggle_rating":
            current = (await self.get_setting("rating_enabled")) == "True"
            await self.set_setting("rating_enabled", "False" if current else "True")
            new_state_text = (
                self.texts.rating_state_on if not current else self.texts.rating_state_off
            )

            await cb.answer(
                self.texts.rating_toggled.format(state=new_state_text),
                show_alert=False,
            )

            rating_enabled = (await self.get_setting("rating_enabled")) == "True"
            enabled_text = (
                self.texts.rating_state_on if rating_enabled else self.texts.rating_state_off
            )
            await cb.message.edit_text(
                self.texts.rating_screen.format(state=enabled_text),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=self.texts.rating_toggle_btn,
                                callback_data="toggle_rating",
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
                reply_markup=self.get_blacklist_view_menu(page=0),
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
                WHERE instance_id = $1
                ORDER BY created_at ASC
                """,
                (self.instance_id,),
            )

            if not rows:
                await cb.message.answer(self.texts.export_no_users)
                return

            import csv
            import io
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
            
            # Если включено — Зеленый, иначе Красный (но без инструкций по привязке)
            if openchat["enabled"]:
                status_line_admin = "🟢 Топики активированы"
            else:
                status_line_admin = "🔴 Топики отключены"

            me = await self.bot.get_me()
            bot_username = me.username or "bot"

            # Всегда показываем стандартную панель
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
        results = [u for u in bl if (u["username"] or "").lower().find(query) != -1]

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

        text = f'🔍 Результаты поиска по "{query}":\n' + "\n".join(lines)
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
                text=self.texts.access_denied,
            )
            return

        if message.text and message.text.strip() == "/clear_greeting":
            await self.set_setting("greeting_text", "")
            await state.clear()
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.greeting_cleared,
            )
            return

        if not message.text:
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.greeting_need_text,
            )
            return

        greeting = self._safe_trim(message.text, self.MAX_DB_TEXT)
        await self.set_setting("greeting_text", greeting)
        await state.clear()
        await self._send_safe_message(
            chat_id=message.chat.id,
            text=self.texts.greeting_saved,
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
                WHERE instance_id = $1 AND username = $2
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

        # Антифлуд: сообщения в минуту от пользователя
        if await self._is_user_flooding(user_id):
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.too_many_messages,
            )
            return

        # 🔹 СЕССИОННЫЙ ФЛУД (>=3 подряд) — честно говорим, что НЕ отправили
        user_msgs = self.user_session_messages.get(user_id, 0)
        SESSION_FLOOD_LIMIT = 3
        if user_msgs >= SESSION_FLOOD_LIMIT:
            logger.warning("User %s session flood (%s msgs)", user_id, user_msgs)
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=(
                    "⚠️ Слишком много сообщений подряд.\n"
                    "Это сообщение не отправлено оператору, чтобы не засорять очередь.\n\n"
                    "Пожалуйста, дождитесь ответа оператора."
                ),
            )
            return

        # Rate-limit на отправку ответов
        if not await self.ratelimiter.can_send(chat_id=message.chat.id):
            wait_for = await self.ratelimiter.wait_for_send()
            await asyncio.sleep(wait_for)

        # Если это админ
        if await self.is_admin(user_id):
            # Если админ пишет внутри топика (thread_id) — это ответ пользователю
            if message.message_thread_id:
                await self.handle_admin_topic_reply(message)
                return
            
            # Если админ пишет в основной чат — показываем админ-панель
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=self.texts.admin_panel_title,
                reply_markup=await self.get_admin_menu(),
            )
            return

        # -------- Валидация размеров вложений (исправлено) --------
        max_bytes = self.max_file_bytes  # задаётся в __init__ из settings.WORKER_MAX_FILE_MB
        too_big = False

        async def _check_by_file_id(file_id: str) -> bool:
            """
            True => файл проходит лимит
            False => файл больше лимита
            """
            try:
                return await self.check_file_size(file_id)
            except Exception as e:
                # Если Telegram API временно не даёт размер — лучше НЕ блокировать,
                # иначе возможны ложные отказы. При желании можно сделать наоборот.
                logger.warning("check_file_size failed for file_id=%s: %s", file_id, e)
                return True

        # Фото (берём максимально крупное)
        if message.photo:
            photo = message.photo[-1]
            if photo.file_size is not None:
                if photo.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(photo.file_id)
                too_big = not ok

        # Документы
        if not too_big and message.document:
            if message.document.file_size is not None:
                if message.document.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.document.file_id)
                too_big = not ok

        # Видео
        if not too_big and message.video:
            if message.video.file_size is not None:
                if message.video.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.video.file_id)
                too_big = not ok

        # Аудио
        if not too_big and message.audio:
            if message.audio.file_size is not None:
                if message.audio.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.audio.file_id)
                too_big = not ok

        # Голосовые
        if not too_big and message.voice:
            if message.voice.file_size is not None:
                if message.voice.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.voice.file_id)
                too_big = not ok

        # Видео-заметки
        if not too_big and message.video_note:
            if message.video_note.file_size is not None:
                if message.video_note.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.video_note.file_id)
                too_big = not ok

        # Стикеры (если хочешь ограничивать и их)
        if not too_big and message.sticker:
            if message.sticker.file_size is not None:
                if message.sticker.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.sticker.file_id)
                too_big = not ok

        if too_big:
            logger.warning(
                "Attachment too large from user %s in private chat %s (limit %s bytes)",
                user_id,
                message.chat.id,
                max_bytes,
            )
            await self._send_safe_message(
                chat_id=message.chat.id,
                text=("❌ Вложение слишком большое.\nПожалуйста, отправьте файл меньшего размера."),
            )
            return
        # ---------------------------------------------------------

        oc = await self.get_openchat_settings()

        # Если включён OpenChat и есть привязанный чат — шлём в топики
        if oc["enabled"] and oc["chat_id"]:
            try:
                await self.forward_to_openchat(message)

                # Обновляем счётчик сессии
                self.user_session_messages[user_id] = user_msgs + 1
                if self.user_session_messages[user_id] > 10:
                    self.user_session_messages[user_id] = 0

            except Exception as e:
                logger.exception("Failed to forward to OpenChat")

            return

        # Если OpenChat не настроен — информируем пользователя
        await self._send_safe_message(
            chat_id=message.chat.id,
            text=self.texts.support_not_configured,
        )


    # ====================== OPENCHAT: СОБЩЕНИЯ И РЕПЛАИ ======================
    async def handle_openchat_message(self, message: Message) -> None:
        """
        Обработка сообщений в OpenChat-режиме в ЛС админа с ботом (private chat с топиками).
        Интересуют только реплаи на сообщения (reply) внутри привязанного private-чата.
        """
        oc = await self.get_openchat_settings()
        if not (oc["enabled"] and oc["chat_id"] and message.chat.id == oc["chat_id"]):
            return

        # OpenChat теперь работает в личном чате админа
        if message.chat.type != ChatType.PRIVATE:
            return

        # Страховка: отвечать пользователям может только админ инстанса
        if message.from_user and not await self.is_admin(message.from_user.id):
            return

        # Берём только ответы на сообщения (reply) — это сигнал ответа клиенту
        if not message.reply_to_message:
            return

        # Не обрабатываем собственные сообщения бота, чтобы не зациклиться
        if message.from_user and message.from_user.is_bot:
            return

        # 🔹 Трекинг оператора по активности в OpenChat
        if message.from_user:
            await self.db.track_operator_activity(
                self.instance_id,
                message.from_user.id,
                message.from_user.username or "",
            )

        # -------- Валидация размеров вложений от админов/операторов в OpenChat --------
        max_bytes = self.max_file_bytes  # задаётся в __init__ из settings.WORKER_MAX_FILE_MB
        too_big = False

        async def _check_by_file_id(file_id: str) -> bool:
            """
            True => файл проходит лимит
            False => файл больше лимита
            """
            try:
                return await self.check_file_size(file_id)
            except Exception as e:
                # При сбоях Telegram API лучше не блокировать (иначе будут ложные отказы).
                logger.warning("check_file_size failed for file_id=%s: %s", file_id, e)
                return True

        # Фото
        if message.photo:
            photo = message.photo[-1]
            if photo.file_size is not None:
                if photo.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(photo.file_id)
                too_big = not ok

        # Документы
        if not too_big and message.document:
            if message.document.file_size is not None:
                if message.document.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.document.file_id)
                too_big = not ok

        # Видео
        if not too_big and message.video:
            if message.video.file_size is not None:
                if message.video.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.video.file_id)
                too_big = not ok

        # Аудио
        if not too_big and message.audio:
            if message.audio.file_size is not None:
                if message.audio.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.audio.file_id)
                too_big = not ok

        # Голосовые
        if not too_big and message.voice:
            if message.voice.file_size is not None:
                if message.voice.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.voice.file_id)
                too_big = not ok

        # Видео-заметки
        if not too_big and message.video_note:
            if message.video_note.file_size is not None:
                if message.video_note.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.video_note.file_id)
                too_big = not ok

        # Стикеры (если тоже ограничиваем)
        if not too_big and message.sticker:
            if message.sticker.file_size is not None:
                if message.sticker.file_size > max_bytes:
                    too_big = True
            else:
                ok = await _check_by_file_id(message.sticker.file_id)
                too_big = not ok

        if too_big:
            operator_id = message.from_user.id if message.from_user else None
            logger.warning(
                "Attachment too large from openchat user %s in chat %s (limit %s bytes)",
                operator_id,
                message.chat.id,
                max_bytes,
            )

            # 1) Определяем целевого пользователя по reply_to_message (маппинг admin_message -> user)
            target_user_id = None
            try:
                target_user_id = await self.get_target_user_by_admin_message(
                    chat_id=message.chat.id,
                    admin_message_id=message.reply_to_message.message_id,
                )
            except Exception as e:
                logger.error("Failed to resolve target user for big attachment: %s", e)

            # 2) Пишем пользователю в ЛС
            if target_user_id:
                try:
                    await self._send_safe_message(
                        chat_id=target_user_id,
                        text=(
                            "❌ Файл слишком большой и не может быть доставлен в поддержку.\n"
                            "Пожалуйста, отправьте файл меньшего размера."
                        ),
                    )
                except Exception as e:
                    logger.error(
                        "Failed to notify user %s about big attachment: %s",
                        target_user_id,
                        e,
                    )

            # 3) (Опционально) сообщаем в текущий топик/тред, чтобы оператор видел причину
            try:
                await self._send_safe_message(
                    chat_id=message.chat.id,
                    text="⚠️ Вложение слишком большое и не было доставлено пользователю.",
                    message_thread_id=getattr(message, "message_thread_id", None),
                )
            except Exception as e:
                logger.error("Failed to notify openchat topic about big attachment: %s", e)

            return
        # ------------------------------------------------------------------------------------------

        await self.handle_openchat_reply(message, message.reply_to_message, oc)

    async def handle_admin_topic_reply(self, message: Message) -> None:
        """
        Обработка ответов админа из топика (Private Chat).
        Определяем получателя по thread_id (из таблицы tickets).
        """
        thread_id = message.message_thread_id
        if not thread_id:
            return

        # Ищем тикет по thread_id
        row = await self.db.fetchone(
            """
            SELECT user_id, id, status 
            FROM tickets 
            WHERE instance_id = $1 AND thread_id = $2
            """,
            (self.instance_id, thread_id),
        )
        
        if not row:
            # Если топик есть, а тикета нет (странно, но бывает)
            return

        target_user_id = row["user_id"]
        ticket_id = row["id"]
        
        # Отправляем копию сообщения пользователю
        try:
            if message.text:
                await self._send_safe_message(chat_id=target_user_id, text=message.text)
            elif message.photo:
                await self._send_safe_photo(chat_id=target_user_id, file_id=message.photo[-1].file_id, caption=message.caption)
            elif message.document:
                await self._send_safe_document(chat_id=target_user_id, file_id=message.document.file_id, caption=message.caption)
            elif message.video:
                await self._send_safe_video(chat_id=target_user_id, file_id=message.video.file_id, caption=message.caption)
            elif message.audio:
                await self._send_safe_audio(chat_id=target_user_id, file_id=message.audio.file_id, caption=message.caption)
            elif message.voice:
                await self._send_safe_voice(chat_id=target_user_id, file_id=message.voice.file_id, caption=message.caption)
            elif message.sticker:
                await self._send_safe_sticker(chat_id=target_user_id, file_id=message.sticker.file_id)
            else:
                await self._send_safe_message(chat_id=target_user_id, text="[Unsupported message type]")
        except Exception as e:
            logger.error(f"Failed to send reply to user {target_user_id} from topic {thread_id}: {e}")
            await self._send_safe_message(
                chat_id=message.chat.id, 
                text="❌ Не удалось отправить сообщение пользователю (возможно, он заблокировал бота).",
                message_thread_id=thread_id
            )
            return

        # Обновляем статус тикета и время ответа
        try:
            now = datetime.now(timezone.utc)
            await self.db.execute(
                """
                UPDATE tickets 
                SET last_admin_reply_at = $1, 
                    updated_at = $2,
                    status = CASE WHEN status = 'new' THEN 'answered' ELSE status END
                WHERE instance_id = $3 AND id = $4
                """,
                (now, now, self.instance_id, ticket_id),
            )
        except Exception as e:
            logger.error(f"Failed to update ticket stats for {ticket_id}: {e}")



    # ====================== РЕГИСТРАЦИЯ ХЭНДЛЕРОВ ======================
    def register_handlers(self) -> None:
        logger.info(f"Registering handlers for worker instance {self.instance_id}")

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
        logger.debug("Registered /start handler for private chats")

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
        

        # Задаём язык (ИСПОЛЬЗУЕМ self.dp)
        self.dp.callback_query.register(
            self.handle_language_callback,
            F.data.in_(["setup_language"]) | F.data.startswith("set_lang:"),
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

        # Общий обработчик приватных сообщений (сообщения от юзеров боту)
        self.dp.message.register(
            self.handle_private_message,
            F.chat.type == ChatType.PRIVATE,
        )
        logger.debug("Registered general private message handler")

        # Общий для ошибок
        self.dp.errors.register(self.global_error_handler)
        logger.info(f"All handlers registered successfully for worker {self.instance_id}")


    # ====================== ЗАПУСК / ИНТЕГРАЦИЯ ======================

    async def process_update(self, update: Update) -> None:
        """
        Доп. метод, если вдруг захочется кормить воркер апдейтами вручную.
        """
        logger.info(f"Worker {self.instance_id} received update id={update.update_id}")
        
        # 🔥 КРИТИЧЕСКАЯ ПРОВЕРКА: бот НЕ ГОТОВ!
        if self.bot is None:
            logger.error(f"❌ Bot not ready for instance {self.instance_id}, skipping update {update.update_id}. Token: {bool(self.token)}")
            return
            
        if update.message:
            logger.info(
                f"Message from user {update.message.from_user.id} ({update.message.from_user.username or 'no username'}): {update.message.text or '[non-text message]'}"
            )
        elif update.callback_query:
            logger.info(
                f"Callback query from user {update.callback_query.from_user.id}: data={update.callback_query.data}"
            )
        else:
            logger.info(f"Other update type: {update}")

        try:
            await self.dp.feed_update(self.bot, update)
            logger.info(
                f"Update {update.update_id} successfully fed to dispatcher for instance {self.instance_id}"
            )
        except Exception as e:
            logger.error(
                f"Error feeding update {update.update_id} to dispatcher for instance {self.instance_id}: {e}",
                exc_info=True,
            )


if __name__ == "__main__":
    import asyncio
    try:
        print("🔥 DEBUG: Starting asyncio.run(run_worker())")  # 🔥 DEBUG!
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped")
    except Exception as e:
        logger.error(f"FATAL: {e}", exc_info=True)
        import sys
        sys.exit(1)