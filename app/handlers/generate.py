"""generate.py — UPI + all QR type wizards with FSM."""
from __future__ import annotations
import io
from typing import Optional
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from PIL import Image

from app.config import settings
from app.database import db
from app.logger import get_logger
from app.services.qr_engine import (
    UPIParams, validate_vpa, parse_amount,
    build_upi, build_url, build_text, build_wifi,
    build_vcard, build_email, build_sms, build_geo,
)
from app.services.renderer import render_poster
from app.utils.helpers import fetch_logo, qr_icon
from app.utils.keyboards import back_kb, home_btn, qr_type_kb

log = get_logger(__name__)
router = Router(name="generate")


# ── FSM ───────────────────────────────────────────────────────────────────

class UPI(StatesGroup):
    vpa    = State()
    name   = State()
    amount = State()
    note   = State()

class QR(StatesGroup):
    url        = State()
    text       = State()
    wifi_ssid  = State()
    wifi_pass  = State()
    vc_name    = State()
    vc_phone   = State()
    vc_email   = State()
    vc_org     = State()
    em_to      = State()
    em_subj    = State()
    em_body    = State()
    sms_phone  = State()
    sms_msg    = State()
    geo_lat    = State()
    geo_lon    = State()


# ── Entry points ──────────────────────────────────────────────────────────

