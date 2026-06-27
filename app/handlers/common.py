"""common.py — /start, /help, /profile, home card, forcesub verify."""
from __future__ import annotations
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from app.config import settings
from app.database import db
from app.middleware.middlewares import _is_member
from app.utils.helpers import fmt_dt
from app.utils.keyboards import forcesub_kb, home_btn, home_kb

router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    u = message.from_user
    await db.upsert_user(u.id, u.username, u.full_name or "", u.language_code or "en")

    maint = await db.get_setting("maintenance","false")
    if maint == "true" and u.id != settings.owner_id:
        msg = await db.get_setting("maintenance_msg","Bot is under maintenance.")
        await message.answer(f"🔧 {msg}"); return

    await _home(message, u.full_name or u.username or "there")


async def _home(message: Message, name: str) -> None:
    text = (
        f"👋 <b>Hey, {name}!</b>\n\n"
        "Welcome to <b>@myqrro_bot</b>\n"
        "Premium QR code & payment poster generator 🎨\n\n"
        "┌ 💳 <b>UPI-first</b> — India-ready\n"
        "├ 🎨 <b>12 stunning themes</b>\n"
        "├ 📐 <b>HD 2048 px output</b>\n"
        "├ 🖼 <b>Logo overlay support</b>\n"
        "└ ⚡ <b>Instant generation</b>\n\n"
        "<i>Choose an option below to get started.</i>"
    )
    await message.answer(text, reply_markup=home_kb(), parse_mode="HTML")


@router.callback_query(F.data == "home")
async def cb_home(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(
        "🏠 <b>Home</b>\n\nWhat would you like to do?",
        reply_markup=home_kb(), parse_mode="HTML"
    )
    await call.answer()


@router.message(Command("help"))
@router.callback_query(F.data == "help:main")
async def cmd_help(event: Message | CallbackQuery) -> None:
    text = (
        "📖 <b>Help — @myqrro_bot</b>\n\n"
        "<b>Generation</b>\n"
        "/upi — UPI payment QR (4-step wizard)\n"
        "/qr — Pick any QR type\n"
        "/qr_url  /qr_text  /qr_wifi  /qr_vcard\n"
        "/qr_email  /qr_sms  /qr_geo\n\n"
        "<b>Manage</b>\n"
        "/mypayees — Saved payees (1-tap generate)\n"
        "/history — Regenerate past QRs\n"
        "/templates — Browse 12 themes\n"
        "/settings — Template, size, watermark, logo\n"
        "/profile — Your stats\n"
        "/setlogo — Upload a logo for QR overlay\n"
        "/dellogo — Remove your logo\n"
        "/delete_me — Delete all your data\n\n"
        "<b>Tips</b>\n"
        "• Save frequent payees in /mypayees\n"
        "• Use 2048×2048 for print-quality output\n"
        "• Upload PNG logos for branded QR codes\n"
    )
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=home_btn())
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=home_btn())
        await event.answer()


@router.message(Command("profile"))
@router.callback_query(F.data == "profile:view")
async def cmd_profile(event: Message | CallbackQuery) -> None:
    uid = event.from_user.id
    u   = await db.get_user(uid)
    us  = await db.get_user_settings(uid)
    h   = await db.get_history(uid, 1)
    if not u:
        text = "❌ Not found. Send /start first."
    else:
        badge = " 👑 Owner" if uid == settings.owner_id else (" 🛡 Admin" if await db.is_admin(uid) else "")
        last  = fmt_dt(h[0]["created_at"]) if h else "Never"
        text  = (
            f"👤 <b>Profile</b>{badge}\n\n"
            f"🆔 <code>{u['user_id']}</code>\n"
            f"📛 {u['full_name']}\n"
            f"🔤 @{u.get('username') or '—'}\n\n"
            f"📸 Generated: <b>{u['total_gen']}</b>\n"
            f"🕘 Last: {last}\n"
            f"📅 Joined: {fmt_dt(u['created_at'])}\n\n"
            f"🎨 Theme: <b>{us.get('template','minimal_pro')}</b>\n"
            f"📐 Size: <b>{us.get('output_size','1080x1350')}</b>\n"
            f"💧 Watermark: {'✅' if us.get('watermark_on') else '❌'}\n"
            f"🖼 Logo: {'✅' if u.get('logo_file_id') else '❌'}\n"
        )
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=home_btn())
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=home_btn())
        await event.answer()


@router.callback_query(F.data == "donate:stars")
async def cb_donate(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "⭐ <b>Donate Stars</b>\n\n"
        "Enjoying @myqrro_bot? Support the developer!\n\n"
        "Stars help keep this bot free, fast, and improving 🙏",
        parse_mode="HTML", reply_markup=home_btn()
    )
    await call.answer()


@router.callback_query(F.data == "fs:verify")
async def fs_verify(call: CallbackQuery) -> None:
    chats = await db.list_forcesub()
    missing = [c for c in chats if not await _is_member(call.bot, call.from_user.id, c["chat_id"])]
    if not missing:
        await call.answer("✅ Verified! Welcome!", show_alert=True)
        u = call.from_user
        await db.upsert_user(u.id, u.username, u.full_name or "")
        await _home(call.message, u.full_name or "there")
    else:
        names = ", ".join(c.get("title","channel") for c in missing)
        await call.answer(f"❌ Still not joined: {names}", show_alert=True)
