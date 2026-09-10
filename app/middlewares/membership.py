from typing import Any, Callable, Dict, Awaitable, List, Tuple, Union
from aiogram import BaseMiddleware, types
from app.config import settings

# In-memory cache for channel details (title, invite_link)
_channel_info_cache: Dict[str, Dict[str, Any]] = {}

async def get_channel_info(bot, channel: Union[int, str]) -> Tuple[str, str]:
    """
    Retrieves and caches the channel/group title and invite link.
    Returns (title, invite_link).
    """
    key = str(channel)
    if key in _channel_info_cache:
        cached = _channel_info_cache[key]
        return cached["title"], cached["invite_link"]

    title = str(channel)
    invite_link = settings.channel_invite_links_map.get(key, "")

    if isinstance(channel, str) and channel.startswith("@"):
        title = channel
        if not invite_link:
            invite_link = f"https://t.me/{channel.lstrip('@')}"

    try:
        chat = await bot.get_chat(chat_id=channel)
        if chat.title:
            title = chat.title
        if not invite_link:
            if chat.username:
                invite_link = f"https://t.me/{chat.username}"
            elif chat.invite_link:
                invite_link = chat.invite_link
            else:
                try:
                    invite_link = await bot.export_chat_invite_link(chat_id=channel)
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠️ [Membership] Could not fetch chat info for {channel}: {e}", flush=True)

    if not invite_link and isinstance(channel, str) and channel.startswith("@"):
        invite_link = f"https://t.me/{channel.lstrip('@')}"

    _channel_info_cache[key] = {"title": title, "invite_link": invite_link}
    return title, invite_link

async def check_user_membership(bot, user_id: int) -> Tuple[bool, List[Tuple[Union[int, str], str, str]], List[str]]:
    """
    Checks membership across all configured channels/groups in settings.required_channels_list.
    Returns:
        (all_joined, unjoined_channels, errors)
        where unjoined_channels is list of (channel, title, invite_link)
    """
    unjoined = []
    errors = []

    for channel in settings.required_channels_list:
        try:
            member = await bot.get_chat_member(
                chat_id=channel,
                user_id=user_id
            )
            # Allowed statuses: owner, creator, administrator, member, restricted (still in group)
            if member.status not in ["owner", "creator", "administrator", "member", "restricted"]:
                title, link = await get_channel_info(bot, channel)
                unjoined.append((channel, title, link))
        except Exception as e:
            err_msg = f"Chat {channel}: {e}"
            errors.append(err_msg)
            print(f"❌ [Membership] Error for user {user_id} in {channel}: {e}", flush=True)
            title, link = await get_channel_info(bot, channel)
            unjoined.append((channel, title, link))

    all_joined = (len(unjoined) == 0 and len(errors) == 0)
    return all_joined, unjoined, errors

def build_membership_keyboard(unjoined_channels: List[Tuple[Union[int, str], str, str]]) -> types.InlineKeyboardMarkup:
    """Builds inline keyboard with join buttons for unjoined channels and a verify button."""
    rows = []
    for idx, (channel, title, link) in enumerate(unjoined_channels, start=1):
        btn_text = f"📢 Join {title}"
        if link:
            rows.append([types.InlineKeyboardButton(text=btn_text, url=link)])
        else:
            ch_str = str(channel)
            if ch_str.startswith("@"):
                rows.append([types.InlineKeyboardButton(text=btn_text, url=f"https://t.me/{ch_str.lstrip('@')}")])
            else:
                rows.append([types.InlineKeyboardButton(text=f"📢 Join Channel {idx}", callback_data="check_membership")])

    rows.append([types.InlineKeyboardButton(text="🔄 Verify Membership", callback_data="check_membership")])
    return types.InlineKeyboardMarkup(inline_keyboard=rows)

class MembershipMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.Update,
        data: Dict[str, Any]
    ) -> Any:
        # 1. Extract user from event
        user = None
        if event.message:
            user = event.message.from_user
        elif event.callback_query:
            user = event.callback_query.from_user

        if not user:
            return await handler(event, data)

        # 2. BYPASS: Authorized Admins
        if user.id in settings.authorized_users:
            return await handler(event, data)

        # 3. BYPASS: No required channels configured
        required_channels = settings.required_channels_list
        if not required_channels:
            return await handler(event, data)

        # 4. Handle "Verify Membership" callback click
        if event.callback_query and event.callback_query.data == "check_membership":
            all_joined, unjoined, errors = await check_user_membership(event.bot, user.id)
            if all_joined:
                await event.callback_query.answer("✅ Membership verified! Thank you.", show_alert=False)
                try:
                    await event.callback_query.message.delete()
                except Exception:
                    pass
                
                # Send welcome message
                from app.routers.bot_handlers import get_main_kb
                from utils.texts import WELCOME_TEXT
                await event.bot.send_message(
                    chat_id=user.id,
                    text=WELCOME_TEXT,
                    reply_markup=get_main_kb(),
                    disable_web_page_preview=True
                )
                return  # Successfully handled verification

            # Still missing some channels
            await event.callback_query.answer("⚠️ You haven't joined all required channels yet. Please join all of them and try again.", show_alert=True)
            # Refresh keyboard with latest unjoined channels
            kb = build_membership_keyboard(unjoined)
            try:
                await event.callback_query.message.edit_reply_markup(reply_markup=kb)
            except Exception:
                pass
            return  # Block further execution

        # 5. General check for all other updates (messages or other callbacks)
        all_joined, unjoined, errors = await check_user_membership(event.bot, user.id)
        if all_joined:
            return await handler(event, data)

        # Access Denied: User has not joined all channels
        print(f"DEBUG: Access DENIED for user {user.id}. Missing {len(unjoined)} channels.")
        
        restriction_msg = (
            "⚠️ **Channel Membership Required**\n\n"
            "To use this bot, you must be a member of all our official Telegram channels.\n\n"
            "Please click the buttons below to join, then click **'🔄 Verify Membership'** to start:"
        )
        
        kb = build_membership_keyboard(unjoined)

        # Admin debugging assistance
        if user.id in settings.authorized_users and errors:
            debug_info = "\n".join(errors)
            debug_msg = (
                f"🔬 [ADMIN DEBUG]\nChannel check errors:\n{debug_info}\n\n"
                "Ensure the bot is added as an Administrator to each channel."
            )
            if event.message:
                await event.message.answer(debug_msg)

        if event.message:
            try:
                await event.message.answer(restriction_msg, reply_markup=kb, parse_mode="Markdown")
            except Exception:
                await event.message.answer(restriction_msg.replace("**", ""), reply_markup=kb)
        elif event.callback_query:
            await event.callback_query.answer("⚠️ Please join all required channels first.", show_alert=True)
            try:
                await event.callback_query.message.answer(restriction_msg, reply_markup=kb, parse_mode="Markdown")
            except Exception:
                try:
                    await event.callback_query.message.answer(restriction_msg.replace("**", ""), reply_markup=kb)
                except Exception:
                    pass
        
        return # Block update
