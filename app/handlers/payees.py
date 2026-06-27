"""payees.py — Saved payees: list, add (5-step wizard), 1-tap generate, delete."""
from __future__ import annotations
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.services.qr_engine import UPIParams, build_upi, validate_vpa, parse_amount
from app.utils.keyboards import (
    back_kb, confirm_kb, home_btn, payees_kb, payee_manage_kb,
)

router = Router(name="payees")


class AddPayee(StatesGroup):
    label  = State()
    vpa    = State()
    name   = State()
    amount = State()
    note   = State()


# ── /mypayees ─────────────────────────────────────────────────────────────

@router.message(Command("mypayees"))
@router.callback_query(F.data == "payees:list")
async def cmd_payees(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    uid    = event.from_user.id
    payees = await db.get_payees(uid)

    if not payees:
        text = (
            "💾 <b>My Payees</b>\n\n"
            "No saved payees yet.\n\n"
            "Tap <b>Add Payee</b> to save a UPI ID for instant 1-tap generation."
        )
    else:
        text = (
            f"💾 <b>My Payees</b>  ·  {len(payees)} saved\n\n"
            "Tap any payee to instantly generate their poster."
        )

    kb = payees_kb(payees)
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


# ── Add payee wizard ──────────────────────────────────────────────────────

@router.callback_query(F.data == "payee:add")
async def cb_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddPayee.label)
    await call.message.edit_text(
        "➕ <b>Add Payee</b>  1/5\n\n"
        "Enter a <b>label</b> for this payee:\n"
        "<i>e.g.  Home Rent  ·  Mom  ·  Office Canteen</i>",
        parse_mode="HTML", reply_markup=back_kb("payees:list")
    )
    await call.answer()


@router.message(AddPayee.label)
async def ap_label(m: Message, s: FSMContext) -> None:
    label = m.text.strip()[:40]
    await s.update_data(label=label)
    await s.set_state(AddPayee.vpa)
    await m.answer(
        f"✅ Label: <b>{label}</b>\n\n"
        "<b>2/5</b> — Enter the <b>UPI ID / VPA</b>:",
        parse_mode="HTML"
    )


@router.message(AddPayee.vpa)
async def ap_vpa(m: Message, s: FSMContext) -> None:
    vpa = m.text.strip()
    if not validate_vpa(vpa):
        await m.answer("❌ Invalid UPI ID. Try: <code>name@upi</code>", parse_mode="HTML")
        return
    await s.update_data(vpa=vpa)
    await s.set_state(AddPayee.name)
    await m.answer(
        f"✅ VPA: <code>{vpa}</code>\n\n"
        "<b>3/5</b> — Enter the <b>payee name</b>:",
        parse_mode="HTML"
    )


@router.message(AddPayee.name)
async def ap_name(m: Message, s: FSMContext) -> None:
    name = m.text.strip()[:50]
    await s.update_data(payee_name=name)
    await s.set_state(AddPayee.amount)
    await m.answer(
        f"✅ Name: <b>{name}</b>\n\n"
        "<b>4/5</b> — Default amount ₹? (or <code>0</code> to skip)",
        parse_mode="HTML"
    )


@router.message(AddPayee.amount)
async def ap_amount(m: Message, s: FSMContext) -> None:
    amt = parse_amount(m.text.strip())
    if amt is None:
        await m.answer("❌ Invalid amount. Enter a number or 0:")
        return
    await s.update_data(amount=amt if amt > 0 else None)
    await s.set_state(AddPayee.note)
    await m.answer("<b>5/5</b> — Default note? (or <code>skip</code>)", parse_mode="HTML")


@router.message(AddPayee.note)
async def ap_note(m: Message, s: FSMContext) -> None:
    note = None if m.text.strip().lower() == "skip" else m.text.strip()[:50]
    d    = await s.get_data()
    await s.clear()

    await db.add_payee(
        m.from_user.id, d["label"], d["vpa"],
        d["payee_name"], d.get("amount"), note
    )
    await m.answer(
        f"✅ <b>Payee saved!</b>\n\n"
        f"💳 {d['label']}\n"
        f"🔗 <code>{d['vpa']}</code>\n"
        f"👤 {d['payee_name']}\n\n"
        "Find it in /mypayees for instant 1-tap generation.",
        parse_mode="HTML", reply_markup=home_btn()
    )


# ── 1-tap generate ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("payee:gen:"))
async def cb_gen(call: CallbackQuery) -> None:
    pid   = int(call.data.split(":")[2])
    payee = await db.get_payee(pid, call.from_user.id)
    if not payee:
        await call.answer("❌ Payee not found.", show_alert=True)
        return

    payload = build_upi(UPIParams(
        vpa=payee["vpa"],
        payee_name=payee["name"],
        amount=float(payee["amount"]) if payee.get("amount") else None,
        note=payee.get("note"),
    ))
    await call.answer("⏳ Generating…")

    from app.handlers.generate import _send_poster
    await _send_poster(
        call.message, payload, "upi",
        label=payee["label"],
        payee_name=payee["name"],
        vpa=payee["vpa"],
        amount=float(payee["amount"]) if payee.get("amount") else None,
    )


# ── Manage / Delete ───────────────────────────────────────────────────────

@router.callback_query(F.data == "payee:manage")
async def cb_manage(call: CallbackQuery) -> None:
    payees = await db.get_payees(call.from_user.id)
    if not payees:
        await call.answer("Nothing to manage.", show_alert=True)
        return
    await call.message.edit_text(
        "🗑 <b>Manage Payees</b>\n\nTap a payee to delete it:",
        parse_mode="HTML", reply_markup=payee_manage_kb(payees)
    )
    await call.answer()


@router.callback_query(F.data.startswith("payee:del:"))
async def cb_del(call: CallbackQuery) -> None:
    pid   = int(call.data.split(":")[2])
    payee = await db.get_payee(pid, call.from_user.id)
    if not payee:
        await call.answer("❌ Not found.", show_alert=True)
        return
    await call.message.edit_text(
        f"🗑 Delete <b>{payee['label']}</b>?",
        parse_mode="HTML",
        reply_markup=confirm_kb(f"payee:confirm:{pid}", "payee:manage")
    )
    await call.answer()


@router.callback_query(F.data.startswith("payee:confirm:"))
async def cb_del_confirm(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[2])
    await db.del_payee(pid, call.from_user.id)
    await call.answer("✅ Deleted.", show_alert=False)
    payees = await db.get_payees(call.from_user.id)
    await call.message.edit_text(
        "💾 <b>My Payees</b>\n\nPayee deleted.",
        parse_mode="HTML", reply_markup=payees_kb(payees)
    )
