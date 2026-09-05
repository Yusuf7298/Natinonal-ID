import sys
import asyncio
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace") # type: ignore
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace") # type: ignore
from app.instances import bot, dp, scheduler, processor
from app.routers.bot_handlers import router as bot_router
from app.middlewares.membership import MembershipMiddleware
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    scheduler.start()
    dp.update.outer_middleware(MembershipMiddleware())
    dp.include_router(bot_router)
    print("Bot is started running ...")
    try:
        await dp.start_polling(bot, processor=processor, scheduler=scheduler, dp=dp)
    finally:
        scheduler.shutdown()
        await bot.session.close()
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
