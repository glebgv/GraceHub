# src/master_bot/miniapp_api.py
"""
Mini App API для управления инстансами ботов.
Интегрируется с master‑ботом и SQLite базой.
"""

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, quote, unquote

import httpx
import stripe
from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi import Path as ApiPath
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr, ValidationError

from shared import settings
from worker.main import GraceHubWorker

from .main import MasterBot
from .routers.test_auth import router as test_auth_router

logger = logging.getLogger(__name__)

# Константы под коды ответов
COMMON_AUTH_RESPONSES = {
    401: {"description": "Unauthorized"},
    403: {"description": "Forbidden"},
}

COMMON_NOT_FOUND_RESPONSES = {
    404: {"description": "Not Found"},
}

COMMON_BAD_REQUEST_RESPONSES = {
    400: {"description": "Bad Request"},
}

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
    instance_id: Optional[StrictStr] = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    admin_id: Optional[StrictInt] = None


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


TELEGRAM_BOT_TOKEN_RE = r"^[0-9]{8,10}:[A-Za-z0-9_-]{35}$"


class CreateInstanceRequest(BaseModel):
    token: str = Field(min_length=1, pattern=TELEGRAM_BOT_TOKEN_RE)


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


class PaymentMethod(str, Enum):
    telegram_stars = "telegram_stars"
    ton = "ton"
    yookassa = "yookassa"
    stripe = "stripe"


class CreateInvoiceRequest(BaseModel):
    plan_code: str = Field(..., description="Код тарифа (lite/pro/enterprise/demo)")
    periods: int = Field(..., ge=1, le=24, description="Количество периодов (1,3,12)")
    payment_method: PaymentMethod = Field(
        default=PaymentMethod.telegram_stars,
        description="Метод оплаты",
    )


class CreateInvoiceResponse(BaseModel):
    invoice_id: int = Field(..., description="Unique identifier for the invoice")
    invoice_link: str = Field(..., description="URL to the invoice or payment page")

    # Для TON (для Stars будут None)
    amount_minor_units: Optional[int] = Field(
        None, description="Amount in minor units (e.g., nanoton for TON)"
    )
    amount_ton: Optional[float] = Field(None, description="Human-readable amount in TON")

    # Для Stripe (для других методов будут None)
    session_id: Optional[str] = Field(None, description="Stripe Checkout session ID")
    amount_cents: Optional[int] = Field(
        None, description="Amount in cents (minor units for Stripe currencies like USD)"
    )

    currency: Optional[str] = Field(None, description="Currency code (e.g., 'TON', 'XTR', 'USD')")


class StripeInvoiceStatusResponse(BaseModel):
    invoice_id: int
    status: str  # pending, succeeded, failed, canceled
    session_id: Optional[str] = None
    payment_intent_id: Optional[str] = None
    period_applied: bool = False


class StripeInvoiceCancelResponse(BaseModel):
    invoice_id: int
    status: str


class TonInvoiceStatusResponse(BaseModel):
    invoice_id: int
    status: str
    tx_hash: Optional[str] = None
    period_applied: bool = False


class TonInvoiceCancelResponse(BaseModel):
    invoice_id: int
    status: str


class UpdateTicketStatusRequest(BaseModel):
    status: str = Field(..., description="new, inprogress, answered, closed, spam")


class YooKassaStatusResponse(BaseModel):
    invoice_id: int
    status: str  # pending/succeeded/canceled/waiting_for_capture
    payment_id: str | None = None
    period_applied: bool = False


class PlatformSettingUpsert(BaseModel):
    value: Dict[str, Any]


class SingleTenantConfig(BaseModel):
    enabled: bool = False
    allowed_user_ids: List[int] = Field(default_factory=list)


class SuperadminsUpsert(BaseModel):
    ids: List[int] = Field(default_factory=list)


class SuperadminsResponse(BaseModel):
    ids: List[int] = Field(default_factory=list)


class OfferSettingsOut(BaseModel):
    enabled: bool = False
    url: str = ""


class OfferStatusOut(BaseModel):
    enabled: bool = False
    url: str = ""
    accepted: bool = True
    acceptedAt: Optional[str] = None


class OfferDecisionIn(BaseModel):
    accepted: StrictBool


class YooKassaWebhook(BaseModel):
    event: StrictStr

    class Object(BaseModel):
        id: StrictStr

    object: Object


INSTANCE_ID_RE = r"^[A-Za-z0-9_-]{1,128}$"

InstanceId = Annotated[
    str,
    ApiPath(
        ...,
        min_length=1,
        max_length=128,
        pattern=INSTANCE_ID_RE,
        description="GraceHub instance id",
    ),
]

# ========================================================================
# Telegram Validation
# ========================================================================


