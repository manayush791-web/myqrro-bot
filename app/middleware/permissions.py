"""permissions.py — @owner_only and @admin_only decorators."""
from __future__ import annotations
import functools
from typing import Any
from aiogram.types import CallbackQuery, Message
from app.config import settings
from app.database import db


def owner_only(fn):
    @functools.wraps(fn)
    async def wrapper(event: Any, *a, **kw):
        uid = event.from_user.id
        if uid != settings.owner_id:
            await _deny(event, "⛔ Owner only.")
            return
        return await fn(event, *a, **kw)
    return wrapper


def admin_only(fn):
    @functools.wraps(fn)
    async def wrapper(event: Any, *a, **kw):
        uid = event.from_user.id
        if uid == settings.owner_id or await db.is_admin(uid):
            return await fn(event, *a, **kw)
        await _deny(event, "⛔ Admin only.")
    return wrapper


async def _deny(event, text: str) -> None:
    if isinstance(event, Message):
        await event.answer(text)
    elif isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)
