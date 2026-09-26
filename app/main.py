import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from app.instances import bot, dp, scheduler, processor
from app.routers.bot_handlers import router as bot_router
from app.config import settings
from app.middlewares.membership import MembershipMiddleware
polling_task: asyncio.Task | None = None
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    dp.update.outer_middleware(MembershipMiddleware())
    dp.include_router(bot_router)
    print("Clearing any existing webhook so polling can receive updates...", flush=True)
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"Bot @{me.username} is now running in POLLING mode!", flush=True)
    global polling_task
    polling_task = asyncio.create_task(
        dp.start_polling(bot, processor=processor, scheduler=scheduler, dp=dp)
    )
    yield
    print("Shutting down bot...", flush=True)
    scheduler.shutdown()
    await dp.stop_polling()
    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    await bot.session.close()
app = FastAPI(title="National ID Bot", lifespan=lifespan)
@app.get("/")
@app.get("/health")
async def health():
    return {"status": "ok", "mode": "polling", "bot": settings.BOT_NAME}
async def run_standalone():
    scheduler.start()
    dp.update.outer_middleware(MembershipMiddleware())
    dp.include_router(bot_router)

    print("Connecting to Telegram API...", flush=True)
    while True:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            me = await bot.get_me()
            print(f"Bot @{me.username} is now running in POLLING mode!", flush=True)
            print(f"Open Telegram, find @{me.username} and send /start to test.", flush=True)
            print("Press Ctrl+C in this terminal to stop.", flush=True)
            await dp.start_polling(bot, processor=processor, scheduler=scheduler, dp=dp)
            break
        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as e:
            print(f"Connection attempt failed ({type(e).__name__}: {e}). Retrying in 5 seconds... (Ensure VPN/Internet is active)", flush=True)
            await asyncio.sleep(5)
    
    try:
        scheduler.shutdown()
        await bot.session.close()
    except Exception:
        pass
if __name__ == "__main__":
    try:
        asyncio.run(run_standalone())
    except (KeyboardInterrupt, SystemExit):
        print("\nBot stopped.")