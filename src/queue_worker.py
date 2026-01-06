# src/worker/queue_worker.py
import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
from typing import Dict, Optional

from aiogram.types import Update

from shared.database import MasterDatabase, get_master_dsn
from shared.cleanup_tasks import QueueCleanupService
from worker.main import GraceHubWorker

logger = logging.getLogger("queue_worker")


def _get_int_env(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        logger.warning("Invalid int env %s=%r, using default=%s", name, v, default)
        return default


def _get_float_env(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return float(v)
    except ValueError:
        logger.warning("Invalid float env %s=%r, using default=%s", name, v, default)
        return default


def _worker_id() -> str:
    # удобно видеть, какой процесс залочил job
    return os.getenv("QUEUE_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"


async def _get_or_create_worker(
    cache: Dict[str, GraceHubWorker],
    db: MasterDatabase,
    instance_id: str,
) -> Optional[GraceHubWorker]:
    """
    Получает или создаёт worker для instance_id.
    Возвращает None, если токен отсутствует или инициализация провалилась.
    """
    w = cache.get(instance_id)
    if w:
        return w

    token = await db.get_decrypted_token(instance_id)
    if not token:
        logger.warning(f"No token found for instance {instance_id}")
        return None

    # ❗ ВАЖНО: правильный порядок аргументов GraceHubWorker(instance_id, db, token=...)
    w = GraceHubWorker(instance_id=instance_id, db=db, token=token)

    try:
        await w.initialize()
        logger.info(f"✅ Worker {instance_id} initialized successfully (bot: {w.bot_username})")
    except Exception as e:
        logger.error(
            f"❌ Failed to initialize worker {instance_id}: {type(e).__name__}: {e}",
            exc_info=True
        )
        return None

    cache[instance_id] = w
    return w


async def stuck_requeue_loop(
    db: MasterDatabase,
    *,
    stuck_seconds: int,
    interval_seconds: int,
) -> None:
    """
    Перекидывает зависшие jobs из status=processing обратно в retry.
    Это must-have, иначе после крэша воркера job может остаться processing навсегда.
    
    ⚠️ DEPRECATED: Эта функция оставлена для обратной совместимости,
    но теперь реквей выполняется через QueueCleanupService.
    """
    logger.warning(
        "⚠️ stuck_requeue_loop is DEPRECATED - requeue now handled by QueueCleanupService"
    )
    while True:
        try:
            n = await db.requeue_stuck_tg_updates(stuck_seconds=stuck_seconds)
            if n:
                logger.warning("Requeued stuck tg updates: %s", n)
        except Exception:
            logger.exception("stuck_requeue_loop failed")
        await asyncio.sleep(interval_seconds)


async def run_worker() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s pid=%(process)d %(name)s %(levelname)s - %(message)s",
    )

    dsn = get_master_dsn()
    db = MasterDatabase(dsn=dsn)
    await db.init()

    wid = _worker_id()
    logger.info("Queue worker started worker_id=%s", wid)

    # env-config
    idle_sleep = _get_float_env("QUEUE_WORKER_IDLE_SLEEP", 0.2)

    # 🔥 НОВАЯ СИСТЕМА ОЧИСТКИ через QueueCleanupService
    cleanup_enabled = os.getenv("QUEUE_CLEANUP_ENABLED", "1").strip().lower() not in ("0", "false", "no")
    
    # Старая система реквея (оставлена для совместимости, но можно отключить)
    requeue_enabled = os.getenv("QUEUE_REQUEUE_ENABLED", "0").strip().lower() not in ("0", "false", "no")
    stuck_seconds = _get_int_env("QUEUE_REQUEUE_STUCK_SECONDS", 600)
    requeue_interval = _get_int_env("QUEUE_REQUEUE_INTERVAL_SECONDS", 30)

    fail_max_attempts = _get_int_env("QUEUE_FAIL_MAX_ATTEMPTS", 10)
    fail_retry_seconds = _get_int_env("QUEUE_FAIL_RETRY_SECONDS", 5)

    no_token_max_attempts = _get_int_env("QUEUE_NO_TOKEN_MAX_ATTEMPTS", 1)
    no_token_retry_seconds = _get_int_env("QUEUE_NO_TOKEN_RETRY_SECONDS", 0)

    cache: Dict[str, GraceHubWorker] = {}

    # 🔥 ЗАПУСКАЕМ НОВЫЙ СЕРВИС ОЧИСТКИ (рекомендуется)
    cleanup_service = None
    if cleanup_enabled:
        cleanup_service = QueueCleanupService(db)
        cleanup_service.start()
        logger.info("✅ QueueCleanupService started (handles requeue + cleanup)")
    else:
        logger.warning("⚠️ QueueCleanupService disabled via QUEUE_CLEANUP_ENABLED=0")

    # Старый реквей-луп (deprecated, но оставлен для миграции)
    if requeue_enabled and not cleanup_enabled:
        asyncio.create_task(
            stuck_requeue_loop(
                db,
                stuck_seconds=stuck_seconds,
                interval_seconds=requeue_interval,
            )
        )
        logger.info(
            "⚠️ Using deprecated stuck_requeue_loop: stuck_seconds=%s interval_seconds=%s",
            stuck_seconds,
            requeue_interval,
        )
        logger.warning("💡 Consider migrating to QUEUE_CLEANUP_ENABLED=1")
    elif requeue_enabled and cleanup_enabled:
        logger.info("ℹ️ QUEUE_REQUEUE_ENABLED ignored (QueueCleanupService active)")

    try:
        while True:
            job = await db.pick_tg_update(worker_id=wid)
            if not job:
                await asyncio.sleep(idle_sleep)
                continue

            job_id = int(job["id"])
            instance_id = job["instance_id"]
            payload = job["payload"]

            try:
                worker = await _get_or_create_worker(cache, db, instance_id)
                if not worker:
                    await db.fail_tg_update(
                        job_id,
                        f"no token for instance_id={instance_id}",
                        max_attempts=no_token_max_attempts,
                        retry_seconds=no_token_retry_seconds,
                    )
                    continue

                if isinstance(payload, str):
                    payload = json.loads(payload)

                update = Update(**payload)
                await worker.process_update(update)

                await db.ack_tg_update(job_id)

            except Exception as e:
                await db.fail_tg_update(
                    job_id,
                    f"{type(e).__name__}: {e}",
                    max_attempts=fail_max_attempts,
                    retry_seconds=fail_retry_seconds,
                )
                logger.exception("Job failed id=%s instance_id=%s", job_id, instance_id)

    except KeyboardInterrupt:
        logger.info("🛑 Received shutdown signal, stopping gracefully...")
    finally:
        # 🔥 GRACEFUL SHUTDOWN для cleanup service
        if cleanup_service:
            logger.info("⏳ Stopping QueueCleanupService...")
            await cleanup_service.stop()
        
        # Закрываем пул БД
        if db.pool:
            await db.pool.close()
            logger.info("✅ Database pool closed")
        
        logger.info("👋 Queue worker shutdown complete")


def run_supervisor() -> None:
    """
    Supervisor-режим: спаунит N воркеров как subprocess.
    Позже это почти 1-в-1 заменится на docker compose --scale.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s pid=%(process)d %(name)s %(levelname)s - %(message)s",
    )

    replicas = _get_int_env("QUEUE_WORKER_REPLICAS", 1)
    replicas = max(1, replicas)

    logger.info("Supervisor starting replicas=%s", replicas)

    procs: list[subprocess.Popen] = []
    for i in range(replicas):
        env = os.environ.copy()
        env["QUEUE_WORKER_MODE"] = "worker"
        # делаем worker_id более читаемым: hostname:pid:idx (pid будет уже дочерний)
        env["QUEUE_WORKER_ID"] = env.get("QUEUE_WORKER_ID") or f"{socket.gethostname()}:replica-{i+1}"

        cmd = [sys.executable, __file__]
        p = subprocess.Popen(cmd, env=env)
        procs.append(p)
        logger.info("Spawned replica %s pid=%s", i + 1, p.pid)

    # Простой "ожидатель": если любой процесс упал — валим supervisor (чтобы ты заметил)
    # При желании можно сделать авто-рестарт.
    try:
        while True:
            for p in procs:
                code = p.poll()
                if code is not None:
                    raise RuntimeError(f"Replica pid={p.pid} exited with code={code}")
            asyncio.run(asyncio.sleep(1.0))
    except KeyboardInterrupt:
        logger.info("Supervisor received KeyboardInterrupt, terminating replicas...")
    finally:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass


def main() -> None:
    mode = os.getenv("QUEUE_WORKER_MODE", "worker").strip().lower()
    if mode == "supervisor":
        run_supervisor()
        return
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
