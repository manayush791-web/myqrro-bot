"""settings.py — /settings, templates, size, watermark, logo, history, /delete_me"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.logger import get_logger
from app.services.renderer import all_themes
from app.utils.keyboards import (
    back_kb, confirm_kb, history_kb,
    home_btn, settings_kb, size_kb, templates_kb,
)

log = get_logger(__name__)
router = Router(name="settings")


class LogoState(StatesGroup):
    waiting = State()


# ── /settings ─────────────────────────────────────────────────────────────

@router.message(Command("settings"))
@router.callback_query(F.data == "settings:main")
async def cmd_settings(event: Message | CallbackQuery) -> None:
    uid = event.from_user.id
    us  = await db.get_user_settings(uid)
    text = (
        "⚙️ <b>Settings</b>\n\n"
        f"🎨 Theme:     <b>{us.get('template','minimal_pro')}</b>\n"
        f"📐 Size:      <b>{us.get('output_size','1080x1350')}</b>\n"
        f"💧 Watermark: {'✅ On' if us.get('watermark_on') else '❌ Off'}\n"
    )
    kb = settings_kb(us)
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


# ── Templates ─────────────────────────────────────────────────────────────

@router.message(Command("templates"))
@router.callback_query(F.data == "templates:list")
@router.callback_query(F.data.startswith("tpl:pg:"))
async def cmd_templates(event: Message | CallbackQuery) -> None:
    uid     = event.from_user.id
    us      = await db.get_user_settings(uid)
    current = us.get("template", "minimal_pro")
    ts      = all_themes()

    page = 0
    if isinstance(event, CallbackQuery) and event.data.startswith("tpl:pg:"):
        page = int(event.data.split(":")[2])

    text = (
        "🎨 <b>Templates</b>  ·  12 themes\n\n"
        "Tap a theme to set it as your default.\n"
        "Your next poster will use this style."
    )
    kb = templates_kb(ts, current, page)
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


@router.callback_query(F.data.startswith("tpl:sel:"))
async def cb_tpl_select(call: CallbackQuery) -> None:
    tid = call.data.split(":")[2]
    await db.update_user_settings(call.from_user.id, template=tid)
    await call.answer(f"✅ Theme set to {tid}", show_alert=False)
    # Refresh checkmarks in list
    us = await db.get_user_settings(call.from_user.id)
    ts = all_themes()
    await call.message.edit_reply_markup(reply_markup=templates_kb(ts, tid))


# ── Size ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings:size")
async def cb_size(call: CallbackQuery) -> None:
    us = await db.get_user_settings(call.from_user.id)
    await call.message.edit_text(
        "📐 <b>Output Size</b>\n\n"
        "Choose your preferred poster size:\n\n"
        "• <b>1080×1350</b> — Portrait (best for WhatsApp/Instagram stories)\n"
        "• <b>1080×1080</b> — Square (feeds, Telegram)\n"
        "• <b>2048×2048</b> — HD QR only (print quality)",
        parse_mode="HTML",
        reply_markup=size_kb(us.get("output_size", "1080x1350"))
    )
    await call.answer()


@router.callback_query(F.data.startswith("size:sel:"))
async def cb_size_select(call: CallbackQuery) -> None:
    size = call.data.split(":")[2]
    await db.update_user_settings(call.from_user.id, output_size=size)
    await call.answer(f"✅ Size set to {size}", show_alert=False)
    await call.message.edit_reply_markup(reply_markup=size_kb(size))


# ── Watermark toggle ──────────────────────────────────────────────────────

@router.callback_query(F.data == "settings:wm_toggle")
async def cb_wm_toggle(call: CallbackQuery) -> None:
    us      = await db.get_user_settings(call.from_user.id)
    new_val = not us.get("watermark_on", True)
    await db.update_user_settings(call.from_user.id, watermark_on=new_val)
    status  = "enabled ✅" if new_val else "disabled ❌"
    await call.answer(f"Watermark {status}", show_alert=False)
    us = await db.get_user_settings(call.from_user.id)
    await call.message.edit_reply_markup(reply_markup=settings_kb(us))


# ── Logo upload ───────────────────────────────────────────────────────────

@router.message(Command("setlogo"))
@router.callback_query(F.data == "settings:setlogo")
async def cmd_setlogo(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(LogoState.waiting)
    text = (
        "🖼 <b>Upload Logo</b>\n\n"
        "Send a <b>PNG or JPG image</b> as your logo.\n\n"
        "It will be overlaid at the centre of every QR code you generate.\n\n"
        "<i>Best results: square PNG with transparent background, max 512×512 px</i>"
    )
    kb = back_kb("settings:main")
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


@router.message(LogoState.waiting)
async def logo_received(message: Message, state: FSMContext) -> None:
    if not message.photo and not message.document:
        await message.answer("❌ Please send a photo or image file.")
        return
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    await db.set_logo(message.from_user.id, file_id)
    await state.clear()
    await message.answer(
        "✅ <b>Logo saved!</b>\n\n"
        "Your logo will appear on all future QR codes.",
        parse_mode="HTML", reply_markup=home_btn()
    )


@router.message(Command("dellogo"))
@router.callback_query(F.data == "settings:dellogo")
async def cmd_dellogo(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await db.set_logo(event.from_user.id, None)
    text = "🗑 <b>Logo removed.</b>\n\nYour QR codes will no longer include a logo overlay."
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=home_btn())
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=home_btn())
        await event.answer()


# ── History ───────────────────────────────────────────────────────────────

@router.message(Command("history"))
@router.callback_query(F.data == "history:list")
async def cmd_history(event: Message | CallbackQuery) -> None:
    uid  = event.from_user.id
    recs = await db.get_history(uid, limit=10)

    if not recs:
        text = "🕘 <b>History</b>\n\nNo history yet. Generate a QR with /upi or /qr."
        kb   = home_btn()
    else:
        text = f"🕘 <b>History</b>  ·  last {len(recs)}\n\nTap any entry to regenerate it:"
        kb   = history_kb(recs)

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


@router.callback_query(F.data.startswith("hist:regen:"))
async def cb_regen(call: CallbackQuery) -> None:
    hid  = int(call.data.split(":")[2])
    recs = await db.get_history(call.from_user.id, limit=50)
    rec  = next((r for r in recs if r["id"] == hid), None)
    if not rec:
        await call.answer("❌ Record not found.", show_alert=True)
        return
    await call.answer("⏳ Regenerating…")
    from app.handlers.generate import _send_poster
    await _send_poster(call.message, rec["payload"], rec["qr_type"])


# ── Delete my data ────────────────────────────────────────────────────────

@router.message(Command("delete_me"))
@router.callback_query(F.data == "settings:deleteme")
async def cmd_delete_me(event: Message | CallbackQuery) -> None:
    text = (
        "⚠️ <b>Delete My Data</b>\n\n"
        "This will permanently erase:\n"
        "• Your profile and settings\n"
        "• All saved payees\n"
        "• All generation history\n\n"
        "<b>This cannot be undone.</b> Continue?"
    )
    kb = confirm_kb("deleteme:confirm", "settings:main")
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


@router.callback_query(F.data == "deleteme:confirm")
async def cb_delete_confirm(call: CallbackQuery) -> None:
    uid = call.from_user.id
    await db.purge_user(uid, uid)
    await call.message.edit_text(
        "✅ <b>All your data has been deleted.</b>\n\n"
        "Send /start to create a fresh account.",
        parse_mode="HTML"
    )
    await call.answer()
