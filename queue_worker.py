# queue_worker.py
import asyncio
import logging
import json
import os
import socket
from typing import Dict, Optional

from aiogram.types import Update

from shared.database import MasterDatabase, get_master_dsn
from worker.main import GraceHubWorker


logger = logging.getLogger("queue_worker")


def _worker_id() -> str:
    # удобно видеть, какой процесс залочил job
    return os.getenv("QUEUE_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"


async def _get_or_create_worker(
    cache: Dict[str, GraceHubWorker],
    db: MasterDatabase,
    instance_id: str,
) -> Optional[GraceHubWorker]:
    w = cache.get(instance_id)
    if w:
        return w

    token = await db.get_decrypted_token(instance_id)
    if not token:
        return None

    w = GraceHubWorker(instance_id, token, db)

    # важно: у тебя в worker_main есть initialize()/init_database() и т.п.
    # В зависимости от твоей реализации это может называться initialize() или initialize_worker()
    # В твоём файле видно метод initialize(self) [file:4]
    try:
        await w.initialize()
    except AttributeError:
        # если у тебя метод называется иначе, поправишь тут
        pass

    cache[instance_id] = w
    return w


async def run_loop(*, concurrency_sleep: float = 0.2) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s pid=%(process)d %(name)s %(levelname)s - %(message)s",
    )

    dsn = get_master_dsn()
    db = MasterDatabase(dsn=dsn)
    await db.init()

    wid = _worker_id()
    logger.info("Queue worker started worker_id=%s", wid)

    cache: Dict[str, GraceHubWorker] = {}

    while True:
        job = await db.pick_tg_update(worker_id=wid)
        if not job:
            await asyncio.sleep(concurrency_sleep)
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
                    max_attempts="1",
                    retry_seconds="0",
                )
                continue

            # payload может быть json/jsonb (dict) или text (str)
            if isinstance(payload, str):
                payload = json.loads(payload)  # str -> dict [web:216]

            update = Update(**payload)
            await worker.process_update(update)

            await db.ack_tg_update(job_id)

        except Exception as e:
            await db.fail_tg_update(
                job_id,
                f"{type(e).__name__}: {e}",
                max_attempts="10",
                retry_seconds="5",
            )
            logger.exception("Job failed id=%s instance_id=%s", job_id, instance_id)

async def main():
    await run_loop()


if __name__ == "__main__":
    asyncio.run(main())

