"""
qr_engine.py — Pure QR payload builders + high-quality segno rendering.
All builders are side-effect-free and fully unit-testable.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote, urlencode

import segno
from PIL import Image, ImageDraw, ImageFilter

from app.logger import get_logger

log = get_logger(__name__)


# ── Validators ────────────────────────────────────────────────────────────

def validate_vpa(vpa: str) -> bool:
    """Format-only VPA check. Does NOT verify with any bank or payment network."""
    return bool(re.match(r"^[\w.\-]{2,64}@[a-zA-Z]{2,32}$", vpa.strip()))


def parse_amount(text: str) -> Optional[float]:
    try:
        v = float(text.replace(",", "").replace("₹", "").strip())
        return round(v, 2) if 0 < v <= 1_00_00_000 else None
    except ValueError:
        return None


# ── UPI ───────────────────────────────────────────────────────────────────

@dataclass
class UPIParams:
    vpa: str
    payee_name: str
    amount: Optional[float] = None
    note: Optional[str] = None
    ref: Optional[str] = None
    currency: str = "INR"


def build_upi(p: UPIParams) -> str:
    """Produce a standards-compliant UPI deep-link URI."""
    parts = {
        "pa": p.vpa.strip(),
        "pn": p.payee_name.strip(),
        "cu": p.currency,
    }
    if p.amount and p.amount > 0:
        parts["am"] = f"{p.amount:.2f}"
    if p.note:
        parts["tn"] = p.note.strip()[:50]
    if p.ref:
        parts["tr"] = p.ref.strip()[:35]
    qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in parts.items())
    return f"upi://pay?{qs}"


# ── Other QR types ────────────────────────────────────────────────────────

def build_url(url: str) -> str:
    return url if url.startswith(("http://", "https://", "ftp://")) else f"https://{url}"


def build_text(text: str) -> str:
    return text


def build_wifi(ssid: str, password: str, auth: str = "WPA", hidden: bool = False) -> str:
    def esc(s: str) -> str:
        for c in ("\\", ";", ",", '"', ":"):
            s = s.replace(c, f"\\{c}")
        return s
    h = "true" if hidden else "false"
    return f"WIFI:T:{auth};S:{esc(ssid)};P:{esc(password)};H:{h};;"


def build_vcard(name: str, phone: str = "", email: str = "",
                org: str = "", url: str = "") -> str:
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"N:{name}", f"FN:{name}"]
    if phone: lines.append(f"TEL:{phone}")
    if email: lines.append(f"EMAIL:{email}")
    if org:   lines.append(f"ORG:{org}")
    if url:   lines.append(f"URL:{url}")
    lines.append("END:VCARD")
    return "\n".join(lines)


def build_email(to: str, subject: str = "", body: str = "") -> str:
    qs = urlencode({k: v for k, v in [("subject", subject), ("body", body)] if v})
    return f"mailto:{to}{'?' + qs if qs else ''}"


def build_sms(phone: str, msg: str = "") -> str:
    return f"sms:{phone}{'?body=' + quote(msg, safe='') if msg else ''}"


def build_geo(lat: float, lon: float, label: str = "") -> str:
    base = f"geo:{lat},{lon}"
    return f"{base}?q={quote(label, safe='')}" if label else base


# ── QR Image rendering ────────────────────────────────────────────────────

_EC = {
    "L": segno.QRErrorCorrection.L,
    "M": segno.QRErrorCorrection.M,
    "Q": segno.QRErrorCorrection.Q,
    "H": segno.QRErrorCorrection.H,
}


def render_qr_image(
    data: str,
    size_px: int = 1024,
    dark: str = "#000000",
    light: str = "#FFFFFF",
    ec: str = "Q",
    logo: Optional[Image.Image] = None,
) -> Image.Image:
    """
    Render a crisp QR code with segno.
    Auto-upgrades to H error correction when logo overlay is used.
    Quiet zone = 4 modules (WCAG / scan reliability standard).
    Returns RGBA PIL Image at exactly size_px × size_px.
    """
    real_ec = "H" if logo else ec
    qr = segno.make_qr(data, error=_EC.get(real_ec.upper(), segno.QRErrorCorrection.Q))

    quiet = 4
    modules = qr.symbol_size()[0]
    total   = modules + quiet * 2
    scale   = max(1, size_px // total)

    buf = io.BytesIO()
    qr.save(buf, kind="PNG", scale=scale, border=quiet, dark=dark, light=light)
    buf.seek(0)
    img = Image.open(buf).convert("RGBA").resize((size_px, size_px), Image.LANCZOS)

    if logo:
        img = _overlay_logo(img, logo)
    return img


def _overlay_logo(qr: Image.Image, logo: Image.Image) -> Image.Image:
    """Centre logo on QR; max 15% coverage, rounded corners, white pad, soft shadow."""
    sz = qr.size[0]
    max_logo = int(sz * (0.15 ** 0.5))  # area-based limit

    logo = logo.convert("RGBA")
    logo.thumbnail((max_logo, max_logo), Image.LANCZOS)
    lw, lh = logo.size
    radius = min(lw, lh) // 5

    # Rounded mask
    mask = Image.new("L", (lw, lh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, lw-1, lh-1], radius=radius, fill=255)
    logo.putalpha(mask)

    # Shadow
    pad = max(3, sz // 120)
    sdw_layer = Image.new("RGBA", qr.size, (0,0,0,0))
    sdw_logo  = Image.new("RGBA", (lw, lh), (0,0,0,70))
    sdw_logo.putalpha(mask)
    sx = (sz - lw) // 2 + pad
    sy = (sz - lh) // 2 + pad
    sdw_layer.paste(sdw_logo, (sx, sy), sdw_logo)
    sdw_layer = sdw_layer.filter(ImageFilter.GaussianBlur(radius=pad*2))
    qr = Image.alpha_composite(qr, sdw_layer)

    # White backing
    bw, bh = lw + pad*2, lh + pad*2
    back = Image.new("RGBA", (bw, bh), (255,255,255,255))
    bm = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(bm).rounded_rectangle([0,0,bw-1,bh-1], radius=radius+pad, fill=255)
    back.putalpha(bm)
    bx = (sz - bw) // 2
    by = (sz - bh) // 2
    qr.paste(back, (bx, by), back)

    # Logo
    lx = (sz - lw) // 2
    ly = (sz - lh) // 2
    qr.paste(logo, (lx, ly), logo)
    return qr
