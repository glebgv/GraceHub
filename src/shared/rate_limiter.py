import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Dict, Optional

from aiogram import types

from .models import UpdateQueueItem

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket for rate limiting"""

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

    async def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from bucket"""
        async with self.lock:
            now = time.time()

            # Refill tokens
            time_passed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + (time_passed * self.refill_rate))
            self.last_refill = now

            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            return False

    async def wait_for_tokens(self, tokens: int = 1) -> float:
        """Calculate wait time for tokens"""
        async with self.lock:
            if self.tokens >= tokens:
                return 0.0

            needed = tokens - self.tokens
            wait_time = needed / self.refill_rate
            return wait_time


class BotRateLimiter:
    """Rate limiter for individual bot instances"""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token

        # Global bot rate limits (Telegram API limits)
        self.global_bucket = TokenBucket(capacity=30, refill_rate=1.0)  # 30 req/sec

        # Per-chat rate limits
        self.chat_buckets: Dict[int, TokenBucket] = defaultdict(
            lambda: TokenBucket(capacity=20, refill_rate=0.5)  # 20 req/40sec per chat
        )

        # Request history for backoff
        self.error_history = deque(maxlen=100)
        self.backoff_until: Optional[datetime] = None

    async def can_send(self, chat_id: Optional[int] = None) -> bool:
        """Check if we can send a request"""
        # Check global backoff
        if self.backoff_until and datetime.now() < self.backoff_until:
            return False

        # Check global rate limit
        if not await self.global_bucket.consume():
            return False

        # Check per-chat rate limit
        if chat_id and not await self.chat_buckets[chat_id].consume():
            return False

        return True

    async def wait_for_send(self, chat_id: Optional[int] = None) -> float:
        """Calculate wait time before sending"""
        wait_times = []

        # Global backoff
        if self.backoff_until and datetime.now() < self.backoff_until:
            wait_times.append((self.backoff_until - datetime.now()).total_seconds())

        # Global rate limit wait
        global_wait = await self.global_bucket.wait_for_tokens()
        if global_wait > 0:
            wait_times.append(global_wait)

        # Per-chat rate limit wait
        if chat_id:
            chat_wait = await self.chat_buckets[chat_id].wait_for_tokens()
            if chat_wait > 0:
                wait_times.append(chat_wait)

        return max(wait_times) if wait_times else 0.0

    def record_error(self, error_code: int, retry_after: Optional[int] = None):
        """Record API error for backoff calculation"""
        now = datetime.now()
        self.error_history.append((now, error_code, retry_after))

        if error_code == 429:  # Too Many Requests
            if retry_after:
                self.backoff_until = now + timedelta(seconds=retry_after + 1)
            else:
                # Exponential backoff based on recent errors
                recent_errors = sum(
                    1 for t, c, _ in self.error_history if (now - t).seconds < 60 and c == 429
                )
                backoff_seconds = min(60, 2**recent_errors)
                self.backoff_until = now + timedelta(seconds=backoff_seconds)

            logger.warning(
                "Rate limit hit for %s..., backing off until %s",
                self.bot_token[:10],
                self.backoff_until,
            )

    def record_success(self):
        """Record successful request"""
        # Clear some error history on success
        if len(self.error_history) > 10:
            self.error_history.popleft()


OnUpdateCallable = Callable[[str, types.Update], Awaitable[None]]


