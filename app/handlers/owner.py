"""owner.py — Owner-only: addadmin, deladmin, export, maintenance, purge."""
from __future__ import annotations

import csv
import io
import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.database import db
from app.logger import get_logger
from app.middleware.permissions import owner_only
from app.utils.keyboards import home_btn, owner_kb

log = get_logger(__name__)
router = Router(name="owner")


# ── /owner panel ──────────────────────────────────────────────────────────

@router.message(Command("owner"))
@owner_only
async def cmd_owner(message: Message) -> None:
    admins = await db.list_admins()
    lines  = ["👑 <b>Owner Panel</b>\n"]
    if admins:
        lines.append("<b>Current Admins:</b>")
        for a in admins:
            name = a.get("full_name") or a.get("username") or str(a["user_id"])
            lines.append(f"  • {name}  (<code>{a['user_id']}</code>)")
    else:
        lines.append("<i>No admins configured yet.</i>")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=owner_kb())


# ── Add / Remove admin ────────────────────────────────────────────────────

@router.message(Command("addadmin"))
@owner_only
async def cmd_addadmin(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /addadmin <user_id>"); return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id must be a number."); return

    user = await db.get_user(uid)
    if not user:
        await message.answer(
            f"❌ User <code>{uid}</code> not found.\n"
            "They must send /start to the bot first.",
            parse_mode="HTML"
        )
        return

    await db.add_admin(uid, message.from_user.id)
    name = user.get("full_name") or user.get("username") or str(uid)
    await message.answer(f"✅ <b>{name}</b> is now an admin.", parse_mode="HTML")
    try:
        await message.bot.send_message(uid, "🛡 You have been granted <b>admin access</b> to this bot.",
                                       parse_mode="HTML")
    except Exception:
        pass


@router.message(Command("deladmin"))
@owner_only
async def cmd_deladmin(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /deladmin <user_id>"); return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id must be a number."); return

    await db.del_admin(uid, message.from_user.id)
    await message.answer(f"✅ Admin access removed from <code>{uid}</code>.", parse_mode="HTML")
    try:
        await message.bot.send_message(uid, "ℹ️ Your admin access has been revoked.")
    except Exception:
        pass


@router.callback_query(F.data == "own:addadmin")
@owner_only
async def cb_addadmin(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "Use the command:\n<code>/addadmin &lt;user_id&gt;</code>",
        parse_mode="HTML", reply_markup=home_btn()
    )
    await call.answer()


@router.callback_query(F.data == "own:deladmin")
@owner_only
async def cb_deladmin(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "Use the command:\n<code>/deladmin &lt;user_id&gt;</code>",
        parse_mode="HTML", reply_markup=home_btn()
    )
    await call.answer()


# ── Export ────────────────────────────────────────────────────────────────

@router.message(Command("export"))
@owner_only
async def cmd_export(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2 or parts[1] not in ("users", "stats", "audit"):
        await message.answer("Usage: /export users|stats|audit"); return
    await _do_export(message, parts[1])


@router.callback_query(F.data.startswith("own:exp:"))
@owner_only
async def cb_export(call: CallbackQuery) -> None:
    kind = call.data.split(":")[2]
    await call.answer("⏳ Generating…")
    await _do_export(call.message, kind)


async def _do_export(message: Message, kind: str) -> None:
    if kind == "users":
        rows  = await db.get_all_users()
        buf   = io.StringIO()
        cols  = ["user_id","username","full_name","is_banned","total_gen","created_at"]
        w     = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: str(r.get(c,"")) for c in cols})
        data, fname = buf.getvalue().encode(), "users.csv"

    elif kind == "stats":
        stats = await db.get_stats()
        data, fname = json.dumps(stats, indent=2, default=str).encode(), "stats.json"

    elif kind == "audit":
        recs  = await db.get_audit(limit=5000)
        data  = json.dumps([dict(r) for r in recs], indent=2, default=str).encode()
        fname = "audit.json"
    else:
        return

    await message.answer_document(
        BufferedInputFile(data, filename=fname),
        caption=f"📤 <b>Export: {kind}</b>", parse_mode="HTML"
    )


# ── Maintenance ───────────────────────────────────────────────────────────

@router.message(Command("maintenance"))
@owner_only
async def cmd_maintenance(message: Message) -> None:
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2 or parts[1].lower() not in ("on","off"):
        await message.answer("Usage: /maintenance on|off [message]"); return
    on = parts[1].lower() == "on"
    await db.set_setting("maintenance", "true" if on else "false")
    if on and len(parts) > 2:
        await db.set_setting("maintenance_msg", parts[2])
    await message.answer(
        "🔧 Maintenance <b>ON</b>" if on else "✅ Maintenance <b>OFF</b>",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "own:maint:on")
@owner_only
async def cb_maint_on(call: CallbackQuery) -> None:
    await db.set_setting("maintenance", "true")
    await call.answer("🔧 Maintenance ON", show_alert=True)


@router.callback_query(F.data == "own:maint:off")
@owner_only
async def cb_maint_off(call: CallbackQuery) -> None:
    await db.set_setting("maintenance", "false")
    await call.answer("✅ Maintenance OFF", show_alert=True)


# ── Purge ─────────────────────────────────────────────────────────────────

@router.message(Command("purge"))
@owner_only
async def cmd_purge(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /purge <user_id>"); return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id must be a number."); return
    await db.purge_user(uid, message.from_user.id)
    await message.answer(
        f"🗑 User <code>{uid}</code> and all their data have been permanently deleted.",
        parse_mode="HTML"
    )