def normalize_ids(v: Any) -> List[int]:
    if not v:
        return []
    out: List[int] = []
    if isinstance(v, list):
        for x in v:
            try:
                n = int(x)
                if n > 0:
                    out.append(n)
            except Exception:
                continue
    else:
        try:
            n = int(v)
            if n > 0:
                out.append(n)
        except Exception:
            pass
    return sorted(list(dict.fromkeys(out)))


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
            h: ts for h, ts in self._session_cache.items() if current_time - ts < self.session_ttl
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
            VALUES ($1, $2, $3, $4, $5, $6)
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
            WHERE ib.instance_id = $1
            """,
            (instance_id,),
        )
        return dict(row) if row else None

    async def get_worker_setting(self, instanceid: str, key: str) -> Optional[str]:
        row = await self.db.fetchone(
            "SELECT value FROM worker_settings WHERE instance_id = $1 AND key = $2",
            (instanceid, key),
        )
        return row["value"] if row else None

    async def get_instance_settings(self, instance_id: str) -> InstanceSettings:
        data = await self.db.get_instance_settings(instance_id)
        if not data:
            raise HTTPException(status_code=404, detail="Instance not found")

        privacy_mode_enabled = await self.get_privacy_mode(instance_id)

        return InstanceSettings(
            openchat_enabled=data["openchat_enabled"],
            general_panel_chat_id=data["general_panel_chat_id"],
            autoclose_hours=data["auto_close_hours"],
            auto_reply=AutoReplyConfig(
                greeting=data["greeting"],
                default_answer=data["default_answer"],
            ),
            branding=BrandingConfig(
                bot_name=data["branding_bot_name"],
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
            language=data["language"],
        )

    async def get_billing_product_by_plan_code(
        self,
        plan_code: str,
    ) -> dict | None:
        row = await self.db.fetchone(
            """
            SELECT
                bp.product_id,
                bp.code        AS product_code,
                bp.plan_id,
                sp.code        AS plan_code,
                sp.name        AS name,
                bp.title       AS title,
                bp.description AS description,
                bp.amount_stars,
                bp.is_active
            FROM billing_products AS bp
            JOIN saas_plans       AS sp ON sp.plan_id = bp.plan_id
            WHERE sp.code = $1
            AND bp.is_active = TRUE
            LIMIT 1
            """,
            (plan_code,),
        )
        return dict(row) if row else None

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
            WHERE bi.owner_user_id = $1
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
            WHERE instance_id = $1
            """,
            (inst["instance_id"],),
        )
        if meta:
            inst.update(dict(meta))
        inst["role"] = "owner"
        return inst

    async def add_instance_member(self, instance_id: str, user_id: int, role: str) -> None:
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
            VALUES ($1, $2, $3, $4)
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
            "DELETE FROM instance_members WHERE instance_id = $1 AND user_id = $2",
            (instance_id, user_id),
        )

    async def get_instance_members(self, instance_id: str) -> List[Dict[str, Any]]:
        """Участники инстанса."""
        rows = await self.db.fetchall(
            """
            SELECT im.user_id, u.username, im.role, im.created_at
            FROM instance_members im
            LEFT JOIN users u ON im.user_id = u.user_id
            WHERE im.instance_id = $1
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

    async def get_instance_stats(self, instance_id: str, days: int = 30) -> Dict[str, Any]:
        """Живая статистика по тикетам из Postgres."""
        date_from = datetime.now(timezone.utc) - timedelta(days=days)

        # 1. Кол-во тикетов по статусам
        rows = await self.db.fetchall(
            """
            SELECT LOWER(status) AS status, COUNT(*) AS cnt
            FROM tickets
            WHERE instance_id = $1
            AND created_at >= $2
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
            WHERE instance_id = $1
            AND created_at >= $2
            """,
            (instance_id, date_from),
        )
        unique_users = uniq_row["uniq_users"] if uniq_row else 0

        # 3. Среднее время до первого ответа админа
        rows = await self.db.fetchall(
            """
            SELECT created_at, last_admin_reply_at
            FROM tickets
            WHERE instance_id = $1
            AND created_at >= $2
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

        where_clauses: List[str] = ["instance_id = $1"]
        params: List[Any] = [instanceid]
        counter = 2

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

            placeholders = ", ".join(f"${counter + i}" for i in range(len(allowed_raw)))
            where_clauses.append(f"LOWER(status) IN ({placeholders})")
            params.extend([s.lower() for s in allowed_raw])
            counter += len(allowed_raw)

        # поиск по username / user_id
        if search:
            where_clauses.append(
                f"(username ILIKE ${counter} OR CAST(user_id AS TEXT) LIKE ${counter + 1})"
            )
            like = f"%{search}%"
            params.extend([like, like])
            counter += 2

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # total
        count_sql = f"SELECT COUNT(*) AS cnt FROM tickets{where_sql}"
        row = await self.db.fetchone(count_sql, tuple(params))
        total = int(row["cnt"]) if row else 0
        if total == 0:
            return [], 0

        # список тикетов
        list_sql = f"""
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
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """
        rows = await self.db.fetchall(list_sql, tuple(params + [limit, offset]))

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
            WHERE bi.instance_id = $1
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
            WHERE instance_id = $1 AND key = 'privacy_mode_enabled'
            """,
            (instance_id,),
        )
        return bool(row and row["value"] == "True")

    async def set_worker_setting(self, instance_id: str, key: str, value: str) -> None:
        await self.db.execute(
            """
            INSERT INTO worker_settings (instance_id, key, value)
            VALUES ($1, $2, $3)
            ON CONFLICT (instance_id, key) DO UPDATE
              SET value = EXCLUDED.value
            """,
            (instance_id, key, value),
        )

    async def update_instance_settings(
        self, instance_id: str, payload: UpdateInstanceSettings
    ) -> None:
        existing = await self.db.fetchone(
            "SELECT * FROM instance_meta WHERE instance_id = $1",
            (instance_id,),
        )

        fields = {
            "auto_close_hours": payload.autoclose_hours,
            "auto_reply_greeting": payload.auto_reply.greeting if payload.auto_reply else None,
            "auto_reply_default_answer": payload.auto_reply.default_answer
            if payload.auto_reply
            else None,
            "branding_bot_name": payload.branding.bot_name if payload.branding else None,
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
                ) VALUES ($1, NULL, NULL, $2, $3, $4, $5, $6, $7, $8)
                """,
                (
                    instance_id,  # $1 (instance_id)
                    fields["auto_close_hours"],  # $2 (auto_close_hours)
                    fields["auto_reply_greeting"],  # $3 (auto_reply_greeting)
                    fields["auto_reply_default_answer"],  # $4 (auto_reply_default_answer)
                    fields["branding_bot_name"],  # $5 (branding_bot_name)
                    fields["openchat_enabled"] if fields["openchat_enabled"] is not None else False, 
                    fields["language"],  # $7 (language)
                    datetime.now(timezone.utc),  # $8 (updated_at)
                ),
            )

        else:
            set_parts = []
            params: List[Any] = []

            for col, value in fields.items():
                if value is not None:
                    set_parts.append(f"{col} = ${len(params) + 1}")
                    params.append(value)

            set_parts.append(f"updated_at = ${len(params) + 1}")
            params.append(datetime.now(timezone.utc))
            params.append(instance_id)

            if set_parts:
                sql = f"""
                UPDATE instance_meta
                SET {", ".join(set_parts)}
                WHERE instance_id = ${len(params)}
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


async def get_global_roles_for_user(user_id: int) -> list[str]:
    superadmins = await _parse_superadmin_ids()
    return ["superadmin"] if int(user_id) in superadmins else []


async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Отсутствует токен")

    token = authorization[7:]
    try:
        session = session_manager.validate_session(token)

        # нормализуем user_id -> int
        raw_user_id = session.get("user_id") or session.get("userid") or session.get("userId")
        user_id = int(raw_user_id or 0)

        # оставляем совместимость ключей (как у тебя по проекту)
        session["userid"] = user_id
        session["user_id"] = user_id

        session["roles"] = await get_global_roles_for_user(user_id) if user_id else []
        return session

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


async def get_single_tenant_config(db) -> SingleTenantConfig:
    # ожидаем, что вся публичная конфигурация miniapp лежит в одном ключе
    raw = await db.get_platform_setting("miniapp_public", default=None)

    logger.warning("get_single_tenant_config: raw miniapp_public=%r", raw)

    if not raw:
        return SingleTenantConfig(enabled=False, allowed_user_ids=[])

    # raw может быть dict (если db уже делает json.loads), либо строка JSON
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            logger.exception("get_single_tenant_config: failed to json.loads(miniapp_public)")
            return SingleTenantConfig(enabled=False, allowed_user_ids=[])

    if not isinstance(raw, dict):
        logger.warning("get_single_tenant_config: miniapp_public is not dict (type=%s)", type(raw))
        return SingleTenantConfig(enabled=False, allowed_user_ids=[])

    st = raw.get("singleTenant") or {}
    if not isinstance(st, dict):
        logger.warning("get_single_tenant_config: singleTenant is not dict (type=%s)", type(st))
        return SingleTenantConfig(enabled=False, allowed_user_ids=[])

    enabled = bool(st.get("enabled", False))

    allowed_ids: List[int] = []
    # новый формат (несколько)
    if isinstance(st.get("allowedUserIds"), list):
        for x in st["allowedUserIds"]:
            try:
                allowed_ids.append(int(x))
            except Exception:
                continue

    # обратная совместимость со старым форматом (один)
    if not allowed_ids and st.get("ownerTelegramId") is not None:
        try:
            allowed_ids = [int(st["ownerTelegramId"])]
        except Exception:
            allowed_ids = []

    # убираем дубликаты, сохраняем порядок
    allowed_ids = list(dict.fromkeys(allowed_ids))

    cfg = SingleTenantConfig(enabled=enabled, allowed_user_ids=allowed_ids)
    logger.warning(
        "get_single_tenant_config: parsed enabled=%s allowed_user_ids=%s",
        cfg.enabled,
        cfg.allowed_user_ids,
    )
    return cfg


async def _parse_superadmin_ids() -> set[int]:
    if miniapp_db is None or getattr(miniapp_db, "db", None) is None:
        return set()

    raw = await miniapp_db.db.get_platform_setting("miniapp_public", default=None)
    if not raw:
        return set()

    # на случай, если драйвер вернул JSON строкой
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return set()

    if not isinstance(raw, dict):
        return set()

    ids = raw.get("superadmins") or []
    out: set[int] = set()

    if isinstance(ids, list):
        for x in ids:
            try:
                n = int(x)
                if n > 0:
                    out.add(n)
            except Exception:
                continue

    return out


async def require_superadmin(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    superadmins = await _parse_superadmin_ids()

    uid = current_user.get("user_id") or current_user.get("userid") or current_user.get("userId")
    uid = int(uid or 0)

    if uid not in superadmins:
        raise HTTPException(status_code=403, detail="Superadmin only")
    return current_user


manage_router = APIRouter(
    prefix="/manage",
    tags=["manage"],
    dependencies=[Depends(require_superadmin)],
    responses={**COMMON_AUTH_RESPONSES},
)


@manage_router.get("/health")
async def manage_health():
    return {"status": "ok"}


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

    telegram_validator = TelegramAuthValidator(bot_token)
    session_manager = SessionManager(ttl_minutes=30)
    miniapp_db = MiniAppDB(master_db)
    master_bot = master_bot_instance

    # 2) Публикуем в app.state (чтобы роуты могли брать через request.app.state)
    app.state.session_manager = session_manager
    app.state.telegram_validator = telegram_validator

    # 3) Подключаем основные роуты
    app.include_router(manage_router)

    env = os.getenv("ENV", "").lower()
    if env in {"ci", "test"}:
        app.include_router(test_auth_router, tags=["__test__"])

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

    # ====================================================================
    # Dependencies
    # ====================================================================

    async def require_instance_access(
        instance_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
        required_role: Optional[str] = None,
    ) -> None:
        has_access = await miniapp_db.check_access(
            instance_id, current_user["user_id"], required_role
        )
        if not has_access:
            raise HTTPException(status_code=403, detail="You cannot access this instance")

    async def assert_payment_method_enabled(payment_method: str) -> None:
        raw = await miniapp_db.db.get_platform_setting("miniapp_public", default=None)
        if not raw:
            raise HTTPException(
                status_code=400, detail="Payment methods have been disabled by the administrator."
            )

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = None

        if not isinstance(raw, dict):
            raise HTTPException(
                status_code=400, detail="Payment methods have been disabled by the administrator."
            )

        enabled = (raw.get("payments") or {}).get("enabled") or {}
        if not isinstance(enabled, dict):
            raise HTTPException(
                status_code=400, detail="Payment methods have been disabled by the administrator."
            )

        pm = payment_method
        if hasattr(pm, "value"):
            pm = pm.value
        pm = str(pm).strip().lower()

        key = {
            "telegram_stars": "telegramStars",
            "telegramstars": "telegramStars",  # можно убрать, если строго только underscore
            "ton": "ton",
            "yookassa": "yookassa",
        }.get(pm)

        if not key:
            raise HTTPException(status_code=400, detail="Unknown payment method")

        if not bool(enabled.get(key, False)):
            raise HTTPException(
                status_code=400, detail="Payment methods have been disabled by the administrator."
            )

    # ====================================================================
    # Endpoints
    # ====================================================================

    @app.post(
        "/api/instances/{instance_id}/billing/create_invoice",
        response_model=CreateInvoiceResponse,
        responses={
            **COMMON_AUTH_RESPONSES,  # 401/403
            **COMMON_BAD_REQUEST_RESPONSES,  # 400
            **COMMON_NOT_FOUND_RESPONSES,  # 404
            409: {"description": "Conflict"},
        },
    )
    async def create_billing_invoice(
        instance_id: InstanceId,
        req: CreateInvoiceRequest,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        import json
        import time
        import uuid

        import httpx

        request_id = str(uuid.uuid4())
        t0 = time.monotonic()

        user_id = current_user["user_id"]

        # IMPORTANT: req.payment_method может быть Enum (PaymentMethod.telegram_stars)
        # Нормализуем в строку: "telegram_stars" | "ton" | "yookassa" | "stripe"
        payment_method = (
            getattr(req, "payment_method", None)
            or getattr(req, "paymentmethod", None)
            or "telegram_stars"
        )
        if hasattr(payment_method, "value"):
            payment_method = payment_method.value
        payment_method = str(payment_method).strip().lower()

        periods = req.periods

        logger.info(
            "billing.create_invoice start request_id=%s instance_id=%s user_id=%s plan_code=%s periods=%s payment_method=%s",
            request_id,
            instance_id,
            user_id,
            getattr(req, "plan_code", None),
            periods,
            payment_method,
        )

        async def get_miniapp_public() -> dict:
            """Читает platformsettings.miniapp_public и гарантированно возвращает dict."""
            try:
                raw = await miniapp_db.db.get_platform_setting("miniapp_public", default=None)
            except Exception:
                raw = None

            if not raw:
                return {}

            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    return {}

            return raw if isinstance(raw, dict) else {}

        # helper: server-side guard for globally disabled payment methods
        async def assert_payment_method_enabled(pm: str) -> None:
            pm = str(pm).strip().lower()

            method_key = {
                "telegram_stars": "telegramStars",
                "ton": "ton",
                "yookassa": "yookassa",
                "stripe": "stripe",  # Добавлен для Stripe
            }.get(pm)

            if not method_key:
                raise HTTPException(status_code=400, detail="Неизвестный метод оплаты")

            raw = await get_miniapp_public()

            # Fail-closed: if settings missing/unreadable -> payments considered disabled
            if not raw:
                raise HTTPException(
                    status_code=400, detail="Методы оплаты отключены администратором"
                )

            enabled_flags = (raw.get("payments") or {}).get("enabled") or {}
            if not isinstance(enabled_flags, dict):
                raise HTTPException(
                    status_code=400, detail="Методы оплаты отключены администратором"
                )

            if not bool(enabled_flags.get(method_key, False)):
                raise HTTPException(status_code=400, detail=f"Метод оплаты отключён: {pm}")

        try:
            # 1) Доступ к инстансу
            await require_instance_access(instance_id, current_user)

            # 1.5) Guard: админ мог выключить метод оплаты
            await assert_payment_method_enabled(payment_method)

            # 2) Продукт
            product = await miniapp_db.get_billing_product_by_plan_code(req.plan_code)
            logger.info(
                "billing.create_invoice product request_id=%s plan_code=%s product=%s",
                request_id,
                req.plan_code,
                {
                    "ok": bool(product),
                    "product_code": (product or {}).get("product_code"),
                    "amount_stars": (product or {}).get("amount_stars"),
                    "title": (product or {}).get("title"),
                    "name": (product or {}).get("name"),
                },
            )
            if not product or not product.get("product_code"):
                raise HTTPException(status_code=400, detail="Тариф недоступен для оплаты")

            # 3) Основной инстанс аккаунта
            main_instance = await miniapp_db.get_instance_by_owner(user_id)
            logger.info(
                "billing.create_invoice main_instance request_id=%s found=%s instance_id=%s",
                request_id,
                bool(main_instance),
                (main_instance or {}).get("instance_id"),
            )
            if not main_instance:
                raise HTTPException(
                    status_code=400,
                    detail="Сначала создайте бота, затем можно оформить тариф",
                )
            account_instance_id = main_instance["instance_id"]

            # -------------------------
            # Stars
            # -------------------------
            if payment_method == "telegram_stars":
                base_amount = product["amount_stars"]
                total_amount = base_amount * periods

                invoice_id = await miniapp_db.db.insert_billing_invoice(
                    instance_id=account_instance_id,
                    user_id=user_id,
                    plan_code=req.plan_code,
                    periods=periods,
                    amount_stars=total_amount,
                    product_code=product["product_code"],
                    payload="",
                    invoice_link="",
                    status="pending",
                    payment_method="telegram_stars",
                    currency="XTR",
                )

                payload = f"saas:{invoice_id}"

                if master_bot is None:
                    logger.error(
                        "billing.create_invoice master_bot is None request_id=%s", request_id
                    )
                    raise HTTPException(status_code=500, detail="MasterBot не инициализирован")

                try:
                    invoice_link = await master_bot.create_stars_invoice_link_for_miniapp(
                        user_id=user_id,
                        title=product.get("title") or product["name"],
                        description=product.get("description") or f"SaaS план {req.plan_code}",
                        payload=payload,
                        currency="XTR",
                        amount_stars=total_amount,
                    )
                except Exception:
                    logger.exception(
                        "billing.create_invoice stars masterbot error request_id=%s", request_id
                    )
                    raise HTTPException(
                        status_code=500, detail="Не удалось создать инвойс Telegram Stars"
                    )

                await miniapp_db.db.update_billing_invoice_link_and_payload(
                    invoice_id=invoice_id,
                    payload=payload,
                    invoice_link=invoice_link,
                )

                logger.info(
                    "billing.create_invoice done request_id=%s method=telegram_stars invoice_id=%s elapsed_ms=%s",
                    request_id,
                    invoice_id,
                    int((time.monotonic() - t0) * 1000),
                )
                return CreateInvoiceResponse(
                    invoice_id=invoice_id,
                    invoice_link=invoice_link,
                    currency="XTR",
                )

            # -------------------------
            # TON (Tonkeeper deeplink)
            # -------------------------
            if payment_method == "ton":
                plan = req.plan_code.lower()

                raw = await get_miniapp_public()
                payments = raw.get("payments") or {}
                ton_cfg = payments.get("ton") or {}

                # prices from SuperAdmin (platformsettings.miniapp_public.payments.ton.*)
                price_map = {
                    "lite": float(ton_cfg.get("pricePerPeriodLite", 0) or 0),
                    "pro": float(ton_cfg.get("pricePerPeriodPro", 0) or 0),
                    "enterprise": float(ton_cfg.get("pricePerPeriodEnterprise", 0) or 0),
                }

                if plan not in price_map or price_map[plan] <= 0:
                    raise HTTPException(
                        status_code=400, detail="TON: цена не настроена в панели администратора"
                    )

                amount_ton = float(price_map[plan]) * float(periods)
                amount_minor_units = int(amount_ton * 1_000_000_000)

                # wallet from SuperAdmin (with fallback to env settings)
                ton_address = (
                    (ton_cfg.get("walletAddress") or "").strip()
                    or getattr(settings, "TON_WALLET_ADDRESS", "")
                    or ""
                )
                ton_address = str(ton_address).strip()
                if not ton_address:
                    raise HTTPException(status_code=500, detail="TON: walletAddress не настроен")

                invoice_id = await miniapp_db.db.insert_billing_invoice(
                    instance_id=account_instance_id,
                    user_id=user_id,
                    plan_code=req.plan_code,
                    periods=periods,
                    amount_stars=0,
                    product_code=product["product_code"],
                    payload="",
                    invoice_link="",
                    status="pending",
                    payment_method="ton",
                    currency="TON",
                    amount_minor_units=amount_minor_units,
                )

                # Генерация уникального memo (комментария) для точной идентификации платежа
                memo = f"saas:{invoice_id}"  # Plain text for comment and memo

                logger.info(
                    "billing.create_invoice ton memo generated request_id=%s invoice_id=%s memo=%s",
                    request_id,
                    invoice_id,
                    memo,
                )

                comment = memo  # Use plain memo as comment
                payload = memo  # Set payload to memo

                # Формируем deeplink с &text={memo}
                invoice_link = (
                    f"https://app.tonkeeper.com/transfer/{ton_address}"
                    f"?amount={amount_minor_units}"
                    f"&text={quote(comment)}"
                )

                # Сохраняем payload и invoice_link (существующий метод)
                await miniapp_db.db.update_billing_invoice_link_and_payload(
                    invoice_id=invoice_id,
                    payload=payload,
                    invoice_link=invoice_link,
                )

                # Дополнительно сохраняем memo в БД (новый запрос, так как метод не поддерживает memo)
                await miniapp_db.db.execute(
                    """
                    UPDATE billing_invoices 
                    SET memo = $1,
                        updated_at = NOW()
                    WHERE invoice_id = $2
                    """,
                    (memo, invoice_id),
                )

                logger.info(
                    "billing.create_invoice done request_id=%s method=ton invoice_id=%s amount_minor_units=%s amount_ton=%s elapsed_ms=%s",
                    request_id,
                    invoice_id,
                    amount_minor_units,
                    amount_ton,
                    int((time.monotonic() - t0) * 1000),
                )
                return CreateInvoiceResponse(
                    invoice_id=invoice_id,
                    invoice_link=invoice_link,
                    amount_minor_units=amount_minor_units,
                    amount_ton=amount_ton,
                    currency="TON",
                )

            # -------------------------
            # YooKassa (redirect confirmation_url)
            # -------------------------
            if payment_method == "yookassa":
                raw = await get_miniapp_public()
                payments = raw.get("payments") or {}
                yk_cfg = payments.get("yookassa") or {}

                # config from SuperAdmin / DB (platformsettings.miniapp_public.payments.yookassa.*)
                shop_id = str(yk_cfg.get("shopId") or "").strip()
                secret_key = str(yk_cfg.get("secretKey") or "").strip()
                return_url = str(yk_cfg.get("returnUrl") or "").strip()
                test_mode = bool(yk_cfg.get("testMode", False))

                logger.info(
                    "billing.create_invoice yookassa config request_id=%s shop_id_set=%s secret_set=%s return_url_set=%s test_mode=%s",
                    request_id,
                    bool(shop_id),
                    bool(secret_key),
                    bool(return_url),
                    test_mode,
                )

                if not shop_id or not secret_key:
                    raise HTTPException(
                        status_code=500,
                        detail="ЮKassa: shopId/secretKey не настроены в панели администратора",
                    )
                if not return_url:
                    raise HTTPException(
                        status_code=500,
                        detail="ЮKassa: returnUrl не настроен в панели администратора",
                    )

                plan = req.plan_code.lower()
                price_map_rub = {
                    "lite": float(yk_cfg.get("priceRubLite", 0) or 0),
                    "pro": float(yk_cfg.get("priceRubPro", 0) or 0),
                    "enterprise": float(yk_cfg.get("priceRubEnterprise", 0) or 0),
                }

                logger.info(
                    "billing.create_invoice yookassa price_map_rub request_id=%s price_lite=%s price_pro=%s price_enterprise=%s",
                    request_id,
                    price_map_rub["lite"],
                    price_map_rub["pro"],
                    price_map_rub["enterprise"],
                )

                if plan not in price_map_rub or price_map_rub[plan] <= 0:
                    raise HTTPException(
                        status_code=400, detail="ЮKassa: цена не настроена в панели администратора"
                    )

                amount_rub = float(price_map_rub[plan]) * float(periods)
                amount_minor_units = int(round(amount_rub * 100))
                amount_value = f"{amount_rub:.2f}"

                logger.info(
                    "billing.create_invoice yookassa amount request_id=%s amount_rub=%s amount_value=%s amount_minor_units=%s",
                    request_id,
                    amount_rub,
                    amount_value,
                    amount_minor_units,
                )
                try:
                    invoice_id = await miniapp_db.db.insert_billing_invoice(
                        instance_id=account_instance_id,
                        user_id=user_id,
                        plan_code=req.plan_code,
                        periods=periods,
                        amount_stars=0,
                        product_code=product["product_code"],
                        payload="",
                        invoice_link="",
                        status="pending",
                        payment_method="yookassa",
                        currency="RUB",
                        amount_minor_units=amount_minor_units,
                    )
                except Exception:
                    logger.exception(
                        "billing.create_invoice yookassa db.insert_billing_invoice failed request_id=%s instance_id=%s account_instance_id=%s user_id=%s product_code=%s",
                        request_id,
                        instance_id,
                        account_instance_id,
                        user_id,
                        product.get("product_code"),
                    )
                    raise

                logger.info(
                    "billing.create_invoice yookassa db invoice created request_id=%s invoice_id=%s",
                    request_id,
                    invoice_id,
                )

                idempotence_key = str(uuid.uuid4())
                yk_url = "https://api.yookassa.ru/v3/payments"

                description = f"SaaS {req.plan_code} x{periods} (invoice {invoice_id})"

                body = {
                    "amount": {"value": amount_value, "currency": "RUB"},
                    "confirmation": {"type": "redirect", "return_url": return_url},
                    "capture": True,
                    "description": description,
                    "metadata": {
                        "saas_invoice_id": invoice_id,
                        "instance_id": account_instance_id,
                        "user_id": user_id,
                        "plan_code": req.plan_code,
                        "periods": periods,
                        "request_id": request_id,
                        "test_mode": test_mode,
                    },
                }

                logger.info(
                    "billing.create_invoice yookassa request request_id=%s url=%s idempotence_key=%s body=%s",
                    request_id,
                    yk_url,
                    idempotence_key,
                    body,
                )

                try:
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        resp = await client.post(
                            yk_url,
                            auth=(shop_id, secret_key),
                            headers={
                                "Idempotence-Key": idempotence_key,
                                "Content-Type": "application/json",
                            },
                            json=body,
                        )

                        logger.info(
                            "billing.create_invoice yookassa response request_id=%s status_code=%s headers_request_id=%s body=%s",
                            request_id,
                            resp.status_code,
                            resp.headers.get("Request-Id") or resp.headers.get("X-Request-Id"),
                            resp.text,
                        )

                        resp.raise_for_status()
                        data = resp.json()

                except httpx.HTTPStatusError as e:
                    logger.exception(
                        "billing.create_invoice yookassa HTTPStatusError request_id=%s status=%s response_body=%s",
                        request_id,
                        getattr(e.response, "status_code", None),
                        getattr(e.response, "text", None),
                    )
                    raise HTTPException(status_code=502, detail="ЮKassa: ошибка создания платежа")
                except Exception:
                    logger.exception(
                        "billing.create_invoice yookassa request failed request_id=%s", request_id
                    )
                    raise HTTPException(status_code=502, detail="ЮKassa: не удалось создать платеж")

                yk_payment_id = data.get("id")
                confirmation = data.get("confirmation") or {}
                confirmation_url = confirmation.get("confirmation_url")

                logger.info(
                    "billing.create_invoice yookassa parsed request_id=%s invoice_id=%s yk_payment_id=%s confirmation_url=%s",
                    request_id,
                    invoice_id,
                    yk_payment_id,
                    confirmation_url,
                )

                if not yk_payment_id or not confirmation_url:
                    logger.error(
                        "billing.create_invoice yookassa missing fields request_id=%s data=%s",
                        request_id,
                        data,
                    )
                    raise HTTPException(status_code=502, detail="ЮKassa: некорректный ответ API")

                payload = f"yookassa:{yk_payment_id}"

                try:
                    await miniapp_db.db.update_billing_invoice_link_and_payload(
                        invoice_id=invoice_id,
                        payload=payload,
                        invoice_link=confirmation_url,
                    )
                except Exception:
                    logger.exception(
                        "billing.create_invoice yookassa db.update_billing_invoice_link_and_payload failed request_id=%s invoice_id=%s payload=%s confirmation_url=%s",
                        request_id,
                        invoice_id,
                        payload,
                        confirmation_url,
                    )
                    raise

                logger.info(
                    "billing.create_invoice done request_id=%s method=yookassa invoice_id=%s yk_payment_id=%s elapsed_ms=%s",
                    request_id,
                    invoice_id,
                    yk_payment_id,
                    int((time.monotonic() - t0) * 1000),
                )

                return CreateInvoiceResponse(
                    invoice_id=invoice_id,
                    invoice_link=confirmation_url,
                    currency="RUB",
                )

            # -------------------------
            # Stripe (Checkout session URL)
            # -------------------------
            if payment_method == "stripe":
                raw = await get_miniapp_public()
                payments = raw.get("payments") or {}
                stripe_cfg = payments.get("stripe") or {}

                # config from SuperAdmin / DB (platformsettings.miniapp_public.payments.stripe.*)
                secret_key = str(stripe_cfg.get("secretKey") or "").strip()
                currency = str(stripe_cfg.get("currency") or "usd").strip().lower()
                # Для success/cancel используем фиксированные или добавьте поля в SuperAdmin
                success_url = "https://your-domain/success?session_id={CHECKOUT_SESSION_ID}"  # Замените на реальный
                cancel_url = "https://your-domain/cancel"  # Замените на реальный
                test_mode = bool(stripe_cfg.get("testMode", False))

                logger.info(
                    "billing.create_invoice stripe config request_id=%s secret_set=%s currency=%s success_url_set=%s cancel_url_set=%s test_mode=%s",
                    request_id,
                    bool(secret_key),
                    currency,
                    bool(success_url),
                    bool(cancel_url),
                    test_mode,
                )

                if not secret_key:
                    raise HTTPException(
                        status_code=500,
                        detail="Stripe: secretKey не настроен в панели администратора",
                    )
                if not success_url or not cancel_url:
                    raise HTTPException(
                        status_code=500, detail="Stripe: success_url/cancel_url не настроены"
                    )

                plan = req.plan_code.lower()
                price_map_usd = {
                    "lite": float(stripe_cfg.get("priceUsdLite", 0) or 0),
                    "pro": float(stripe_cfg.get("priceUsdPro", 0) or 0),
                    "enterprise": float(stripe_cfg.get("priceUsdEnterprise", 0) or 0),
                }

                logger.info(
                    "billing.create_invoice stripe price_map_usd request_id=%s price_lite=%s price_pro=%s price_enterprise=%s",
                    request_id,
                    price_map_usd["lite"],
                    price_map_usd["pro"],
                    price_map_usd["enterprise"],
                )

                if plan not in price_map_usd or price_map_usd[plan] <= 0:
                    raise HTTPException(
                        status_code=400, detail="Stripe: цена не настроена в панели администратора"
                    )

                amount_usd = float(price_map_usd[plan]) * float(periods)
                amount_minor_units = int(
                    round(amount_usd * 100)
                )  # Центы для USD (или другой валюты)
                amount_value = f"{amount_usd:.2f}"

                logger.info(
                    "billing.create_invoice stripe amount request_id=%s amount_usd=%s amount_value=%s amount_minor_units=%s",
                    request_id,
                    amount_usd,
                    amount_value,
                    amount_minor_units,
                )
                try:
                    invoice_id = await miniapp_db.db.insert_billing_invoice(
                        instance_id=account_instance_id,
                        user_id=user_id,
                        plan_code=req.plan_code,
                        periods=periods,
                        amount_stars=0,
                        product_code=product["product_code"],
                        payload="",
                        invoice_link="",
                        status="pending",
                        payment_method="stripe",
                        currency=currency.upper(),
                        amount_minor_units=amount_minor_units,
                    )
                except Exception:
                    logger.exception(
                        "billing.create_invoice stripe db.insert_billing_invoice failed request_id=%s instance_id=%s account_instance_id=%s user_id=%s product_code=%s",
                        request_id,
                        instance_id,
                        account_instance_id,
                        user_id,
                        product.get("product_code"),
                    )
                    raise

                logger.info(
                    "billing.create_invoice stripe db invoice created request_id=%s invoice_id=%s",
                    request_id,
                    invoice_id,
                )

                stripe.api_key = secret_key

                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[
                            {
                                "price_data": {
                                    "currency": currency,
                                    "product_data": {
                                        "name": f"{product.get('title') or product['name']} x{periods}",
                                    },
                                    "unit_amount": amount_minor_units,
                                },
                                "quantity": 1,
                            }
                        ],
                        mode="payment",
                        success_url=success_url,
                        cancel_url=cancel_url,
                        metadata={
                            "saas_invoice_id": invoice_id,
                            "instance_id": account_instance_id,
                            "user_id": user_id,
                            "plan_code": req.plan_code,
                            "periods": periods,
                            "request_id": request_id,
                            "test_mode": test_mode,
                        },
                    )
                except stripe.error.StripeError as e:
                    logger.exception(
                        "billing.create_invoice stripe session create error request_id=%s: %s",
                        request_id,
                        e,
                    )
                    raise HTTPException(status_code=502, detail="Stripe: ошибка создания сессии")
                except Exception:
                    logger.exception(
                        "billing.create_invoice stripe request failed request_id=%s", request_id
                    )
                    raise HTTPException(status_code=502, detail="Stripe: не удалось создать сессию")

                session_id = session.id
                invoice_link = session.url

                logger.info(
                    "billing.create_invoice stripe parsed request_id=%s invoice_id=%s session_id=%s invoice_link=%s",
                    request_id,
                    invoice_id,
                    session_id,
                    invoice_link,
                )

                if not session_id or not invoice_link:
                    logger.error(
                        "billing.create_invoice stripe missing fields request_id=%s data=%s",
                        request_id,
                        session,
                    )
                    raise HTTPException(status_code=502, detail="Stripe: некорректный ответ API")

                payload = f"stripe:{session_id}"

                try:
                    await miniapp_db.db.update_billing_invoice_link_and_payload(
                        invoice_id=invoice_id,
                        payload=payload,
                        invoice_link=invoice_link,
                        external_id=session_id,  # важно: session.id -> billinginvoices.externalid
                    )

                except Exception:
                    logger.exception(
                        "billing.create_invoice stripe db.update_billing_invoice_link_and_payload failed request_id=%s invoice_id=%s payload=%s invoice_link=%s",
                        request_id,
                        invoice_id,
                        payload,
                        invoice_link,
                    )
                    raise

                logger.info(
                    "billing.create_invoice done request_id=%s method=stripe invoice_id=%s session_id=%s elapsed_ms=%s",
                    request_id,
                    invoice_id,
                    session_id,
                    int((time.monotonic() - t0) * 1000),
                )
                return CreateInvoiceResponse(
                    invoice_id=invoice_id,
                    invoice_link=invoice_link,
                    session_id=session_id,
                    amount_minor_units=amount_minor_units,
                    currency=currency.upper(),
                )

            raise HTTPException(status_code=400, detail="Неизвестный метод оплаты")

        except HTTPException as e:
            logger.warning(
                "billing.create_invoice http_exception request_id=%s status_code=%s detail=%s elapsed_ms=%s",
                request_id,
                e.status_code,
                getattr(e, "detail", None),
                int((time.monotonic() - t0) * 1000),
            )
            raise
        except Exception:
            logger.exception(
                "billing.create_invoice unhandled_error request_id=%s elapsed_ms=%s",
                request_id,
                int((time.monotonic() - t0) * 1000),
            )
            raise HTTPException(status_code=500, detail=f"Internal error (request_id={request_id})")

    async def _toncenter_get_transactions(address: str, limit: int = 30) -> list[dict]:
        """
        Получаем последние транзакции по адресу через TonCenter API v2.

        Основной источник конфигурации:
        platformsettings.miniapp_public.payments.ton.apiBaseUrl
        platformsettings.miniapp_public.payments.ton.apiKey (optional)

        Fallback:
        shared.settings.TON_API_BASE_URL / shared.settings.TON_API_KEY
        """
        import json

        import httpx

        # 1) load miniapp_public
        try:
            raw = await miniapp_db.db.get_platform_setting("miniapp_public", default=None)
        except Exception:
            raw = None

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = None

        raw = raw if isinstance(raw, dict) else {}
        ton_cfg = ((raw.get("payments") or {}).get("ton")) or {}

        # 2) base url + api key from DB with fallback to settings
        base_url = (
            str(ton_cfg.get("apiBaseUrl") or "").strip()
            or str(getattr(settings, "TON_API_BASE_URL", "") or "").strip()
        )
        if not base_url:
            raise HTTPException(
                status_code=500,
                detail="TON: apiBaseUrl not configured (miniapp_public.payments.ton.apiBaseUrl)",
            )

        api_key = (
            str(ton_cfg.get("apiKey") or "").strip()
            or str(getattr(settings, "TON_API_KEY", "") or "").strip()
        )

        url = f"{base_url.rstrip('/')}/getTransactions"

        headers: Dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key

        params = {"address": address, "limit": limit}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        if not data.get("ok"):
            raise RuntimeError(f"TonCenter error: {data.get('error')}")

        result = data.get("result")
        return result or []

    def _maybe_b64decode(s: str) -> str:
        """Попытка декодировать base64 в обычный текст. Если не получится — вернём как есть."""
        if not s or not isinstance(s, str):
            return s
        try:
            # base64 обычно кратен 4 и содержит [A-Za-z0-9+/=]
            decoded = base64.b64decode(s, validate=True)
            text = decoded.decode("utf-8", errors="strict")
            return text
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return s

    def _extract_in_msg_comment(tx: dict) -> str | None:
        """
        Извлекает комментарий из TON-транзакции, декодируя base64 если нужно.
        Поддержка plain text и encoded.
        """
        in_msg = tx.get("in_msg") or {}
        logger.debug("Extract comment: raw_in_msg=%s", in_msg)

        # Проверяем 'message' (альтернативное поле в некоторых API responses)
        message = in_msg.get("message")
        if message:
            logger.debug("Extract comment: found message=%s", message)
            return str(message).strip()

        # Если API уже парсит comment
        comment = in_msg.get("comment")
        if comment:
            logger.debug("Extract comment: found comment=%s", comment)
            return str(comment).strip()

        # Декодируем из msg_data (base64)
        msg_data = in_msg.get("msg_data") or {}
        if msg_data.get("@type") == "msg.dataText":
            text_b64 = msg_data.get("text")
            logger.debug("Extract comment: found msg_data.text_b64=%s", text_b64)
            if text_b64:
                try:
                    decoded_bytes = base64.b64decode(text_b64)
                    decoded_text = decoded_bytes.decode("utf-8").strip()
                    logger.debug("Extract comment: decoded_text=%s", decoded_text)
                    return decoded_text
                except Exception as e:
                    logger.error("TON comment decode error: %s text_b64=%s", e, text_b64)

        # Альтернатива: decoded_body для некоторых форматов
        decoded_body = tx.get("decoded_body") or {}
        if decoded_body.get("type") == "text_comment":
            text = decoded_body.get("text", "").strip()
            logger.debug("Extract comment: found decoded_body.text=%s", text)
            return text

        # Лог если ничего не найдено
        logger.debug("Extract comment: no comment found in tx")

        return None

    async def check_ton_payment(invoice_id: int) -> dict:
        """
        Проверяет статус оплаты TON-инвойса через TonCenter.

        Особенности:
        - Использует memo из БД (если есть) или payload как expected_comment.
        - Применяет тариф ТОЛЬКО если mark_billing_invoice_paid_ton вернул True
        (т.е. статус реально изменился с pending/cancelled на paid).
        - Полностью безопасно от race conditions благодаря блокировке строки в БД.
        """
        import base64  # Добавлено для декодирования base64
        import json

        inv = await miniapp_db.db.get_billing_invoice(invoice_id)
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")

        if inv.get("payment_method") != "ton":
            raise HTTPException(status_code=400, detail="Invoice is not TON")

        current_status = inv.get("status", "pending")

        # Если уже оплачен — сразу возвращаем
        if current_status == "paid":
            return {"status": "paid", "tx_hash": inv.get("provider_tx_hash")}

        # --- Конфигурация TON из platform_settings ---
        try:
            raw = await miniapp_db.db.get_platform_setting("miniapp_public", default=None)
        except Exception:
            raw = None

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = None

        raw = raw if isinstance(raw, dict) else {}
        ton_cfg = (raw.get("payments") or {}).get("ton") or {}

        wallet = str(ton_cfg.get("walletAddress") or "").strip()
        if not wallet:
            raise HTTPException(
                status_code=500,
                detail="TON walletAddress not configured in miniapp_public.payments.ton.walletAddress",
            )

        need_amount = inv.get("amount_minor_units") or 0
        if need_amount <= 0:
            raise HTTPException(status_code=500, detail="Invalid invoice amount_minor_units")

        # --- Получаем expected_comment: memo из БД (приоритет) или fallback на payload ---
        expected_comment = inv.get("memo") or inv.get("payload")

        # Добавлено: fallback если memo выглядит как base64 — декодируем перед сравнением
        if (
            expected_comment
            and isinstance(expected_comment, str)
            and len(expected_comment) % 4 == 0
        ):
            try:
                # Добавляем padding если нужно и декодируем
                decoded_bytes = base64.urlsafe_b64decode(expected_comment + "==")
                expected_comment = decoded_bytes.decode("utf-8").strip()
                logger.info(
                    "TON expected_comment decoded from base64: original=%s decoded=%s",
                    inv.get("memo") or inv.get("payload"),
                    expected_comment,
                )
            except Exception as e:
                logger.warning(
                    "TON expected_comment base64 decode failed: %s - keeping original", e
                )
                # Если ошибка, оставляем как есть

        # --- Получаем последние транзакции ---
        try:
            txs = await _toncenter_get_transactions(wallet, limit=30)
            # Добавлено: Лог полного raw txs (sample первых 5 для экономии места)
            sample_txs = txs[:5]
            logger.debug("TON raw txs sample (first 5): %s", json.dumps(sample_txs, default=str))
        except Exception as e:
            logger.exception("check_ton_payment: TonCenter API error: %s", e)
            return {"status": "pending"}

        # Логируем raw in_msg для отладки (только первые 3 tx)
        raw_in_msgs = [tx.get("in_msg") for tx in txs[:3]]
        logger.debug("TON raw in_msgs (sample): %s", raw_in_msgs)

        found_comments = [
            _extract_in_msg_comment(tx) for tx in txs if _extract_in_msg_comment(tx) is not None
        ]

        logger.info(
            "TON check: invoice_id=%s wallet=%s need_amount=%s expected_comment=%s current_status=%s found_comments=%s",
            invoice_id,
            wallet,
            need_amount,
            expected_comment,
            current_status,
            found_comments,
        )

        # --- Ищем подходящую входящую транзакцию ---
        for tx in txs:
            in_msg = tx.get("in_msg") or {}
            value_str = in_msg.get("value")
            try:
                value = int(value_str) if value_str is not None else 0
            except Exception:
                value = 0

            comment = _extract_in_msg_comment(tx)

            # Добавлено: Расширенный лог для каждого tx
            logger.info(
                "TON tx scan: tx_hash=%s value=%s comment=%s raw_in_msg=%s (need_amount=%s expected_comment=%s)",
                tx.get("transaction_id", {}).get("hash"),
                value,
                comment,
                in_msg,
                need_amount,
                expected_comment,
            )

            # Проверяем сумму
            if value < need_amount:
                continue

            # Проверяем комментарий (если ожидается)
            if expected_comment:
                if comment is None or str(comment).strip() != expected_comment:
                    continue

            # Извлекаем хэш транзакции
            tx_id = tx.get("transaction_id") or {}
            tx_hash = (tx_id.get("hash") if isinstance(tx_id, dict) else None) or tx.get("hash")
            if not tx_hash:
                continue

            # --- Пытаемся пометить как оплаченный (с блокировкой строки в БД) ---
            updated = await miniapp_db.db.mark_billing_invoice_paid_ton(
                invoice_id=invoice_id,
                tx_hash=tx_hash,
                amount_minor_units=value,
                currency="TON",
            )

            # Применяем тариф только если статус реально изменился
            if updated:
                await miniapp_db.db.apply_saas_plan_for_invoice(invoice_id)
                logger.info(
                    "TON payment confirmed and plan applied: invoice_id=%s tx_hash=%s amount=%s",
                    invoice_id,
                    tx_hash,
                    value,
                )
                return {"status": "paid", "tx_hash": tx_hash}
            else:
                # Кто-то другой уже успел обработать эту транзакцию
                logger.info(
                    "TON payment already processed by concurrent request: invoice_id=%s tx_hash=%s",
                    invoice_id,
                    tx_hash,
                )
                return {
                    "status": "paid",
                    "tx_hash": tx_hash,  # Можно взять из БД, но для простоты возвращаем найденный
                }

        # Добавлено: Если ничего не нашли — лог summary всех value/comment
        summary_tx = [
            (tx.get("in_msg", {}).get("value"), _extract_in_msg_comment(tx)) for tx in txs
        ]
        logger.info("TON no match summary: tx_values_comments=%s", summary_tx)

        # Если ничего не нашли — возвращаем текущий статус (pending или cancelled)
        return {"status": current_status}

    @app.get(
        "/api/invoices/stripe/{invoice_id}/status",
        response_model=StripeInvoiceStatusResponse,
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
            **COMMON_BAD_REQUEST_RESPONSES,
        },
    )
    async def get_stripe_invoice_status(
        invoice_id: int = ApiPath(..., ge=1, le=9223372036854775807),
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        invoice = await miniapp_db.db.fetchone(
            """
            SELECT
                invoice_id,
                user_id,
                payment_method,
                status,
                external_id,
                period_applied,
                created_at,
                updated_at,
                paid_at
            FROM billing_invoices
            WHERE invoice_id = $1 AND user_id = $2
            LIMIT 1
            """,
            (invoice_id, current_user["user_id"]),
        )
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        if str(invoice.get("payment_method") or "").lower() != "stripe":
            raise HTTPException(status_code=400, detail="Not a Stripe invoice")

        return StripeInvoiceStatusResponse(
            invoice_id=int(invoice["invoice_id"]),
            status=str(invoice.get("status") or "pending"),
            session_id=invoice.get("external_id"),
            payment_intent_id=None,
            period_applied=bool(invoice.get("period_applied", False)),
        )

    @app.get("/api/offer/settings", response_model=OfferSettingsOut)
    async def get_offer_settings():
        s = await master_db.get_offer_settings()
        return OfferSettingsOut(enabled=s["enabled"], url=s["url"])

    @app.get("/api/offer/status", response_model=OfferStatusOut)
    async def get_offer_status(current_user: Dict[str, Any] = Depends(get_current_user)):
        uid = int(current_user.get("user_id") or 0)
        s = await master_db.get_offer_settings()
        if not s["enabled"] or not s["url"]:
            return OfferStatusOut(enabled=False, url="", accepted=True, acceptedAt=None)

        accepted = await master_db.has_accepted_offer(uid, s["url"])
        row = await master_db.get_user_offer_status(uid)
        acceptedat = row.get("acceptedat")
        return OfferStatusOut(
            enabled=True,
            url=s["url"],
            accepted=accepted,
            acceptedAt=acceptedat.isoformat() if acceptedat else None,
        )

    @app.post("/api/offer/decision")
    async def post_offer_decision(
        payload: OfferDecisionIn,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        uid = int(current_user.get("user_id") or 0)
        s = await master_db.get_offer_settings()
        if not s["enabled"] or not s["url"]:
            return {"status": "ignored"}

        await master_db.upsert_user_offer(uid, s["url"], payload.accepted, source="miniapp")
        return {"status": "ok", "accepted": payload.accepted}

    @app.post(
        "/api/invoices/stripe/{invoice_id}/cancel",
        response_model=StripeInvoiceCancelResponse,
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
        },
    )
    async def cancel_stripe_invoice(
        invoice_id: int,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        invoice = await miniapp_db.db.fetchone(
            "SELECT * FROM billing_invoices WHERE invoice_id = $1 AND user_id = $2",
            (invoice_id, current_user["user_id"]),
        )
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            session = stripe.checkout.Session.retrieve(invoice["external_id"])
            if session.status != "complete":
                stripe.checkout.Session.expire(invoice["external_id"])
                await miniapp_db.db.update_billing_invoice_status(invoice_id, "canceled")
            return StripeInvoiceCancelResponse(invoice_id=invoice_id, status="canceled")
        except stripe.error.StripeError as e:
            logger.error(f"Stripe cancel error for invoice {invoice_id}: {e}")
            raise HTTPException(status_code=500, detail="Ошибка отмены сессии Stripe")

    @app.post(
        "/api/webhook/stripe",
        responses={
            **COMMON_BAD_REQUEST_RESPONSES,
            422: {"description": "Validation Error"},
            503: {"description": "Stripe webhook not configured"},
        },
    )
    async def stripe_webhook(
        request: Request,
        stripe_signature: str = Header(..., alias="stripe-signature"),
    ):
        payload = await request.body()

        ps = await miniapp_db.db.get_platform_setting("miniapp_public", default=None)
        if isinstance(ps, str):
            try:
                ps = json.loads(ps)
            except Exception:
                ps = None

        # Было 500 → лучше 503 (в окружении сервис поднят, но конфиг не готов)
        if not isinstance(ps, dict):
            raise HTTPException(status_code=503, detail="Platform settings not configured")

        stripe_cfg = (ps.get("payments") or {}).get("stripe") or {}
        wh_secret = str(stripe_cfg.get("webhookSecret") or "").strip()

        # Было 500 → нужно 503, и он уже задокументирован в responses
        if not wh_secret:
            raise HTTPException(status_code=503, detail="Stripe webhook not configured")

        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature, wh_secret)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")

        if event.get("type") == "checkout.session.completed":
            session = (event.get("data") or {}).get("object") or {}
            external_id = session.get("id")
            metadata = session.get("metadata") or {}
            invoice_id = metadata.get("saas_invoice_id") or metadata.get("saasInvoiceId")

            if external_id and invoice_id:
                await miniapp_db.db.update_billing_invoice_status_by_external(
                    external_id, "succeeded"
                )
                await miniapp_db.db.apply_invoice_to_billing(int(invoice_id))

        return {"status": "ok"}

    @app.get(
        "/api/platform/single-tenant",
        response_model=SingleTenantConfig,
        responses={
            **COMMON_AUTH_RESPONSES,  # 401/403
        },
    )
    async def get_single_tenant_config_endpoint(
        current_user: Dict[str, Any] = Depends(require_superadmin),
    ):
        # Читаем ТОЛЬКО из miniapp_public.singleTenant
        return await get_single_tenant_config(master_db)

    @app.get(
        "/api/platform/superadmins",
        response_model=SuperadminsResponse,
        responses={
            **COMMON_AUTH_RESPONSES,  # 401/403
        },
    )
    async def get_platform_superadmins(
        currentuser: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_superadmin(currentuser)  # superadmin-guard

        raw = await master_db.get_platform_setting("miniapp_public", default={})
        if not isinstance(raw, dict):
            raw = {}

        ids = normalize_ids(raw.get("superadmins"))
        return SuperadminsResponse(ids=ids)

    @app.post(
        "/api/platform/superadmins",
        response_model=SuperadminsResponse,
        responses={
            **COMMON_AUTH_RESPONSES,  # 401/403
            **COMMON_BAD_REQUEST_RESPONSES,  # 400 (если вдруг добавишь валидацию/ограничения)
        },
    )
    async def set_platform_superadmins(
        payload: SuperadminsUpsert,
        currentuser: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_superadmin(currentuser)

        raw = await master_db.get_platform_setting("miniapp_public", default={})
        if not isinstance(raw, dict):
            raw = {}

        raw["superadmins"] = normalize_ids(payload.ids)

        await master_db.set_platform_setting("miniapp_public", raw)
        return SuperadminsResponse(ids=raw["superadmins"])

    @app.post(
        "/api/platform/single-tenant",
        response_model=SingleTenantConfig,
        responses={
            **COMMON_AUTH_RESPONSES,  # 401/403
            **COMMON_BAD_REQUEST_RESPONSES,  # 400 (у тебя уже есть raise HTTPException(400,...))
        },
    )
    async def set_single_tenant_config_endpoint(
        payload: SingleTenantConfig,
        current_user: Dict[str, Any] = Depends(require_superadmin),
    ):
        # 1) нормализуем список id
        allowed: List[int] = []
        for x in payload.allowed_user_ids or []:
            try:
                allowed.append(int(x))
            except (TypeError, ValueError):
                continue
        allowed = sorted(set(allowed))

        # 2) safety: нельзя включить single-tenant без allowlist
        if bool(payload.enabled) and not allowed:
            raise HTTPException(
                status_code=400,
                detail="allowed_user_ids must not be empty when enabled=true",
            )

        # 3) safety: не дать супер-админу случайно выкинуть самого себя из allowlist
        if bool(payload.enabled):
            cur_uid = int(current_user.get("userid") or 0)
            if cur_uid and cur_uid not in allowed:
                allowed.append(cur_uid)
                allowed = sorted(set(allowed))

        # 4) читаем текущий miniapp_public
        raw = await master_db.get_platform_setting("miniapp_public", default=None)
        if not raw:
            raw = {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        if not isinstance(raw, dict):
            raw = {}

        # 5) обновляем raw["singleTenant"]
        raw["singleTenant"] = {
            "enabled": bool(payload.enabled),
            "allowedUserIds": allowed,
        }

        # 6) сохраняем обратно miniapp_public
        await master_db.set_platform_setting("miniapp_public", raw)

        # 7) возвращаем нормализованный конфиг
        return SingleTenantConfig(enabled=bool(payload.enabled), allowed_user_ids=allowed)

    @app.post(
        "/api/auth/telegram",
        response_model=AuthResponse,
        responses={
            **COMMON_AUTH_RESPONSES,
        },
    )
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

        try:
            user_data = telegram_validator.validate(req.init_data)
        except ValueError as e:
            logger.warning("Ошибка валидации Telegram: %s", e)
            raise HTTPException(status_code=401, detail=str(e))

        user_id = user_data.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="user_id не найден в initData")

        logger.info(
            "auth_telegram: validated telegram user_id=%s username=%s first_name=%s last_name=%s",
            user_id,
            user_data.get("username"),
            user_data.get("first_name"),
            user_data.get("last_name"),
        )

        # ------------------------------------------------------------------
        # Глобальные роли (platform-level): superadmin только из ENV
        # ------------------------------------------------------------------
        roles: list[str] = []
        try:
            superadmins = await _parse_superadmin_ids()
            is_superadmin = int(user_id) in superadmins
            if is_superadmin:
                roles.append("superadmin")
            logger.info(
                "auth_telegram: superadmin_check user_id=%s is_superadmin=%s superadmins_count=%s",
                user_id,
                is_superadmin,
                len(superadmins),
            )
        except Exception:
            logger.exception("auth_telegram: failed to evaluate GRACEHUB_SUPERADMIN_TELEGRAM_ID")

        # ------------------------------------------------------------------
        # single-tenant mode (from DB: platform_settings.single_tenant)
        # schema: {"enabled": bool, "allowed_user_ids": [int, ...]}
        # ------------------------------------------------------------------
        single_tenant = await get_single_tenant_config(miniapp_db.db)

        logger.warning(
            "auth_telegram: single_tenant config enabled=%s allowed_user_ids=%s (len=%s) user_id=%s",
            single_tenant.enabled,
            single_tenant.allowed_user_ids,
            len(single_tenant.allowed_user_ids or []),
            user_id,
        )

        if single_tenant.enabled:
            allowed = {int(x) for x in (single_tenant.allowed_user_ids or [])}

            logger.warning(
                "auth_telegram: single_tenant check user_id=%s allowed=%s result=%s",
                user_id,
                sorted(allowed),
                int(user_id) in allowed,
            )

            if int(user_id) not in allowed:
                logger.warning(
                    "auth_telegram: single_tenant DENY user_id=%s username=%s allowed=%s",
                    user_id,
                    user_data.get("username"),
                    sorted(allowed),
                )
                raise HTTPException(
                    status_code=403,
                    detail="панель доступна только разрешённым пользователям",
                )

        await miniapp_db.upsert_user(
            user_id=user_id,
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            language=user_data.get("language_code"),
        )

        instances = await master_bot.db.get_user_instances_with_meta(user_id)

        default_instance_id: str | None = None
        if req.start_param and req.start_param.startswith("inst_"):
            requested_id = req.start_param[5:]
            for inst in instances:
                if inst["instance_id"] == requested_id:
                    default_instance_id = requested_id
                    break

        if not default_instance_id and instances:
            default_instance_id = instances[0]["instance_id"]

        token = session_manager.create_session(user_id, user_data.get("username"))

        logger.info(
            "auth_telegram: user_id=%s roles=%s instances=%s default_instance_id=%s",
            user_id,
            roles,
            [i["instance_id"] for i in instances],
            default_instance_id,
        )

        user_response = UserResponse(
            user_id=user_id,
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            language=user_data.get("language_code"),
            roles=roles,
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
            "auth_telegram RESPONSE user_id=%s roles=%s user.instances=%s default_instance_id=%s",
            user_id,
            roles,
            [i["instance_id"] for i in user_response.instances],
            default_instance_id,
        )

        return AuthResponse(
            token=token,
            user=user_response,
            default_instance_id=default_instance_id,
        )

    @app.post(
        "/api/billing/ton/cancel",
        response_model=TonInvoiceCancelResponse,
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
            **COMMON_BAD_REQUEST_RESPONSES,
            409: {"description": "Conflict"},
        },
    )
    async def cancel_ton_invoice(
        invoice_id: int = Query(..., ge=1, le=9223372036854775807),
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        inv = await miniapp_db.db.get_billing_invoice(invoice_id)
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")

        await require_instance_access(inv["instance_id"], current_user)

        if inv.get("payment_method") != "ton":
            raise HTTPException(status_code=400, detail="Invoice is not TON")

        if inv.get("status") == "paid":
            raise HTTPException(status_code=409, detail="Invoice already paid")

        if inv.get("status") == "cancelled":
            return TonInvoiceCancelResponse(invoice_id=invoice_id, status="cancelled")

        await miniapp_db.db.cancel_billing_invoice(invoice_id)
        return TonInvoiceCancelResponse(invoice_id=invoice_id, status="cancelled")

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

    # Юkassa метод получения статусов платежей
    def _extract_yk_payment_id(payload: str | None) -> str | None:
        if not payload:
            return None
        if payload.startswith("yookassa:"):
            return payload.split("yookassa:", 1)[1].strip() or None
        return None

    async def _yookassa_get_payment(payment_id: str) -> dict:
        import json

        import httpx

        # читаем креды из platformsettings.miniapp_public
        try:
            raw = await miniapp_db.db.get_platform_setting("miniapp_public", default=None)
        except Exception:
            raw = None

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = None

        raw = raw if isinstance(raw, dict) else {}
        yk_cfg = ((raw.get("payments") or {}).get("yookassa")) or {}

        shop_id = str(yk_cfg.get("shopId") or "").strip()
        secret_key = str(yk_cfg.get("secretKey") or "").strip()

        if not shop_id or not secret_key:
            raise HTTPException(
                status_code=500,
                detail="ЮKassa credentials not configured (miniapp_public.payments.yookassa.shopId/secretKey)",
            )

        url = f"https://api.yookassa.ru/v3/payments/{payment_id}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                auth=(shop_id, secret_key),
            )
            resp.raise_for_status()
            return resp.json()

    @app.get(
        "/api/billing/yookassa/status",
        response_model=YooKassaStatusResponse,
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
            **COMMON_BAD_REQUEST_RESPONSES,
            500: {"description": "Internal Server Error"},
        },
    )
    async def yookassa_invoice_status(
        invoice_id: int = Query(..., ge=1, le=9223372036854775807),
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        inv = await miniapp_db.db.get_billing_invoice(invoice_id)
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")

        await require_instance_access(inv["instance_id"], current_user)

        if (inv.get("payment_method") or "").lower() != "yookassa":
            raise HTTPException(status_code=400, detail="Invoice is not YooKassa")

        if (inv.get("status") or "").lower() == "paid":
            return YooKassaStatusResponse(
                invoice_id=invoice_id,
                status="succeeded",
                payment_id=_extract_yk_payment_id(inv.get("payload")),
                period_applied=True,
            )

        payment_id = _extract_yk_payment_id(inv.get("payload"))
        if not payment_id:
            raise HTTPException(
                status_code=500, detail="YooKassa payment_id missing in invoice payload"
            )

        data = await _yookassa_get_payment(payment_id)
        st = (data.get("status") or "pending").lower()

        amt = data.get("amount") or {}
        currency = amt.get("currency") or "RUB"
        value_str = amt.get("value") or "0.00"
        try:
            amount_minor_units = int(round(float(value_str) * 100))
        except Exception:
            amount_minor_units = 0

        if st == "succeeded":
            await miniapp_db.db.mark_billing_invoice_paid_yookassa(
                invoice_id=invoice_id,
                payment_id=payment_id,
                amount_minor_units=amount_minor_units,
                currency=currency,
            )
            await miniapp_db.db.apply_saas_plan_for_invoice(invoice_id)
            return YooKassaStatusResponse(
                invoice_id=invoice_id,
                status="succeeded",
                payment_id=payment_id,
                period_applied=True,
            )

        return YooKassaStatusResponse(
            invoice_id=invoice_id,
            status=st,
            payment_id=payment_id,
            period_applied=False,
        )

    @app.post(
        "/api/billing/yookassa/webhook",
        responses={
            **COMMON_BAD_REQUEST_RESPONSES,
        },
    )
    async def yookassa_webhook(
        request: Request,
        body: YooKassaWebhook = Body(...),
    ):
        try:
            raw = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid json")

        try:
            body = YooKassaWebhook.model_validate(raw)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())

        event = body.event
        payment_id = body.object.id

        if event not in ("payment.succeeded", "payment.canceled", "payment.waiting_for_capture"):
            return {"ok": True}

        payload = f"yookassa:{payment_id}"
        inv = await miniapp_db.db.find_billing_invoice_by_payload(payload)
        if not inv:
            return {"ok": True}

        invoice_id = int(inv["invoiceid"])

        data = await _yookassa_get_payment(payment_id)
        st = (data.get("status") or "pending").lower()

        if st == "succeeded" and (inv.get("status") or "").lower() != "paid":
            amt = data.get("amount") or {}
            currency = amt.get("currency") or "RUB"
            value_str = amt.get("value") or "0.00"
            try:
                amount_minor_units = int(round(float(value_str) * 100))
            except Exception:
                amount_minor_units = 0

            await miniapp_db.db.mark_billing_invoice_paid_yookassa(
                invoice_id=invoice_id,
                payment_id=payment_id,
                amount_minor_units=amount_minor_units,
                currency=currency,
            )
            await miniapp_db.db.apply_saas_plan_for_invoice(invoice_id)

        return {"ok": True, "status": st}

    @app.get(
        "/api/platform/settings",
        responses={
            **COMMON_AUTH_RESPONSES,  # 401/403 (если в твоих константах 403 тоже есть)
        },
    )
    async def get_platform_settings(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        logger.warning("HIT get_platform_settings build=2025-12-19-1239")

        data = await master_db.get_platform_setting("miniapp_public", default={})
        return {"key": "miniapp_public", "value": data}

    def _short_hash(obj: Any) -> str:
        try:
            s = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            s = str(obj)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]

    def _safe_enabled(value: Any) -> Optional[Dict[str, Any]]:
        """
        Достаём только payments.enabled (без секретов).
        """
        if not isinstance(value, dict):
            return None
        payments = value.get("payments")
        if not isinstance(payments, dict):
            return None
        enabled = payments.get("enabled")
        if not isinstance(enabled, dict):
            return None
        return {
            "telegramStars": enabled.get("telegramStars"),
            "ton": enabled.get("ton"),
            "yookassa": enabled.get("yookassa"),
            "stripe": enabled.get("stripe"),
        }

    def _enabled_debug(value: Any) -> Dict[str, Any]:
        """
        Диагностика структуры payments/enabled (без секретов).
        """
        if not isinstance(value, dict):
            return {
                "valueType": type(value).__name__,
                "paymentsType": None,
                "enabledType": None,
                "enabledKeys": None,
            }

        payments = value.get("payments", None)
        if not isinstance(payments, dict):
            return {
                "valueType": "dict",
                "paymentsType": type(payments).__name__,
                "enabledType": None,
                "enabledKeys": None,
            }

        enabled = payments.get("enabled", None)
        if not isinstance(enabled, dict):
            return {
                "valueType": "dict",
                "paymentsType": "dict",
                "enabledType": type(enabled).__name__,
                "enabledKeys": None,
            }

        return {
            "valueType": "dict",
            "paymentsType": "dict",
            "enabledType": "dict",
            "enabledKeys": sorted(enabled.keys()),
        }

    @app.post(
        "/api/platform/settings/{key}",
        responses={
            **COMMON_AUTH_RESPONSES,  # 401/403 (get_current_user + require_superadmin)
            **COMMON_BAD_REQUEST_RESPONSES,  # 400 (miniapp_public value must be object + возможные другие проверки)
            # 422 FastAPI добавит сам для ошибок валидации тела/параметров, если payload не проходит pydantic
        },
    )
    async def set_platform_settings(
        key: str,
        payload: PlatformSettingUpsert,
        request: Request,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_superadmin(current_user)

        uid = current_user.get("userId") or current_user.get("userid") or current_user.get("id")
        ip = request.client.host if request.client else None
        ct = request.headers.get("content-type")

        incoming = payload.value

        # BEFORE (что было в БД до записи)
        before = await master_db.get_platform_setting(key, default=None)

        logger.warning(
            "platform_settings.save IN ip=%s user=%s key=%s content_type=%s before_hash=%s incoming_hash=%s before_enabled=%s incoming_enabled=%s incoming_dbg=%s",
            ip,
            uid,
            key,
            ct,
            _short_hash(before),
            _short_hash(incoming),
            _safe_enabled(before),
            _safe_enabled(incoming),
            _enabled_debug(incoming),
        )

        # Нормализация miniapp_public перед сохранением
        if key == "miniapp_public":
            v = incoming or {}
            if not isinstance(v, dict):
                raise HTTPException(status_code=400, detail="miniapp_public value must be object")

            payments = v.get("payments") or {}
            if not isinstance(payments, dict):
                payments = {}

            enabled = payments.get("enabled") or {}
            if not isinstance(enabled, dict):
                enabled = {}

            # ВАЖНО: гарантируем наличие всех флагов, включая stripe
            enabled["telegramStars"] = bool(enabled.get("telegramStars", False))
            enabled["ton"] = bool(enabled.get("ton", False))
            enabled["yookassa"] = bool(enabled.get("yookassa", False))
            enabled["stripe"] = bool(enabled.get("stripe", False))

            payments["enabled"] = enabled
            v["payments"] = payments

            # сохраняем УЖЕ нормализованное значение
            await master_db.set_platform_setting(key, v)

            # AFTER (что получилось в БД)
            after = await master_db.get_platform_setting(key, default=None)
            logger.warning(
                "platform_settings.save OUT ip=%s user=%s key=%s after_hash=%s after_enabled=%s after_dbg=%s",
                ip,
                uid,
                key,
                _short_hash(after),
                _safe_enabled(after),
                _enabled_debug(after),
            )

            # синхронизируем Stars-цены
            tg_stars = payments.get("telegramStars") or {}
            price_lite = tg_stars.get("priceStarsLite")
            price_pro = tg_stars.get("priceStarsPro")
            price_ent = tg_stars.get("priceStarsEnterprise")

            mapping = [("lite", price_lite), ("pro", price_pro), ("enterprise", price_ent)]
            for plancode, price in mapping:
                if price is None:
                    continue
                await master_db.update_saas_plan_price_stars(plancode, int(price))
                await master_db.sync_billing_product_amount_from_plan(plancode)

            return {"status": "ok"}

        # все остальные ключи — как раньше
        await master_db.set_platform_setting(key, incoming)

        after = await master_db.get_platform_setting(key, default=None)
        logger.warning(
            "platform_settings.save OUT ip=%s user=%s key=%s after_hash=%s after_enabled=%s after_dbg=%s",
            ip,
            uid,
            key,
            _short_hash(after),
            _safe_enabled(after),
            _enabled_debug(after),
        )

        return {"status": "ok"}

    @app.get(
        "/api/instances/{instance_id}/billing",
        response_model=BillingInfo,
        responses={
            **COMMON_AUTH_RESPONSES,  # 401/403
            **COMMON_NOT_FOUND_RESPONSES,  # 404
        },
    )
    async def get_instance_billing_endpoint(
        instance_id: InstanceId,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        """
        Возвращает информацию о тарифе и лимитах для инстанса.
        Доступен всем, у кого есть доступ к инстансу (owner/operator/viewer).
        """
        await require_instance_access(instance_id, current_user, required_role=None)

        billing = await miniapp_db.get_instance_billing(instance_id)
        if not billing:
            raise HTTPException(status_code=404, detail="Billing not found for this instance")

        # single-tenant режим: безлимитный тариф (config from DB)
        single_tenant = await get_single_tenant_config(miniapp_db.db)
        if single_tenant.enabled:
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

    @app.get(
        "/api/billing/ton/status",
        response_model=TonInvoiceStatusResponse,
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
            **COMMON_BAD_REQUEST_RESPONSES,
        },
    )
    async def ton_invoice_status(
        invoice_id: int = Query(..., ge=1, le=9223372036854775807),
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        inv = await miniapp_db.db.get_billing_invoice(invoice_id)
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")

        await require_instance_access(inv["instance_id"], current_user)

        if inv.get("payment_method") != "ton":
            raise HTTPException(status_code=400, detail="Invoice is not TON")

        if inv.get("status") == "paid":
            return TonInvoiceStatusResponse(
                invoice_id=invoice_id,
                status="paid",
                tx_hash=inv.get("provider_tx_hash"),
                period_applied=True,
            )

        res = await check_ton_payment(invoice_id)

        if res["status"] == "paid":
            return TonInvoiceStatusResponse(
                invoice_id=invoice_id,
                status="paid",
                tx_hash=res.get("tx_hash"),
                period_applied=True,
            )

        return TonInvoiceStatusResponse(
            invoice_id=invoice_id,
            status="pending",
            tx_hash=None,
            period_applied=False,
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
            inst = await master_bot.db.get_instance_with_meta_by_id(payload.instance_id)
            if not inst:
                logger.info(
                    "resolve_instance: instance not found instance_id=%s",
                    payload.instance_id,
                )
                return ResolveInstanceResponse(instance_id=None, link_forbidden=False)

            owner_match = inst.get("owner_id") == user_id or inst.get("owner_user_id") == user_id
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

            integrator_instance = await miniapp_db.get_instance_by_owner(payload.admin_id)
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
                general_panel_chat_id=integrator_instance.get("general_panel_chat_id"),
                link_forbidden=False,
            )

        logger.info(
            "resolve_instance: no instance/admin provided for user_id=%s, returning empty",
            user_id,
        )
        return ResolveInstanceResponse(instance_id=None, link_forbidden=False)

    @app.get("/api/me", response_model=UserResponse)
    async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
        # Совместимость: где-то у тебя user_id, где-то userid.
        user_id = (
            current_user.get("user_id") or current_user.get("userid") or current_user.get("userId")
        )
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user_id = int(user_id)
        roles: list[str] = []
        try:
            superadmins = await _parse_superadmin_ids()
            if user_id in superadmins:
                roles.append("superadmin")
        except Exception:
            logger.exception("get_me: failed to evaluate superadmins from miniapp_public")

        instances = await master_bot.db.get_user_instances_with_meta(user_id)

        return UserResponse(
            user_id=user_id,
            username=current_user.get("username"),
            first_name=None,
            last_name=None,
            language=None,
            roles=roles,
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

    @app.get("/api/instances", response_model=List[InstanceInfo])
    async def list_instances(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        instances = await master_bot.db.get_user_instances_with_meta(current_user["user_id"])

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

    @app.post(
        "/api/instances",
        response_model=CreateInstanceResponse,
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_BAD_REQUEST_RESPONSES,
            500: {"description": "Internal Server Error"},
        },
    )
    async def create_instance(
        req: CreateInstanceRequest,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        """
        Создать новый инстанс по токену бота через MasterBot:
        - MasterBot проверяет токен, создаёт запись в БД, шифрует токен.
        - Miniapp создаёт worker в памяти и настраивает webhook для инстанса.
        - Auto-close тикетов теперь глобальный цикл в MasterBot, поэтому тут НЕ запускается.
        """
        user_id = current_user["user_id"]
        token = req.token

        logger.info(
            "create_instance (miniapp): user_id=%s token_preview=%s",
            user_id,
            token[:10],
        )

        if master_bot is None:
            logger.error("create_instance: master_bot is not initialized")
            raise HTTPException(status_code=500, detail="MasterBot не инициализирован")

        # 1) Создаём инстанс в БД через MasterBot (валидация токена + запись в БД)
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

        try:
            worker = GraceHubWorker(instance.instance_id, token, master_bot.db)
            master_bot.workers[instance.instance_id] = worker

            # На всякий случай гарантируем, что instance доступен в master_bot.instances
            master_bot.instances[instance.instance_id] = instance

            if not await master_bot.setup_worker_webhook(instance.instance_id, token):
                raise ValueError("Failed to setup webhook")

        except Exception as e:
            logger.error(
                "Failed to setup worker/webhook for new instance %s: %s",
                instance.instance_id,
                e,
            )
            # rollback: удаляем созданный инстанс из БД
            await master_bot.db.delete_instance(instance.instance_id)
            raise HTTPException(
                status_code=500,
                detail="Ошибка при настройке webhook для нового инстанса",
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

    @app.get(
        "/api/instances/{instance_id}/stats",
        response_model=InstanceStats,
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
            **COMMON_BAD_REQUEST_RESPONSES,
        },
    )
    async def get_instance_stats(
        instance_id: InstanceId,
        current_user: Dict[str, Any] = Depends(get_current_user),
        days: int = Query(30, ge=1, le=365),
    ):
        await require_instance_access(instance_id, current_user)

        stats = await miniapp_db.get_instance_stats(instance_id, days)
        return InstanceStats(**stats)

    @app.delete(
        "/api/instances/{instance_id}",
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
        },
    )
    async def delete_instance_endpoint(
        instance_id: InstanceId,
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

        # 1. Берём инстанс из master_db, как делает мастер-бот
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

        # 2. Остановить воркер (включает отмену tasks, удаление из памяти и снятие webhook)
        try:
            await master_bot.stop_worker(instance_id)
        except Exception as e:
            logger.warning(
                "delete_instance: failed to stop worker for %s: %s",
                instance_id,
                e,
            )

        # 3. Удалить из БД и кэша master_bot
        await master_bot.db.delete_instance(instance_id)
        master_bot.instances.pop(instance_id, None)

        logger.info(
            "delete_instance: removed instance_id=%s by user_id=%s",
            instance_id,
            current_user["user_id"],
        )

        return {"status": "ok"}

    # ---------- НАСТРОЙКИ ИНСТАНСА (Settings.tsx) ----------

    @app.get(
        "/api/instances/{instance_id}/settings",
        response_model=InstanceSettings,
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
        },
    )
    async def get_instance_settings_endpoint(
        instance_id: InstanceId,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_instance_access(instance_id, current_user)
        settings = await miniapp_db.get_instance_settings(instance_id)
        # New: Fetch instance status from DB (e.g., running/error)
        instance = await master_bot.db.get_instance(instance_id)
        status = instance.status.value if instance else "unknown"

        logger.info(
            "Instance settings for %s: openchat_enabled=%s general_panel_chat_id=%s language=%s status=%s",
            instance_id,
            settings.openchat_enabled,
            settings.general_panel_chat_id,
            settings.language,
            status,
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
            status=status,
        )

    @app.post(
        "/api/instances/{instance_id}/settings",
        response_model=InstanceSettings,
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_BAD_REQUEST_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
        },
    )
    async def update_instance_settings_endpoint(
        instance_id: InstanceId,
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

    @app.get(
        "/api/instances/{instance_id}/tickets",
        response_model=TicketsListResponse,
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
        },
    )
    async def list_tickets_endpoint(
        instance_id: InstanceId,
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
                status_emoji="",
                created_at=row["createdat"],
                last_user_msg_at=row.get("lastusermsgat"),
                last_admin_reply_at=row.get("lastadminreplyat"),
                openchat_topic_id=row.get("openchattopicid"),
            )
            for row in rows
        ]

        return TicketsListResponse(items=items, total=total)

    @app.post(
        "/api/instances/{instance_id}/tickets/{ticket_id}/status",
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_BAD_REQUEST_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
        },
    )
    async def update_ticket_status_endpoint(
        instance_id: InstanceId,
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
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
        },
    )
    async def get_operators(
        instance_id: InstanceId,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_instance_access(instance_id, current_user)

        members = await miniapp_db.get_instance_members(instance_id)
        return [InstanceMember(**m) for m in members]

    @app.post(
        "/api/instances/{instance_id}/operators",
        responses={
            **COMMON_AUTH_RESPONSES,
            **COMMON_BAD_REQUEST_RESPONSES,
            **COMMON_NOT_FOUND_RESPONSES,
        },
    )
    async def add_operator(
        instance_id: InstanceId,
        req: AddOperatorRequest,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_instance_access(instance_id, current_user, required_role="owner")

        if not req.user_id and not req.username:
            raise HTTPException(status_code=400, detail="Укажите user_id или username")

        user_id = req.user_id
        if req.username and not user_id:
            raise HTTPException(
                status_code=400,
                detail=("Поиск по username требует интеграции. Используйте user_id."),
            )

        await miniapp_db.add_instance_member(instance_id, user_id, req.role)
        return {"status": "ok", "message": "Оператор добавлен"}

    @app.delete(
        "/api/instances/{instance_id}/operators/{user_id}",
        responses={
            **COMMON_AUTH_RESPONSES,
        },
    )
    async def remove_operator(
        user_id: int,
        instance_id: InstanceId,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        await require_instance_access(instance_id, current_user, required_role="owner")
        await miniapp_db.remove_instance_member(instance_id, user_id)
        return {"status": "ok", "message": "Оператор удалён"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
