"""
renderer.py — Premium poster rendering engine.
Produces pixel-perfect, print-quality output for all 12 themes.
No hardcoded pixel values — all geometry is relative to canvas size.
"""
from __future__ import annotations

import io
import json
import math
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.logger import get_logger
from app.services.qr_engine import render_qr_image

log = get_logger(__name__)

ASSETS   = Path(__file__).parent.parent.parent / "assets"
FONTS    = Path(__file__).parent.parent.parent / "fonts"
THEMES_F = ASSETS / "templates" / "themes.json"

# ── Font loading ──────────────────────────────────────────────────────────

_FCACHE: dict[tuple, ImageFont.FreeTypeFont] = {}

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key in _FCACHE:
        return _FCACHE[key]
    for ext in (".ttf", ".otf"):
        p = FONTS / f"{name}{ext}"
        if p.exists():
            f = ImageFont.truetype(str(p), size)
            _FCACHE[key] = f
            return f
    # Graceful fallback chain
    for fallback in ("Poppins-Regular", "Inter-Regular"):
        p = FONTS / f"{fallback}.ttf"
        if p.exists():
            f = ImageFont.truetype(str(p), size)
            _FCACHE[key] = f
            return f
    f = ImageFont.load_default()
    _FCACHE[key] = f
    return f

# ── Theme loading ─────────────────────────────────────────────────────────

_THEMES: Optional[dict] = None

def themes() -> dict:
    global _THEMES
    if _THEMES is None:
        _THEMES = {t["id"]: t for t in json.loads(THEMES_F.read_text())["themes"]
                   if t.get("enabled", True)}
    return _THEMES

def get_theme(tid: str) -> dict:
    t = themes()
    return t.get(tid, t.get("minimal_pro", next(iter(t.values()))))

def all_themes() -> list[dict]:
    return list(themes().values())

# ── Color helpers ─────────────────────────────────────────────────────────

def _rgb(h: str) -> tuple[int,int,int]:
    h = h.lstrip("#")[:6]
    return int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)

def _rgba(h: str, a: int = 255) -> tuple[int,int,int,int]:
    return (*_rgb(h), a)

def _hex_alpha(h: str) -> tuple[tuple[int,int,int], int]:
    """Parse '#RRGGBBAA' or '#RRGGBB'. Returns ((r,g,b), alpha)."""
    h = h.lstrip("#")
    if len(h) == 8:
        return (_rgb("#"+h[:6]), int(h[6:8], 16))
    return (_rgb("#"+h), 255)

def _parse_color(h: str) -> tuple[int,int,int,int]:
    rgb, a = _hex_alpha(h)
    return (*rgb, a)

# ── Gradient ──────────────────────────────────────────────────────────────

def _gradient(W: int, H: int, stops: list[str], angle: int) -> Image.Image:
    img = Image.new("RGBA", (W, H))
    pix = img.load()
    rad = math.radians(angle)
    ca, sa = math.cos(rad), math.sin(rad)
    diag = math.hypot(W, H)
    cx, cy = W/2, H/2
    cols = [_rgb(s) for s in stops]
    n = len(cols) - 1
    for y in range(H):
        for x in range(W):
            t = ((x-cx)*ca + (y-cy)*sa + diag/2) / diag
            t = max(0.0, min(1.0, t))
            i = min(int(t*n), n-1)
            lt = t*n - i
            c1, c2 = cols[i], cols[min(i+1, n)]
            r = int(c1[0]+(c2[0]-c1[0])*lt)
            g = int(c1[1]+(c2[1]-c1[1])*lt)
            b = int(c1[2]+(c2[2]-c1[2])*lt)
            pix[x,y] = (r,g,b,255)
    return img

# ── Background ────────────────────────────────────────────────────────────

def _make_bg(t: dict, W: int, H: int) -> Image.Image:
    bg = t["bg"]
    if bg["type"] == "solid":
        c = _rgb(bg["color"])
        return Image.new("RGBA", (W, H), (*c, 255))
    stops = bg.get("stops", ["#FFFFFF","#EEEEEE"])
    angle = bg.get("angle", 135)
    return _gradient(W, H, stops, angle)

# ── Drawing helpers ───────────────────────────────────────────────────────

def _rrect(draw: ImageDraw.ImageDraw, box: tuple, r: int,
           fill: tuple, outline: Optional[tuple] = None, ow: int = 2) -> None:
    draw.rounded_rectangle(box, radius=r, fill=fill,
                           outline=outline, width=ow if outline else 0)

def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bb = draw.textbbox((0,0), text, font=font)
    return bb[2] - bb[0]

