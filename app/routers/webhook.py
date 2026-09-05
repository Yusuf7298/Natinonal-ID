# app/routers/webhook.py
import asyncio
from fastapi import APIRouter, Request, Depends, HTTPException, status
from aiogram import types
from app.instances import bot, dp, scheduler
from app.dependencies import get_processing_service
from app.config import settings

router = APIRouter()
@router.post("/webhook")
async def telegram_webhook(
    request: Request, 
    processor=Depends(get_processing_service)
):
    # Security: Verify Telegram Webhook Secret Token if configured
    if settings.TELEGRAM_WEBHOOK_SECRET:
        secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret_header != settings.TELEGRAM_WEBHOOK_SECRET:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        update_data = await request.json()
        
        # Use model_validate instead of Update(**update_data)
        update = types.Update.model_validate(update_data, context={"bot": bot})

        # --- THE FIX: Non-blocking background task ---
        # We start the processing but return 200 OK to Telegram immediately.
        # This prevents Telegram from retrying if processing is slow.
        asyncio.create_task(
            dp.feed_update(
                bot, 
                update, 
                processor=processor, 
                scheduler=scheduler, 
                dp=dp
            )
        )
    except Exception as e:
        print(f"⚠️ Webhook Error: {e}")
        # We still return OK to Telegram so it doesn't retry infinitely on a bad update
    
    return {"ok": True}