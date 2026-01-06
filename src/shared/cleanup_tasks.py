# src/shared/cleanup_tasks.py
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class QueueCleanupService:
    """Регламентные задачи очистки БД для GraceHub"""
    
    def __init__(self, db):  # db: MasterDatabase
        self.db = db
        self.tasks = []
        self.is_running = False
        
        # Читаем настройки из ENV или используем дефолты
        self.cleanup_interval_hours = int(os.getenv("CLEANUP_INTERVAL_HOURS", "6"))
        self.cleanup_done_days = int(os.getenv("CLEANUP_DONE_DAYS", "7"))
        self.cleanup_dead_days = int(os.getenv("CLEANUP_DEAD_DAYS", "30"))
        self.cleanup_stale_days = int(os.getenv("CLEANUP_STALE_DAYS", "3"))
        self.requeue_stuck_minutes = int(os.getenv("REQUEUE_STUCK_MINUTES", "5"))
        
    async def cleanup_done_updates(self, days: Optional[int] = None) -> int:
        """Удаляет успешно обработанные обновления старше N дней"""
        days = days or self.cleanup_done_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        result = await self.db.execute(
            """
            DELETE FROM tg_update_queue
            WHERE status = 'done'
              AND updated_at < $1
            """,
            (cutoff,)
        )
        # asyncpg execute возвращает строку "DELETE N"
        deleted = int(result.split()[-1]) if result and result.split() else 0
        
        if deleted > 0:
            logger.info(f"🧹 Cleaned {deleted} done updates older than {days}d")
        return deleted
    
    async def cleanup_dead_updates(self, days: Optional[int] = None) -> int:
        """Удаляет мёртвые задачи старше N дней"""
        days = days or self.cleanup_dead_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        result = await self.db.execute(
            """
            DELETE FROM tg_update_queue
            WHERE status = 'dead'
              AND updated_at < $1
            """,
            (cutoff,)
        )
        deleted = int(result.split()[-1]) if result and result.split() else 0
        
        if deleted > 0:
            logger.info(f"🧹 Cleaned {deleted} dead updates older than {days}d")
        return deleted
    
    async def cleanup_stale_pending(self, days: Optional[int] = None) -> int:
        """Удаляет зависшие pending/retry старше N дней"""
        days = days or self.cleanup_stale_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        result = await self.db.execute(
            """
            DELETE FROM tg_update_queue
            WHERE status IN ('pending', 'retry')
              AND created_at < $1
            """,
            (cutoff,)
        )
        deleted = int(result.split()[-1]) if result and result.split() else 0
        
        if deleted > 0:
            logger.info(f"🧹 Cleaned {deleted} stale pending/retry older than {days}d")
        return deleted
    
    async def vacuum_analyze_queue(self):
        """VACUUM ANALYZE для оптимизации таблицы после массовых удалений"""
        try:
            # VACUUM нельзя выполнить в транзакции, поэтому используем отдельное соединение
            async with self.db.pool.acquire() as conn:
                await conn.execute("VACUUM ANALYZE tg_update_queue")
            logger.info("✅ VACUUM ANALYZE tg_update_queue completed")
        except Exception as e:
            logger.warning(f"⚠️ VACUUM failed (non-critical): {e}")
    
    async def get_queue_stats(self) -> dict:
        """Статистика очереди для мониторинга"""
        rows = await self.db.fetchall(
            """
            SELECT 
                status,
                COUNT(*) as count,
                MIN(created_at) as oldest,
                MAX(created_at) as newest
            FROM tg_update_queue
            GROUP BY status
            """
        )
        stats = {row["status"]: dict(row) for row in rows}
        
        # Общее количество
        total = sum(s["count"] for s in stats.values())
        stats["_total"] = total
        
        return stats
    
    async def periodic_cleanup_loop(self):
        """Основной цикл периодической очистки"""
        self.is_running = True
        logger.info(
            f"🚀 Cleanup service started: interval={self.cleanup_interval_hours}h, "
            f"done={self.cleanup_done_days}d, dead={self.cleanup_dead_days}d, "
            f"stale={self.cleanup_stale_days}d"
        )
        
        while self.is_running:
            try:
                logger.info("🔄 Starting periodic queue cleanup cycle")
                
                # Статистика ДО очистки
                stats_before = await self.get_queue_stats()
                logger.info(f"📊 Queue stats BEFORE: {stats_before}")
                
                # 1. Реквей застрявших задач (используем твой существующий метод!)
                stuck_seconds = self.requeue_stuck_minutes * 60
                stuck = await self.db.requeue_stuck_tg_updates(stuck_seconds=stuck_seconds)
                if stuck > 0:
                    logger.info(f"♻️ Requeued {stuck} stuck updates")
                
                await asyncio.sleep(2)
                
                # 2. Очистка done (самое частое)
                deleted_done = await self.cleanup_done_updates()
                await asyncio.sleep(1)
                
                # 3. Очистка stale pending/retry
                deleted_stale = await self.cleanup_stale_pending()
                await asyncio.sleep(1)
                
                # 4. Очистка dead (реже всего)
                deleted_dead = await self.cleanup_dead_updates()
                await asyncio.sleep(1)
                
                # 5. VACUUM только ночью (в 3:00-4:00 UTC) и если удалили много
                total_deleted = deleted_done + deleted_stale + deleted_dead
                current_hour = datetime.now(timezone.utc).hour
                
                if total_deleted > 100 and 3 <= current_hour <= 4:
                    logger.info(f"🧹 Running VACUUM (deleted {total_deleted} rows)")
                    await self.vacuum_analyze_queue()
                
                # Статистика ПОСЛЕ очистки
                stats_after = await self.get_queue_stats()
                logger.info(f"📊 Queue stats AFTER: {stats_after}")
                
                logger.info(
                    f"✅ Cleanup cycle completed: "
                    f"requeued={stuck}, deleted={total_deleted} "
                    f"(done={deleted_done}, stale={deleted_stale}, dead={deleted_dead})"
                )
                logger.info(f"😴 Sleeping for {self.cleanup_interval_hours}h until next cycle")
                
                await asyncio.sleep(self.cleanup_interval_hours * 3600)
                
            except Exception as e:
                logger.error(f"❌ Cleanup cycle error: {e}", exc_info=True)
                logger.info("⏳ Retrying in 5 minutes after error...")
                await asyncio.sleep(300)  # При ошибке ждём 5 минут
    
    def start(self):
        """Запускает фоновую задачу очистки"""
        if self.tasks:
            logger.warning("⚠️ Cleanup service already started")
            return
        
        task = asyncio.create_task(self.periodic_cleanup_loop())
        self.tasks.append(task)
        return task
    
    async def stop(self):
        """Останавливает все фоновые задачи"""
        logger.info("🛑 Stopping cleanup service...")
        self.is_running = False
        
        for task in self.tasks:
            task.cancel()
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        logger.info("✅ Cleanup service stopped")