@router.message(Command("upi"))
@router.callback_query(F.data == "gen:upi")
async def start_upi(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(UPI.vpa)
    text = (
        "💳 <b>UPI QR Wizard</b>  1/4\n\n"
        "Enter the <b>UPI ID / VPA</b>:\n"
        "<i>e.g.  name@upi  ·  mobile@paytm  ·  handle@okaxis</i>"
    )
    _reply(event, text, back_kb("home"))


@router.message(Command("generate"))
@router.callback_query(F.data == "gen:other")
async def start_other(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = "🔗 <b>QR Code Generator</b>\n\nChoose the type:"
    _reply(event, text, qr_type_kb())


@router.callback_query(F.data.startswith("qrtype:"))
async def pick_type(call: CallbackQuery, state: FSMContext) -> None:
    qt = call.data.split(":")[1]
    await state.update_data(qr_type=qt)
    await _start_wizard(call, state, qt)
    await call.answer()


# ── Shortcut commands ─────────────────────────────────────────────────────

@router.message(Command("qr"))
async def cmd_qr(m: Message, state: FSMContext) -> None:
    await state.clear()
    await m.answer("🔗 Choose QR type:", reply_markup=qr_type_kb())

@router.message(Command("qr_url"))
async def cmd_url(m: Message, s: FSMContext) -> None:
    await s.set_state(QR.url); await s.update_data(qr_type="url")
    await m.answer("🌐 Enter the URL:", reply_markup=back_kb("home"))

@router.message(Command("qr_text"))
async def cmd_text(m: Message, s: FSMContext) -> None:
    await s.set_state(QR.text); await s.update_data(qr_type="text")
    await m.answer("📝 Enter the text:", reply_markup=back_kb("home"))

@router.message(Command("qr_wifi"))
async def cmd_wifi(m: Message, s: FSMContext) -> None:
    await s.update_data(qr_type="wifi"); await s.set_state(QR.wifi_ssid)
    await m.answer("📶 Enter Wi-Fi network name (SSID):", reply_markup=back_kb("home"))

@router.message(Command("qr_vcard"))
async def cmd_vc(m: Message, s: FSMContext) -> None:
    await s.update_data(qr_type="vcard"); await s.set_state(QR.vc_name)
    await m.answer("👤 Enter the contact's full name:", reply_markup=back_kb("home"))

@router.message(Command("qr_email"))
async def cmd_email(m: Message, s: FSMContext) -> None:
    await s.update_data(qr_type="email"); await s.set_state(QR.em_to)
    await m.answer("✉️ Enter recipient email address:", reply_markup=back_kb("home"))

@router.message(Command("qr_sms"))
async def cmd_sms(m: Message, s: FSMContext) -> None:
    await s.update_data(qr_type="sms"); await s.set_state(QR.sms_phone)
    await m.answer("💬 Enter phone number (with country code):", reply_markup=back_kb("home"))

@router.message(Command("qr_geo"))
async def cmd_geo(m: Message, s: FSMContext) -> None:
    await s.update_data(qr_type="geo"); await s.set_state(QR.geo_lat)
    await m.answer("📍 Enter latitude (e.g. 28.6139):", reply_markup=back_kb("home"))


# ── UPI FSM ───────────────────────────────────────────────────────────────

@router.message(UPI.vpa)
async def upi_vpa(m: Message, s: FSMContext) -> None:
    vpa = m.text.strip()
    if not validate_vpa(vpa):
        await m.answer("❌ Invalid UPI ID format.\nTry: <code>name@upi</code> or <code>9876@paytm</code>",
                       parse_mode="HTML"); return
    await s.update_data(vpa=vpa)
    await s.set_state(UPI.name)
    await m.answer(f"✅ VPA: <code>{vpa}</code>\n\n<b>2/4</b> — Enter the <b>payee name</b>:",
                   parse_mode="HTML")


@router.message(UPI.name)
async def upi_name(m: Message, s: FSMContext) -> None:
    name = m.text.strip()[:50]
    await s.update_data(payee_name=name)
    await s.set_state(UPI.amount)
    await m.answer(f"✅ Name: <b>{name}</b>\n\n<b>3/4</b> — Enter <b>amount ₹</b> or <code>0</code> to skip:",
                   parse_mode="HTML")


@router.message(UPI.amount)
async def upi_amount(m: Message, s: FSMContext) -> None:
    amt = parse_amount(m.text.strip())
    if amt is None:
        await m.answer("❌ Invalid amount. Enter a number or 0 to skip:"); return
    await s.update_data(amount=amt if amt > 0 else None)
    await s.set_state(UPI.note)
    await m.answer("<b>4/4</b> — Enter a <b>payment note</b> or send <code>skip</code>:",
                   parse_mode="HTML")


@router.message(UPI.note)
async def upi_note(m: Message, s: FSMContext) -> None:
    note = None if m.text.strip().lower() == "skip" else m.text.strip()[:50]
    d    = await s.get_data()
    await s.clear()
    p = UPIParams(vpa=d["vpa"], payee_name=d["payee_name"],
                  amount=d.get("amount"), note=note)
    await _send_poster(m, build_upi(p), "upi",
                       payee_name=d["payee_name"], vpa=d["vpa"], amount=d.get("amount"))


# ── Generic QR FSM ────────────────────────────────────────────────────────

@router.message(QR.url)
async def qr_url(m: Message, s: FSMContext) -> None:
    await s.clear(); await _send_poster(m, build_url(m.text.strip()), "url")

@router.message(QR.text)
async def qr_text(m: Message, s: FSMContext) -> None:
    await s.clear(); await _send_poster(m, build_text(m.text.strip()), "text")

# Wi-Fi
@router.message(QR.wifi_ssid)
async def wifi_ssid(m: Message, s: FSMContext) -> None:
    await s.update_data(ssid=m.text.strip()); await s.set_state(QR.wifi_pass)
    await m.answer("Password? (or send <code>open</code> for no password):", parse_mode="HTML")

@router.message(QR.wifi_pass)
async def wifi_pass(m: Message, s: FSMContext) -> None:
    pw = m.text.strip(); d = await s.get_data(); await s.clear()
    auth = "nopass" if pw.lower() == "open" else "WPA"
    pwd  = "" if pw.lower() == "open" else pw
    await _send_poster(m, build_wifi(d["ssid"], pwd, auth), "wifi", label=f"Wi-Fi: {d['ssid']}")

# vCard
@router.message(QR.vc_name)
async def vc_name(m: Message, s: FSMContext) -> None:
    await s.update_data(vn=m.text.strip()); await s.set_state(QR.vc_phone)
    await m.answer("Phone number? (or <code>skip</code>):", parse_mode="HTML")

@router.message(QR.vc_phone)
async def vc_phone(m: Message, s: FSMContext) -> None:
    ph = "" if m.text.strip().lower()=="skip" else m.text.strip()
    await s.update_data(vp=ph); await s.set_state(QR.vc_email)
    await m.answer("Email? (or <code>skip</code>):", parse_mode="HTML")

@router.message(QR.vc_email)
async def vc_email(m: Message, s: FSMContext) -> None:
    em = "" if m.text.strip().lower()=="skip" else m.text.strip()
    await s.update_data(ve=em); await s.set_state(QR.vc_org)
    await m.answer("Organisation? (or <code>skip</code>):", parse_mode="HTML")

@router.message(QR.vc_org)
async def vc_org(m: Message, s: FSMContext) -> None:
    org = "" if m.text.strip().lower()=="skip" else m.text.strip()
    d   = await s.get_data(); await s.clear()
    await _send_poster(m, build_vcard(d["vn"], d.get("vp",""), d.get("ve",""), org),
                       "vcard", label=d["vn"])

# Email
@router.message(QR.em_to)
async def em_to(m: Message, s: FSMContext) -> None:
    await s.update_data(et=m.text.strip()); await s.set_state(QR.em_subj)
    await m.answer("Subject? (or <code>skip</code>):", parse_mode="HTML")

@router.message(QR.em_subj)
async def em_subj(m: Message, s: FSMContext) -> None:
    subj = "" if m.text.strip().lower()=="skip" else m.text.strip()
    await s.update_data(es=subj); await s.set_state(QR.em_body)
    await m.answer("Message body? (or <code>skip</code>):", parse_mode="HTML")

@router.message(QR.em_body)
async def em_body(m: Message, s: FSMContext) -> None:
    body = "" if m.text.strip().lower()=="skip" else m.text.strip()
    d    = await s.get_data(); await s.clear()
    await _send_poster(m, build_email(d["et"], d.get("es",""), body), "email", label=d["et"])

# SMS
@router.message(QR.sms_phone)
async def sms_phone(m: Message, s: FSMContext) -> None:
    await s.update_data(sp=m.text.strip()); await s.set_state(QR.sms_msg)
    await m.answer("Message? (or <code>skip</code>):", parse_mode="HTML")

@router.message(QR.sms_msg)
async def sms_msg(m: Message, s: FSMContext) -> None:
    msg = "" if m.text.strip().lower()=="skip" else m.text.strip()
    d   = await s.get_data(); await s.clear()
    await _send_poster(m, build_sms(d["sp"], msg), "sms", label=d["sp"])

# Geo
@router.message(QR.geo_lat)
async def geo_lat(m: Message, s: FSMContext) -> None:
    try: lat = float(m.text.strip())
    except ValueError: await m.answer("❌ Invalid. Enter decimal like 28.6139:"); return
    await s.update_data(lat=lat); await s.set_state(QR.geo_lon)
    await m.answer("Longitude? (e.g. 77.2090):")

@router.message(QR.geo_lon)
async def geo_lon(m: Message, s: FSMContext) -> None:
    try: lon = float(m.text.strip())
    except ValueError: await m.answer("❌ Invalid longitude:"); return
    d = await s.get_data(); await s.clear()
    await _send_poster(m, build_geo(d["lat"], lon), "geo",
                       label=f"{d['lat']:.4f}, {lon:.4f}")


# ── Core send ─────────────────────────────────────────────────────────────

async def _send_poster(
    message: Message,
    payload: str,
    qr_type: str,
    label: str = "",
    payee_name: str = "",
    vpa: str = "",
    amount: Optional[float] = None,
) -> None:
    uid = message.from_user.id
    us  = await db.get_user_settings(uid)
    usr = await db.get_user(uid)

    wm_global = await db.get_setting("watermark_enabled","true") == "true"
    wm_text   = await db.get_setting("watermark_text", settings.default_watermark) if wm_global else None
    if wm_text and not us.get("watermark_on", True):
        wm_text = None

    logo: Optional[Image.Image] = None
    if usr and usr.get("logo_file_id"):
        logo = await fetch_logo(message.bot, usr["logo_file_id"])

    thinking = await message.answer("⏳ Generating your poster…")

    try:
        img_bytes = render_poster(
            payload=payload,
            qr_type=qr_type,
            theme_id=us.get("template","minimal_pro"),
            size=us.get("output_size","1080x1350"),
            label=label,
            payee_name=payee_name,
            vpa=vpa,
            amount=amount,
            watermark=wm_text,
            logo=logo,
        )
    except Exception as exc:
        log.error("render_failed", uid=uid, error=str(exc), exc_info=True)
        await thinking.delete()
        await message.answer("❌ Generation failed. Please try again.")
        return

    await thinking.delete()

    caption = _caption(qr_type, payee_name, vpa, amount)
    sent    = await message.answer_photo(
        BufferedInputFile(img_bytes, "poster.png"),
        caption=caption,
        parse_mode="HTML",
        reply_markup=home_btn(),
    )

    fid = sent.photo[-1].file_id if sent.photo else None
    await db.add_history(uid, qr_type, payload,
                         us.get("template","minimal_pro"),
                         us.get("output_size","1080x1350"), fid)
    await db.increment_generated(uid)


def _caption(qt: str, name: str, vpa: str, amt: Optional[float]) -> str:
    if qt == "upi":
        lines = [f"{qr_icon(qt)} <b>UPI Payment QR</b>"]
        if name: lines.append(f"👤 {name}")
        if vpa:  lines.append(f"🔗 <code>{vpa}</code>")
        if amt:  lines.append(f"💰 ₹ {amt:,.2f}")
        lines.append("\n<i>Scan with any UPI app to pay instantly.</i>")
        return "\n".join(lines)
    return f"{qr_icon(qt)} <b>{qt.upper()} QR</b>\n<i>Scan with your camera or QR reader.</i>"


# ── Helper ────────────────────────────────────────────────────────────────

def _reply(event: Message | CallbackQuery, text: str, kb) -> None:
    import asyncio
    if isinstance(event, Message):
        asyncio.ensure_future(event.answer(text, parse_mode="HTML", reply_markup=kb))
    else:
        asyncio.ensure_future(event.message.edit_text(text, parse_mode="HTML", reply_markup=kb))


async def _start_wizard(event: Message | CallbackQuery, state: FSMContext, qt: str) -> None:
    p = {
        "url":   ("🌐 URL QR",    "Enter the URL:",               QR.url),
        "text":  ("📝 Text QR",   "Enter the text:",              QR.text),
        "wifi":  ("📶 Wi-Fi QR",  "Enter the network name (SSID):", QR.wifi_ssid),
        "vcard": ("👤 vCard QR",  "Enter the contact's full name:", QR.vc_name),
        "email": ("✉️ Email QR",  "Enter recipient email:",        QR.em_to),
        "sms":   ("💬 SMS QR",    "Enter phone number:",           QR.sms_phone),
        "geo":   ("📍 Geo QR",    "Enter latitude (e.g. 28.6139):", QR.geo_lat),
    }
    title, prompt, st = p.get(qt, ("QR","Enter value:", QR.text))
    await state.set_state(st)
    text = f"<b>{title}</b>\n\n{prompt}"
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=back_kb("home"))
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb("home"))
