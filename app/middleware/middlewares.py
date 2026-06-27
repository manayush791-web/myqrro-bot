"""
middlewares.py — All middleware in one file.
Registration order: BanCheck → ForceSub → RateLimit
"""
from __future__ import annotations
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import settings
from app.database import db
from app.services.rate_limiter import check_rate
from app.utils.keyboards import forcesub_kb

_GEN_CMDS = frozenset(["/generate","/upi","/qr","/qr_url","/qr_text",
                        "/qr_wifi","/qr_vcard","/qr_email","/qr_sms","/qr_geo"])
_ADMIN_CMDS = frozenset([
    "/admin","/ban","/unban","/broadcast","/setwatermark","/setwatermarktext",
    "/setlimits","/audit","/health","/forcesub_on","/forcesub_off",
    "/forcesub_add","/forcesub_list","/forcesub_del",
    "/owner","/addadmin","/deladmin","/export","/maintenance","/purge",
])


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict) -> Any:
        user = data.get("event_from_user")
        if user and user.id != settings.owner_id:
            if await db.is_banned(user.id):
                if isinstance(event, Message):
                    await event.answer("🚫 You are banned from using this bot.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 You are banned.", show_alert=True)
                return None
        return await handler(event, data)


class ForceSub(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        uid = user.id

        # Owner and admins always pass
        if uid == settings.owner_id or await db.is_admin(uid):
            return await handler(event, data)

        # Admin commands pass through (will fail with permission error if not admin)
        if isinstance(event, Message) and event.text:
            cmd = event.text.split()[0].split("@")[0].lower()
            if cmd in _ADMIN_CMDS:
                return await handler(event, data)

        enabled = await db.get_setting("forcesub_enabled","false")
        if enabled != "true":
            return await handler(event, data)

        chats = await db.list_forcesub()
        if not chats:
            return await handler(event, data)

        bot: Bot = data["bot"]
        not_joined = [c for c in chats if not await _is_member(bot, uid, c["chat_id"])]

        if not not_joined:
            return await handler(event, data)

        text = (
            "🔐 <b>Join Required</b>\n\n"
            "Please join the following to use this bot:\n\n" +
            "\n".join(f"• <b>{c.get('title','Channel')}</b>" for c in not_joined) +
            "\n\n<i>Join, then tap ✅ Verify.</i>"
        )
        if isinstance(event, Message):
            await event.answer(text, reply_markup=forcesub_kb(not_joined), parse_mode="HTML")
        elif isinstance(event, CallbackQuery):
            await event.answer("Please join required channels first.", show_alert=True)
        return None


class RateLimitMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        uid = user.id

        if uid == settings.owner_id or await db.is_admin(uid):
            return await handler(event, data)

        if isinstance(event, Message) and event.text:
            cmd = event.text.split()[0].split("@")[0].lower()
            if cmd not in _GEN_CMDS:
                return await handler(event, data)
        else:
            return await handler(event, data)

        ok, window = await check_rate(uid)
        if not ok:
            msg = (f"⚡ Slow down! Max {await db.get_setting('rate_per_min','10')}/minute."
                   if window == "minute"
                   else f"📊 Daily limit reached. Resets at midnight.")
            await event.answer(msg)
            return None
        return await handler(event, data)


async def _is_member(bot: Bot, uid: int, chat_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id, uid)
        return m.status in ("member","administrator","creator","restricted")
    except (TelegramBadRequest, TelegramForbiddenError):
        return True  # Fail open
    except Exception:
        return True