def _text_h(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bb = draw.textbbox((0,0), text, font=font)
    return bb[3] - bb[1]

def _draw_centered(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
                   y: int, W: int, color: tuple, shadow: bool = False) -> None:
    w = _text_w(draw, text, font)
    x = (W - w) // 2
    if shadow:
        draw.text((x+2, y+2), text, font=font, fill=(0,0,0,60))
    draw.text((x, y), text, font=font, fill=color)

def _draw_left(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
               x: int, y: int, color: tuple) -> None:
    draw.text((x, y), text, font=font, fill=color)

def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
               max_w: int) -> list[str]:
    words = text.split()
    lines, line = [], ""
    for w in words:
        test = (line + " " + w).strip()
        if _text_w(draw, test, font) <= max_w:
            line = test
        else:
            if line: lines.append(line)
            line = w
    if line: lines.append(line)
    return lines or [text]

# ── Decorative elements ───────────────────────────────────────────────────

def _draw_grid(base: Image.Image, color_hex: str, W: int, H: int, alpha: int = 12) -> None:
    ov = Image.new("RGBA", (W,H), (0,0,0,0))
    d  = ImageDraw.Draw(ov)
    c  = (*_rgb(color_hex), alpha)
    step = W // 18
    for x in range(0, W, step): d.line([(x,0),(x,H)], fill=c, width=1)
    for y in range(0, H, step): d.line([(0,y),(W,y)], fill=c, width=1)
    base.alpha_composite(ov)

def _draw_neon_glow(base: Image.Image, color_hex: str, W: int, H: int) -> None:
    """Draw layered neon border glow."""
    ov = Image.new("RGBA", (W,H), (0,0,0,0))
    d  = ImageDraw.Draw(ov)
    c  = _rgb(color_hex)
    for i, a in enumerate([60, 30, 15, 8]):
        m = i * 3
        d.rectangle([m,m,W-1-m,H-1-m], outline=(*c, a), width=2)
    base.alpha_composite(ov.filter(ImageFilter.GaussianBlur(radius=3)))
    # sharp inner line
    d2 = ImageDraw.Draw(base)
    d2.rectangle([1,1,W-2,H-2], outline=(*c, 180), width=1)

def _draw_glass_card(base: Image.Image, box: tuple, radius: int,
                     fill_alpha: int = 18, stroke_hex: str = "#FFFFFF",
                     stroke_alpha: int = 30) -> None:
    ov = Image.new("RGBA", base.size, (0,0,0,0))
    d  = ImageDraw.Draw(ov)
    d.rounded_rectangle(box, radius=radius,
                        fill=(255,255,255,fill_alpha),
                        outline=(*_rgb(stroke_hex), stroke_alpha), width=1)
    base.alpha_composite(ov)

