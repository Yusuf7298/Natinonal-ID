import asyncio
from typing import Any
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import TelegramMethod, Response
from aiogram.methods.base import TelegramType
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from services.processing_service import ProcessingService
class RetryRequestMiddleware(BaseRequestMiddleware):
    def __init__(self, max_retries: int = 3, initial_delay: float = 1.0, backoff_factor: float = 2.0):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        delay = self.initial_delay
        for attempt in range(1, self.max_retries + 1):
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as e:
                if attempt >= self.max_retries:
                    raise
                wait_time = e.retry_after + 0.5
                print(f"RateLimit: Waiting {wait_time:.1f}s before retrying {method.__api_method__}...", flush=True)
                await asyncio.sleep(wait_time)
            except TelegramNetworkError as e:
                if attempt >= self.max_retries:
                    raise
                print(f"Network Error: ({type(e).__name__}: {e}) on {method.__api_method__}. Retrying attempt {attempt + 1}/{self.max_retries} in {delay:.1f}s...", flush=True)
                await asyncio.sleep(delay)
                delay *= self.backoff_factor
class RobustAiohttpSession(AiohttpSession):
    def __init__(self, *args: Any, keepalive_timeout: float = 30.0, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._connector_init["keepalive_timeout"] = keepalive_timeout
        self._connector_init["enable_cleanup_closed"] = True
session = RobustAiohttpSession(timeout=1200.0)
session.middleware.register(RetryRequestMiddleware(max_retries=3, initial_delay=1.5))
bot = Bot(token=settings.TELEGRAM_TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()
processor = ProcessingService(bot=bot)