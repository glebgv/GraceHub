# src/master_bot/miniapp_api.py
"""
Mini App API для управления инстансами ботов.
Интегрируется с master‑ботом и SQLite базой.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import secrets
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from shared import settings

from .main import MasterBot

logger = logging.getLogger(__name__)

# ========================================================================
# Models & Schemas
# ========================================================================


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(..., alias="initData")
    start_param: Optional[str] = None

    class Config:
        populate_by_name = True


class UserResponse(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    language: Optional[str]
    roles: List[str] = Field(default_factory=list)
    instances: List[Dict[str, Any]] = Field(default_factory=list)


class AuthResponse(BaseModel):
    token: str
    user: UserResponse
    default_instance_id: Optional[str] = None


class InstanceMember(BaseModel):
    user_id: int
    username: Optional[str]
    role: str  # owner, operator, viewer
    created_at: str


class InstanceInfo(BaseModel):
    instance_id: str
    bot_username: str
    bot_name: str
    role: str
    status: str = "running"
    created_at: str
    openchat_username: Optional[str] = None
    general_panel_chat_id: Optional[int] = None


class TicketStats(BaseModel):
    new: int = 0
    inprogress: int = 0
    answered: int = 0
    closed: int = 0
    spam: int = 0


class UsageStats(BaseModel):
    messages: int = 0
    api_calls: int = 0


class InstanceStats(BaseModel):
    instance_id: str
    period: Dict[str, str]
    tickets_by_status: TicketStats
    avg_first_response_sec: int = 0
    unique_users: int = 0
    usage: UsageStats


class AutoReplyConfig(BaseModel):
    greeting: Optional[str] = None
    default_answer: Optional[str] = None


class BrandingConfig(BaseModel):
    bot_name: Optional[str] = None
    status_emoji_scheme: Optional[Dict[str, str]] = None


class OpenChatConfig(BaseModel):
    enabled: bool = False
    openchat_username: Optional[str] = None
    general_panel_chat_id: Optional[int] = None

class InstanceSettings(BaseModel):
    openchat_enabled: bool = False
    autoclose_hours: int = 12
    general_panel_chat_id: Optional[int] = None 
    auto_reply: AutoReplyConfig
    branding: BrandingConfig
    privacy_mode_enabled: bool = False
    language: Optional[str] = None
    openchat: Optional[OpenChatConfig] = None

class UpdateInstanceSettings(BaseModel):
    autoclose_hours: Optional[int] = None
    auto_reply: Optional[AutoReplyConfig] = None
    branding: Optional[BrandingConfig] = None
    openchat_enabled: Optional[bool] = None
    privacy_mode_enabled: Optional[bool] = None
    language: Optional[str] = None


class TicketItem(BaseModel):
    ticket_id: int
    user_id: int
    username: Optional[str]
    status: str
    status_emoji: str
    created_at: str
    last_user_msg_at: Optional[str]
    last_admin_reply_at: Optional[str]
    openchat_topic_id: Optional[int]


class TicketsListResponse(BaseModel):
    items: List[TicketItem]
    total: int


class AddOperatorRequest(BaseModel):
    user_id: Optional[int] = None
    username: Optional[str] = None
    role: str = "operator"  # operator, viewer


class ResolveInstanceRequest(BaseModel):
    """
    Запрос на определение инстанса при старте мини‑аппы.
    Любое из полей может быть None:
    - instance_id: явное указание инстанса
    - admin_id: Telegram user id администратора, к которому привязан инстанс
    """

    instance_id: Optional[str] = None
    admin_id: Optional[int] = None


class ResolveInstanceResponse(BaseModel):
    """
    Ответ для мини‑аппы при старте.
    Если instance_id указан — панель открывается сразу для этого инстанса.
    Если instance_id = None — фронт должен запросить список инстансов /api/instances.
    """

    instance_id: Optional[str] = None
    bot_username: Optional[str] = None
    bot_name: Optional[str] = None
    role: Optional[str] = None
    created_at: Optional[str] = None
    openchat_username: Optional[str] = None
    general_panel_chat_id: Optional[int] = None
    # флаг, что ссылка запрещена (панель только для владельца)
    link_forbidden: bool = False


class CreateInstanceRequest(BaseModel):
    """Создание нового инстанса по токену бота (аналог /add_bot)."""

    token: str


class CreateInstanceResponse(BaseModel):
    instanceid: str
    botusername: str
    botname: str
    role: str = "owner"

class BillingInfo(BaseModel):
    instance_id: str
    plan_code: str
    plan_name: str
    price_stars: int
    tickets_used: int
    tickets_limit: int
    over_limit: bool
    period_start: str
    period_end: str
    days_left: int
    unlimited: bool 

class SaasPlanOut(BaseModel):
    planCode: str
    planName: str
    periodDays: int
    ticketsLimit: int
    priceStars: int
    productCode: str | None

# ========================================================================
# Telegram Validation
# ========================================================================


class TelegramAuthValidator:
    """Безопасная валидация Telegram initData."""

    def __init__(self, bot_token: str, session_ttl_hours: int = 24):
        self.bot_token = bot_token
        self.session_ttl = session_ttl_hours * 3600
        self._session_cache: Dict[str, float] = {}  # hash -> timestamp

    def validate(self, init_data: str) -> Dict[str, Any]:
        """Валидирует initData и возвращает распарсенные данные."""
        logger.debug(
            "TelegramAuthValidator.validate: raw init_data length=%s",
            len(init_data) if init_data else 0,
        )

        if not init_data or init_data.isspace():
            raise ValueError("initData пуста")

        from urllib.parse import parse_qsl, unquote

        try:
            params = dict(parse_qsl(init_data, keep_blank_values=True))
        except ValueError:
            logger.error("initData parse error, raw=%r", init_data)
            raise ValueError("Ошибка парсинга initData")

        hash_value = params.pop("hash", None)
        if not hash_value:
            logger.error("initData missing hash, raw=%r", init_data)
            raise ValueError("hash отсутствует в initData")

        if "user" in params:
            try:
                params["user"] = unquote(params["user"])
            except Exception:
                logger.warning("Не удалось URL-декодировать user, используем как есть")

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

        secret_key = hmac.new(
            b"WebAppData",
            self.bot_token.encode(),
            hashlib.sha256,
        ).digest()

        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        logger.error(
            "initData sign check: expected=%s given=%s data_check_string=%r",
            expected_hash,
            hash_value,
            data_check_string,
        )

        if not hmac.compare_digest(expected_hash, hash_value):
            raise ValueError("Подпись initData невалидна")

        auth_date = params.get("auth_date")
        if not auth_date:
            raise ValueError("auth_date отсутствует")

        try:
            auth_timestamp = int(auth_date)
        except ValueError:
            raise ValueError("auth_date некорректна")

        current_timestamp = int(time.time())
        if current_timestamp - auth_timestamp > 3600:
            raise ValueError("initData истекла (> 1 часа)")

        if self._check_replay(hash_value):
            logger.info("initData replay detected, пропускаем (hash=%s)", hash_value)
        else:
            self._session_cache[hash_value] = current_timestamp

        user_data_str = params.get("user")
        if not user_data_str:
            raise ValueError("user отсутствует в initData")

        try:
            user_data = json.loads(user_data_str)
        except (json.JSONDecodeError, ValueError):
            raise ValueError("Ошибка парсинга user JSON")

        logger.debug(
            "TelegramAuthValidator.validate: user parsed user_id=%s username=%s",
            user_data.get("id"),
            user_data.get("username"),
        )

        return {
            "user_id": user_data.get("id"),
            "username": user_data.get("username"),
            "first_name": user_data.get("first_name"),
            "last_name": user_data.get("last_name"),
            "language_code": user_data.get("language_code"),
        }

    def _check_replay(self, hash_value: str) -> bool:
        """Проверяет, видели ли мы этот hash раньше."""
        current_time = time.time()

        self._session_cache = {
            h: ts
            for h, ts in self._session_cache.items()
            if current_time - ts < self.session_ttl
        }

        return hash_value in self._session_cache


# ========================================================================
# JWT / Session Token (минимальный, для MVP)
# ========================================================================


class SessionManager:
    """Управление сессиями mini app."""

    def __init__(self, ttl_minutes: int = 30):
        self.ttl = ttl_minutes * 60
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def create_session(self, user_id: int, username: Optional[str]) -> str:
        """Создаёт токен сессии."""
        token = secrets.token_urlsafe(32)
        self._sessions[token] = {
            "user_id": user_id,
            "username": username,
            "created_at": time.time(),
        }
        logger.info(
            "SessionManager.create_session: user_id=%s token_prefix=%s",
            user_id,
            token[:8],
        )
        return token

    def validate_session(self, token: str) -> Dict[str, Any]:
        """Валидирует токен и возвращает данные."""
        session = self._sessions.get(token)
        if not session:
            raise ValueError("Сессия не найдена")

        created_at = session.get("created_at", 0)
        if time.time() - created_at > self.ttl:
            del self._sessions[token]
            raise ValueError("Сессия истекла")

        return session

    def cleanup_expired(self):
        """Удаляет истекшие сессии."""
        current_time = time.time()
        before = len(self._sessions)
        self._sessions = {
            token: session
            for token, session in self._sessions.items()
            if current_time - session.get("created_at", 0) < self.ttl
        }
        after = len(self._sessions)
        if before != after:
            logger.info(
                "SessionManager.cleanup_expired: %s -> %s",
                before,
                after,
            )


# ========================================================================
# Database Access Layer
# ========================================================================


class MiniAppDB:
    """Обёртка над MasterDatabase для mini app."""

    def __init__(self, db):
        self.db = db

    async def upsert_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        logger.debug("MiniAppDB.upsert_user: user_id=%s username=%s", user_id, username)
        await self.db.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name, language, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
                username   = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name  = EXCLUDED.last_name,
                language   = EXCLUDED.language,
                updated_at = EXCLUDED.updated_at
            """,
            (
                user_id,
                username,
                first_name,
                last_name,
                language,
                datetime.now(timezone.utc),
            ),
        )


    async def get_user_instances(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Инстансы, к которым у юзера есть доступ (владельцы/интеграторы).
        """
        logger.debug("MiniAppDB.get_user_instances: user_id=%s", user_id)

        rows = await self.db.fetchall(
            """
            SELECT
                bi.instance_id   AS instance_id,
                bi.bot_username  AS bot_username,
                bi.bot_name      AS bot_name,
                bi.created_at    AS created_at,
                bi.owner_user_id AS owner_user_id,
                bi.admin_private_chat_id AS admin_private_chat_id,
                bi.user_id       AS owner_id
            FROM bot_instances bi
            WHERE bi.user_id = %s OR bi.owner_user_id = %s
            ORDER BY bi.created_at DESC
            """,
            (user_id, user_id),
        )


        result: List[Dict[str, Any]] = []
        for row in rows:
            inst = dict(row)
            inst["role"] = "owner"
            meta = await self.db.fetchone(
                """
                SELECT openchat_username,
                    general_panel_chat_id,
                    auto_close_hours,
                    auto_reply_greeting,
                    auto_reply_default_answer,
                    branding_bot_name,
                    openchat_enabled,
                    language
                FROM instance_meta
                WHERE instance_id = %s
                """,
                (inst["instance_id"],),
            )

            if meta:
                inst.update(dict(meta))
            result.append(inst)

        logger.info(
            "MiniAppDB.get_user_instances: user_id=%s instances=%s",
            user_id,
            [i["instance_id"] for i in result],
        )
        return result

    async def get_instance_billing(self, instance_id: str) -> Optional[Dict[str, Any]]:
        row = await self.db.fetchone(
            """
            SELECT
                ib.instance_id,
                ib.plan_id,
                ib.period_start,
                ib.period_end,
                ib.tickets_used,
                ib.tickets_limit,
                ib.over_limit,
                sp.code       AS plan_code,
                sp.name       AS plan_name,
                sp.price_stars,
                sp.period_days
            FROM instance_billing AS ib
            JOIN saas_plans AS sp ON sp.plan_id = ib.plan_id
            WHERE ib.instance_id = %s
            """,
            (instance_id,),
        )
        return dict(row) if row else None


    async def get_worker_setting(self, instanceid: str, key: str) -> Optional[str]:
        row = await self.db.fetchone(
            "SELECT value FROM workersettings WHERE instanceid = %s AND key = %s",
            (instanceid, key),
        )
        return row["value"] if row else None

    async def set_worker_setting(self, instanceid: str, key: str, value: str) -> None:
        await self.db.execute(
            """
            INSERT INTO workersettings (instanceid, key, value)
            VALUES (%s, %s, %s)
            ON CONFLICT (instanceid, key) DO UPDATE
              SET value = EXCLUDED.value
            """,
            (instanceid, key, value),
        )

    async def get_instance_by_id(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Инстанс по instance_id с метаданными."""
        logger.debug("MiniAppDB.get_instance_by_id: instance_id=%s", instance_id)
        row = await self.db.fetchone(
            """
            SELECT
                bi.instance_id,
                bi.bot_username,
                bi.bot_name,
                bi.created_at,
                bi.owner_user_id,
                bi.admin_private_chat_id,
                bi.user_id as owner_id
            FROM bot_instances bi
            WHERE bi.instance_id = %s
            LIMIT 1
            """,
            (instance_id,),
        )

        if not row:
            return None

        inst = dict(row)
        meta = await self.db.fetchone(
            """
            SELECT
                openchat_username,
                general_panel_chat_id,
                auto_close_hours,
                auto_reply_greeting,
                auto_reply_default_answer,
                branding_bot_name,
                openchat_enabled,
                language
            FROM instance_meta
            WHERE instance_id = %s
            """,
            (inst["instance_id"],),
        )
        if meta:
            inst.update(dict(meta))
        inst["role"] = "owner"
        return inst

    async def get_instance_by_owner(self, owner_user_id: int) -> Optional[Dict[str, Any]]:
        """Инстанс, где owner_user_id совпадает с переданным Telegram user id."""
        logger.debug("MiniAppDB.get_instance_by_owner: owner_user_id=%s", owner_user_id)
        row = await self.db.fetchone(
            """
            SELECT
                bi.instance_id,
                bi.bot_username,
                bi.bot_name,
                bi.created_at,
                bi.owner_user_id,
                bi.admin_private_chat_id
            FROM bot_instances bi
            WHERE bi.owner_user_id = %s
            ORDER BY bi.created_at DESC
            LIMIT 1
            """,
            (owner_user_id,),
        )

        if not row:
            return None

        inst = dict(row)
        meta = await self.db.fetchone(
            """
            SELECT
                openchat_username,
                general_panel_chat_id,
                auto_close_hours,
                auto_reply_greeting,
                auto_reply_default_answer,
                branding_bot_name,
                openchat_enabled,
                language
            FROM instance_meta
            WHERE instance_id = %s
            """,
            (inst["instance_id"],),
        )
        if meta:
            inst.update(dict(meta))
        inst["role"] = "owner"
        return inst

    async def add_instance_member(
        self, instance_id: str, user_id: int, role: str
    ) -> None:
        """Добавляет участника к инстансу."""
        logger.info(
            "MiniAppDB.add_instance_member: instance_id=%s user_id=%s role=%s",
            instance_id,
            user_id,
            role,
        )
        await self.db.execute(
            """
            INSERT INTO instance_members (instance_id, user_id, role, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (instance_id, user_id)
            DO UPDATE SET
                role       = EXCLUDED.role,
                created_at = EXCLUDED.created_at
            """,
            (instance_id, user_id, role, datetime.now(timezone.utc)),
        )


    async def remove_instance_member(self, instance_id: str, user_id: int) -> None:
        """Удаляет участника."""
        logger.info(
            "MiniAppDB.remove_instance_member: instance_id=%s user_id=%s",
            instance_id,
            user_id,
        )
        await self.db.execute(
            "DELETE FROM instance_members WHERE instance_id = %s AND user_id = %s",
            (instance_id, user_id),
        )




    async def get_instance_members(self, instance_id: str) -> List[Dict[str, Any]]:
        """Участники инстанса."""
        rows = await self.db.fetchall(
            """
            SELECT im.user_id, u.username, im.role, im.created_at
            FROM instance_members im
            LEFT JOIN users u ON im.user_id = u.user_id
            WHERE im.instance_id = %s
            ORDER BY im.role DESC, im.created_at ASC
            """,
            (instance_id,),
        )

        result = [dict(row) for row in rows]
        logger.debug(
            "MiniAppDB.get_instance_members: instance_id=%s count=%s",
            instance_id,
            len(result),
        )
        return result

    async def get_instance_stats(
        self, instance_id: str, days: int = 30
    ) -> Dict[str, Any]:
        """Живая статистика по тикетам из Postgres."""
        date_from = datetime.now(timezone.utc) - timedelta(days=days)

        # 1. Кол-во тикетов по статусам
        rows = await self.db.fetchall(
            """
            SELECT LOWER(status) AS status, COUNT(*) AS cnt
            FROM tickets
            WHERE instance_id = %s
            AND created_at >= %s
            GROUP BY LOWER(status)
            """,
            (instance_id, date_from),
        )

        status_counts = {
            "new": 0,
            "inprogress": 0,
            "answered": 0,
            "closed": 0,
            "spam": 0,
        }

        status_map = {
            "new": "new",
            "open": "new",
            "inprogress": "inprogress",
            "solved": "answered",
            "answered": "answered",
            "closed": "closed",
            "spam": "spam",
        }

        for row in rows:
            raw = (row["status"] or "").lower()
            key = status_map.get(raw)
            if key:
                status_counts[key] += row["cnt"]

        # 2. Уникальные пользователи
        uniq_row = await self.db.fetchone(
            """
            SELECT COUNT(DISTINCT user_id) AS uniq_users
            FROM tickets
            WHERE instance_id = %s
            AND created_at >= %s
            """,
            (instance_id, date_from),
        )
        unique_users = uniq_row["uniq_users"] if uniq_row else 0

        # 3. Среднее время до первого ответа админа
        rows = await self.db.fetchall(
            """
            SELECT created_at, last_admin_reply_at
            FROM tickets
            WHERE instance_id = %s
            AND created_at >= %s
            AND last_admin_reply_at IS NOT NULL
            """,
            (instance_id, date_from),
        )

        total_delta = 0.0
        count = 0

        for row in rows:
            created = row["created_at"]
            first_reply = row["last_admin_reply_at"]
            if not created or not first_reply:
                continue
            delta = (first_reply - created).total_seconds()
            if delta >= 0:
                total_delta += delta
                count += 1

        avg_first_response_sec = int(total_delta / count) if count > 0 else 0

        now = datetime.now(timezone.utc)

        return {
            "instance_id": instance_id,
            "period": {
                "from": date_from.isoformat(),
                "to": now.isoformat(),
            },
            "tickets_by_status": status_counts,
            "avg_first_response_sec": avg_first_response_sec,
            "unique_users": unique_users,
            "usage": {
                "messages": 0,
                "api_calls": 0,
            },
        }


    # ==== Тикеты: листинг ====
    async def list_tickets(
        self,
        instanceid: str,
        status: Optional[str],
        search: Optional[str],
        limit: int,
        offset: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Возвращает список тикетов из Postgres (tickets),
        с учётом фильтра по статусу и поиску, плюс total для пагинации.
        """

        where_clauses: List[str] = ["instance_id = %s"]
        params: List[Any] = [instanceid]

        # фильтр по статусу (нормализуем как раньше)
        if status:
            status_map = {
                "new": ["new", "open"],
                "inprogress": ["inprogress"],
                "answered": ["answered", "solved"],
                "closed": ["closed"],
                "spam": ["spam"],
            }
            allowed_raw = status_map.get(status.lower())
            if not allowed_raw:
                return [], 0

            placeholders = ", ".join(["%s"] * len(allowed_raw))
            where_clauses.append(f"LOWER(status) IN ({placeholders})")
            params.extend([s.lower() for s in allowed_raw])

        # поиск по username / user_id
        if search:
            where_clauses.append(
                "(username ILIKE %s OR CAST(user_id AS TEXT) LIKE %s)"
            )
            like = f"%{search}%"
            params.extend([like, like])

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # total
        row = await self.db.fetchone(
            f"SELECT COUNT(*) AS cnt FROM tickets{where_sql}",
            tuple(params),
        )
        total = int(row["cnt"]) if row else 0
        if total == 0:
            return [], 0

        # список тикетов
        rows = await self.db.fetchall(
            f"""
            SELECT
                id                  AS ticketid,
                user_id             AS userid,
                username            AS username,
                status              AS status,
                created_at          AS createdat,
                last_user_msg_at    AS lastusermsgat,
                last_admin_reply_at AS lastadminreplyat,
                thread_id           AS openchattopicid
            FROM tickets
            {where_sql}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params + [limit, offset]),
        )

        status_norm_map = {
            "new": "new",
            "open": "new",
            "inprogress": "inprogress",
            "answered": "answered",
            "solved": "answered",
            "closed": "closed",
            "spam": "spam",
        }

        result: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)

            # нормализуем статус
            raw = (item.get("status") or "").lower()
            item["status"] = status_norm_map.get(raw, "new")

            # конвертируем даты в строки (для Pydantic TicketItem: created_at/last_* = str)
            for key in ("createdat", "lastusermsgat", "lastadminreplyat"):
                v = item.get(key)
                if isinstance(v, datetime):
                    item[key] = v.isoformat()
                elif v is not None:
                    item[key] = str(v)

            result.append(item)

        return result, total

    # ==== Тикеты: обновление статуса ====

    async def update_ticket_status(
        self,
        instanceid: str,
        ticketid: int,
        status: str,
    ) -> None:
        """
        Обновляет статус тикета в worker-DB.
        Фронт шлёт нормализованный статус: new / inprogress / answered / closed / spam.
        """
        worker_db_path = Path("data/instances") / f"{instanceid}.db"
        if not worker_db_path.exists():
            logger.error(
                "MiniAppDB.update_ticket_status worker DB not found for instance_id=%s, path=%s",
                instanceid,
                worker_db_path,
            )
            raise HTTPException(status_code=404, detail="Instance worker DB not found")

        allowed = {"new", "inprogress", "answered", "closed", "spam"}
        norm = status.lower()
        if norm not in allowed:
            raise HTTPException(status_code=400, detail="Invalid status")

        # маппинг обратно в raw-значение для таблицы tickets
        norm_to_raw = {
            "new": "new",
            "inprogress": "inprogress",
            "answered": "answered",
            "closed": "closed",
            "spam": "spam",
        }
        raw_status = norm_to_raw[norm]

        conn = sqlite3.connect(str(worker_db_path))
        cur = conn.cursor()

        now_iso = datetime.now(timezone.utc).isoformat()

        set_parts: List[str] = ["status = ?", "updatedat = ?"]
        params: List[Any] = [raw_status, now_iso]

        # если закрываем тикет — ставим closedat
        if norm in {"closed", "spam"}:
            set_parts.append("closedat = ?")
            params.append(now_iso)

        params.append(ticketid)
        sql = f"UPDATE tickets SET {', '.join(set_parts)} WHERE id = ?"
        cur.execute(sql, params)
        conn.commit()
        conn.close()


    async def check_access(
        self, instance_id: str, user_id: int, required_role: Optional[str] = None
    ) -> bool:
        """Бинарный доступ: только владелец (user_id или owner_user_id)."""
        row = await self.db.fetchone(
            """
            SELECT
                bi.user_id       AS owner_id,
                bi.owner_user_id AS integrator_id
            FROM bot_instances bi
            WHERE bi.instance_id = %s
            """,
            (instance_id,),
        )

        if not row:
            logger.info(
                "MiniAppDB.check_access: deny (no row) instance_id=%s user_id=%s",
                instance_id,
                user_id,
            )
            return False

        owner_match = row["owner_id"] == user_id or (
            "integrator_id" in row.keys() and row["integrator_id"] == user_id
        )

        if not owner_match:
            logger.info(
                "MiniAppDB.check_access: deny (not owner) instance_id=%s user_id=%s",
                instance_id,
                user_id,
            )
            return False

        logger.debug(
            "MiniAppDB.check_access: allow (owner) instance_id=%s user_id=%s",
            instance_id,
            user_id,
        )
        return True

    async def find_instance_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        row = await self.db.fetchone(
            """
            SELECT
                instance_id,
                bot_username,
                bot_name,
                created_at,
                owner_user_id,
                user_id AS owner_id
            FROM bot_instances
            WHERE token_hash = ?
            LIMIT 1
            """,
            (token_hash,),
        )
        return dict(row) if row else None

    # -------- Настройки инстанса (для mini app Settings.tsx) --------

    async def get_privacy_mode(self, instance_id: str) -> bool:
        row = await self.db.fetchone(
            """
            SELECT value
            FROM worker_settings
            WHERE instance_id = %s AND key = 'privacy_mode_enabled'
            """,
            (instance_id,),
        )
        return bool(row and row["value"] == "True")

    async def get_instance_settings(self, instance_id: str) -> InstanceSettings:
        inst = await self.get_instance_by_id(instance_id)
        if not inst:
            raise HTTPException(status_code=404, detail="Instance not found")

        # базовые значения по умолчанию
        auto_close_hours = 12
        greeting: Optional[str] = None
        default_answer: Optional[str] = None
        branding_bot_name = inst.get("bot_name")
        openchat_enabled = False
        openchat_username = inst.get("openchat_username")
        general_panel_chat_id = inst.get("general_panel_chat_id")
        language: Optional[str] = None

        meta = await self.db.fetchone(
            """
            SELECT
                openchat_username,
                general_panel_chat_id,
                auto_close_hours,
                auto_reply_greeting,
                auto_reply_default_answer,
                branding_bot_name,
                openchat_enabled,
                language
            FROM instance_meta
            WHERE instance_id = %s
            """,
            (instance_id,),
        )

        if meta:
            m = dict(meta)
            if m.get("auto_close_hours") is not None:
                auto_close_hours = m["auto_close_hours"]
            greeting = m.get("auto_reply_greeting")
            default_answer = m.get("auto_reply_default_answer")
            if m.get("branding_bot_name"):
                branding_bot_name = m["branding_bot_name"]
            if m.get("openchat_enabled") is not None:
                openchat_enabled = bool(m["openchat_enabled"])
            if m.get("openchat_username") is not None:
                openchat_username = m["openchat_username"]
            if m.get("general_panel_chat_id") is not None:
                general_panel_chat_id = m["general_panel_chat_id"]
            if m.get("language") is not None:
                language = m["language"]

        # читаем реальный Privacy Mode из worker_settings
        privacy_mode_enabled = await self.get_privacy_mode(instance_id)

        return InstanceSettings(
            openchat_enabled=openchat_enabled,
            general_panel_chat_id=general_panel_chat_id,
            autoclose_hours=auto_close_hours,
            auto_reply=AutoReplyConfig(
                greeting=greeting,
                default_answer=default_answer,
            ),
            branding=BrandingConfig(
                bot_name=branding_bot_name,
                status_emoji_scheme={
                    "new": "⬜️",
                    "inprogress": "🟨",
                    "answered": "🟩",
                    "closed": "🟥",
                    "spam": "🟦",
                    "muted": "⬛️",
                },
            ),
            privacy_mode_enabled=privacy_mode_enabled,
            language=language,
        )


    async def set_worker_setting(self, instance_id: str, key: str, value: str) -> None:
        await self.db.execute(
            """
            INSERT INTO worker_settings (instance_id, key, value)
            VALUES (%s, %s, %s)
            ON CONFLICT (instance_id, key) DO UPDATE
              SET value = EXCLUDED.value
            """,
            (instance_id, key, value),
        )

    async def update_instance_settings(
        self, instance_id: str, payload: UpdateInstanceSettings
    ) -> None:
        existing = await self.db.fetchone(
            "SELECT * FROM instance_meta WHERE instance_id = %s",
            (instance_id,),
        )

        fields = {
            "auto_close_hours": payload.autoclose_hours,
            "auto_reply_greeting": payload.auto_reply.greeting
            if payload.auto_reply
            else None,
            "auto_reply_default_answer": payload.auto_reply.default_answer
            if payload.auto_reply
            else None,
            "branding_bot_name": payload.branding.bot_name
            if payload.branding
            else None,
            "openchat_enabled": payload.openchat_enabled
            if payload.openchat_enabled is not None
            else None,
            "language": payload.language if payload.language is not None else None,
        }

        # синхронизация greeting с worker_settings.greeting_text
        if payload.auto_reply and payload.auto_reply.greeting is not None:
            greeting_text = payload.auto_reply.greeting or ""
            await self.set_worker_setting(instance_id, "greeting_text", greeting_text)

        # синхронизация автоответа с worker_settings.autoreply_*
        if payload.auto_reply:
            enabled = getattr(payload.auto_reply, "enabled", None)
            if enabled is not None:
                await self.set_worker_setting(
                    instance_id,
                    "autoreply_enabled",
                    "True" if enabled else "False",
                )

            if payload.auto_reply.default_answer is not None:
                auto_text = payload.auto_reply.default_answer or ""
                await self.set_worker_setting(
                    instance_id,
                    "autoreply_text",
                    auto_text,
                )

        # синхронизация Privacy Mode
        if payload.privacy_mode_enabled is not None:
            await self.set_worker_setting(
                instance_id,
                "privacy_mode_enabled",
                "True" if payload.privacy_mode_enabled else "False",
            )

        if not existing:
            await self.db.execute(
                """
                INSERT INTO instance_meta (
                    instance_id,
                    openchat_username,
                    general_panel_chat_id,
                    auto_close_hours,
                    auto_reply_greeting,
                    auto_reply_default_answer,
                    branding_bot_name,
                    openchat_enabled,
                    language,
                    updated_at
                ) VALUES (%s, NULL, NULL, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    instance_id,                         # %s (instance_id)
                    fields["auto_close_hours"],          # %s (auto_close_hours)
                    fields["auto_reply_greeting"],       # %s (auto_reply_greeting)
                    fields["auto_reply_default_answer"], # %s (auto_reply_default_answer)
                    fields["branding_bot_name"],         # %s (branding_bot_name)
                    fields["openchat_enabled"],          # %s (openchat_enabled)
                    fields["language"],                  # %s (language)
                    datetime.now(timezone.utc),          # %s (updated_at)
                ),
            )

        else:
            set_parts = []
            params: List[Any] = []

            for col, value in fields.items():
                if value is not None:
                    set_parts.append(f"{col} = %s")
                    params.append(value)

            set_parts.append("updated_at = %s")
            params.append(datetime.now(timezone.utc))
            params.append(instance_id)

            if set_parts:
                sql = f"""
                UPDATE instance_meta
                SET {", ".join(set_parts)}
                WHERE instance_id = %s
                """
                await self.db.execute(sql, tuple(params))


# ========================================================================
# FastAPI App
# ========================================================================


telegram_validator: Optional[TelegramAuthValidator] = None
session_manager: Optional[SessionManager] = None
miniapp_db: Optional[MiniAppDB] = None
master_bot: Optional[MasterBot] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и очистка."""
    logger.info("Mini App API запущен")
    yield
    logger.info("Mini App API завершает работу")


def create_miniapp_app(
    master_db,
    master_bot_instance: MasterBot,
    bot_token: str,
    webhook_domain: str,
    debug: bool = False,
) -> FastAPI:
    """Создаёт FastAPI приложение для mini app."""
    global telegram_validator, session_manager, miniapp_db, master_bot

    app = FastAPI(title="GraceHub Mini App API", debug=debug, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        body = exc.body
        logger.error(
            "Validation error on %s %s: errors=%s body=%s",
            request.method,
            request.url.path,
            exc.errors(),
            body,
        )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "body": body},
        )

    telegram_validator = TelegramAuthValidator(bot_token)
    session_manager = SessionManager(ttl_minutes=30)
    miniapp_db = MiniAppDB(master_db)
    master_bot = master_bot_instance

    # ====================================================================
    # Dependencies
    # ====================================================================

    async def get_current_user(
        authorization: Optional[str] = Header(None),
    ) -> Dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Отсутствует токен")

        token = authorization[7:]
        try:
            session = session_manager.validate_session(token)
            return session
        except ValueError as e:
            raise HTTPException(status_code=401, detail=str(e))

    async def require_instance_access(
        instance_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
        required_role: Optional[str] = None,
    ) -> None:
        has_access = await miniapp_db.check_access(
            instance_id, current_user["user_id"], required_role
        )
        if not has_access:
            raise HTTPException(status_code=403, detail="Нет доступа к этому инстансу")

    # ====================================================================
    # Endpoints
    # ====================================================================
    @app.post("/api/auth/telegram", response_model=AuthResponse)
    async def auth_telegram(req: TelegramAuthRequest, request: Request):
        init_header = request.headers.get("X-Telegram-Init-Data")
        logger.info(
            "auth_telegram: initData_len=%s start_param=%s has_header=%s header_len=%s",
            len(req.init_data) if req.init_data else 0,
            req.start_param,
            bool(init_header),
            len(init_header or ""),
        )
        logger.debug("auth_telegram RAW initData: %r", req.init_data)

        # Валидация initData от Telegram
        try:
            user_data = telegram_validator.validate(req.init_data)
        except ValueError as e:
            logger.warning("Ошибка валидации Telegram: %s", e)
            raise HTTPException(status_code=401, detail=str(e))

        user_id = user_data.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="user_id не найден в initData")

        # Single-tenant режим: панель доступна только владельцу
        if settings.SINGLE_TENANT_OWNER_ONLY:
            owner_id = settings.OWNER_TELEGRAM_ID
            if not owner_id or user_id != owner_id:
                # фронт уже умеет показывать t('app.owner_only') по 403
                raise HTTPException(
                    status_code=403,
                    detail="панель доступна только владельцу",
                )

        # Обновляем/создаём пользователя в БД мини‑аппы
        await miniapp_db.upsert_user(
            user_id=user_id,
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            language=user_data.get("language_code"),
        )

        # Получаем инстансы, к которым у юзера есть доступ (владельцы/интеграторы)
        instances = await miniapp_db.get_user_instances(user_id)

        # Определяем default_instance_id: сначала из start_param=inst_<id>, потом первый из списка
        default_instance_id: str | None = None
        if req.start_param and req.start_param.startswith("inst_"):
            requested_id = req.start_param[5:]
            for inst in instances:
                if inst["instance_id"] == requested_id:
                    default_instance_id = requested_id
                    break

        if not default_instance_id and instances:
            default_instance_id = instances[0]["instance_id"]

        # Создаём сессию для mini app
        token = session_manager.create_session(user_id, user_data.get("username"))

        logger.info(
            "auth_telegram: user_id=%s instances=%s default_instance_id=%s",
            user_id,
            [i["instance_id"] for i in instances],
            default_instance_id,
        )

        # Формируем payload пользователя для фронтенда mini app
        user_response = UserResponse(
            user_id=user_id,
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            language=user_data.get("language_code"),
            roles=[],
            instances=[
                {
                    "instance_id": inst["instance_id"],
                    "bot_username": inst.get("bot_username") or "",
                    "bot_name": inst.get("bot_name") or "",
                    "role": inst.get("role") or "owner",
                }
                for inst in instances
            ],
        )

        logger.info(
            "auth_telegram RESPONSE user_id=%s user.instances=%s default_instance_id=%s",
            user_id,
            [i["instance_id"] for i in user_response.instances],
            default_instance_id,
        )

        return AuthResponse(
            token=token,
            user=user_response,
            default_instance_id=default_instance_id,
        )


    @app.get("/api/saas/plans", response_model=list[SaasPlanOut])
    async def get_saas_plans():
        """
        Возвращает список активных тарифных планов с ценой в Stars
        и привязанным billing_product (если есть).
        """
        rows = await miniapp_db.db.fetchall(
            """
            SELECT
                p.plan_id,
                p.code,
                p.name,
                p.price_stars,
                p.period_days,
                p.tickets_limit,
                bp.code AS product_code
            FROM saas_plans AS p
            LEFT JOIN billing_products AS bp
                ON bp.plan_id = p.plan_id
               AND bp.is_active = TRUE
            WHERE p.is_active = TRUE
            ORDER BY p.price_stars
            """,
        )

        result: list[SaasPlanOut] = []
        for row in rows or []:
            result.append(
                SaasPlanOut(
                    planCode=row["code"],
                    planName=row["name"],
                    periodDays=row["period_days"],
                    ticketsLimit=row["tickets_limit"],
                    priceStars=row["price_stars"],
                    productCode=row["product_code"],
                )
            )
        return result

    @app.get("/api/instances/{instance_id}/billing", response_model=BillingInfo)
    async def get_instance_billing_endpoint(
        instance_id: str,
        _: Any = Depends(lambda instance_id=Depends(lambda instance_id: instance_id), current_user=Depends(get_current_user): require_instance_access(instance_id, current_user, required_role=None)),  # псевдо-заглушка, см. ниже
    ):
        """
        Возвращает информацию о тарифе и лимитах для инстанса.
        Доступен всем, у кого есть доступ к инстансу (owner/operator/viewer).
        """

        billing = await miniapp_db.get_instance_billing(instance_id)
        if not billing:
            raise HTTPException(status_code=404, detail="Billing not found for this instance")

        # single-tenant режим: безлимитный тариф
        if settings.SINGLE_TENANT_OWNER_ONLY:
            return BillingInfo(
                instance_id=billing["instance_id"],
                plan_code=billing["plan_code"],
                plan_name=billing["plan_name"],
                price_stars=billing["price_stars"],
                tickets_used=billing["tickets_used"],
                tickets_limit=billing["tickets_limit"],  # можно вернуть как есть или 0/None
                over_limit=False,
                period_start=billing["period_start"].isoformat(),
                period_end=billing["period_end"].isoformat(),
                days_left=0,
                unlimited=True,
            )

        # обычный режим биллинга
        now = datetime.now(timezone.utc)
        period_end: datetime = billing["period_end"]
        days_left = max(0, (period_end.date() - now.date()).days)

        return BillingInfo(
            instance_id=billing["instance_id"],
            plan_code=billing["plan_code"],
            plan_name=billing["plan_name"],
            price_stars=billing["price_stars"],
            tickets_used=billing["tickets_used"],
            tickets_limit=billing["tickets_limit"],
            over_limit=billing["over_limit"],
            period_start=billing["period_start"].isoformat(),
            period_end=billing["period_end"].isoformat(),
            days_left=days_left,
            unlimited=False,
        )


    @app.post("/api/resolve_instance", response_model=ResolveInstanceResponse)
    async def resolve_instance(
        payload: ResolveInstanceRequest,
        current_user: Dict[str, Any] = Depends(get_current_user),
        request: Request = None,
    ):
        user_id = current_user["user_id"]
        init_header = request.headers.get("X-Telegram-Init-Data") if request else None
        logger.info(
            "resolve_instance: user_id=%s payload=%s has_init_header=%s",
            user_id,
            payload.dict(),
            bool(init_header),
        )

        if payload.instance_id:
            inst = await miniapp_db.get_instance_by_id(payload.instance_id)
            if not inst:
                logger.info(
                    "resolve_instance: instance not found instance_id=%s",
                    payload.instance_id,
                )
                return ResolveInstanceResponse(instance_id=None, link_forbidden=False)

            owner_match = (
                inst.get("owner_id") == user_id
                or inst.get("owner_user_id") == user_id
            )
            if not owner_match:
                logger.info(
                    "resolve_instance: forbidden for user_id=%s instance_id=%s",
                    user_id,
                    inst["instance_id"],
                )
                return ResolveInstanceResponse(instance_id=None, link_forbidden=True)

            logger.info(
                "resolve_instance: by instance_id user_id=%s instance_id=%s",
                user_id,
                inst["instance_id"],
            )
            return ResolveInstanceResponse(
                instance_id=inst["instance_id"],
                bot_username=inst.get("bot_username"),
                bot_name=inst.get("bot_name"),
                role="owner",
                created_at=str(inst.get("created_at", "")),
                openchat_username=inst.get("openchat_username"),
                general_panel_chat_id=inst.get("general_panel_chat_id"),
                link_forbidden=False,
            )

        if payload.admin_id is not None:
            if user_id != payload.admin_id:
                logger.info(
                    "resolve_instance: admin_id mismatch current_user_id=%s admin_id=%s",
                    user_id,
                    payload.admin_id,
                )
                return ResolveInstanceResponse(instance_id=None, link_forbidden=True)

            integrator_instance = await miniapp_db.get_instance_by_owner(
                payload.admin_id
            )
            if not integrator_instance:
                logger.info(
                    "resolve_instance: no instance for owner admin_id=%s",
                    payload.admin_id,
                )
                return ResolveInstanceResponse(instance_id=None, link_forbidden=False)

            owner_match = integrator_instance.get("owner_user_id") == user_id
            if not owner_match:
                logger.info(
                    "resolve_instance: user_id=%s has no access to owner instance=%s",
                    user_id,
                    integrator_instance["instance_id"],
                )
                return ResolveInstanceResponse(instance_id=None, link_forbidden=True)

            logger.info(
                "resolve_instance: by admin_id user_id=%s instance_id=%s",
                user_id,
                integrator_instance["instance_id"],
            )
            return ResolveInstanceResponse(
                instance_id=integrator_instance["instance_id"],
                bot_username=integrator_instance.get("bot_username"),
                bot_name=integrator_instance.get("bot_name"),
                role="owner",
                created_at=str(integrator_instance.get("created_at", "")),
                openchat_username=integrator_instance.get("openchat_username"),
                general_panel_chat_id=integrator_instance.get(
                    "general_panel_chat_id"
                ),
                link_forbidden=False,
            )

        logger.info(
            "resolve_instance: no instance/admin provided for user_id=%s, returning empty",
            user_id,
        )
        return ResolveInstanceResponse(instance_id=None, link_forbidden=False)

    @app.get("/api/me", response_model=UserResponse)
    async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
        instances = await miniapp_db.get_user_instances(current_user["user_id"])

        return UserResponse(
            user_id=current_user["user_id"],
            username=current_user.get("username"),
            first_name=None,
            last_name=None,
            language=None,
            roles=[],
            instances=[
                {
                    "instance_id": inst["instance_id"],
                    "role": "owner",
                }
                for inst in instances
            ],
        )

    @app.get("/api/instances", response_model=List[InstanceInfo])
    async def list_instances(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        instances = await miniapp_db.get_user_instances(current_user["user_id"])

        logger.info(
            "/api/instances user_id=%s -> %s",
            current_user["user_id"],
            [i["instance_id"] for i in instances],
        )

        result: List[InstanceInfo] = []
        for inst in instances:
            result.append(
                InstanceInfo(
                    instance_id=inst["instance_id"],
                    bot_username=inst.get("bot_username", "unknown"),
                    bot_name=inst.get("bot_name", "Unknown Bot"),
                    role="owner",
                    created_at=str(inst.get("created_at", "")),
                    openchat_username=inst.get("openchat_username"),
                    general_panel_chat_id=inst.get("general_panel_chat_id"),
                )
            )

        logger.info(
            "/api/instances RESPONSE user_id=%s count=%s",
            current_user["user_id"],
            len(result),
        )

        return result

    # ---------- Создание инстанса через mini app ----------

    async def _telegram_get_me(bot_token: str) -> Dict[str, Any]:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            logger.warning(
                "getMe HTTP error: status=%s body=%s",
                resp.status_code,
                resp.text[:500],
            )
            raise HTTPException(
                status_code=400,
                detail="Не удалось обратиться к Telegram Bot API (getMe)",
            )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("getMe returned not ok: %s", data)
            raise HTTPException(
                status_code=400,
                detail="Telegram вернул ошибку при проверке токена бота",
            )
        result = data.get("result") or {}
        if not result.get("is_bot", True):
            raise HTTPException(
                status_code=400,
                detail="Указан токен не бота",
            )
        return result

    @app.post("/api/instances", response_model=CreateInstanceResponse)
    async def create_instance(
        req: CreateInstanceRequest,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        """
        Создать новый инстанс по токену бота через MasterBot:
        - MasterBot проверяет токен, создаёт запись в БД, шифрует токен, запускает воркер.
        """
        user_id = current_user["user_id"]
        token = req.token.strip()

        if not token:
            raise HTTPException(status_code=400, detail="Токен бота пустой")

        logger.info(
            "create_instance (miniapp): user_id=%s token_preview=%s",
            user_id,
            token[:10],
        )

        if master_bot is None:
            logger.error("create_instance: master_bot is not initialized")
            raise HTTPException(status_code=500, detail="MasterBot не инициализирован")

        try:
            instance = await master_bot.process_bot_token_from_miniapp(
                token=token,
                owner_user_id=user_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception("create_instance: error from MasterBot: %s", e)
            raise HTTPException(
                status_code=500,
                detail="Ошибка при добавлении бота через MasterBot",
            )

        logger.info(
            "create_instance (miniapp): created instance_id=%s user_id=%s bot_username=%s",
            instance.instance_id,
            user_id,
            instance.bot_username,
        )

        return CreateInstanceResponse(
            instanceid=instance.instance_id,
            botusername=instance.bot_username,
            botname=instance.bot_name,
            role="owner",
        )

    @app.get("/api/instances/{instance_id}/stats", response_model=InstanceStats)
    async def get_instance_stats(
        instance_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
        days: int = Query(30, ge=1, le=365),
    ):
        await require_instance_access(instance_id, current_user)

        stats = await miniapp_db.get_instance_stats(instance_id, days)
        return InstanceStats(**stats)


    @app.delete("/api/instances/{instance_id}")
    async def delete_instance_endpoint(
        instance_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        """
        Удаление инстанса из мини-аппы (аналог /remove_bot в мастере).
        Доступ только у владельца / интегратора.
        """
        if master_bot is None:
            logger.error("delete_instance: master_bot is not initialized")
            raise HTTPException(status_code=500, detail="MasterBot не инициализирован")

        # проверяем доступ
        await require_instance_access(instance_id, current_user, required_role="owner")

        # 1. Берём инстанс и токен из master_db, как делает мастер-бот
        instance = await master_bot.db.get_instance(instance_id)
        if not instance:
            logger.info(
                "delete_instance: instance not found instance_id=%s user_id=%s",
                instance_id,
                current_user["user_id"],
            )
            raise HTTPException(status_code=404, detail="Instance not found")

        # Бинарная проверка владельца на всякий случай
        if instance.userid != current_user["user_id"]:
            logger.info(
                "delete_instance: instance not owned by user instance_id=%s user_id=%s",
                instance_id,
                current_user["user_id"],
            )
            raise HTTPException(status_code=403, detail="Нет доступа к этому инстансу")

        token = await master_bot.db.get_decrypted_token(instance_id)

        # 2. Снять вебхук
        if token:
            try:
                await master_bot.webhook_manager.remove_webhook(token)
            except Exception as e:
                logger.warning(
                    "delete_instance: failed to remove webhook for %s: %s",
                    instance_id,
                    e,
                )

        # 3. Остановить воркер
        try:
            master_bot.stop_worker(instance_id)
        except Exception as e:
            logger.warning(
                "delete_instance: failed to stop worker for %s: %s",
                instance_id,
                e,
            )

        # 4. Удалить из БД и кэша master_bot
        await master_bot.db.delete_instance(instance_id)
        master_bot.instances.pop(instance_id, None)

        logger.info(
            "delete_instance: removed instance_id=%s by user_id=%s",
            instance_id,
            current_user["user_id"],
        )

        return {"status": "ok"}



    # ---------- НАСТРОЙКИ ИНСТАНСА (Settings.tsx) ----------

    @app.get("/api/instances/{instance_id}/settings", response_model=InstanceSettings)
    async def get_instance_settings_endpoint(
        instance_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_instance_access(instance_id, current_user)

        settings = await miniapp_db.get_instance_settings(instance_id)
        # settings здесь – твой внутренний объект/словарь с:
        # openchat_enabled, general_panel_chat_id, auto_close_hours,
        # auto_reply, branding, privacy_mode_enabled, language, openchat_username

        logger.info(
            "Instance settings for %s: openchat_enabled=%s general_panel_chat_id=%s language=%s",
            instance_id,
            settings.openchat_enabled,
            settings.general_panel_chat_id,
            settings.language,
        )

        return InstanceSettings(
            openchat_enabled=settings.openchat_enabled,
            autoclose_hours=settings.autoclose_hours,
            general_panel_chat_id=settings.general_panel_chat_id,
            auto_reply=settings.auto_reply,
            branding=settings.branding,
            privacy_mode_enabled=settings.privacy_mode_enabled,
            language=settings.language,
            openchat=OpenChatConfig(
                enabled=settings.openchat_enabled,
                openchat_username=getattr(settings, "openchat_username", None),
                general_panel_chat_id=settings.general_panel_chat_id,
            ),
        )

    @app.post(
        "/api/instances/{instance_id}/settings",
        response_model=InstanceSettings,
    )
    async def update_instance_settings_endpoint(
        instance_id: str,
        settings: UpdateInstanceSettings,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_instance_access(instance_id, current_user, required_role="owner")

        logger.info(
            "update_instance_settings payload: %s",
            settings.dict(),
        )

        logger.info(
            "update_instance_settings: instance_id=%s auto_close_hours=%s openchat_enabled=%s privacy_mode_enabled=%s language=%s",
            instance_id,
            settings.autoclose_hours,
            settings.openchat_enabled,
            settings.privacy_mode_enabled,
            settings.language,
        )

        await miniapp_db.update_instance_settings(instance_id, settings)
        return await miniapp_db.get_instance_settings(instance_id)


    # ---------- Tickets / Operators ----------

    class UpdateTicketStatusRequest(BaseModel):
        status: str = Field(..., description="new, inprogress, answered, closed, spam")

    @app.get(
        "/api/instances/{instance_id}/tickets",
        response_model=TicketsListResponse,
    )
    async def list_tickets_endpoint(
        instance_id: str,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_instance_access(instance_id, current_user)

        logger.debug(
            "list_tickets instance_id=%s status=%s search=%s limit=%s offset=%s",
            instance_id,
            status,
            search,
            limit,
            offset,
        )

        rows, total = await miniapp_db.list_tickets(
            instanceid=instance_id,
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )

        items = [
            TicketItem(
                ticket_id=row["ticketid"],
                user_id=row["userid"],
                username=row.get("username"),
                status=row["status"],
                status_emoji="",  # TODO: подставить из настроек, если нужно
                created_at=row["createdat"],
                last_user_msg_at=row.get("lastusermsgat"),
                last_admin_reply_at=row.get("lastadminreplyat"),
                openchat_topic_id=row.get("openchattopicid"),
            )
            for row in rows
        ]


        return TicketsListResponse(items=items, total=total)

    @app.post("/api/instances/{instance_id}/tickets/{ticket_id}/status")
    async def update_ticket_status_endpoint(
        instance_id: str,
        ticket_id: int,
        payload: UpdateTicketStatusRequest,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_instance_access(instance_id, current_user)

        logger.info(
            "update_ticket_status instance_id=%s ticket_id=%s status=%s user_id=%s",
            instance_id,
            ticket_id,
            payload.status,
            current_user["user_id"],
        )

        await miniapp_db.update_ticket_status(
            instanceid=instance_id,
            ticketid=ticket_id,
            status=payload.status,
        )
        return {"status": "ok"}

    @app.get(
        "/api/instances/{instance_id}/operators",
        response_model=List[InstanceMember],
    )
    async def get_operators(
        instance_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_instance_access(instance_id, current_user)

        members = await miniapp_db.get_instance_members(instance_id)
        return [InstanceMember(**m) for m in members]

    @app.post("/api/instances/{instance_id}/operators")
    async def add_operator(
        instance_id: str,
        req: AddOperatorRequest,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_instance_access(instance_id, current_user, required_role="owner")

        if not req.user_id and not req.username:
            raise HTTPException(
                status_code=400, detail="Укажите user_id или username"
            )

        user_id = req.user_id
        if req.username and not user_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Поиск по username требует интеграции. Используйте user_id."
                ),
            )

        await miniapp_db.add_instance_member(instance_id, user_id, req.role)
        return {"status": "ok", "message": "Оператор добавлен"}

    @app.delete("/api/instances/{instance_id}/operators/{user_id}")
    async def remove_operator(
        instance_id: str,
        user_id: int,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_instance_access(instance_id, current_user, required_role="owner")

        await miniapp_db.remove_instance_member(instance_id, user_id)
        return {"status": "ok", "message": "Оператор удалён"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
