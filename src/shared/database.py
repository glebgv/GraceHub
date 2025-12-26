# src/shared/database.py
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Any, Dict, Tuple

import asyncpg
from cryptography.fernet import Fernet
from cachetools import TTLCache

from .models import BotInstance, InstanceStatus
from . import settings

logger = logging.getLogger(__name__)


def get_master_dsn() -> str:
    """
    Возвращает DSN для master-БД.

    Приоритет:
    1) env DATABASE_URL (обязательно для CI)
    2) settings.DATABASE_URL (удобно для локальной разработки)
    """
    env = (os.getenv("ENV") or "").lower()
    env_dsn = os.getenv("DATABASE_URL")

    # CI guard: в CI запрещаем "молча" брать DSN из settings/.env
    if env == "ci":
        if not env_dsn:
            raise RuntimeError(
                "ENV=ci: DATABASE_URL не задан (или пустой).\n"
                "Нужно передать DATABASE_URL через GitHub Actions env, например:\n"
                "DATABASE_URL=postgresql://gh_user:postgres@127.0.0.1:5432/gracehub"
            )
        return env_dsn

    # Не-CI: сначала env (если задан), чтобы можно было переопределять локально
    if env_dsn:
        return env_dsn

    # Фоллбек на settings
    try:
        from . import settings
        dsn = getattr(settings, "DATABASE_URL", None)
        if dsn:
            return dsn
    except ImportError:
        pass

    raise RuntimeError(
        "DATABASE_URL не задан.\n"
        "1. Добавь в .env: DB_USER, DB_PASSWORD, DB_HOST, DB_NAME\n"
        "2. Или DATABASE_URL=postgresql://user:pass@host:port/dbname"
    )

