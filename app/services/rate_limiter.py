"""
rate_limiter.py — Sliding-window rate limiter, in-memory.
Railway single-instance; no Redis dependency needed.
"""
from __future__ import annotations
import time
from collections import defaultdict, deque
from typing import Optional


class RateLimiter:
    def __init__(self) -> None:
        self._min: dict[int, deque] = defaultdict(deque)
        self._day: dict[int, deque] = defaultdict(deque)

    def _clean(self, dq: deque, window: float) -> None:
        t = time.time()
        while dq and dq[0] < t - window:
            dq.popleft()

    def check(self, uid: int, per_min: int, per_day: int) -> tuple[bool, str]:
        now = time.time()
        md, dd = self._min[uid], self._day[uid]
        self._clean(md, 60)
        self._clean(dd, 86400)
        if len(md) >= per_min:
            return False, "minute"
        if len(dd) >= per_day:
            return False, "day"
        md.append(now)
        dd.append(now)
        return True, ""


_limiter = RateLimiter()


async def check_rate(uid: int, per_min: Optional[int] = None,
                     per_day: Optional[int] = None) -> tuple[bool, str]:
    from app.config import settings
    from app.database.db import get_setting
    pm = per_min or int(await get_setting("rate_per_min", str(settings.rate_limit_per_minute)))
    pd = per_day or int(await get_setting("rate_per_day", str(settings.rate_limit_per_day)))
    return _limiter.check(uid, pm, pd)
