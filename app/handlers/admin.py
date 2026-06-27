"""admin.py — Full admin panel: stats, broadcast, ban/unban, watermark, ForceSub, audit, health."""
from __future__ import annotations

import asyncio
import csv
import io
import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.database import db
from app.logger import get_logger
from app.middleware.permissions import admin_only
from app.utils.keyboards import admin_kb, back_kb, confirm_kb, home_btn

log = get_logger(__name__)
router = Router(name="admin")


class AdminState(StatesGroup):
    ban_id     = State()
    ban_reason = State()
    unban_id   = State()
    broadcast  = State()
    bcast_confirm = State()


# ── /admin panel ──────────────────────────────────────────────────────────

@router.message(Command("admin"))
@admin_only
async def cmd_admin(message: Message) -> None:
    await message.answer(
        "🛡 <b>Admin Panel</b>\n\nChoose an action:",
        parse_mode="HTML", reply_markup=admin_kb()
    )


@router.callback_query(F.data == "adm:back")
async def cb_adm_back(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "🛡 <b>Admin Panel</b>", parse_mode="HTML", reply_markup=admin_kb()
    )
    await call.answer()


# ── Stats ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:stats")
@admin_only
async def cb_stats(call: CallbackQuery) -> None:
    stats = await db.get_stats()
    h     = await db.health_check()
    text  = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total users:   <b>{stats['total_users']}</b>\n"
        f"🚫 Banned:        <b>{stats['banned']}</b>\n"
        f"📸 All-time gen:  <b>{stats['total_generated']}</b>\n"
        f"📅 Today:         <b>{stats['today']}</b>\n\n"
        f"🗄 DB status:     <b>{h['status']}</b>"
        + (f"  ({h.get('latency_ms')} ms)" if h.get('latency_ms') else "")
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb("adm:back"))
    await call.answer()


# ── Health ────────────────────────────────────────────────────────────────

@router.message(Command("health"))
@router.callback_query(F.data == "adm:health")
@admin_only
async def cb_health(event: Message | CallbackQuery) -> None:
    import psutil, time
    h    = await db.health_check()
    proc = psutil.Process()
    mem  = round(proc.memory_info().rss / 1024 ** 2, 2)
    uptime_s = round(time.time() - proc.create_time())
    hrs, rem = divmod(uptime_s, 3600)
    mins     = rem // 60
    text = (
        "🏥 <b>Health</b>\n\n"
        f"🗄 Database:  <b>{h['status']}</b>"
        + (f"  ({h.get('latency_ms')} ms)" if h.get('latency_ms') else "") + "\n"
        f"🧠 Memory:   <b>{mem} MB</b>\n"
        f"⏱ Uptime:   <b>{hrs}h {mins}m</b>\n"
    )
    kb = back_kb("adm:back")
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


# ── Watermark ─────────────────────────────────────────────────────────────

