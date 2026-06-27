"""
db.py — Async asyncpg connection pool + every database function.
One file keeps imports simple across handlers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import asyncpg

from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)

_pool: asyncpg.Pool | None = None


# ── Pool lifecycle ────────────────────────────────────────────────────────

async def create_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.asyncpg_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    log.info("db_pool_created")


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        log.info("db_pool_closed")


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call create_pool() first")
    return _pool


# ── Migrations ────────────────────────────────────────────────────────────

async def run_migrations() -> None:
    mig_dir = Path(__file__).parent.parent.parent / "migrations"
    async with pool().acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
        for f in sorted(mig_dir.glob("*.sql"), key=lambda p: int(p.stem.split("_")[0])):
            ver = int(f.stem.split("_")[0])
            if ver in applied:
                continue
            log.info("applying_migration", file=f.name)
            await conn.execute(f.read_text())
            log.info("migration_ok", version=ver)


async def health_check() -> dict:
    import time
    t = time.perf_counter()
    try:
        async with pool().acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "latency_ms": round((time.perf_counter() - t) * 1000, 2)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Users ─────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: Optional[str],
                      full_name: str, lang: str = "en") -> None:
    async with pool().acquire() as c:
        await c.execute("""
            INSERT INTO users (user_id, username, full_name, language_code, last_seen_at)
            VALUES ($1,$2,$3,$4,now())
            ON CONFLICT (user_id) DO UPDATE
              SET username=EXCLUDED.username, full_name=EXCLUDED.full_name, last_seen_at=now()
        """, user_id, username, full_name, lang)
        await c.execute("INSERT INTO user_settings (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                        user_id)


async def get_user(uid: int) -> Optional[dict]:
    async with pool().acquire() as c:
        r = await c.fetchrow("SELECT * FROM users WHERE user_id=$1", uid)
        return dict(r) if r else None


async def is_banned(uid: int) -> bool:
    async with pool().acquire() as c:
        v = await c.fetchval("SELECT is_banned FROM users WHERE user_id=$1", uid)
        return bool(v)


async def ban_user(uid: int, reason: str, actor: int) -> None:
    async with pool().acquire() as c:
        await c.execute("UPDATE users SET is_banned=TRUE, ban_reason=$2 WHERE user_id=$1", uid, reason)
        await _audit(c, actor, "ban", uid, reason)


async def unban_user(uid: int, actor: int) -> None:
    async with pool().acquire() as c:
        await c.execute("UPDATE users SET is_banned=FALSE, ban_reason=NULL WHERE user_id=$1", uid)
        await _audit(c, actor, "unban", uid, None)


async def purge_user(uid: int, actor: int) -> None:
    async with pool().acquire() as c:
        await c.execute("DELETE FROM users WHERE user_id=$1", uid)
        await _audit(c, actor, "purge", uid, None)


async def get_all_users(limit: int = 50000) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("SELECT * FROM users ORDER BY created_at DESC LIMIT $1", limit)
        return [dict(r) for r in rows]


async def increment_generated(uid: int) -> None:
    async with pool().acquire() as c:
        await c.execute("UPDATE users SET total_gen=total_gen+1 WHERE user_id=$1", uid)


async def set_logo(uid: int, file_id: Optional[str]) -> None:
    async with pool().acquire() as c:
        await c.execute("UPDATE users SET logo_file_id=$2 WHERE user_id=$1", uid, file_id)


# ── User settings ─────────────────────────────────────────────────────────

async def get_user_settings(uid: int) -> dict:
    async with pool().acquire() as c:
        r = await c.fetchrow("SELECT * FROM user_settings WHERE user_id=$1", uid)
        if r:
            return dict(r)
        return {"user_id": uid, "template": "minimal_pro",
                "output_size": "1080x1350", "watermark_on": True}


async def update_user_settings(uid: int, **kw: Any) -> None:
    if not kw:
        return
    sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(kw))
    vals = list(kw.values())
    async with pool().acquire() as c:
        await c.execute(
            f"UPDATE user_settings SET {sets}, updated_at=now() WHERE user_id=$1",
            uid, *vals
        )


# ── Admins ────────────────────────────────────────────────────────────────

async def add_admin(uid: int, grantor: int) -> None:
    async with pool().acquire() as c:
        await c.execute("""
            INSERT INTO admins (user_id, granted_by) VALUES ($1,$2) ON CONFLICT DO NOTHING
        """, uid, grantor)
        await _audit(c, grantor, "add_admin", uid, None)


async def del_admin(uid: int, actor: int) -> None:
    async with pool().acquire() as c:
        await c.execute("DELETE FROM admins WHERE user_id=$1", uid)
        await _audit(c, actor, "del_admin", uid, None)


async def is_admin(uid: int) -> bool:
    async with pool().acquire() as c:
        return await c.fetchval("SELECT 1 FROM admins WHERE user_id=$1", uid) is not None


async def list_admins() -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT a.user_id, a.granted_at, u.username, u.full_name
            FROM admins a LEFT JOIN users u USING(user_id)
        """)
        return [dict(r) for r in rows]