class MasterDatabase:
    """
    Master DB на PostgreSQL.
    - Подключение через asyncpg с пулом соединений.
    - Шифрование токенов через Fernet, ключ хранится в settings.ENCRYPTION_KEY_FILE.
    """

    def __init__(self, dsn: Optional[str] = None):
        self.dsn: str = dsn or get_master_dsn()
        self.pool: Optional[asyncpg.Pool] = None
        self.cipher: Optional[Fernet] = None
        self.settings_cache = TTLCache(maxsize=100, ttl=60)  # Кэш для платформенных настроек

    async def init(self) -> None:
        """
        Полная инициализация: проверка DSN, создание пула соединений,
        настройка шифрования и создание таблиц.
        Вызывать один раз при старте мастера или воркера.
        """
        if not self.dsn.startswith("postgresql://"):
            raise RuntimeError(
                "SQLite больше не поддерживается для master DB. "
                "Задай env DATABASE_URL=postgresql://..."
            )

        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=5,
            max_size=20,
            timeout=30,
            max_inactive_connection_lifetime=300
        )

        key = self.get_or_create_encryption_key()
        self.cipher = Fernet(key)

        await self.create_tables()
        await self.ensure_default_platform_settings()
        logger.info(f"Master database (Postgres) initialized: {self.dsn}")

    async def count_instances_for_user(self, userid: int) -> int:
        row = await self.fetchone(
            "SELECT COUNT(*) AS cnt FROM bot_instances WHERE user_id = $1",
            (userid,)
        )
        return int(row["cnt"]) if row else 0

    async def get_offer_settings(self) -> Dict[str, Any]:
        raw = await self.get_platform_setting("miniapp_public", default=None)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = None

        raw = raw if isinstance(raw, dict) else {}
        offer = raw.get("offer") or {}
        if not isinstance(offer, dict):
            offer = {}

        enabled = bool(offer.get("enabled", False))
        url = str(offer.get("url", "") or "").strip()
        return {"enabled": enabled, "url": url}


    async def get_user_offer_status(self, user_id: int) -> Dict[str, Any]:
        row = await self.fetchone(
            """
            SELECT user_id, offer_url, accepted, accepted_at
            FROM user_offer_acceptance
            WHERE user_id = $1
            """,
            (user_id,),
        )

        return (
            dict(row)
            if row
            else {"user_id": user_id, "offer_url": None, "accepted": False, "accepted_at": None}
        )


    async def upsert_user_offer(
        self,
        user_id: int,
        offer_url: str,
        accepted: bool,
        source: str,
    ) -> None:
        await self.execute(
            """
            INSERT INTO user_offer_acceptance (
            user_id, offer_url, accepted, accepted_at, source, updated_at
            )
            VALUES (
            $1,
            $2,
            $3,
            CASE WHEN $3 THEN NOW() ELSE NULL END,
            $4,
            NOW()
            )
            ON CONFLICT (user_id)
            DO UPDATE SET
            offer_url = EXCLUDED.offer_url,
            accepted = EXCLUDED.accepted,
            accepted_at = CASE WHEN EXCLUDED.accepted THEN NOW() ELSE NULL END,
            source = EXCLUDED.source,
            updated_at = NOW()
            """,
            (user_id, offer_url, accepted, source),
        )


    async def has_accepted_offer(self, user_id: int, offer_url: str) -> bool:
        if not offer_url:
            return True

        row = await self.fetchone(
            """
            SELECT accepted
            FROM user_offer_acceptance
            WHERE user_id = $1 AND offer_url = $2
            """,
            (user_id, offer_url),
        )
        return bool(row and row["accepted"])

    async def get_max_instances_per_user(self) -> int:
        raw = await self.get_platform_setting("miniapp_public", default=None)
        if isinstance(raw, str):
            try:
                import json
                raw = json.loads(raw)
            except Exception:
                raw = None
        raw = raw if isinstance(raw, dict) else {}
        inst = raw.get("instanceDefaults") or {}
        inst = inst if isinstance(inst, dict) else {}
        try:
            v = int(inst.get("maxInstancesPerUser") or 0)
        except Exception:
            v = 0
        return max(v, 0)


    async def update_instance_webhook(
        self,
        instance_id: str,
        webhook_url: str,
        webhook_path: str,
        webhook_secret: str,
    ) -> None:
        await self.execute(
            """
            UPDATE bot_instances
            SET webhook_url = $1,
                webhook_path = $2,
                webhook_secret = $3,
                updated_at = NOW()
            WHERE instance_id = $4
            """,
            (webhook_url, webhook_path, webhook_secret, instance_id),
        )

    def get_or_create_encryption_key(self) -> bytes:
        keyfile = Path(settings.ENCRYPTION_KEY_FILE)
        keyfile.parent.mkdir(parents=True, exist_ok=True)
        if keyfile.exists():
            return keyfile.read_bytes()
        key = Fernet.generate_key()
        keyfile.write_bytes(key)
        try:
            os.chmod(keyfile, 0o600)
        except Exception:
            pass
        return key

    async def get_single_tenant(self) -> Dict[str, Any]:
        data = await self.get_platform_setting("single_tenant", default=None)
        if not data:
            return {"enabled": False, "allowed_user_ids": []}
        return {
            "enabled": bool(data.get("enabled", False)),
            "allowed_user_ids": list(data.get("allowed_user_ids") or []),
        }

    async def set_single_tenant(self, enabled: bool, allowed_user_ids: List[int]) -> None:
        allowed_user_ids = sorted({int(x) for x in allowed_user_ids})
        await self.set_platform_setting(
            "single_tenant",
            {"enabled": bool(enabled), "allowed_user_ids": allowed_user_ids},
        )

    async def get_platform_setting(
        self,
        key: str,
        default: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        cache_key = f"platform_setting:{key}"
        if cache_key in self.settings_cache:
            return self.settings_cache[cache_key]

        row = await self.fetchone(
            "SELECT value FROM platform_settings WHERE key = $1 LIMIT 1",
            (key,)
        )
        value = row["value"] if row else default
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = default
        self.settings_cache[cache_key] = value
        return value


    async def set_platform_setting(
        self,
        key: str,
        value: Dict[str, Any],
    ) -> None:
        value_json = json.dumps(value)
        await self.execute(
            """
            INSERT INTO platform_settings (key, value, created_at, updated_at)
            VALUES ($1, $2, NOW(), NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = NOW()
            """,
            (key, value_json)
        )
        # Инвалидируем кэш после обновления
        cache_key = f"platform_setting:{key}"
        if cache_key in self.settings_cache:
            del self.settings_cache[cache_key]

    async def track_operator_activity(self, instance_id: str, user_id: int, username: str) -> None:
        """
        Обновляет/создаёт оператора по активности в OpenChat.
        """
        now = datetime.now(timezone.utc)
        await self.execute(
            """
            INSERT INTO operators (instance_id, user_id, username, last_seen)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (instance_id, user_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                last_seen = EXCLUDED.last_seen
            """,
            (instance_id, user_id, username, now),
        )

    async def mark_expiring_notified_today(self, instance_id: str) -> None:
        """
        Помечает, что для инстанса сегодня уже отправлено напоминание о скором окончании.
        """
        await self.execute(
            """
            UPDATE instance_billing
               SET last_expiring_notice_date = CURRENT_DATE,
                   updated_at = NOW()
             WHERE instance_id = $1
            """,
            (instance_id,),
        )

    async def mark_paused_notified_now(self, instance_id: str) -> None:
        """
        Помечает, что для инстанса только что отправлено уведомление о паузе тарифа.
        """
        await self.execute(
            """
            UPDATE instance_billing
               SET last_paused_notice_at = NOW(),
                   updated_at = NOW()
             WHERE instance_id = $1
            """,
            (instance_id,),
        )

    async def update_billing_flags(self) -> None:
        """
        Пересчитывает days_left / over_limit / service_paused для всех instance_billing.
        """
        sql = """
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
        WHERE TRUE;
        """
        await self.execute(sql)

    async def get_instances_expiring_in_7_days_for_notify(self) -> list[dict]:
        """
        Инстансы, у которых осталось ровно 7 дней, service_paused = FALSE
        и которым ещё не отправляли напоминание сегодня.
        """
        sql = """
        SELECT ib.instance_id,
               ib.period_end,
               ib.days_left,
               ib.tickets_used,
               ib.tickets_limit,
               ib.last_expiring_notice_date,
               bi.owner_user_id,
               bi.admin_private_chat_id,
               bi.bot_username
        FROM instance_billing ib
        JOIN bot_instances bi ON bi.instance_id = ib.instance_id
        WHERE ib.service_paused = FALSE
          AND ib.days_left = 7
          AND (
                ib.last_expiring_notice_date IS NULL
                OR ib.last_expiring_notice_date < CURRENT_DATE
          );
        """
        rows = await self.fetchall(sql)
        return [dict(r) for r in rows]

    async def get_recently_paused_instances_for_notify(self) -> list[dict]:
        """
        Инстансы, которые за последние сутки ушли в паузу,
        и которым ещё не отправляли уведомление (или отправляли давно).
        """
        sql = """
        SELECT ib.instance_id,
               ib.period_end,
               ib.days_left,
               ib.tickets_used,
               ib.tickets_limit,
               ib.over_limit,
               ib.last_paused_notice_at,
               bi.owner_user_id,
               bi.admin_private_chat_id,
               bi.bot_username
        FROM instance_billing ib
        JOIN bot_instances bi ON bi.instance_id = ib.instance_id
        WHERE ib.service_paused = TRUE
          AND ib.updated_at >= (NOW() - INTERVAL '1 day')
          AND (
                ib.last_paused_notice_at IS NULL
                OR ib.last_paused_notice_at < (NOW() - INTERVAL '1 hour')
          );
        """
        rows = await self.fetchall(sql)
        return [dict(r) for r in rows]


    async def get_all_instances_for_monitor(self) -> list[BotInstance]:
        """
        Возвращает все инстансы для мониторинга (running + error и т.д.).
        """
        rows = await self.fetchall(
            """
            SELECT
                instance_id,
                user_id,
                token_hash,
                bot_username,
                bot_name,
                webhook_url,
                webhook_path,
                webhook_secret,
                status,
                created_at,
                updated_at AS updated_at,    
                error_message,
                owner_user_id,
                admin_private_chat_id
            FROM bot_instances
            """
        )
        return [BotInstance(**row) for row in rows]



    async def get_instance_settings(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Настройки инстанса для мастер-бота (как dict).
        """
        row = await self.fetchone(
            """
            SELECT
                bi.instance_id,
                bi.bot_username,
                bi.bot_name,
                bi.created_at,
                bi.owner_user_id,
                bi.admin_private_chat_id,
                bi.user_id AS owner_id
            FROM bot_instances bi
            WHERE bi.instance_id = $1
            LIMIT 1
            """,
            (instance_id,)
        )
        if not row:
            return None

        inst = dict(row)

        auto_close_hours = 12
        greeting: Optional[str] = None
        default_answer: Optional[str] = None
        branding_bot_name = inst.get("bot_name")
        openchat_enabled = False
        openchat_username = inst.get("openchat_username")
        general_panel_chat_id = inst.get("general_panel_chat_id")
        language: Optional[str] = None

        meta = await self.fetchone(
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
            (instance_id,)
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

        return {
            "instance_id": inst["instance_id"],
            "bot_username": inst.get("bot_username"),
            "bot_name": inst.get("bot_name"),
            "auto_close_hours": auto_close_hours,
            "greeting": greeting,
            "default_answer": default_answer,
            "branding_bot_name": branding_bot_name,
            "openchat_enabled": openchat_enabled,
            "openchat_username": openchat_username,
            "general_panel_chat_id": general_panel_chat_id,
            "language": language,
        }

    async def mark_billing_invoice_paid(
        self,
        invoice_id: int,
        telegram_invoice_id: str,
        total_amount: int,
        currency: str,
    ) -> None:
        """
        Обновляет статус инвойса на paid и сохраняет данные от Telegram.
        total_amount для Stars Telegram отдаёт в тех же единицах, что и мы передавали (кол-во звёзд).
        """
        await self.execute(
            """
            UPDATE billing_invoices
            SET status = 'paid',
                telegram_invoice_id = $1,
                stars_amount = $2,
                currency = $3,
                paid_at = NOW(),
                updated_at = NOW()
            WHERE invoice_id = $4
            """,
            (telegram_invoice_id, total_amount, currency, invoice_id),
        )

    async def find_billing_invoice_by_payload(self, payload: str) -> Optional[Dict[str, Any]]:
        row = await self.fetchone(
            """
            SELECT invoice_id, instance_id, user_id, product_id, payload, invoice_link, stars_amount,
                amount_minor_units, currency, payment_method, provider_tx_hash, status,
                created_at, updated_at, paid_at
            FROM billing_invoices
            WHERE payload = $1
            LIMIT 1
            """,
            (payload,)
        )
        return dict(row) if row else None

    async def mark_billing_invoice_paid_yookassa(
            self,
            invoice_id: int,
            payment_id: str,
            amount_minor_units: int,
            currency: str = "RUB",
        ) -> bool:
            """
            Идемпотентно помечает YooKassa-инвойс оплаченным с блокировкой строки.
            Возвращает True, если статус изменился на 'paid' (был не paid).
            Возвращает False, если инвойс уже был paid или не найден.
            """
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Блокируем строку инвойса для исключения race conditions
                    row = await conn.fetchrow(
                        """
                        SELECT status
                        FROM billing_invoices
                        WHERE invoice_id = $1
                        FOR UPDATE
                        """,
                        invoice_id
                    )

                    if not row:
                        return False  # Инвойс не найден

                    if row["status"] == "paid":
                        return False  # Уже оплачен — идемпотентно выходим

                    # Обновляем только если статус ещё не paid
                    await conn.execute(
                        """
                        UPDATE billing_invoices
                        SET status = 'paid',
                            provider_tx_hash = $1,
                            amount_minor_units = $2,
                            currency = $3,
                            paid_at = NOW(),
                            updated_at = NOW()
                        WHERE invoice_id = $4
                        """,
                        payment_id, amount_minor_units, currency, invoice_id
                    )
                    return True


    async def get_billing_invoice(self, invoice_id: int) -> dict | None:
        # Добавлено для TON (комментарий перемещён вне строки SQL)
        row = await self.fetchone(
            """
            SELECT
                invoice_id,
                instance_id,
                user_id,
                product_id,
                payload,
                invoice_link,
                stars_amount,
                amount_minor_units,
                currency,
                payment_method,
                provider_tx_hash,
                status,
                created_at,
                updated_at,
                paid_at,
                memo
            FROM billing_invoices
            WHERE invoice_id = $1
            LIMIT 1
            """,
            (invoice_id,)
        )
        return dict(row) if row else None

    async def cancel_billing_invoice(self, invoice_id: int) -> bool:
        """
        Мягкая отмена: переводим pending -> cancelled.
        Возвращает True если что-то реально поменялось, иначе False.
        Не отменяем paid.
        """
        now = datetime.now(timezone.utc)

        # Если paid — не трогаем
        await self.execute(
            """
            UPDATE billing_invoices
            SET status = 'cancelled',
                updated_at = $1
            WHERE invoice_id = $2
            AND status != 'paid'
            """,
            (now, invoice_id),
        )

        # Если нужно понимать, изменилось ли реально — можно проверить статус после
        row = await self.fetchone(
            "SELECT status FROM billing_invoices WHERE invoice_id = $1",
            (invoice_id,)
        )
        return bool(row and row["status"] == "cancelled")


    async def get_saas_plans_for_billing(self) -> list[dict]:
        """
        Список тарифов для витрины биллинга:
        saas_plans + billing_products (если product есть и активен).
        """
        rows = await self.fetchall(
            """
            SELECT
                sp.code         AS plan_code,
                sp.name         AS plan_name,
                sp.period_days  AS period_days,
                sp.tickets_limit,
                sp.price_stars,
                bp.code         AS product_code
            FROM saas_plans AS sp
            LEFT JOIN billing_products AS bp
            ON bp.plan_id = sp.plan_id
            AND bp.is_active = TRUE
            ORDER BY sp.plan_id
            """
        )
        return [dict(r) for r in rows]


    async def mark_billing_invoice_paid_ton(
            self,
            invoice_id: int,
            tx_hash: str,
            amount_minor_units: int,
            currency: str = "TON",
        ) -> bool:
            """
            Идемпотентно помечает TON-инвойс оплаченным с блокировкой строки.
            Возвращает True, если статус реально обновили (pending/cancelled → paid).
            Возвращает False, если инвойс уже был paid или не найден.
            """
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Блокируем строку инвойса
                    row = await conn.fetchrow(
                        """
                        SELECT status
                        FROM billing_invoices
                        WHERE invoice_id = $1
                        FOR UPDATE
                        """,
                        invoice_id
                    )

                    if not row:
                        return False  # Инвойс не найден

                    if row["status"] == "paid":
                        return False  # Уже оплачен — идемпотентно

                    # Обновляем данные
                    await conn.execute(
                        """
                        UPDATE billing_invoices
                        SET status = 'paid',
                            provider_tx_hash = $1,
                            amount_minor_units = $2,
                            currency = $3,
                            paid_at = NOW(),
                            updated_at = NOW()
                        WHERE invoice_id = $4
                        """,
                        tx_hash, amount_minor_units, currency, invoice_id
                    )
                    return True


    async def set_billing_invoice_ton_failed(
        self,
        invoice_id: int,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        """
        Помечает TON-инвойс как failed и сохраняет диагностическую информацию.
        Подходит для случаев, когда проверка транзакции не удалась/просрочена/найден конфликт.
        """
        await self.execute(
            """
            UPDATE billing_invoices
               SET status = 'failed',
                   error_code = $1,
                   error_message = $2,
                   updated_at = NOW()
             WHERE invoice_id = $3
            """,
            (error_code, error_message, invoice_id),
        )

    async def upsert_billing_invoice_ton_tx(
        self,
        invoice_id: int,
        tx_hash: str | None,
        amount_minor_units: int | None,
        currency: str = "TON",
    ) -> None:
        """
        Обновляет служебные поля TON-инвойса без смены статуса.
        Удобно вызывать при промежуточных событиях (нашли tx, но ждём подтверждений).
        """
        await self.execute(
            """
            UPDATE billing_invoices
               SET provider_tx_hash = COALESCE($1, provider_tx_hash),
                   amount_minor_units = COALESCE($2, amount_minor_units),
                   currency = $3,
                   updated_at = NOW()
             WHERE invoice_id = $4
            """,
            (tx_hash, amount_minor_units, currency, invoice_id),
        )


    async def get_saas_plan_with_product_by_code(self, plan_code: str) -> dict | None:
        row = await self.fetchone(
            """
            SELECT
                sp.plan_id,
                sp.code         AS plan_code,
                sp.name         AS plan_name,
                sp.period_days,
                sp.tickets_limit,
                sp.price_stars,
                bp.product_id,
                bp.code         AS product_code,
                bp.amount_stars
            FROM saas_plans AS sp
            LEFT JOIN billing_products AS bp
              ON bp.plan_id = sp.plan_id
             AND bp.is_active = TRUE
            WHERE sp.code = $1
            LIMIT 1
            """,
            (plan_code,)
        )
        return dict(row) if row else None



    async def apply_saas_plan_for_invoice(self, invoice_id: int) -> None:
        """
        По invoice_id находим instance_id и соответствующий saas_plan
        и применяем/продлеваем тариф в instance_billing.
        """
        row = await self.fetchone(
            """
            SELECT
                bi.instance_id,
                bi.user_id,
                bi.product_id,
                bp.plan_id,
                sp.code        AS plan_code,
                sp.name        AS plan_name,
                sp.period_days AS period_days,
                sp.tickets_limit
            FROM billing_invoices AS bi
            JOIN billing_products AS bp ON bp.product_id = bi.product_id
            JOIN saas_plans       AS sp ON sp.plan_id = bp.plan_id
            WHERE bi.invoice_id = $1
            """,
            (invoice_id,)
        )
        if not row:
            logger.warning("apply_saas_plan_for_invoice: invoice %s not found", invoice_id)
            return

        data = dict(row)
        instance_id = data["instance_id"]
        plan_id = data["plan_id"]
        period_days = data["period_days"]
        tickets_limit = data["tickets_limit"]

        # продлеваем/устанавливаем период для инстанса:
        # - если period_end > NOW() — добавляем дни к существующему period_end
        # - иначе начинаем новый период от NOW()
        await self.execute(
            """
            INSERT INTO instance_billing (
                instance_id,
                plan_id,
                period_start,
                period_end,
                tickets_used,
                tickets_limit,
                over_limit,
                last_expiring_notice_date,
                last_paused_notice_at
            )
            VALUES (
                $1,
                $2,
                NOW(),
                NOW() + ($3 || ' days')::interval,
                0,
                $4,
                FALSE,
                NULL,
                NULL
            )
            ON CONFLICT (instance_id) DO UPDATE SET
                plan_id = EXCLUDED.plan_id,
                period_start = CASE
                                WHEN instance_billing.period_end > NOW()
                                THEN instance_billing.period_start
                                ELSE NOW()
                            END,
                period_end = CASE
                                WHEN instance_billing.period_end > NOW()
                                THEN instance_billing.period_end + ($3 || ' days')::interval
                                ELSE NOW() + ($3 || ' days')::interval
                            END,
                tickets_used = 0,
                tickets_limit = EXCLUDED.tickets_limit,
                over_limit = FALSE,
                -- при новом периоде очищаем отметки уведомлений
                last_expiring_notice_date = NULL,
                last_paused_notice_at     = NULL,
                updated_at = NOW()
            """,
            (
                instance_id,
                plan_id,
                str(period_days),
                tickets_limit,
            ),
        )

        logger.info(
            "apply_saas_plan_for_invoice: instance=%s plan=%s +%s days",
            instance_id,
            data["plan_code"],
            period_days,
        )


    async def create_tables(self) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # bot_instances
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bot_instances (
                        instance_id             TEXT PRIMARY KEY,
                        user_id                 BIGINT NOT NULL,
                        token_hash              TEXT NOT NULL UNIQUE,
                        bot_username            TEXT NOT NULL,
                        bot_name                TEXT NOT NULL,
                        webhook_url             TEXT NOT NULL,
                        webhook_path            TEXT NOT NULL,
                        webhook_secret          TEXT NOT NULL,
                        status                  TEXT NOT NULL,
                        created_at              TIMESTAMPTZ NOT NULL,
                        updated_at               TIMESTAMPTZ,
                        error_message           TEXT,
                        owner_user_id           BIGINT,
                        admin_private_chat_id   BIGINT
                    )
                    """
                )

                # encrypted_tokens
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS encrypted_tokens (
                        instance_id      TEXT PRIMARY KEY,
                        encrypted_token  BYTEA NOT NULL,
                        CONSTRAINT fk_tokens_instance
                            FOREIGN KEY(instance_id)
                            REFERENCES bot_instances(instance_id)
                            ON DELETE CASCADE
                    )
                    """
                )

                # user_states (master)
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_states (
                        user_id    BIGINT PRIMARY KEY,
                        state      TEXT NOT NULL,
                        data       TEXT,
                        language   TEXT DEFAULT 'ru',
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                    """
                )

                # rate_limits
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rate_limits (
                        instance_id   TEXT NOT NULL,
                        chat_id       BIGINT NOT NULL,
                        last_request  TIMESTAMPTZ NOT NULL,
                        request_count INTEGER DEFAULT 1,
                        PRIMARY KEY (instance_id, chat_id)
                    )
                    """
                )

                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_offer_acceptance (
                        user_id BIGINT PRIMARY KEY,
                        offer_url TEXT NOT NULL,
                        accepted BOOLEAN NOT NULL DEFAULT FALSE,
                        accepted_at TIMESTAMPTZ,
                        source TEXT, -- 'bot' | 'miniapp'
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                # ------------------------------------------------------------------------
                # platform_settings (master-bot / platform-level settings)
                # ------------------------------------------------------------------------
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS platform_settings (
                        key         TEXT PRIMARY KEY,
                        value       JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                # Индекс для выборок по JSON (если будешь искать по value->...):
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_platform_settings_value_gin "
                    "ON platform_settings USING GIN (value)"
                )

                # usage_stats
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS usage_stats (
                        instance_id   TEXT NOT NULL,
                        date          DATE NOT NULL,
                        message_count INTEGER DEFAULT 0,
                        api_calls     INTEGER DEFAULT 0,
                        PRIMARY KEY (instance_id, date)
                    )
                    """
                )

                # instance_settings (уже добавлена ранее)
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS instance_settings (
                        instance_id TEXT PRIMARY KEY REFERENCES bot_instances(instance_id) ON DELETE CASCADE,
                        openchat_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                        autoclose_hours INTEGER NOT NULL DEFAULT 12,
                        general_panel_chat_id BIGINT,
                        auto_reply JSONB,
                        branding JSONB,
                        privacy_mode_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                        language TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ
                    )
                    """
                )

                # blacklisted_users
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS blacklisted_users (
                        instance_id TEXT NOT NULL REFERENCES bot_instances(instance_id) ON DELETE CASCADE,
                        user_id BIGINT NOT NULL,
                        reason TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (instance_id, user_id)
                    )
                    """
                )

                # Индексы
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_instances_user   ON bot_instances(user_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_instances_status ON bot_instances(status)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_time ON rate_limits(last_request)")

                # Таблицы mini app
                await self._create_miniapp_tables(conn)

                await self._create_worker_tables(conn)

                # Таблицы биллинга SaaS
                await self._create_billing_tables(conn)

        # Сидим дефолтные тарифы (Demo/Lite/Pro/Enterprise)
        await self.ensure_default_plans()
        logger.info(
            "Master database tables initialized (Postgres, including miniapp, worker and billing tables)"
        )


    async def ensure_default_platform_settings(self) -> None:
        """
        Гарантирует дефолтные значения в platform_settings.miniapp_public.
        Для миграции: добавляет/обновляет только отсутствующие поля в JSON.
        """
        key = "miniapp_public"
        default_data = {
            "singleTenant": {
                "enabled": False,
                "allowedUserIds": [],
            },
            "superadmins": [],
            "payments": {
                "enabled": {
                    "telegramStars": True,
                    "ton": True,
                    "yookassa": False,
                    "stripe": False,  # Новый дефолт
                },
                "telegramStars": {
                    "priceStarsLite": 100,
                    "priceStarsPro": 300,
                    "priceStarsEnterprise": 999,
                },
                "ton": {
                    "network": "testnet",
                    "walletAddress": "",
                    "apiBaseUrl": "https://testnet.toncenter.com/api/v2",
                    "apiKey": "",
                    "checkDelaySeconds": 5,
                    "confirmationsRequired": 1,
                    "pricePerPeriodLite": 0.5,
                    "pricePerPeriodPro": 2.0,
                    "pricePerPeriodEnterprise": 5.0,
                },
                "yookassa": {
                    "shopId": "",
                    "secretKey": "",
                    "returnUrl": "",
                    "testMode": True,
                    "priceRubLite": 199,
                    "priceRubPro": 499,
                    "priceRubEnterprise": 1999,
                },
                "stripe": {  # Новый блок с дефолтами
                    "secretKey": "",
                    "publishableKey": "",
                    "webhookSecret": "",
                    "currency": "usd",
                    "priceUsdLite": 4.99,
                    "priceUsdPro": 9.99,
                    "priceUsdEnterprise": 29.99,
                },
            },
            "instanceDefaults": {
                "antifloodMaxUserMessagesPerMinute": 20,
                "workerMaxFileMb": 10,
                "maxInstancesPerUser": 3,
            },
        }

        # Получаем текущие данные
        current = await self.get_platform_setting(key, default=default_data)

        # Миграция: добавляем отсутствующие поля (рекурсивно мержим дефолты)
        def merge_dict(target: dict, source: dict) -> dict:
            for k, v in source.items():
                if k not in target:
                    target[k] = v
                elif isinstance(v, dict) and isinstance(target[k], dict):
                    merge_dict(target[k], v)
            return target

        updated = merge_dict(current, default_data)

        # Если изменилось — сохраняем
        if updated != current:
            await self.set_platform_setting(key, updated)
            logger.info(f"Applied migration for {key}: added/updated Stripe defaults")

    async def _create_miniapp_tables(self, conn) -> None:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id    BIGINT PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                last_name  TEXT,
                language   TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )
            """
        )

        # instance_members
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instance_members (
                instance_id TEXT NOT NULL,
                user_id     BIGINT NOT NULL,
                role        TEXT NOT NULL CHECK (role IN ('owner', 'operator', 'viewer')),
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (instance_id, user_id),
                CONSTRAINT fk_members_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_instance_members_instance
            ON instance_members(instance_id)
            """
        )

        # instance_meta (для openchat_enabled, auto_close_hours, etc)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instance_meta (
                instance_id               TEXT PRIMARY KEY,
                openchat_username         TEXT,
                general_panel_chat_id     BIGINT,
                auto_close_hours          INTEGER DEFAULT 12,
                auto_reply_greeting       TEXT,
                auto_reply_default_answer TEXT,
                branding_bot_name         TEXT,
                openchat_enabled          BOOLEAN NOT NULL DEFAULT FALSE,
                language                  TEXT,
                created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT fk_meta_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # worker_settings (key-value для worker по instance_id)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_settings (
                instance_id TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                PRIMARY KEY (instance_id, key),
                CONSTRAINT fk_worker_settings_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # operators (авто-добавление по активности в OpenChat)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operators (
                instance_id TEXT NOT NULL,
                user_id     BIGINT NOT NULL,
                username    TEXT,
                last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (instance_id, user_id),
                CONSTRAINT fk_operators_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # tickets (тикетная история из всех worker-DB)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                instance_id         TEXT NOT NULL,
                id                  INTEGER NOT NULL,  -- ticket_id из worker-DB
                user_id             BIGINT NOT NULL,
                username            TEXT,
                status              TEXT NOT NULL,
                created_at          TIMESTAMPTZ NOT NULL,
                last_user_msg_at    TIMESTAMPTZ,
                last_admin_reply_at TIMESTAMPTZ,
                thread_id           BIGINT,  -- openchat_topic_id
                updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (instance_id, id),
                CONSTRAINT fk_tickets_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tickets_instance_created
            ON tickets(instance_id, created_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tickets_status
            ON tickets(instance_id, status)
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tickets_instance_status_msg
            ON tickets (instance_id, status, last_user_msg_at)
            """
        )

    async def _create_worker_tables(self, conn) -> None:
        # worker_user_states: состояния пользователей в воркере
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_user_states (
                instance_id TEXT NOT NULL,
                user_id     BIGINT NOT NULL,
                state       TEXT NOT NULL,
                data        TEXT,
                PRIMARY KEY (instance_id, user_id),
                CONSTRAINT fk_worker_user_states_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

    async def _create_billing_tables(self, conn) -> None:
        """
        SaaS-биллинг: тарифы, товары, сессии оплаты, транзакции, биллинг инстансов.
        """
        # saas_plans: тарифы (Demo/Lite/Pro/Enterprise)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS saas_plans (
                plan_id       SERIAL PRIMARY KEY,
                name          TEXT NOT NULL,
                code          TEXT NOT NULL UNIQUE,
                price_stars   INTEGER NOT NULL,  
                period_days   INTEGER NOT NULL,
                tickets_limit INTEGER NOT NULL,
                features_json JSONB DEFAULT '{}'::jsonb,
                is_active     BOOLEAN NOT NULL DEFAULT TRUE,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        # instance_billing: текущий тариф + статистика для инстанса
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instance_billing (
                instance_id                TEXT PRIMARY KEY,
                plan_id                    INTEGER NOT NULL
                    REFERENCES saas_plans(plan_id)
                    ON DELETE RESTRICT,

                period_start               TIMESTAMPTZ NOT NULL,
                period_end                 TIMESTAMPTZ NOT NULL,
                days_left                  INTEGER NOT NULL DEFAULT 0,
                service_paused             BOOLEAN NOT NULL DEFAULT FALSE,

                tickets_used               INTEGER NOT NULL DEFAULT 0,
                tickets_limit              INTEGER NOT NULL DEFAULT 0,
                over_limit                 BOOLEAN NOT NULL DEFAULT FALSE,

                last_expiring_notice_date  DATE,       
                last_paused_notice_at      TIMESTAMPTZ,

                created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                CONSTRAINT fk_instance_billing_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # billing_products: товары для Telegram Stars (привязаны к планам)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS billing_products (
                product_id     SERIAL PRIMARY KEY,
                code           TEXT NOT NULL UNIQUE,
                plan_id        INTEGER NOT NULL
                    REFERENCES saas_plans(plan_id)
                    ON DELETE CASCADE,
                title          TEXT NOT NULL,
                description    TEXT,
                amount_stars   INTEGER NOT NULL,  
                is_active      BOOLEAN NOT NULL DEFAULT TRUE,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        # billing_invoices: сессии оплаты (Telegram Stars + TON + YooKassa + Stripe)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS billing_invoices (
                invoice_id          BIGSERIAL PRIMARY KEY,
                instance_id         TEXT NOT NULL,
                user_id             BIGINT,

                product_id          INTEGER NOT NULL
                    REFERENCES billing_products(product_id)
                    ON DELETE RESTRICT,

                plan_code           TEXT,
                periods             INTEGER NOT NULL DEFAULT 1,

                payload             TEXT NOT NULL,

                telegram_invoice_id TEXT,
                invoice_link        TEXT,

                stars_amount        INTEGER NOT NULL,
                amount_minor_units  BIGINT,

                currency            TEXT NOT NULL DEFAULT 'XTR',
                payment_method      TEXT NOT NULL DEFAULT 'telegram_stars',

                provider_tx_hash    TEXT,
                memo                TEXT,

                external_id         TEXT,
                period_applied      BOOLEAN NOT NULL DEFAULT FALSE,

                status              TEXT NOT NULL DEFAULT 'pending',
                error_code          TEXT,
                error_message       TEXT,

                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                paid_at             TIMESTAMPTZ,

                CONSTRAINT fk_billing_invoices_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE,

                CONSTRAINT unique_provider_tx_hash UNIQUE (provider_tx_hash)
            )

            """
        )

        # Миграции для существующих баз: добавляем новые поля и constraints
        await conn.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS external_id TEXT;")
        await conn.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS plan_code TEXT;")
        await conn.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS period_applied BOOLEAN NOT NULL DEFAULT FALSE;")
        await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS unique_external_id_non_null ON billing_invoices (external_id) WHERE external_id IS NOT NULL;")  # Partial UNIQUE index для NULL-safe
        await conn.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS periods INTEGER NOT NULL DEFAULT 1;")
        await conn.execute(
            """
            ALTER TABLE billing_invoices 
            DROP CONSTRAINT IF EXISTS check_payment_method;
            """
        )
        await conn.execute(
            """
            ALTER TABLE billing_invoices 
            ADD CONSTRAINT check_payment_method 
            CHECK (payment_method IN ('telegram_stars', 'ton', 'yookassa', 'stripe'));
            """
        )

        # Индексы для производительности и частичной уникальности
        await conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_billing_invoices_memo_ton
            ON billing_invoices (memo)
            WHERE payment_method = 'ton' AND memo IS NOT NULL;
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_billing_invoices_instance
            ON billing_invoices(instance_id);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_billing_invoices_status
            ON billing_invoices(status);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_billing_invoices_method_status
            ON billing_invoices(payment_method, status);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_billing_invoices_provider_tx_hash
            ON billing_invoices(provider_tx_hash) WHERE provider_tx_hash IS NOT NULL;
            """
        )

        # billing_transactions: что произошло с биллингом по факту (продление, списание и т.п.)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS billing_transactions (
                tx_id          BIGSERIAL PRIMARY KEY,
                instance_id    TEXT NOT NULL,
                invoice_id     BIGINT
                    REFERENCES billing_invoices(invoice_id)
                    ON DELETE SET NULL,
                tx_type        TEXT NOT NULL,          -- subscription_purchase, manual_adjustment и т.п.
                plan_id        INTEGER
                    REFERENCES saas_plans(plan_id)
                    ON DELETE SET NULL,
                period_start   TIMESTAMPTZ,
                period_end     TIMESTAMPTZ,
                tickets_delta  INTEGER,                -- изменение лимита тикетов (можно NULL)
                meta_json      JSONB,                  -- любые доп. данные
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT fk_billing_transactions_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_billing_tx_instance
            ON billing_transactions(instance_id)
            """
        )

    

    # === Thin async wrappers for miniapp_api and worker ===

    async def execute(self, sql: str, params: Optional[tuple] = None) -> asyncpg.Record:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            return await conn.execute(sql, *(params or ()))

    async def fetchone(self, sql: str, params: Optional[tuple] = None):
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(sql, *(params or ()))

    async def fetchall(self, sql: str, params: Optional[tuple] = None):
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            return await conn.fetch(sql, *(params or ()))

    # === Instance CRUD ===

    async def create_instance(self, instance: BotInstance) -> None:
        """
        Создаёт инстанс и сразу вешает Demo-план на 7 дней (если ещё не создан billing).
        """
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO bot_instances (
                        instance_id,
                        user_id,
                        token_hash,
                        bot_username,
                        bot_name,
                        webhook_url,
                        webhook_path,
                        webhook_secret,
                        status,
                        created_at,
                        owner_user_id,
                        admin_private_chat_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    *(
                        instance.instance_id,
                        instance.user_id,
                        instance.token_hash,
                        instance.bot_username,
                        instance.bot_name,
                        instance.webhook_url,
                        instance.webhook_path,
                        instance.webhook_secret,
                        instance.status.value
                        if hasattr(instance.status, "value")
                        else str(instance.status),
                        instance.created_at,
                        instance.owner_user_id,
                        instance.admin_private_chat_id,
                    ),
                )

        # после создания инстанса — инициализируем Demo-биллинг
        await self.ensure_default_billing(instance.instance_id)

    async def delete_instance(self, instance_id: str) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Удаляем связанные записи
                await conn.execute("DELETE FROM instance_settings WHERE instance_id = $1", *(instance_id,))
                await conn.execute("DELETE FROM instance_billing WHERE instance_id = $1", *(instance_id,))
                await conn.execute("DELETE FROM operators WHERE instance_id = $1", *(instance_id,))
                await conn.execute("DELETE FROM tickets WHERE instance_id = $1", *(instance_id,))
                await conn.execute("DELETE FROM blacklisted_users WHERE instance_id = $1", *(instance_id,))
                await conn.execute("DELETE FROM rate_limits WHERE instance_id = $1", *(instance_id,))
                # Удаляем инстанс
                await conn.execute("DELETE FROM bot_instances WHERE instance_id = $1", *(instance_id,))


    async def update_billing_invoice_link_and_payload(
        self,
        invoice_id: int,
        payload: str,
        invoice_link: str,
        external_id: str | None = None,
    ) -> None:
        if external_id:
            await self.execute(
                """
                UPDATE billing_invoices
                SET payload = $1,
                    invoice_link = $2,
                    external_id = $3,
                    updated_at = NOW()
                WHERE invoice_id = $4
                """,
                (payload, invoice_link, external_id, invoice_id),
            )
            return

        await self.execute(
            """
            UPDATE billing_invoices
            SET payload = $1,
                invoice_link = $2,
                updated_at = NOW()
            WHERE invoice_id = $3
            """,
            (payload, invoice_link, invoice_id),
        )

    async def insert_billing_invoice(
        self,
        instance_id: str,
        user_id: int,
        plan_code: str,      # для совместимости, можно не использовать
        periods: int,
        amount_stars: int,   # Stars сумма (XTR), оставляем для совместимости
        product_code: str,
        payload: str,
        invoice_link: str,
        status: str = "pending",
        *,
        payment_method: str = "telegram_stars",    # telegram_stars | ton | yookassa | stripe
        currency: str = "XTR",                     # XTR | TON | RUB | (Stripe: USD/EUR/...)
        amount_minor_units: int | None = None,     # TON: nanoton, YooKassa: kopeks, Stripe: cents
    ) -> int:
        # product_code = billing_products.code → достаём product_id
        product_row = await self.fetchone(
            """
            SELECT product_id
            FROM billing_products
            WHERE code = $1
            LIMIT 1
            """,
            (product_code,),
        )
        if not product_row:
            raise ValueError(f"Unknown billing product_code={product_code}")

        product_id = product_row["product_id"]

        # Нормализуем periods (на всякий)
        try:
            periods_val = int(periods)
        except Exception:
            periods_val = 1
        if periods_val <= 0:
            periods_val = 1

        # Нормализация plan_code (может быть пустым)
        plan_code_val = str(plan_code or "").strip().lower() or None

        # Нормализация payment_method (на случай enum/алиасов)
        if hasattr(payment_method, "value"):
            payment_method = payment_method.value

        payment_method = str(payment_method or "").strip().lower()

        # алиасы, если где-то в коде встречаются другие значения
        if payment_method in ("telegram_stars", "tg_stars", "stars", "telegramstars", "telegram-stars"):
            payment_method = "telegram_stars"

        # Нормализация под метод
        if payment_method == "telegram_stars":
            currency = "XTR"
            stars_amount_val = int(amount_stars)
            amount_minor_val = None

        elif payment_method == "ton":
            currency = "TON"
            stars_amount_val = 0  # stars_amount NOT NULL
            if amount_minor_units is None or int(amount_minor_units) <= 0:
                raise ValueError("TON invoice requires amount_minor_units > 0 (nanoton)")
            amount_minor_val = int(amount_minor_units)

        elif payment_method == "yookassa":
            # Для YooKassa сохраняем сумму в минимальных единицах (копейки) в amount_minor_units
            currency = (currency or "RUB").strip().upper()
            if currency != "RUB":
                # чтобы не разъехались ожидания в остальном коде
                raise ValueError(f"YooKassa invoice requires currency=RUB, got {currency}")

            stars_amount_val = 0  # stars_amount NOT NULL
            if amount_minor_units is None or int(amount_minor_units) <= 0:
                raise ValueError("YooKassa invoice requires amount_minor_units > 0 (kopeks)")
            amount_minor_val = int(amount_minor_units)

        elif payment_method == "stripe":
            # Stripe: тоже храним сумму в минимальных единицах (центы) в amount_minor_units.
            # Валюту берём из аргумента currency (например USD/EUR).
            currency = str(currency or "").strip().upper()
            if not currency:
                raise ValueError("Stripe invoice requires currency (e.g. USD)")

            stars_amount_val = 0  # stars_amount NOT NULL
            if amount_minor_units is None or int(amount_minor_units) <= 0:
                raise ValueError("Stripe invoice requires amount_minor_units > 0 (cents)")
            amount_minor_val = int(amount_minor_units)

        else:
            raise ValueError(f"Unsupported payment_method={payment_method}")

        row = await self.fetchone(
            """
            INSERT INTO billing_invoices (
                instance_id,
                user_id,
                product_id,
                plan_code,
                periods,
                payload,
                telegram_invoice_id,
                invoice_link,
                stars_amount,
                amount_minor_units,
                currency,
                payment_method,
                status
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            RETURNING invoice_id
            """,
            (
                instance_id,
                user_id,
                product_id,
                plan_code_val,
                periods_val,
                payload,
                None,
                invoice_link,
                stars_amount_val,
                amount_minor_val,
                currency,
                payment_method,
                status,
            ),
        )
        return row["invoice_id"]


    async def update_billing_invoice_status(self, invoice_id: int, status: str) -> None:
        """
        Обновляет статус инвойса в billing_invoices.
        Аналогично логике для TON/YooKassa.
        """
        await self.execute(
            """
            UPDATE billing_invoices
            SET status = $1,
                updated_at = NOW()
            WHERE invoice_id = $2
            """,
            (status, invoice_id),
        )
        logger.info(f"Updated invoice {invoice_id} status to {status}")

    async def update_billing_invoice_status_by_external(self, external_id: str, status: str) -> None:
        """
        Обновляет статус инвойса по external_id (для webhook Stripe).
        """
        await self.execute(
            """
            UPDATE billing_invoices
            SET status = $1,
                updated_at = NOW()
            WHERE external_id = $2
            """,
            (status, external_id),
        )
        logger.info(f"Updated invoice by external_id {external_id} status to {status}")

    async def apply_invoice_to_billing(self, invoice_id: int) -> None:
        """
        Применяет оплаченный инвойс к instance_billing: продлевает период, сбрасывает счётчики.
        (Аналогично для Stars/TON/YooKassa; адаптируйте под вашу логику, если метод уже есть под другим именем).
        """
        now = datetime.now(timezone.utc)
        invoice = await self.fetchone(
            "SELECT * FROM billing_invoices WHERE invoice_id = $1",
            (invoice_id,)
        )
        if not invoice or invoice['status'] != 'succeeded':
            logger.warning(f"Cannot apply invoice {invoice_id}: invalid status")
            return

        instance_id = invoice['instance_id']
        periods = invoice['periods']
        plan_code = invoice['plan_code']

        # Получаем текущий биллинг
        billing = await self.fetchone(
            "SELECT * FROM instance_billing WHERE instance_id = $1",
            (instance_id,)
        )
        if not billing:
            logger.error(f"No billing for instance {instance_id}")
            return

        # Получаем план для period_days и tickets_limit
        plan = await self.fetchone(
            "SELECT period_days, tickets_limit FROM saas_plans WHERE code = $1",
            (plan_code,)
        )
        if not plan:
            logger.error(f"Plan {plan_code} not found")
            return

        # Вычисляем новый period_end (продлеваем от текущего конца или now)
        current_end = billing['period_end'] if billing['period_end'] > now else now
        new_end = current_end + timedelta(days=plan['period_days'] * periods)

        await self.execute(
            """
            UPDATE instance_billing
            SET plan_id = (SELECT plan_id FROM saas_plans WHERE code = $1),
                period_end = $2,
                tickets_used = 0,
                tickets_limit = $3,
                over_limit = FALSE,
                service_paused = FALSE,
                updated_at = NOW()
            WHERE instance_id = $4
            """,
            (plan_code, new_end, plan['tickets_limit'], instance_id),
        )

        # Обновляем инвойс как applied
        await self.execute(
            """
            UPDATE billing_invoices
            SET period_applied = TRUE,
                updated_at = NOW()
            WHERE invoice_id = $1
            """,
            (invoice_id,)
        )
        logger.info(f"Applied invoice {invoice_id} to instance {instance_id}")

    async def get_instance(self, instance_id: str) -> Optional[BotInstance]:
        row = await self.fetchone("SELECT * FROM bot_instances WHERE instance_id = $1", (instance_id,))
        if not row:
            return None
        return self.row_to_instance(row)

    async def get_instance_by_token_hash(self, token_hash: str) -> Optional[BotInstance]:
        row = await self.fetchone("SELECT * FROM bot_instances WHERE token_hash = $1", (token_hash,))
        if not row:
            return None
        return self.row_to_instance(row)

    async def get_user_instances(self, user_id: int) -> List[BotInstance]:
        rows = await self.fetchall(
            "SELECT * FROM bot_instances WHERE user_id = $1 ORDER BY created_at DESC",
            (user_id,)
        )
        return [self.row_to_instance(r) for r in rows]

    async def get_user_instances_with_meta(
        self, user_id: int
    ) -> List[Dict[str, Any]]:
        rows = await self.fetchall(
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
            WHERE bi.user_id = $1 OR bi.owner_user_id = $1
            ORDER BY bi.created_at DESC
            """,
            (user_id,)
        )

        result: List[Dict[str, Any]] = []
        for row in rows:
            inst = dict(row)
            inst["role"] = "owner"
            meta = await self.fetchone(
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
                WHERE instance_id = $1
                """,
                (inst["instance_id"],)
            )
            if meta:
                inst.update(dict(meta))
            result.append(inst)

        return result

    async def get_instance_with_meta_by_id(self, instance_id: str) -> Optional[Dict[str, Any]]:
        row = await self.fetchone(
            """
            SELECT
                bi.instance_id,
                bi.bot_username,
                bi.bot_name,
                bi.created_at,
                bi.owner_user_id,
                bi.admin_private_chat_id,
                bi.user_id AS owner_id
            FROM bot_instances bi
            WHERE bi.instance_id = $1
            LIMIT 1
            """,
            (instance_id,)
        )

        if not row:
            return None

        inst = dict(row)

        meta = await self.fetchone(
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
            (inst["instance_id"],)
        )

        if meta:
            inst.update(dict(meta))

        inst["role"] = "owner"
        return inst


    async def get_all_active_instances(self) -> List[BotInstance]:
        rows = await self.fetchall(
            """
            SELECT * FROM bot_instances
             WHERE status IN ($1, $2)
             ORDER BY created_at
            """,
            (InstanceStatus.RUNNING.value, InstanceStatus.STARTING.value)
        )
        return [self.row_to_instance(r) for r in rows]

    async def update_instance_status(
        self,
        instance_id: str,
        status: InstanceStatus,
        error_message: Optional[str] = None,
    ) -> None:
        await self.execute(
            """
            UPDATE bot_instances
               SET status = $1, updated_at = $2, error_message = $3
             WHERE instance_id = $4
            """,
            (
                status.value if hasattr(status, "value") else str(status),
                datetime.now(timezone.utc),
                error_message,
                instance_id,
            ),
        )

    # === Token storage ===

    async def store_encrypted_token(self, instance_id: str, token: str) -> None:
        assert self.cipher is not None
        encrypted = self.cipher.encrypt(token.encode("utf-8"))
        await self.execute(
            """
            INSERT INTO encrypted_tokens (instance_id, encrypted_token)
            VALUES ($1, $2)
            ON CONFLICT (instance_id)
            DO UPDATE SET encrypted_token = EXCLUDED.encrypted_token
            """,
            (instance_id, encrypted),
        )

    async def get_decrypted_token(self, instance_id: str) -> Optional[str]:
        assert self.cipher is not None
        row = await self.fetchone(
            "SELECT encrypted_token FROM encrypted_tokens WHERE instance_id = $1",
            (instance_id,)
        )
        if not row:
            return None
        try:
            return self.cipher.decrypt(bytes(row["encrypted_token"])).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to decrypt token for {instance_id}: {e}")
            return None

    # === User state helpers (для master UI) ===

    async def set_user_state(self, user_id: int, state: str, data: Optional[str] = None) -> None:
        await self.execute(
            """
            INSERT INTO user_states (user_id, state, data)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id)
            DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data
            """,
            (user_id, state, data),
        )
        logger.info("set_user_state: user_id=%s, state=%s", user_id, state)

    async def get_user_state(self, user_id: int) -> Optional[str]:
        row = await self.fetchone(
            "SELECT state FROM user_states WHERE user_id = $1",
            (user_id,)
        )
        logger.info("get_user_state: user_id=%s, state=%s", user_id, row["state"] if row else None)
        return row["state"] if row else None

    async def clear_user_state(self, user_id: int) -> None:
        await self.execute("DELETE FROM user_states WHERE user_id = $1", (user_id,))

    # === Worker helpers ===

    async def worker_set_user_state(
        self,
        instance_id: str,
        user_id: int,
        state: str,
        data: Optional[str] = None,
    ) -> None:
        await self.execute(
            """
            INSERT INTO worker_user_states (instance_id, user_id, state, data)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (instance_id, user_id)
            DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data
            """,
            (instance_id, user_id, state, data),
        )

    # === Billing helpers ===

    async def get_instance_billing(self, instance_id: str) -> Optional[dict]:
        """
        Возвращает запись instance_billing для инстанса или None.
        Включает поля:
        - period_start / period_end / days_left / service_paused
        - tickets_used / tickets_limit / over_limit
        - last_expiring_notice_date / last_paused_notice_at
        """
        row = await self.fetchone(
            """
            SELECT *
            FROM instance_billing
            WHERE instance_id = $1
            """,
            (instance_id,)
        )
        return dict(row) if row else None


    async def get_saas_plan_by_id(self, plan_id: int) -> Optional[dict]:
        """
        Возвращает saas_plan по plan_id (для отображения текущего тарифа инстанса).
        """
        row = await self.fetchone(
            """
            SELECT
                plan_id,
                code        AS plan_code,
                name        AS plan_name,
                period_days,
                tickets_limit,
                price_stars,
                features_json
            FROM saas_plans
            WHERE plan_id = $1
            LIMIT 1
            """,
            (plan_id,)
        )
        return dict(row) if row else None


    async def increment_tickets_used(self, instance_id: str) -> Tuple[bool, Optional[str]]:
        """
        Пытается инкрементировать счётчик тикетов у инстанса.
        Возвращает (ok, error_reason).

        ok = True  -> можно создавать тикет, счётчик увеличен.
        ok = False -> тикет создавать нельзя, error_reason:
                      'no_billing', 'expired', 'limit_reached'.
        """
        now = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT *
                    FROM instance_billing
                    WHERE instance_id = $1
                    FOR UPDATE
                    """,
                    instance_id
                )

                if not row:
                    # Нет записи биллинга — считаем это ошибкой конфигурации.
                    return False, "no_billing"

                period_end = row["period_end"]
                tickets_used = row["tickets_used"]
                tickets_limit = row["tickets_limit"]

                if now > period_end:
                    await conn.execute(
                        """
                        UPDATE instance_billing
                           SET over_limit = TRUE,
                               updated_at = $1
                         WHERE instance_id = $2
                        """,
                        now,
                        instance_id
                    )
                    return False, "expired"

                if tickets_used >= tickets_limit:
                    await conn.execute(
                        """
                        UPDATE instance_billing
                           SET over_limit = TRUE,
                               updated_at = $1
                         WHERE instance_id = $2
                        """,
                        now,
                        instance_id
                    )
                    return False, "limit_reached"

                await conn.execute(
                    """
                    UPDATE instance_billing
                       SET tickets_used = tickets_used + 1,
                           updated_at   = $1
                     WHERE instance_id = $2
                    """,
                    now,
                    instance_id
                )
        return True, None

    async def ensure_default_plans(self) -> None:
        """
        Создаёт базовые планы Demo/Lite/Pro/Enterprise, если их нет,
        и под них товары billing_products для оплаты Stars.
        Demo: 7 дней, 0 Stars, небольшой лимит тикетов.
        Остальные: 30 дней, разные лимиты и цены.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # --- планы ---
                rows = await conn.fetch("SELECT code FROM saas_plans")
                existing = {row["code"] for row in rows}

                plans_to_insert = []

                if "demo" not in existing:
                    plans_to_insert.append(
                        ("Demo", "demo", 0, 7, 30, {"can_openchat": False, "branding": False})
                    )
                if "lite" not in existing:
                    plans_to_insert.append(
                        ("Lite", "lite", 300, 30, 200, {"can_openchat": True, "branding": False})
                    )
                if "pro" not in existing:
                    plans_to_insert.append(
                        ("Pro", "pro", 800, 30, 1000, {"can_openchat": True, "branding": True})
                    )
                if "enterprise" not in existing:
                    plans_to_insert.append(
                        ("Enterprise", "enterprise", 2500, 30, 100000, {"can_openchat": True, "branding": True})
                    )

                for name, code, price_stars, period_days, tickets_limit, features_json in plans_to_insert:
                    features_json_str = json.dumps(features_json)
                    await conn.execute(
                        """
                        INSERT INTO saas_plans (name, code, price_stars, period_days, tickets_limit, features_json)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        (name, code, price_stars, period_days, tickets_limit, features_json_str),
                    )

                # --- товары под планы (кроме demo) ---
                # читаем актуальные планы
                plans = await conn.fetch(
                    "SELECT plan_id, code, name, price_stars, period_days FROM saas_plans"
                )

                # уже существующие продукты
                try:
                    rows = await conn.fetch("SELECT code FROM billing_products")
                    existing_products = {row["code"] for row in rows}
                except asyncpg.UndefinedTableError:
                    # если миграция ещё не прогнана и таблицы нет
                    return

                products_to_insert = []
                for row in plans:
                    plan_code = row["code"]
                    if plan_code == "demo":
                        continue  # demo не продаём как товар
                    product_code = f"plan_{plan_code}_{row['period_days']}d"
                    if product_code in existing_products:
                        continue

                    products_to_insert.append(
                        (
                            product_code,
                            row["plan_id"],
                            row["name"],
                            f"{row['name']} – {row['period_days']} дней доступа",
                            row["price_stars"],
                        )
                    )

                for code, plan_id, title, description, amount_stars in products_to_insert:
                    await conn.execute(
                        """
                        INSERT INTO billing_products (code, plan_id, title, description, amount_stars)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        (code, plan_id, title, description, amount_stars),
                    )

    async def update_saas_plan_price_stars(self, plancode: str, price_stars: int) -> None:
        code = (plancode or "").strip().lower()
        if code not in ("lite", "pro", "enterprise", "demo"):
            raise ValueError(f"Unsupported plancode for Stars price update: {plancode}")

        try:
            price = int(price_stars)
        except Exception:
            raise ValueError(f"Invalid price_stars: {price_stars}")

        if price < 0:
            raise ValueError("price_stars must be >= 0")

        await self.execute(
            """
            UPDATE saas_plans
            SET price_stars = $1,
                updated_at = NOW()
            WHERE code = $2
            """,
            (price, code),
        )

    async def sync_billing_product_amount_from_plan(self, plancode: str) -> None:
        code = (plancode or "").strip().lower()
        if code not in ("lite", "pro", "enterprise", "demo"):
            raise ValueError(f"Unsupported plancode for billing product sync: {plancode}")

        await self.execute(
            """
            UPDATE billing_products AS bp
            SET amount_stars = sp.price_stars,
                updated_at = NOW()
            FROM saas_plans AS sp
            WHERE bp.plan_id = sp.plan_id
                AND sp.code = $1
                AND bp.is_active = TRUE
            """,
            (code,),
        )


    async def ensure_default_billing(self, instance_id: str) -> None:
        """
        Гарантирует, что для инстанса есть запись instance_billing.
        По умолчанию выдаёт Demo-план на 7 дней с его лимитами.
        """
        now = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # уже есть биллинг — ничего не делаем
                row = await conn.fetchrow(
                    "SELECT 1 FROM instance_billing WHERE instance_id = $1",
                    *(instance_id,)
                )
                if row:
                    return

                # ищем demo-план
                row = await conn.fetchrow(
                    "SELECT plan_id, period_days, tickets_limit FROM saas_plans WHERE code = $1",
                    *("demo",)
                )
                if not row:
                    logger.error("ensure_default_billing: demo plan not found, instance_id=%s", instance_id)
                    return

                plan_id = row["plan_id"]
                period_days = row["period_days"]
                tickets_limit = row["tickets_limit"]

                period_start = now
                period_end = now + timedelta(days=period_days)

                await conn.execute(
                    """
                    INSERT INTO instance_billing (
                        instance_id,
                        plan_id,
                        period_start,
                        period_end,
                        tickets_used,
                        tickets_limit,
                        over_limit,
                        last_expiring_notice_date,
                        last_paused_notice_at,
                        created_at,
                        updated_at
                    )
                    VALUES ($1, $2, $3, $4, 0, $5, FALSE, NULL, NULL, $6, $7)
                    """,
                    *(
                        instance_id,
                        plan_id,
                        period_start,
                        period_end,
                        tickets_limit,
                        now,
                        now,
                    ),
                )

    # === Row mapping ===

    def row_to_instance(self, row) -> BotInstance:
        return BotInstance(
            instance_id=row["instance_id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
            bot_username=row["bot_username"],
            bot_name=row["bot_name"],
            webhook_url=row["webhook_url"],
            webhook_path=row["webhook_path"],
            webhook_secret=row["webhook_secret"],
            status=InstanceStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error_message=row["error_message"],
            owner_user_id=row.get("owner_user_id"),
            admin_private_chat_id=row.get("admin_private_chat_id"),
        )

    async def get_user_language(self, user_id: int) -> Optional[str]:
        row = await self.fetchone(
            "SELECT language FROM user_states WHERE user_id = $1",
            (user_id,)
        )
        return row["language"] if row and row["language"] is not None else None


    async def set_user_language(self, user_id: int, lang_code: str) -> None:
        """
        Обновляет язык пользователя, не трогая state/data.
        Если записи нет — создаёт с пустым state.
        """
        await self.execute(
            """
            INSERT INTO user_states (user_id, state, data, language, created_at)
            VALUES ($1, '', NULL, $2, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET language = EXCLUDED.language
            """,
            (user_id, lang_code),
        )