@router.message(Command("setwatermark"))
@admin_only
async def cmd_setwatermark(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2 or parts[1].lower() not in ("on", "off"):
        await message.answer("Usage: /setwatermark on|off")
        return
    val = "true" if parts[1].lower() == "on" else "false"
    await db.set_setting("watermark_enabled", val)
    await message.answer(f"💧 Watermark globally {'✅ enabled' if val=='true' else '❌ disabled'}.")


@router.message(Command("setwatermarktext"))
@admin_only
async def cmd_setwatermarktext(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /setwatermarktext <text>")
        return
    text = parts[1].strip()[:40]
    await db.set_setting("watermark_text", text)
    await message.answer(f"💧 Watermark text set to: <code>{text}</code>", parse_mode="HTML")


@router.callback_query(F.data == "adm:wm")
@admin_only
async def cb_wm(call: CallbackQuery) -> None:
    enabled = await db.get_setting("watermark_enabled", "true")
    text_   = await db.get_setting("watermark_text", "@myqrro_bot")
    await call.message.edit_text(
        f"💧 <b>Watermark</b>\n\n"
        f"Status: {'✅ Enabled' if enabled=='true' else '❌ Disabled'}\n"
        f"Text:   <code>{text_}</code>\n\n"
        "Commands:\n"
        "<code>/setwatermark on|off</code>\n"
        "<code>/setwatermarktext &lt;text&gt;</code>",
        parse_mode="HTML", reply_markup=back_kb("adm:back")
    )
    await call.answer()


# ── Rate limits ───────────────────────────────────────────────────────────

@router.message(Command("setlimits"))
@admin_only
async def cmd_setlimits(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /setlimits <per_min> <per_day>")
        return
    try:
        pm, pd = int(parts[1]), int(parts[2])
    except ValueError:
        await message.answer("❌ Both values must be integers.")
        return
    await db.set_setting("rate_per_min", str(pm))
    await db.set_setting("rate_per_day", str(pd))
    await message.answer(
        f"✅ Rate limits updated:\n"
        f"  ⚡ Per minute: <b>{pm}</b>\n"
        f"  📊 Per day:   <b>{pd}</b>",
        parse_mode="HTML"
    )


# ── Ban / Unban ───────────────────────────────────────────────────────────

@router.message(Command("ban"))
@admin_only
async def cmd_ban(message: Message, state: FSMContext) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) >= 2:
        try:
            uid    = int(parts[1])
            reason = parts[2] if len(parts) > 2 else "Banned by admin"
            await _do_ban(message, uid, reason)
            return
        except ValueError:
            pass
    await state.set_state(AdminState.ban_id)
    await message.answer("🚫 Enter the <b>user_id</b> to ban:", parse_mode="HTML")


@router.message(AdminState.ban_id)
@admin_only
async def ban_id(m: Message, s: FSMContext) -> None:
    try:
        uid = int(m.text.strip())
    except ValueError:
        await m.answer("❌ Invalid user ID. Enter a number:"); return
    await s.update_data(ban_uid=uid)
    await s.set_state(AdminState.ban_reason)
    await m.answer("Enter ban reason (or <code>skip</code>):", parse_mode="HTML")


@router.message(AdminState.ban_reason)
@admin_only
async def ban_reason(m: Message, s: FSMContext) -> None:
    d      = await s.get_data()
    reason = "Banned by admin" if m.text.strip().lower() == "skip" else m.text.strip()
    await s.clear()
    await _do_ban(m, d["ban_uid"], reason)


async def _do_ban(m: Message, uid: int, reason: str) -> None:
    await db.ban_user(uid, reason, m.from_user.id)
    await m.answer(f"🚫 User <code>{uid}</code> banned.\nReason: {reason}", parse_mode="HTML")
    try:
        await m.bot.send_message(uid, f"🚫 You have been banned.\nReason: {reason}")
    except Exception:
        pass


@router.message(Command("unban"))
@admin_only
async def cmd_unban(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /unban <user_id>"); return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("❌ Invalid user ID."); return
    await db.unban_user(uid, message.from_user.id)
    await message.answer(f"✅ User <code>{uid}</code> unbanned.", parse_mode="HTML")
    try:
        await message.bot.send_message(uid, "✅ You have been unbanned. Send /start to continue.")
    except Exception:
        pass


@router.callback_query(F.data == "adm:ban")
@admin_only
async def cb_ban(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminState.ban_id)
    await call.message.edit_text(
        "🚫 Enter the <b>user_id</b> to ban:",
        parse_mode="HTML", reply_markup=back_kb("adm:back")
    )
    await call.answer()


@router.callback_query(F.data == "adm:unban")
@admin_only
async def cb_unban(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminState.unban_id)
    await call.message.edit_text(
        "✅ Enter the <b>user_id</b> to unban:",
        parse_mode="HTML", reply_markup=back_kb("adm:back")
    )
    await call.answer()


@router.message(AdminState.unban_id)
@admin_only
async def unban_id(m: Message, s: FSMContext) -> None:
    try:
        uid = int(m.text.strip())
    except ValueError:
        await m.answer("❌ Invalid user ID."); return
    await s.clear()
    await db.unban_user(uid, m.from_user.id)
    await m.answer(f"✅ User <code>{uid}</code> unbanned.", parse_mode="HTML")
    try:
        await m.bot.send_message(uid, "✅ You have been unbanned. Send /start to continue.")
    except Exception:
        pass


# ── ForceSub ──────────────────────────────────────────────────────────────

@router.message(Command("forcesub_on"))
@admin_only
async def fs_on(m: Message) -> None:
    await db.set_setting("forcesub_enabled", "true")
    await m.answer("🔐 ForceSub <b>enabled</b>.", parse_mode="HTML")


@router.message(Command("forcesub_off"))
@admin_only
async def fs_off(m: Message) -> None:
    await db.set_setting("forcesub_enabled", "false")
    await m.answer("🔓 ForceSub <b>disabled</b>.", parse_mode="HTML")


@router.message(Command("forcesub_add"))
@admin_only
async def fs_add(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "Usage:\n"
            "/forcesub_add @username\n"
            "/forcesub_add -1001234567890 https://t.me/+invite"
        )
        return
    arg = parts[1]
    invite = parts[2] if len(parts) > 2 else None

    if arg.startswith("@"):
        handle = arg.lstrip("@")
        try:
            chat = await message.bot.get_chat(f"@{handle}")
            await db.add_forcesub(chat.id, handle, None, chat.title or handle, message.from_user.id)
            await message.answer(f"✅ Added @{handle} (ID: <code>{chat.id}</code>)", parse_mode="HTML")
        except Exception as e:
            await message.answer(f"❌ Failed: {e}\nMake sure the bot is admin in that chat.")
        return

    try:
        cid = int(arg)
    except ValueError:
        await message.answer("❌ Invalid chat_id. Must be a number or @username.")
        return

    try:
        chat  = await message.bot.get_chat(cid)
        title = chat.title or str(cid)
    except Exception:
        title = str(cid)

    await db.add_forcesub(cid, None, invite, title, message.from_user.id)
    await message.answer(f"✅ Added chat <code>{cid}</code> to ForceSub list.", parse_mode="HTML")


@router.message(Command("forcesub_del"))
@admin_only
async def fs_del(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /forcesub_del <chat_id>"); return
    try:
        cid = int(parts[1])
    except ValueError:
        await message.answer("❌ Invalid chat_id."); return
    await db.del_forcesub(cid, message.from_user.id)
    await message.answer(f"✅ Removed <code>{cid}</code> from ForceSub.", parse_mode="HTML")


@router.message(Command("forcesub_list"))
@admin_only
async def fs_list(message: Message) -> None:
    chats   = await db.list_forcesub()
    enabled = await db.get_setting("forcesub_enabled", "false") == "true"
    if not chats:
        await message.answer(
            f"🔐 ForceSub: {'✅ Enabled' if enabled else '❌ Disabled'}\n\n"
            "No chats configured.\nUse /forcesub_add to add channels."
        )
        return
    lines = [f"🔐 ForceSub: {'✅ Enabled' if enabled else '❌ Disabled'}\n"]
    for c in chats:
        handle = f"@{c['username']}" if c.get("username") else str(c["chat_id"])
        link   = f"  <a href='{c['invite_link']}'>invite</a>" if c.get("invite_link") else ""
        lines.append(f"• <b>{c.get('title', handle)}</b>  (<code>{c['chat_id']}</code>){link}")
    await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


@router.callback_query(F.data == "adm:fs")
@admin_only
async def cb_fs(call: CallbackQuery) -> None:
    chats   = await db.list_forcesub()
    enabled = await db.get_setting("forcesub_enabled","false") == "true"
    lines   = [f"🔐 <b>ForceSub</b>  {'✅ On' if enabled else '❌ Off'}\n"]
    if chats:
        for c in chats:
            lines.append(f"• {c.get('title', c['chat_id'])}  (<code>{c['chat_id']}</code>)")
    else:
        lines.append("No chats configured.\n\n/forcesub_add @channel to add one.")
    await call.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=back_kb("adm:back")
    )
    await call.answer()


# ── Broadcast ─────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
@router.callback_query(F.data == "adm:broadcast")
@admin_only
async def cmd_broadcast(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminState.broadcast)
    text = (
        "📢 <b>Broadcast</b>\n\n"
        "Send your message (HTML supported).\n"
        "It will be delivered to <b>all users</b>.\n\n"
        "<i>Send /cancel to abort.</i>"
    )
    kb = back_kb("adm:back")
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


@router.message(AdminState.broadcast)
@admin_only
async def bcast_text(m: Message, s: FSMContext) -> None:
    await s.update_data(bcast=m.text or "")
    await s.set_state(AdminState.bcast_confirm)
    await m.answer(
        f"📢 <b>Preview:</b>\n\n{m.text}\n\n<b>Send to all users?</b>",
        parse_mode="HTML",
        reply_markup=confirm_kb("bcast:go", "bcast:cancel")
    )


@router.callback_query(F.data == "bcast:go")
@admin_only
async def bcast_go(call: CallbackQuery, state: FSMContext) -> None:
    d     = await state.get_data()
    text  = d.get("bcast","")
    await state.clear()
    users = await db.get_all_users()
    ok = fail = 0
    status = await call.message.edit_text(f"📢 Sending to {len(users)} users…")
    for u in users:
        try:
            await call.bot.send_message(u["user_id"], text, parse_mode="HTML")
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)   # 20 msg/s — well within Telegram limits
    await status.edit_text(
        f"📢 <b>Broadcast complete</b>\n✅ Sent: {ok}\n❌ Failed: {fail}",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "bcast:cancel")
async def bcast_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("❌ Broadcast cancelled.", reply_markup=home_btn())
    await call.answer()


# ── Audit ─────────────────────────────────────────────────────────────────

@router.message(Command("audit"))
@router.callback_query(F.data == "adm:audit")
@admin_only
async def cmd_audit(event: Message | CallbackQuery) -> None:
    recs = await db.get_audit(limit=20)
    if not recs:
        text = "📋 <b>Audit Log</b>\n\nNo events yet."
    else:
        lines = ["📋 <b>Audit Log</b>  ·  last 20\n"]
        for r in recs:
            ts    = str(r["created_at"])[:16]
            actor = f"@{r['username']}" if r.get("username") else str(r["actor_id"])
            tgt   = f" → {r['target_id']}" if r.get("target_id") else ""
            note  = f"  <i>{r['note']}</i>" if r.get("note") else ""
            lines.append(f"<code>{ts}</code>  {actor}: <b>{r['action']}</b>{tgt}{note}")
        text = "\n".join(lines)

    kb = back_kb("adm:back")
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()