class RateLimiter:
    """Main rate limiter managing all bot instances"""

    def __init__(self, on_update: Optional[OnUpdateCallable] = None):
        self.on_update = on_update

        self.bot_limiters: Dict[str, BotRateLimiter] = {}
        self.update_queues: Dict[str, asyncio.Queue[UpdateQueueItem]] = defaultdict(
            lambda: asyncio.Queue(maxsize=1000)
        )
        self.processing_tasks: Dict[str, asyncio.Task] = {}
        self.shutdown_event = asyncio.Event()

    def get_or_create_limiter(self, instance_id: str, bot_token: str) -> BotRateLimiter:
        """Get or create rate limiter for bot instance"""
        if instance_id not in self.bot_limiters:
            self.bot_limiters[instance_id] = BotRateLimiter(bot_token)
        return self.bot_limiters[instance_id]

    async def add_update(self, instance_id: str, update_data: dict, priority: int = 0):
        """Add update to processing queue"""
        queue = self.update_queues[instance_id]

        try:
            item = UpdateQueueItem(
                instance_id=instance_id,
                update_data=update_data,
                priority=priority,
            )
            await queue.put(item)

            # Start processing task if not running
            if instance_id not in self.processing_tasks:
                self.processing_tasks[instance_id] = asyncio.create_task(
                    self.process_queue(instance_id)
                )
        except asyncio.QueueFull:
            logger.warning("Update queue full for instance %s, dropping update", instance_id)

    async def process_queue(self, instance_id: str):
        """Process updates for specific instance"""
        queue = self.update_queues[instance_id]
        limiter = self.bot_limiters.get(instance_id)

        if not limiter:
            logger.error("No rate limiter found for instance %s", instance_id)
            return

        logger.info("Started processing queue for instance %s", instance_id)

        try:
            while not self.shutdown_event.is_set():
                try:
                    # Get next update
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)

                    # Check rate limits
                    chat_id = self.extract_chat_id(item.update_data)

                    if not await limiter.can_send(chat_id):
                        wait_time = await limiter.wait_for_send(chat_id)
                        if wait_time > 0:
                            logger.debug(
                                "Rate limiting instance %s, waiting %.2fs",
                                instance_id,
                                wait_time,
                            )
                            await asyncio.sleep(wait_time)

                    # Process the update
                    await self.process_update(instance_id, item)
                    limiter.record_success()

                    queue.task_done()

                except asyncio.TimeoutError:
                    continue  # Check shutdown event
                except Exception as e:
                    logger.exception("Error processing update for %s: %s", instance_id, e)
                    limiter.record_error(500)  # Generic error

        except asyncio.CancelledError:
            logger.info("Processing task cancelled for instance %s", instance_id)
        finally:
            # Clean up
            self.processing_tasks.pop(instance_id, None)

    def extract_chat_id(self, update_data: dict) -> Optional[int]:
        """Extract chat ID from update for per-chat rate limiting"""
        try:
            if "message" in update_data:
                return update_data["message"]["chat"]["id"]
            if "callback_query" in update_data:
                return update_data["callback_query"]["message"]["chat"]["id"]
            if "edited_message" in update_data:
                return update_data["edited_message"]["chat"]["id"]
        except (KeyError, TypeError):
            pass
        return None

    async def process_update(self, instance_id: str, item: UpdateQueueItem) -> None:
        """
        Parse update and dispatch to injected handler.

        NOTE: If on_update is not configured, this is a configuration error.
        """
        logger.debug("Processing update for instance %s", instance_id)

        update = types.Update(**item.update_data)

        if not self.on_update:
            raise RuntimeError("RateLimiter.on_update is not configured")

        await self.on_update(instance_id, update)

    async def process_updates_loop(self):
        """Main processing loop"""
        logger.info("Started update processing loop")

        try:
            await self.shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            # Cancel all processing tasks
            for task in list(self.processing_tasks.values()):
                task.cancel()

            # Wait for tasks to complete
            if self.processing_tasks:
                await asyncio.gather(*self.processing_tasks.values(), return_exceptions=True)

            logger.info("Update processing loop stopped")

    def stop(self):
        """Stop all processing"""
        self.shutdown_event.set()

    async def remove_instance(self, instance_id: str):
        """Remove instance from rate limiter"""
        # Cancel processing task
        task = self.processing_tasks.pop(instance_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Clean up data structures
        self.bot_limiters.pop(instance_id, None)
        self.update_queues.pop(instance_id, None)

        logger.info("Removed instance %s from rate limiter", instance_id)

    def get_stats(self, instance_id: str) -> dict:
        """Get rate limiting stats for instance"""
        limiter = self.bot_limiters.get(instance_id)
        queue = self.update_queues.get(instance_id)

        if not limiter or not queue:
            return {}

        return {
            "global_tokens": limiter.global_bucket.tokens,
            "chat_buckets": len(limiter.chat_buckets),
            "queue_size": queue.qsize(),
            "error_count": len(limiter.error_history),
            "backoff_until": limiter.backoff_until.isoformat() if limiter.backoff_until else None,
        }