# ── Bot settings (KV) ─────────────────────────────────────────────────────

async def get_setting(key: str, default: str = "") -> str:
    async with pool().acquire() as c:
        v = await c.fetchval("SELECT value FROM bot_settings WHERE key=$1", key)
        return v if v is not None else default


async def set_setting(key: str, value: str) -> None:
    async with pool().acquire() as c:
        await c.execute("""
            INSERT INTO bot_settings (key, value, updated_at) VALUES ($1,$2,now())
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()
        """, key, value)


# ── ForceSub chats ────────────────────────────────────────────────────────

async def add_forcesub(chat_id: int, username: Optional[str],
                       invite_link: Optional[str], title: str, actor: int) -> None:
    async with pool().acquire() as c:
        await c.execute("""
            INSERT INTO forcesub_chats (chat_id, username, invite_link, title, added_by)
            VALUES ($1,$2,$3,$4,$5)
            ON CONFLICT (chat_id) DO UPDATE
              SET username=EXCLUDED.username, invite_link=EXCLUDED.invite_link, title=EXCLUDED.title
        """, chat_id, username, invite_link, title, actor)
        await _audit(c, actor, "forcesub_add", chat_id, title)


async def del_forcesub(chat_id: int, actor: int) -> None:
    async with pool().acquire() as c:
        await c.execute("DELETE FROM forcesub_chats WHERE chat_id=$1", chat_id)
        await _audit(c, actor, "forcesub_del", chat_id, None)


async def list_forcesub() -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("SELECT * FROM forcesub_chats ORDER BY added_at")
        return [dict(r) for r in rows]


# ── Saved payees ──────────────────────────────────────────────────────────

async def add_payee(uid: int, label: str, vpa: str, name: str,
                    amount: Optional[float], note: Optional[str]) -> int:
    async with pool().acquire() as c:
        r = await c.fetchrow("""
            INSERT INTO saved_payees (user_id,label,vpa,name,amount,note)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (user_id,vpa,label) DO UPDATE
              SET name=EXCLUDED.name, amount=EXCLUDED.amount, note=EXCLUDED.note
            RETURNING id
        """, uid, label, vpa, name, amount, note)
        return r["id"]


async def get_payees(uid: int) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM saved_payees WHERE user_id=$1 ORDER BY created_at DESC", uid)
        return [dict(r) for r in rows]


async def get_payee(payee_id: int, uid: int) -> Optional[dict]:
    async with pool().acquire() as c:
        r = await c.fetchrow(
            "SELECT * FROM saved_payees WHERE id=$1 AND user_id=$2", payee_id, uid)
        return dict(r) if r else None


async def del_payee(payee_id: int, uid: int) -> None:
    async with pool().acquire() as c:
        await c.execute("DELETE FROM saved_payees WHERE id=$1 AND user_id=$2", payee_id, uid)


# ── History ───────────────────────────────────────────────────────────────

async def add_history(uid: int, qr_type: str, payload: str,
                      template: str, size: str, file_id: Optional[str]) -> int:
    async with pool().acquire() as c:
        r = await c.fetchrow("""
            INSERT INTO history (user_id,qr_type,payload,template,size,file_id)
            VALUES ($1,$2,$3,$4,$5,$6) RETURNING id
        """, uid, qr_type, payload, template, size, file_id)
        # Prune old records
        await c.execute("""
            DELETE FROM history WHERE user_id=$1
            AND id NOT IN (
                SELECT id FROM history WHERE user_id=$1
                ORDER BY created_at DESC LIMIT $2
            )
        """, uid, 50)
        return r["id"]


async def get_history(uid: int, limit: int = 10) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT * FROM history WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2
        """, uid, limit)
        return [dict(r) for r in rows]


# ── Audit ─────────────────────────────────────────────────────────────────

async def _audit(conn: asyncpg.Connection, actor: int, action: str,
                 target: Optional[int], note: Optional[str]) -> None:
    await conn.execute("""
        INSERT INTO audit_log (actor_id, action, target_id, note) VALUES ($1,$2,$3,$4)
    """, actor, action, target, note)


async def get_audit(limit: int = 30) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT al.*, u.username FROM audit_log al
            LEFT JOIN users u ON al.actor_id=u.user_id
            ORDER BY al.created_at DESC LIMIT $1
        """, limit)
        return [dict(r) for r in rows]


# ── Stats ─────────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    async with pool().acquire() as c:
        total   = await c.fetchval("SELECT COUNT(*) FROM users")
        banned  = await c.fetchval("SELECT COUNT(*) FROM users WHERE is_banned")
        gen     = await c.fetchval("SELECT COALESCE(SUM(total_gen),0) FROM users")
        today   = await c.fetchval(
            "SELECT COUNT(*) FROM history WHERE created_at > now() - interval '24h'")
        return {"total_users": total, "banned": banned,
                "total_generated": gen, "today": today}
