"""keyboards.py — Every InlineKeyboardMarkup in one place."""
from __future__ import annotations
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def home_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="💳 UPI QR",     callback_data="gen:upi"),
        InlineKeyboardButton(text="🔗 Other QR",   callback_data="gen:other"),
    )
    b.row(
        InlineKeyboardButton(text="💾 My Payees",  callback_data="payees:list"),
        InlineKeyboardButton(text="🕘 History",    callback_data="history:list"),
    )
    b.row(
        InlineKeyboardButton(text="🎨 Templates",  callback_data="templates:list"),
        InlineKeyboardButton(text="⚙️ Settings",   callback_data="settings:main"),
    )
    b.row(
        InlineKeyboardButton(text="👤 Profile",    callback_data="profile:view"),
        InlineKeyboardButton(text="❓ Help",        callback_data="help:main"),
    )
    b.row(InlineKeyboardButton(text="⭐ Donate Stars", callback_data="donate:stars"))
    return b.as_markup()


def qr_type_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🌐 URL",    callback_data="qrtype:url"),
        InlineKeyboardButton(text="📝 Text",   callback_data="qrtype:text"),
    )
    b.row(
        InlineKeyboardButton(text="📶 Wi-Fi",  callback_data="qrtype:wifi"),
        InlineKeyboardButton(text="👤 vCard",  callback_data="qrtype:vcard"),
    )
    b.row(
        InlineKeyboardButton(text="✉️ Email",  callback_data="qrtype:email"),
        InlineKeyboardButton(text="💬 SMS",    callback_data="qrtype:sms"),
    )
    b.row(InlineKeyboardButton(text="📍 Geo",  callback_data="qrtype:geo"))
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def templates_kb(all_t: list[dict], current: str, page: int = 0) -> InlineKeyboardMarkup:
    b   = InlineKeyboardBuilder()
    PPG = 6
    sl  = all_t[page*PPG:(page+1)*PPG]
    for t in sl:
        chk = "✅ " if t["id"] == current else ""
        b.row(InlineKeyboardButton(
            text=f"{t['emoji']}  {chk}{t['name']}",
            callback_data=f"tpl:sel:{t['id']}",
        ))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"tpl:pg:{page-1}"))
    if (page+1)*PPG < len(all_t):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"tpl:pg:{page+1}"))
    if nav: b.row(*nav)
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def size_kb(current: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    opts = [
        ("📱 Portrait  1080×1350", "1080x1350"),
        ("⬛ Square   1080×1080",  "1080x1080"),
        ("🔲 HD QR    2048×2048",  "2048x2048"),
    ]
    for lbl, val in opts:
        ck = "✅ " if val == current else ""
        b.row(InlineKeyboardButton(text=f"{ck}{lbl}", callback_data=f"size:sel:{val}"))
    b.row(InlineKeyboardButton(text="⬅️ Back", callback_data="settings:main"))
    return b.as_markup()


def payees_kb(payees: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in payees:
        amt = f"  ₹{float(p['amount']):.0f}" if p.get("amount") else ""
        b.row(InlineKeyboardButton(
            text=f"💳 {p['label']}{amt}",
            callback_data=f"payee:gen:{p['id']}",
        ))
    b.row(
        InlineKeyboardButton(text="➕ Add Payee", callback_data="payee:add"),
        InlineKeyboardButton(text="🗑 Manage",    callback_data="payee:manage"),
    )
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def payee_manage_kb(payees: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in payees:
        b.row(InlineKeyboardButton(
            text=f"🗑 {p['label']}",
            callback_data=f"payee:del:{p['id']}",
        ))
    b.row(InlineKeyboardButton(text="⬅️ Back", callback_data="payees:list"))
    return b.as_markup()


def history_kb(recs: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in recs:
        d = str(r["created_at"])[:10]
        b.row(InlineKeyboardButton(
            text=f"🔄 {r['qr_type'].upper()} · {d}",
            callback_data=f"hist:regen:{r['id']}",
        ))
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def settings_kb(us: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    wm = "✅ On" if us.get("watermark_on") else "❌ Off"
    b.row(InlineKeyboardButton(text=f"💧 Watermark: {wm}", callback_data="settings:wm_toggle"))
    b.row(
        InlineKeyboardButton(text="🎨 Template",   callback_data="templates:list"),
        InlineKeyboardButton(text="📐 Size",       callback_data="settings:size"),
    )
    b.row(
        InlineKeyboardButton(text="🖼 Set Logo",   callback_data="settings:setlogo"),
        InlineKeyboardButton(text="🗑 Del Logo",   callback_data="settings:dellogo"),
    )
    b.row(InlineKeyboardButton(text="❌ Delete My Data", callback_data="settings:deleteme"))
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def admin_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📊 Stats",      callback_data="adm:stats"),
        InlineKeyboardButton(text="🏥 Health",     callback_data="adm:health"),
    )
    b.row(
        InlineKeyboardButton(text="📢 Broadcast",  callback_data="adm:broadcast"),
        InlineKeyboardButton(text="📋 Audit",      callback_data="adm:audit"),
    )
    b.row(
        InlineKeyboardButton(text="💧 Watermark",  callback_data="adm:wm"),
        InlineKeyboardButton(text="🔐 ForceSub",   callback_data="adm:fs"),
    )
    b.row(
        InlineKeyboardButton(text="🚫 Ban",        callback_data="adm:ban"),
        InlineKeyboardButton(text="✅ Unban",      callback_data="adm:unban"),
    )
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def owner_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Add Admin",  callback_data="own:addadmin"),
        InlineKeyboardButton(text="➖ Del Admin",  callback_data="own:deladmin"),
    )
    b.row(
        InlineKeyboardButton(text="📤 Export Users", callback_data="own:exp:users"),
        InlineKeyboardButton(text="📤 Export Stats", callback_data="own:exp:stats"),
    )
    b.row(
        InlineKeyboardButton(text="🔧 Maintenance On",  callback_data="own:maint:on"),
        InlineKeyboardButton(text="✅ Maintenance Off", callback_data="own:maint:off"),
    )
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def forcesub_kb(chats: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in chats:
        title = c.get("title") or "Join Channel"
        url   = (f"https://t.me/{c['username'].lstrip('@')}"
                 if c.get("username") else c.get("invite_link",""))
        if url:
            b.row(InlineKeyboardButton(text=f"📢 {title}", url=url))
    b.row(InlineKeyboardButton(text="✅ Verify", callback_data="fs:verify"))
    return b.as_markup()


def confirm_kb(yes: str, no: str = "home") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Yes", callback_data=yes),
        InlineKeyboardButton(text="❌ No",  callback_data=no),
    )
    return b.as_markup()


def back_kb(cb: str = "home") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⬅️ Back", callback_data=cb))
    return b.as_markup()


def home_btn() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()