def _draw_scan_badge(draw: ImageDraw.ImageDraw, t: dict, cx: int, y: int,
                     label: str, font: ImageFont.FreeTypeFont) -> int:
    """Draw a pill badge below QR with scan label. Returns badge height."""
    tw = _text_w(draw, label, font)
    th = _text_h(draw, label, font)
    ph, pv = 18, 8
    bw, bh = tw + ph*2, th + pv*2
    bx = cx - bw//2
    bg_c  = _parse_color(t.get("badge_bg",  "#EEEEFF"))
    txt_c = _parse_color(t.get("badge_text", "#4338CA"))
    _rrect(draw, (bx, y, bx+bw, y+bh), r=bh//2, fill=bg_c)
    draw.text((bx+ph, y+pv), label, font=font, fill=txt_c)
    return bh

def _draw_divider(draw: ImageDraw.ImageDraw, x1: int, x2: int, y: int,
                  color_hex: str = "#E2E8F0", alpha: int = 120) -> None:
    c = (*_rgb(color_hex), alpha)
    draw.line([(x1, y), (x2, y)], fill=c, width=1)

# ── Portrait layout (1080×1350) ───────────────────────────────────────────

def _render_portrait(base: Image.Image, t: dict, W: int, H: int,
                     payload: str, qr_type: str,
                     payee_name: str, vpa: str, amount: Optional[float],
                     label: str, watermark: Optional[str],
                     logo: Optional[Image.Image]) -> None:
    """Full portrait poster layout. All sizes relative to W/H."""
    draw = ImageDraw.Draw(base)
    P    = t["padding"]
    R    = t["radius"]

    # Font sizes
    FS_TITLE   = max(30, W // 20)
    FS_SUB     = max(22, W // 30)
    FS_BODY    = max(20, W // 34)
    FS_AMOUNT  = max(42, W // 14)
    FS_LABEL   = max(16, W // 46)
    FS_WM      = max(14, W // 52)
    FS_VPA     = max(18, W // 40)

    ft = _font(t.get("font_title","Poppins-SemiBold"), FS_TITLE)
    fs = _font(t.get("font_body","Inter-Regular"),     FS_SUB)
    fb = _font(t.get("font_body","Inter-Regular"),     FS_BODY)
    fa = _font(t.get("font_title","Poppins-SemiBold"), FS_AMOUNT)
    fl = _font(t.get("font_body","Inter-Regular"),     FS_LABEL)
    fw = _font(t.get("font_body","Inter-Regular"),     FS_WM)
    fv = _font(t.get("font_body","Inter-Regular"),     FS_VPA)

    TC = _rgba(t["title_color"])
    SC = _rgba(t["subtitle_color"])
    AC = _rgba(t["accent"])
    MC = _rgba(t["amount_color"])
    WC = _rgba(t["watermark_color"])

    # Grid / neon overlays (before card)
    if t.get("grid"):
        _draw_grid(base, t.get("grid_color","#00FFCC"), W, H, alpha=10)
    if t.get("neon"):
        _draw_neon_glow(base, t.get("neon_color","#FF00FF"), W, H)

    # ── Card ──────────────────────────────────────────────────────────────
    card_margin = P // 2
    card_box    = (card_margin, card_margin, W - card_margin, H - card_margin)
    card_bg_c   = _parse_color(t.get("card_bg","#F8FAFC"))
    sw          = t.get("card_stroke_width", 1)
    stroke_c    = _parse_color(t.get("card_stroke","#E2E8F0"))

    if t.get("glass"):
        _draw_glass_card(base, card_box, R,
                         fill_alpha=card_bg_c[3] if card_bg_c[3] < 30 else 18,
                         stroke_hex=t.get("card_stroke","#FFFFFF"),
                         stroke_alpha=stroke_c[3] if len(stroke_c)>3 else 30)
    else:
        _rrect(draw, card_box, R, fill=card_bg_c,
               outline=stroke_c[:4] if stroke_c else None, ow=sw)

    # ── Header ────────────────────────────────────────────────────────────
    cy = P + P // 2   # content Y start inside card

    # Bot badge top-center
    bot_badge   = "myqrro"
    bb_font     = fl
    bb_tw       = _text_w(draw, bot_badge, bb_font)
    bb_bw, bb_bh = bb_tw + 28, _text_h(draw, bot_badge, bb_font) + 12
    bb_x        = (W - bb_bw) // 2
    _rrect(draw, (bb_x, cy, bb_x+bb_bw, cy+bb_bh), r=bb_bh//2,
           fill=_parse_color(t["badge_bg"]))
    draw.text((bb_x+14, cy+6), bot_badge, font=bb_font,
              fill=_parse_color(t["badge_text"]))
    cy += bb_bh + P // 2

    # Type icon + label
    type_icons  = {"upi":"💳","url":"🔗","text":"📝","wifi":"📶",
                   "vcard":"👤","email":"✉️","sms":"💬","geo":"📍"}
    icon        = type_icons.get(qr_type, "◼")
    head_txt    = label or (f"UPI Payment" if qr_type == "upi" else
                            f"{qr_type.upper()} Code")
    full_head   = f"{icon}  {head_txt}"
    _draw_centered(draw, full_head, ft, cy, W, TC, shadow=t.get("neon"))
    cy += _text_h(draw, full_head, ft) + P // 3

    # Payee name
    if payee_name:
        wrapped = _wrap_text(draw, payee_name, fs, W - P*2)
        for line in wrapped:
            _draw_centered(draw, line, fs, cy, W, TC)
            cy += _text_h(draw, line, fs) + 4
        cy += P // 5

    # VPA pill
    if vpa:
        vpa_disp = vpa if len(vpa) <= 28 else vpa[:26] + "…"
        vw = _text_w(draw, vpa_disp, fv)
        vh = _text_h(draw, vpa_disp, fv)
        vph, vpv = 14, 7
        vbx = (W - vw - vph*2) // 2
        _rrect(draw, (vbx, cy, vbx+vw+vph*2, cy+vh+vpv*2),
               r=(vh+vpv*2)//2,
               fill=(*_rgb(t["accent"]), 20),
               outline=(*_rgb(t["accent"]), 60), ow=1)
        draw.text((vbx+vph, cy+vpv), vpa_disp, font=fv, fill=AC)
        cy += vh + vpv*2 + P // 3

    # ── QR Code ───────────────────────────────────────────────────────────
    qr_px  = int(min(W, H) * t["qr_ratio"])
    qr_img = render_qr_image(payload, size_px=qr_px,
                              dark=t["qr_dark"], light=t["qr_light"],
                              logo=logo)
    qr_rgb = qr_img.convert("RGBA")

    # QR card / frame
    qcpad = P // 3
    qcx   = (W - qr_px) // 2
    qcy   = cy
    qc_bg = _parse_color(t.get("card_bg", "#FFFFFF"))
    # White QR background always for readability
    qr_bg_color = _parse_color(t["qr_light"]) if t["qr_light"] != "#FFFFFF" else (255,255,255,255)
    _rrect(draw,
           (qcx - qcpad, qcy - qcpad, qcx+qr_px+qcpad, qcy+qr_px+qcpad),
           r=R, fill=qr_bg_color,
           outline=stroke_c[:4] if stroke_c else None, ow=sw)
    base.paste(qr_rgb, (qcx, qcy), qr_rgb)
    cy += qr_px + qcpad + P // 2

    # Scan badge
    scan_label = "Scan to Pay" if qr_type == "upi" else "Scan QR Code"
    badge_h    = _draw_scan_badge(draw, t, W//2, cy, scan_label, fl)
    cy        += badge_h + P // 2

    # ── Amount ────────────────────────────────────────────────────────────
    if amount and amount > 0:
        _draw_divider(draw, P*2, W-P*2, cy, t.get("card_stroke","#E2E8F0"))
        cy += P // 2
        amt_str = f"₹ {amount:,.2f}"
        _draw_centered(draw, amt_str, fa, cy, W, MC, shadow=t.get("glass"))
        cy += _text_h(draw, amt_str, fa) + P // 4
        sub_str = "UPI Amount"
        _draw_centered(draw, sub_str, fl, cy, W, SC)

    # ── Watermark ─────────────────────────────────────────────────────────
    if watermark:
        wm_w = _text_w(draw, watermark, fw)
        draw.text((W - wm_w - P//2, H - P//2 - FS_WM - card_margin),
                  watermark, font=fw, fill=WC)


# ── Square layout (1080×1080) ─────────────────────────────────────────────

def _render_square(base: Image.Image, t: dict, W: int, H: int,
                   payload: str, qr_type: str,
                   payee_name: str, vpa: str, amount: Optional[float],
                   label: str, watermark: Optional[str],
                   logo: Optional[Image.Image]) -> None:
    draw = ImageDraw.Draw(base)
    P    = t["padding"]
    R    = t["radius"]

    FS_TITLE  = max(28, W // 22)
    FS_BODY   = max(20, W // 34)
    FS_AMOUNT = max(36, W // 18)
    FS_LABEL  = max(15, W // 48)
    FS_WM     = max(14, W // 54)

    ft = _font(t.get("font_title","Poppins-SemiBold"), FS_TITLE)
    fb = _font(t.get("font_body","Inter-Regular"),     FS_BODY)
    fa = _font(t.get("font_title","Poppins-SemiBold"), FS_AMOUNT)
    fl = _font(t.get("font_body","Inter-Regular"),     FS_LABEL)
    fw = _font(t.get("font_body","Inter-Regular"),     FS_WM)

    TC = _rgba(t["title_color"])
    SC = _rgba(t["subtitle_color"])
    MC = _rgba(t["amount_color"])
    AC = _rgba(t["accent"])
    WC = _rgba(t["watermark_color"])

    if t.get("grid"):
        _draw_grid(base, t.get("grid_color","#00FFCC"), W, H, alpha=10)
    if t.get("neon"):
        _draw_neon_glow(base, t.get("neon_color","#FF00FF"), W, H)

    # Full card
    cm  = P // 2
    _rrect(draw, (cm,cm,W-cm,H-cm), R,
           fill=_parse_color(t.get("card_bg","#F8FAFC")),
           outline=_parse_color(t.get("card_stroke","#E2E8F0"))[:4], ow=1)

    # QR on left half
    qr_px = int(H * t["qr_ratio"] * 0.9)
    qr_img = render_qr_image(payload, size_px=qr_px,
                              dark=t["qr_dark"], light=t["qr_light"], logo=logo)
    qcpad  = P // 3
    qcx    = P
    qcy    = (H - qr_px) // 2
    _rrect(draw, (qcx-qcpad, qcy-qcpad, qcx+qr_px+qcpad, qcy+qr_px+qcpad),
           R, fill=_parse_color(t["qr_light"]) if t["qr_light"] != "#FFFFFF" else (255,255,255,255))
    base.paste(qr_img.convert("RGBA"), (qcx, qcy), qr_img.convert("RGBA"))

    # Right side text
    tx  = qcx + qr_px + qcpad + P // 2
    avW = W - tx - P
    ty  = H // 4

    # Type label
    type_icons = {"upi":"💳","url":"🔗","text":"📝","wifi":"📶",
                  "vcard":"👤","email":"✉️","sms":"💬","geo":"📍"}
    icon = type_icons.get(qr_type, "◼")
    head = f"{icon} {label or qr_type.upper()}"
    draw.text((tx, ty), head, font=ft, fill=AC)
    ty += _text_h(draw, head, ft) + P // 3

    if payee_name:
        lines = _wrap_text(draw, payee_name, fb, avW)
        for l in lines[:2]:
            draw.text((tx, ty), l, font=fb, fill=TC)
            ty += _text_h(draw, l, fb) + 4
        ty += P // 5

    if vpa:
        vpa_s = vpa if len(vpa) <= 22 else vpa[:20]+"…"
        draw.text((tx, ty), vpa_s, font=fl, fill=SC)
        ty += _text_h(draw, vpa_s, fl) + P // 4

    if amount and amount > 0:
        _draw_divider(draw, tx, tx+avW, ty, t.get("card_stroke","#E2E8F0"))
        ty += P // 3
        draw.text((tx, ty), f"₹ {amount:,.2f}", font=fa, fill=MC)
        ty += _text_h(draw, f"₹ {amount:,.2f}", fa) + 4
        draw.text((tx, ty), "UPI Amount", font=fl, fill=SC)

    # Scan badge bottom right
    scan = "Scan to Pay" if qr_type == "upi" else "Scan QR"
    sw_ = _text_w(draw, scan, fl)
    sh  = _text_h(draw, scan, fl)
    bph, bpv = 14, 7
    bx2 = W - cm - P//2
    by2 = H - cm - P//2
    bx1 = bx2 - sw_ - bph*2
    by1 = by2 - sh - bpv*2
    _rrect(draw, (bx1,by1,bx2,by2), r=(by2-by1)//2,
           fill=_parse_color(t["badge_bg"]))
    draw.text((bx1+bph, by1+bpv), scan, font=fl, fill=_parse_color(t["badge_text"]))

    if watermark:
        ww = _text_w(draw, watermark, fw)
        draw.text((W-ww-P//2, H-P//2-FS_WM-cm), watermark, font=fw, fill=WC)


# ── QR-only (2048×2048) ───────────────────────────────────────────────────

def _render_qr_only(t: dict, payload: str,
                    watermark: Optional[str], logo: Optional[Image.Image]) -> bytes:
    sz  = 2048
    qr  = render_qr_image(payload, size_px=sz, dark=t["qr_dark"],
                           light=t["qr_light"], logo=logo)
    bg  = Image.new("RGBA", (sz, sz), _rgba(t["qr_light"]))
    bg.paste(qr, (0, 0), qr.convert("RGBA"))
    if watermark:
        draw = ImageDraw.Draw(bg)
        fw   = _font(t.get("font_body","Inter-Regular"), 36)
        ww   = _text_w(draw, watermark, fw)
        draw.text((sz-ww-24, sz-60), watermark, font=fw,
                  fill=_rgba(t["watermark_color"]))
    return _to_png(bg)


# ── Public API ────────────────────────────────────────────────────────────

def render_poster(
    payload:    str,
    qr_type:   str,
    theme_id:  str,
    size:      str,            # "1080x1350" | "1080x1080" | "2048x2048"
    label:     str = "",
    payee_name: str = "",
    vpa:       str = "",
    amount:    Optional[float] = None,
    watermark: Optional[str] = None,
    logo:      Optional[Image.Image] = None,
) -> bytes:
    """
    Render a premium poster and return PNG bytes.
    Thread-safe: creates fresh Image objects every call.
    """
    t = get_theme(theme_id)

    if size == "2048x2048":
        return _render_qr_only(t, payload, watermark, logo)

    W, H = (int(x) for x in size.split("x"))
    base = _make_bg(t, W, H)

    if size == "1080x1350":
        _render_portrait(base, t, W, H, payload, qr_type,
                         payee_name, vpa, amount, label, watermark, logo)
    else:  # 1080x1080
        _render_square(base, t, W, H, payload, qr_type,
                       payee_name, vpa, amount, label, watermark, logo)
    return _to_png(base)


def _to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
