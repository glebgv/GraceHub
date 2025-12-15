# src/shared/database.py
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Any, Dict, Tuple

import psycopg2
import psycopg2.extras
from cryptography.fernet import Fernet

from .models import BotInstance, InstanceStatus
from . import settings

logger = logging.getLogger(__name__)


def get_master_dsn() -> str:
    """
    Возвращает DSN для master-БД.
    Обязательно должен быть задан env DATABASE_URL (postgresql://...).
    """
    env_dsn = os.getenv("DATABASE_URL")
    if env_dsn:
        return env_dsn

    raise RuntimeError(
        "DATABASE_URL не задан. Укажи DATABASE_URL=postgresql://user:pass@host:port/dbname"
    )


class MasterDatabase:
    """
    Master DB на PostgreSQL.
    - Подключение через psycopg2.
    - Шифрование токенов через Fernet, ключ хранится в settings.ENCRYPTION_KEY_FILE.
    """

    def __init__(self, dsn: Optional[str] = None):
        self.dsn: str = dsn or get_master_dsn()
        self.conn: Optional[psycopg2.extensions.connection] = None
        self.cipher: Optional[Fernet] = None

    async def init(self) -> None:
        """
        Полная инициализация: проверка DSN, создание sync‑коннекта,
        настройка шифрования и создание таблиц.
        Вызывать один раз при старте мастера или воркера.
        """
        if not self.dsn.startswith("postgresql://"):
            raise RuntimeError(
                "SQLite больше не поддерживается для master DB. "
                "Задай env DATABASE_URL=postgresql://..."
            )

        self.conn = psycopg2.connect(self.dsn)
        self.conn.autocommit = False
        self.conn.cursor_factory = psycopg2.extras.DictCursor

        key = self.get_or_create_encryption_key()
        self.cipher = Fernet(key)

        await self.create_tables()
        logger.info(f"Master database (Postgres) initialized: {self.dsn}")

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


    async def mark_expiring_notified_today(self, instance_id: str) -> None:
        """
        Помечает, что для инстанса сегодня уже отправлено напоминание о скором окончании.
        """
        await self.execute(
            """
            UPDATE instance_billing
               SET last_expiring_notice_date = CURRENT_DATE,
                   updated_at = NOW()
             WHERE instance_id = %s
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
             WHERE instance_id = %s
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
                updatedat AS updated_at,    
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
        assert self.conn is not None

        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
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
                WHERE bi.instance_id = %s
                LIMIT 1
                """,
                (instance_id,),
            )
            row = cur.fetchone()

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

        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
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
            meta = cur.fetchone()

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
                telegram_invoice_id = %s,
                stars_amount = %s,
                currency = %s,
                paid_at = NOW(),
                updated_at = NOW()
            WHERE invoice_id = %s
            """,
            (telegram_invoice_id, total_amount, currency, invoice_id),
        )

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
            WHERE sp.code = %s
            LIMIT 1
            """,
            (plan_code,),
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
            WHERE bi.invoice_id = %s
            """,
            (invoice_id,),
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
                %(instance_id)s,
                %(plan_id)s,
                NOW(),
                NOW() + (%(period_days)s || ' days')::interval,
                0,
                %(tickets_limit)s,
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
                                THEN instance_billing.period_end + (%(period_days)s || ' days')::interval
                                ELSE NOW() + (%(period_days)s || ' days')::interval
                            END,
                tickets_used = 0,
                tickets_limit = EXCLUDED.tickets_limit,
                over_limit = FALSE,
                -- при новом периоде очищаем отметки уведомлений
                last_expiring_notice_date = NULL,
                last_paused_notice_at     = NULL,
                updated_at = NOW()
            """,
            {
                "instance_id": instance_id,
                "plan_id": plan_id,
                "period_days": period_days,
                "tickets_limit": tickets_limit,
            },
        )

        logger.info(
            "apply_saas_plan_for_invoice: instance=%s plan=%s +%s days",
            instance_id,
            data["plan_code"],
            period_days,
        )


    async def create_tables(self) -> None:
        assert self.conn is not None
        cur = self.conn.cursor()

        # bot_instances
        cur.execute(
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
                updatedat               TIMESTAMPTZ,
                error_message           TEXT,
                owner_user_id           BIGINT,
                admin_private_chat_id   BIGINT
            )
            """
        )

        # encrypted_tokens
        cur.execute(
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
        cur.execute(
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
        cur.execute(
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

        # usage_stats
        cur.execute(
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

        # Индексы
        cur.execute("CREATE INDEX IF NOT EXISTS idx_instances_user   ON bot_instances(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_instances_status ON bot_instances(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_time ON rate_limits(last_request)")

        # Таблицы mini app
        self._create_miniapp_tables(cur)

        # Таблицы worker (перенос с SQLite)
        self._create_worker_tables(cur)

        # Таблицы биллинга SaaS
        self._create_billing_tables(cur)

        self.conn.commit()

        # Сидим дефолтные тарифы (Demo/Lite/Pro/Enterprise)
        await self.ensure_default_plans()
        self.conn.commit()
        logger.info(
            "Master database tables initialized (Postgres, including miniapp, worker and billing tables)"
        )

    def _create_miniapp_tables(self, cur) -> None:
        # users
        cur.execute(
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
        cur.execute(
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
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_instance_members_user
            ON instance_members(user_id)
            """
        )

        # instance_meta
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS instance_meta (
                instance_id                 TEXT PRIMARY KEY,
                openchat_username           TEXT,
                general_panel_chat_id       BIGINT,
                auto_close_hours            INTEGER,
                auto_reply_greeting         TEXT,
                auto_reply_default_answer   TEXT,
                branding_bot_name           TEXT,
                openchat_enabled            BOOLEAN,
                language                    TEXT,
                updated_at                  TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT fk_meta_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # instance_ticket_stats
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS instance_ticket_stats (
                instance_id               TEXT NOT NULL,
                date                      DATE NOT NULL,
                new                       INTEGER DEFAULT 0,
                inprogress                INTEGER DEFAULT 0,
                answered                  INTEGER DEFAULT 0,
                closed                    INTEGER DEFAULT 0,
                spam                      INTEGER DEFAULT 0,
                avg_first_response_sec    REAL DEFAULT 0,
                unique_users              INTEGER DEFAULT 0,
                updated_at                TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (instance_id, date),
                CONSTRAINT fk_ticket_stats_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

    def _create_worker_tables(self, cur) -> None:
        """
        Worker-часть, перенесённая из SQLite в Postgres.
        Все таблицы содержат instance_id.
        """

        # settings (per-instance key-value)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_settings (
                instance_id TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT,
                PRIMARY KEY (instance_id, key),
                CONSTRAINT fk_worker_settings_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # tickets
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                instance_id          TEXT        NOT NULL,
                id                   BIGSERIAL   NOT NULL,
                user_id              BIGINT      NOT NULL,
                username             TEXT,
                chat_id              BIGINT      NOT NULL,
                status               TEXT        NOT NULL DEFAULT 'new',
                thread_id            BIGINT,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_user_msg_at     TIMESTAMPTZ,
                last_admin_reply_at  TIMESTAMPTZ,
                closed_at            TIMESTAMPTZ,
                assigned_username    TEXT,
                assigned_user_id     BIGINT,
                PRIMARY KEY (instance_id, id),
                CONSTRAINT fk_tickets_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tickets_status
            ON tickets(instance_id, status)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tickets_thread
            ON tickets(instance_id, chat_id, thread_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tickets_user_unique
            ON tickets(instance_id, user_id)
            """
        )

        # messages
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                instance_id  TEXT        NOT NULL,
                id           BIGSERIAL   NOT NULL,
                chat_id      BIGINT      NOT NULL,
                message_id   BIGINT      NOT NULL,
                user_id      BIGINT,
                direction    TEXT        NOT NULL,
                content      TEXT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (instance_id, id),
                CONSTRAINT fk_messages_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # user_states (worker)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_user_states (
                instance_id  TEXT        NOT NULL,
                user_id      BIGINT      NOT NULL,
                state        TEXT        NOT NULL,
                data         TEXT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (instance_id, user_id),
                CONSTRAINT fk_worker_states_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # admin_reply_map_v2
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_reply_map_v2 (
                instance_id      TEXT        NOT NULL,
                chat_id          BIGINT      NOT NULL,
                admin_message_id BIGINT      NOT NULL,
                target_user_id   BIGINT      NOT NULL,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (instance_id, chat_id, admin_message_id),
                CONSTRAINT fk_admin_reply_map_v2_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # admin_reply_map (legacy)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_reply_map (
                instance_id      TEXT        NOT NULL,
                admin_message_id BIGINT      NOT NULL,
                target_user_id   BIGINT      NOT NULL,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (instance_id, admin_message_id),
                CONSTRAINT fk_admin_reply_map_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # autoreply_log
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS autoreply_log (
                instance_id TEXT NOT NULL,
                user_id     BIGINT NOT NULL,
                date        DATE   NOT NULL,
                PRIMARY KEY (instance_id, user_id, date),
                CONSTRAINT fk_autoreply_log_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # blacklist
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS blacklist (
                instance_id TEXT     NOT NULL,
                user_id     BIGINT   NOT NULL,
                username    TEXT,
                added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (instance_id, user_id),
                CONSTRAINT fk_blacklist_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        # greetings
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS greetings (
                instance_id TEXT NOT NULL,
                id          BIGSERIAL PRIMARY KEY,
                type        TEXT,
                file_id     TEXT,
                text        TEXT,
                CONSTRAINT fk_greetings_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

    def _create_billing_tables(self, cur) -> None:
        """
        Таблицы биллинга SaaS: тарифные планы и состояние биллинга инстансов.
        """
        # saas_plans: тарифные планы
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS saas_plans (
                plan_id       SERIAL PRIMARY KEY,
                name          TEXT NOT NULL,
                code          TEXT NOT NULL UNIQUE, -- demo, lite, pro, enterprise
                price_stars   INTEGER NOT NULL,    -- стоимость за период в Stars
                period_days   INTEGER NOT NULL,    -- длина биллингового периода
                tickets_limit INTEGER NOT NULL,    -- лимит тикетов на период
                features_json JSONB,
                is_active     BOOLEAN NOT NULL DEFAULT TRUE,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        # instance_billing: состояние биллинга для инстанса
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS instance_billing (
                instance_id                 TEXT PRIMARY KEY,
                plan_id                     INTEGER NOT NULL
                    REFERENCES saas_plans(plan_id)
                    ON DELETE RESTRICT,
                period_start               TIMESTAMPTZ NOT NULL,
                period_end                 TIMESTAMPTZ NOT NULL,
                tickets_used               INTEGER NOT NULL DEFAULT 0,
                tickets_limit              INTEGER NOT NULL,
                last_billed_at             TIMESTAMPTZ,
                over_limit                 BOOLEAN NOT NULL DEFAULT FALSE,
                days_left                  INTEGER NOT NULL DEFAULT 0,
                service_paused             BOOLEAN NOT NULL DEFAULT FALSE,
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

        # billing_products: что именно продаём за Stars
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS billing_products (
                product_id     SERIAL PRIMARY KEY,
                code           TEXT NOT NULL UNIQUE, -- например: plan_lite_30d
                plan_id        INTEGER NOT NULL
                    REFERENCES saas_plans(plan_id)
                    ON DELETE RESTRICT,
                title          TEXT NOT NULL,
                description    TEXT,
                amount_stars   INTEGER NOT NULL,   -- стоимость в XTR (целое)
                is_active      BOOLEAN NOT NULL DEFAULT TRUE,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        # billing_invoices: сессии оплаты через Telegram Stars
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS billing_invoices (
                invoice_id          BIGSERIAL PRIMARY KEY,
                instance_id         TEXT NOT NULL,
                user_id             BIGINT,              -- кто платит (Telegram user_id)
                product_id          INTEGER NOT NULL
                    REFERENCES billing_products(product_id)
                    ON DELETE RESTRICT,
                payload             TEXT NOT NULL,       -- то, что передаём в createInvoiceLink
                telegram_invoice_id TEXT,                -- если будешь сохранять id из успешного платежа
                invoice_link        TEXT,                -- URL вида https://t.me/...
                stars_amount        INTEGER NOT NULL,
                currency            TEXT NOT NULL DEFAULT 'XTR',
                status              TEXT NOT NULL DEFAULT 'pending', -- pending/paid/expired/canceled/failed
                error_code          TEXT,
                error_message       TEXT,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                paid_at             TIMESTAMPTZ,
                CONSTRAINT fk_billing_invoices_instance
                    FOREIGN KEY (instance_id)
                    REFERENCES bot_instances(instance_id)
                    ON DELETE CASCADE
            )
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_billing_invoices_instance
            ON billing_invoices(instance_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_billing_invoices_status
            ON billing_invoices(status)
            """
        )

        # billing_transactions: что произошло с биллингом по факту (продление, списание и т.п.)
        cur.execute(
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

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_billing_tx_instance
            ON billing_transactions(instance_id)
            """
        )

    

    # === Thin async wrappers for miniapp_api and worker ===

    async def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(sql, params or ())
        self.conn.commit()

    async def fetchone(self, sql: str, params: Optional[tuple] = None):
        assert self.conn is not None
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()

    async def fetchall(self, sql: str, params: Optional[tuple] = None):
        assert self.conn is not None
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()

    # === Instance CRUD ===

    async def create_instance(self, instance: BotInstance) -> None:
        """
        Создаёт инстанс и сразу вешает Demo-план на 7 дней (если ещё не создан billing).
        """
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
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
        self.conn.commit()

    async def delete_instance(self, instance_id: str) -> None:
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM bot_instances WHERE instance_id = %s", (instance_id,))
        self.conn.commit()


    async def update_billing_invoice_link_and_payload(
        self,
        invoice_id: int,
        payload: str,
        invoice_link: str,
    ) -> None:
        await self.execute(
            """
            UPDATE billing_invoices
            SET payload = %s,
                invoice_link = %s,
                updated_at = NOW()
            WHERE invoice_id = %s
            """,
            (payload, invoice_link, invoice_id),
        )

    async def insert_billing_invoice(
        self,
        instance_id: str,
        user_id: int,
        plan_code: str,      # можно не использовать, но оставим для совместимости
        periods: int,
        amount_stars: int,
        product_code: str,
        payload: str,
        invoice_link: str,
        status: str = "pending",
    ) -> int:
        # product_code = billing_products.code → достаём product_id
        product_row = await self.fetchone(
            """
            SELECT product_id
            FROM billing_products
            WHERE code = %s
            LIMIT 1
            """,
            (product_code,),
        )
        if not product_row:
            raise ValueError(f"Unknown billing product_code={product_code}")

        product_id = product_row["product_id"]

        row = await self.fetchone(
            """
            INSERT INTO billing_invoices (
                instance_id,
                user_id,
                product_id,
                payload,
                telegram_invoice_id,
                invoice_link,
                stars_amount,
                currency,
                status
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING invoice_id
            """,
            (
                instance_id,
                user_id,
                product_id,
                payload,
                None,             
                invoice_link,
                amount_stars,     
                "XTR",
                status,
            ),
        )
        return row["invoice_id"]


    async def get_instance(self, instance_id: str) -> Optional[BotInstance]:
        assert self.conn is not None
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM bot_instances WHERE instance_id = %s", (instance_id,))
            row = cur.fetchone()
        if not row:
            return None
        return self.row_to_instance(row)

    async def get_instance_by_token_hash(self, token_hash: str) -> Optional[BotInstance]:
        assert self.conn is not None
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM bot_instances WHERE token_hash = %s", (token_hash,))
            row = cur.fetchone()
        if not row:
            return None
        return self.row_to_instance(row)

    async def get_user_instances(self, user_id: int) -> List[BotInstance]:
        assert self.conn is not None
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT * FROM bot_instances WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
            rows = cur.fetchall()
        return [self.row_to_instance(r) for r in rows]

    async def get_user_instances_with_meta(
        self, user_id: int
    ) -> List[Dict[str, Any]]:
        assert self.conn is not None
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
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
            rows = cur.fetchall()

        result: List[Dict[str, Any]] = []
        for row in rows:
            inst = dict(row)
            inst["role"] = "owner"
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
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
                meta = cur.fetchone()
            if meta:
                inst.update(dict(meta))
            result.append(inst)

        return result

    async def get_instance_with_meta_by_id(self, instance_id: str) -> Optional[Dict[str, Any]]:
        assert self.conn is not None
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
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
                WHERE bi.instance_id = %s
                LIMIT 1
                """,
                (instance_id,),
            )
            row = cur.fetchone()

        if not row:
            return None

        inst = dict(row)

        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
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
            meta = cur.fetchone()

        if meta:
            inst.update(dict(meta))

        inst["role"] = "owner"
        return inst


    async def get_all_active_instances(self) -> List[BotInstance]:
        assert self.conn is not None
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM bot_instances
                 WHERE status IN (%s, %s)
                 ORDER BY created_at
                """,
                (InstanceStatus.RUNNING.value, InstanceStatus.STARTING.value),
            )
            rows = cur.fetchall()
        return [self.row_to_instance(r) for r in rows]

    async def update_instance_status(
        self,
        instance_id: str,
        status: InstanceStatus,
        error_message: Optional[str] = None,
    ) -> None:
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE bot_instances
                   SET status = %s, updatedat = %s, error_message = %s
                 WHERE instance_id = %s
                """,
                (
                    status.value if hasattr(status, "value") else str(status),
                    datetime.now(timezone.utc),
                    error_message,
                    instance_id,
                ),
            )
        self.conn.commit()

    # === Token storage ===

    async def store_encrypted_token(self, instance_id: str, token: str) -> None:
        assert self.conn is not None
        assert self.cipher is not None
        encrypted = self.cipher.encrypt(token.encode("utf-8"))
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO encrypted_tokens (instance_id, encrypted_token)
                VALUES (%s, %s)
                ON CONFLICT (instance_id)
                DO UPDATE SET encrypted_token = EXCLUDED.encrypted_token
                """,
                (instance_id, psycopg2.Binary(encrypted)),
            )
        self.conn.commit()

    async def get_decrypted_token(self, instance_id: str) -> Optional[str]:
        assert self.conn is not None
        assert self.cipher is not None
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT encrypted_token FROM encrypted_tokens WHERE instance_id = %s",
                (instance_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        try:
            return self.cipher.decrypt(bytes(row[0])).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to decrypt token for {instance_id}: {e}")
            return None

    # === User state helpers (для master UI) ===

    async def set_user_state(self, user_id: int, state: str, data: Optional[str] = None) -> None:
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_states (user_id, state, data)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data
                """,
                (user_id, state, data),
            )
        self.conn.commit()
        logger.info("set_user_state: user_id=%s, state=%s", user_id, state)

    async def get_user_state(self, user_id: int) -> Optional[str]:
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT state FROM user_states WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        logger.info("get_user_state: user_id=%s, state=%s", user_id, row[0] if row else None)
        return row[0] if row else None

    async def clear_user_state(self, user_id: int) -> None:
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM user_states WHERE user_id = %s", (user_id,))
        self.conn.commit()

    # === Worker helpers ===

    async def worker_set_user_state(
        self,
        instance_id: str,
        user_id: int,
        state: str,
        data: Optional[str] = None,
    ) -> None:
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO worker_user_states (instance_id, user_id, state, data)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (instance_id, user_id)
                DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data
                """,
                (instance_id, user_id, state, data),
            )
        self.conn.commit()

    # === Billing helpers ===

    async def get_instance_billing(self, instance_id: str) -> Optional[dict]:
        """
        Возвращает запись instance_billing для инстанса или None.
        Включает поля:
        - period_start / period_end / days_left / service_paused
        - tickets_used / tickets_limit / over_limit
        - last_expiring_notice_date / last_paused_notice_at
        """
        assert self.conn is not None
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM instance_billing
                WHERE instance_id = %s
                """,
                (instance_id,),
            )
            row = cur.fetchone()
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
            WHERE plan_id = %s
            LIMIT 1
            """,
            (plan_id,),
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
        assert self.conn is not None
        now = datetime.now(timezone.utc)

        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM instance_billing
                WHERE instance_id = %s
                FOR UPDATE
                """,
                (instance_id,),
            )
            row = cur.fetchone()

            if not row:
                # Нет записи биллинга — считаем это ошибкой конфигурации.
                return False, "no_billing"

            period_end = row["period_end"]
            tickets_used = row["tickets_used"]
            tickets_limit = row["tickets_limit"]

            if now > period_end:
                cur.execute(
                    """
                    UPDATE instance_billing
                       SET over_limit = TRUE,
                           updated_at = %s
                     WHERE instance_id = %s
                    """,
                    (now, instance_id),
                )
                self.conn.commit()
                return False, "expired"

            if tickets_used >= tickets_limit:
                cur.execute(
                    """
                    UPDATE instance_billing
                       SET over_limit = TRUE,
                           updated_at = %s
                     WHERE instance_id = %s
                    """,
                    (now, instance_id),
                )
                self.conn.commit()
                return False, "limit_reached"

            cur.execute(
                """
                UPDATE instance_billing
                   SET tickets_used = tickets_used + 1,
                       updated_at   = %s
                 WHERE instance_id = %s
                """,
                (now, instance_id),
            )
        self.conn.commit()
        return True, None

    async def ensure_default_plans(self) -> None:
        """
        Создаёт базовые планы Demo/Lite/Pro/Enterprise, если их нет,
        и под них товары billing_products для оплаты Stars.
        Demo: 7 дней, 0 Stars, небольшой лимит тикетов.
        Остальные: 30 дней, разные лимиты и цены.
        """
        assert self.conn is not None
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # --- планы ---
            cur.execute("SELECT code FROM saas_plans")
            existing = {row["code"] for row in cur.fetchall()}

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
                cur.execute(
                    """
                    INSERT INTO saas_plans (name, code, price_stars, period_days, tickets_limit, features_json)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (name, code, price_stars, period_days, tickets_limit,
                     psycopg2.extras.Json(features_json)),
                )

            # --- товары под планы (кроме demo) ---
            # читаем актуальные планы
            cur.execute(
                "SELECT plan_id, code, name, price_stars, period_days FROM saas_plans"
            )
            plans = cur.fetchall()

            # уже существующие продукты
            try:
                cur.execute("SELECT code FROM billing_products")
                existing_products = {row["code"] for row in cur.fetchall()}
            except psycopg2.errors.UndefinedTable:
                # если миграция ещё не прогнана и таблицы нет
                self.conn.rollback()
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
                cur.execute(
                    """
                    INSERT INTO billing_products (code, plan_id, title, description, amount_stars)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (code, plan_id, title, description, amount_stars),
                )


    async def ensure_default_billing(self, instance_id: str) -> None:
        """
        Гарантирует, что для инстанса есть запись instance_billing.
        По умолчанию выдаёт Demo-план на 7 дней с его лимитами.
        """
        assert self.conn is not None
        now = datetime.now(timezone.utc)

        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # уже есть биллинг — ничего не делаем
            cur.execute(
                "SELECT 1 FROM instance_billing WHERE instance_id = %s",
                (instance_id,),
            )
            if cur.fetchone():
                return

            # ищем demo-план
            cur.execute(
                "SELECT plan_id, period_days, tickets_limit FROM saas_plans WHERE code = %s",
                ("demo",),
            )
            row = cur.fetchone()
            if not row:
                logger.error("ensure_default_billing: demo plan not found, instance_id=%s", instance_id)
                return

            plan_id = row["plan_id"]
            period_days = row["period_days"]
            tickets_limit = row["tickets_limit"]

            period_start = now
            period_end = now + timedelta(days=period_days)

            cur.execute(
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
                VALUES (%s, %s, %s, %s, 0, %s, FALSE, NULL, NULL, %s, %s)
                """,
                (
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
            updated_at=row["updatedat"],
            error_message=row["error_message"],
            owner_user_id=row.get("owner_user_id"),
            admin_private_chat_id=row.get("admin_private_chat_id"),
        )

    async def get_user_language(self, user_id: int) -> Optional[str]:
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT language FROM user_states WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        return row[0] if row and row[0] is not None else None

    async def set_user_language(self, user_id: int, lang_code: str) -> None:
        """
        Обновляет язык пользователя, не трогая state/data.
        Если записи нет — создаёт с пустым state.
        """
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_states (user_id, state, data, language)
                VALUES (%s, COALESCE(
                           (SELECT state FROM user_states WHERE user_id = %s),
                           ''
                       ),
                        COALESCE(
                           (SELECT data FROM user_states WHERE user_id = %s),
                           NULL
                       ),
                        %s)
                ON CONFLICT (user_id)
                DO UPDATE SET language = EXCLUDED.language
                """,
                (user_id, user_id, user_id, lang_code),
            )
        self.conn.commit()


class WorkerDatabase:
    """
    Stub-класс для обратной совместимости.
    Вся логика перенесена в MasterDatabase/worker-таблицы Postgres.
    Новые воркеры должны напрямую использовать MasterDatabase.
    """

    def __init__(self, dbpath: str):
        raise RuntimeError(
            "WorkerDatabase на SQLite больше не поддерживается. "
            "Используй MasterDatabase и worker-таблицы в Postgres."
        )
