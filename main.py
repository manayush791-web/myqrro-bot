"""
main.py — Bot entrypoint for Railway deployment.

• Webhook mode  — when RAILWAY_PUBLIC_DOMAIN is set (Railway auto-sets this)
• Polling mode  — when running locally without RAILWAY_PUBLIC_DOMAIN

FastAPI serves:
  POST /webhook/<secret>  — Telegram update receiver
  GET  /health            — Health probe (used by Railway and uptime monitors)
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

import psutil
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.config import settings
from app.database.db import create_pool, close_pool, run_migrations, health_check
from app.handlers import ALL_ROUTERS
from app.logger import configure_logging, get_logger
from app.middleware.middlewares import BanCheckMiddleware, ForceSub, RateLimitMiddleware

configure_logging()
log = get_logger("main")

_START = time.time()


# ── Bot + Dispatcher factory ──────────────────────────────────────────────

def _make_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def _make_dp() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware — order: BanCheck → ForceSub → RateLimit
    dp.update.outer_middleware(BanCheckMiddleware())
    dp.update.outer_middleware(ForceSub())
    dp.message.middleware(RateLimitMiddleware())

    for r in ALL_ROUTERS:
        dp.include_router(r)

    return dp


bot = _make_bot()
dp  = _make_dp()


# ── FastAPI lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    log.info("startup_begin", webhook_mode=settings.is_webhook_mode)
    await create_pool()
    await run_migrations()

    if settings.is_webhook_mode:
        await bot.set_webhook(
            url=settings.full_webhook_url,
            secret_token=settings.webhook_secret,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
        )
        log.info("webhook_registered", url=settings.full_webhook_url)
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("polling_mode_startup")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    log.info("shutdown_begin")
    await close_pool()
    await bot.session.close()


app = FastAPI(
    title="myqrro_bot",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


# ── Webhook endpoint ──────────────────────────────────────────────────────

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request) -> Response:
    if secret != settings.webhook_secret:
        log.warning("webhook_bad_secret", prefix=secret[:6])
        return Response(status_code=403)

    body   = await request.body()
    update = Update.model_validate_json(body)
    await dp.feed_update(bot=bot, update=update)
    return Response(status_code=200)


# ── Health endpoint ───────────────────────────────────────────────────────

@app.get("/health")
async def health() -> JSONResponse:
    db     = await health_check()
    proc   = psutil.Process()
    mem_mb = round(proc.memory_info().rss / 1024 ** 2, 2)
    uptime = round(time.time() - _START, 1)

    ok   = db["status"] == "ok"
    code = 200 if ok else 503
    return JSONResponse(
        {
            "status":    "ok" if ok else "degraded",
            "uptime_s":  uptime,
            "memory_mb": mem_mb,
            "db":        db,
        },
        status_code=code,
    )


# ── Local polling entry ───────────────────────────────────────────────────

async def _polling() -> None:
    configure_logging()
    await create_pool()
    await run_migrations()
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("polling_started")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await close_pool()
        await bot.session.close()


if __name__ == "__main__":
    import os
    if settings.is_webhook_mode:
        port = int(os.environ.get("PORT", 8000))
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            log_config=None,   # structlog owns logging
            access_log=False,
        )
    else:
        asyncio.run(_polling())
