"""helpers.py — Shared utility functions."""
from __future__ import annotations
import io
from datetime import datetime
from typing import Optional
from PIL import Image


def fmt_dt(dt: Optional[datetime]) -> str:
    return dt.strftime("%d %b %Y, %H:%M") if dt else "—"


def parse_amount(text: str) -> Optional[float]:
    try:
        v = float(text.replace(",","").replace("₹","").strip())
        return round(v, 2) if 0 < v <= 1_00_00_000 else None
    except ValueError:
        return None


def qr_icon(qt: str) -> str:
    return {"upi":"💳","url":"🌐","text":"📝","wifi":"📶",
            "vcard":"👤","email":"✉️","sms":"💬","geo":"📍"}.get(qt, "◼")


async def fetch_logo(bot, file_id: str) -> Optional[Image.Image]:
    try:
        f   = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(f.file_path, buf)
        buf.seek(0)
        return Image.open(buf).convert("RGBA")
    except Exception:
        return None


def img_to_file(data: bytes, name: str = "qr.png"):
    from aiogram.types import BufferedInputFile
    return BufferedInputFile(data, filename=name)
