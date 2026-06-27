# @myqrro_bot — Railway Deployment Guide

Production-ready Telegram QR code & poster bot.
Single Railway service + Railway PostgreSQL. No Redis required.

---

## Project Structure

```
myqrro_railway/
├── main.py                        # Entrypoint — webhook (Railway) or polling (local)
├── requirements.txt
├── Dockerfile
├── railway.toml
├── .env.example
│
├── app/
│   ├── config.py                  # Pydantic settings (all from env vars)
│   ├── logger.py                  # Structured JSON logging
│   │
│   ├── database/
│   │   └── db.py                  # asyncpg pool + every DB function + migrations runner
│   │
│   ├── handlers/
│   │   ├── common.py              # /start /help /profile home-card forcesub-verify
│   │   ├── generate.py            # UPI wizard + all 7 QR type wizards (FSM)
│   │   ├── payees.py              # Saved payees — add, list, 1-tap generate, delete
│   │   ├── settings.py            # Templates, size, watermark, logo, history, delete_me
│   │   ├── admin.py               # Admin panel — ban, broadcast, ForceSub, watermark, audit
│   │   └── owner.py               # Owner panel — addadmin, export, maintenance, purge
│   │
│   ├── middleware/
│   │   ├── middlewares.py         # BanCheck + ForceSub + RateLimit (all in one file)
│   │   └── permissions.py         # @owner_only / @admin_only decorators
│   │
│   ├── services/
│   │   ├── qr_engine.py           # Pure payload builders + segno QR renderer
│   │   ├── renderer.py            # Pillow poster engine — all 12 themes
│   │   └── rate_limiter.py        # In-memory sliding-window rate limiter
│   │
│   └── utils/
│       ├── keyboards.py           # Every InlineKeyboardMarkup builder
│       └── helpers.py             # Shared utilities
│
├── assets/templates/themes.json   # 12 theme configs — add themes here, no code change
├── fonts/                         # Downloaded at Docker build time (OFL licensed)
├── migrations/001_schema.sql      # Full DB schema
├── scripts/download_fonts.sh      # Font downloader (called by Dockerfile)
└── tests/test_qr_engine.py        # Unit tests (no DB/network needed)
```

---

## Deploy on Railway — Step by Step

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "initial"
gh repo create myqrro-bot --private --push --source=.
```

### Step 2 — Create Railway project

1. Go to [railway.app](https://railway.app) → **New Project**
2. Click **Deploy from GitHub repo** → select your repo
3. Railway detects `railway.toml` and uses the Dockerfile automatically

### Step 3 — Add PostgreSQL

In Railway dashboard:

1. Click **+ New** inside your project
2. Choose **Database → Add PostgreSQL**
3. Railway creates a free internal PostgreSQL instance
4. Click on the PostgreSQL service → **Connect** tab
5. Copy the `DATABASE_URL` value (starts with `postgresql://...`)

### Step 4 — Set Environment Variables

In Railway dashboard → your bot service → **Variables** tab, add:

| Variable | Value | Notes |
|---|---|---|
| `BOT_TOKEN` | `7123456789:AAF...` | From @BotFather |
| `OWNER_ID` | `123456789` | Your Telegram user ID |
| `WEBHOOK_SECRET` | `random32charstring` | Generate: `openssl rand -hex 16` |
| `DATABASE_URL` | `postgresql://...` | Paste from Step 3 |

> **Do NOT set** `RAILWAY_PUBLIC_DOMAIN` or `PORT` — Railway injects these automatically.

### Step 5 — Deploy

Railway auto-deploys on every push. Watch the build logs:

```
⬇  Poppins-Regular.ttf
⬇  Inter-Regular.ttf
...
✅  All fonts ready.
```

Then:
```
startup_begin  webhook_mode=true
db_pool_created
applying_migration  file=001_schema.sql
webhook_registered  url=https://myqrro-bot-xxxx.railway.app/webhook/...
```

### Step 6 — Verify

```bash
# Check health endpoint
curl https://your-app.railway.app/health

# Expected:
{
  "status": "ok",
  "uptime_s": 12.3,
  "memory_mb": 145.2,
  "db": {"status": "ok", "latency_ms": 1.8}
}
```

Open Telegram → find your bot → send `/start`

---

## Local Development

```bash
# 1. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Download fonts
bash scripts/download_fonts.sh

# 3. Start local PostgreSQL
docker run -d --name myqrro-pg \
  -e POSTGRES_DB=myqrro \
  -e POSTGRES_USER=myqrro \
  -e POSTGRES_PASSWORD=secret \
  -p 5432:5432 postgres:16

# 4. Configure .env
cp .env.example .env
# Set BOT_TOKEN, OWNER_ID, WEBHOOK_SECRET
# Set DATABASE_URL=postgresql://myqrro:secret@localhost:5432/myqrro
# Leave RAILWAY_PUBLIC_DOMAIN unset → runs in polling mode

# 5. Run
python main.py
```

---

## Bot Commands

### User
| Command | Description |
|---|---|
| `/start` | Home card |
| `/help` | Full command reference |
| `/upi` | UPI payment QR wizard |
| `/qr` | QR type selector |
| `/qr_url` `/qr_text` `/qr_wifi` | Quick shortcuts |
| `/qr_vcard` `/qr_email` `/qr_sms` `/qr_geo` | Quick shortcuts |
| `/mypayees` | Saved payees — 1-tap generate |
| `/history` | Regenerate past QRs |
| `/templates` | Browse 12 themes |
| `/settings` | Template, size, watermark, logo |
| `/setlogo` | Upload logo for QR overlay |
| `/dellogo` | Remove logo |
| `/profile` | Your stats |
| `/delete_me` | Delete all your data |

### Admin
| Command | Description |
|---|---|
| `/admin` | Admin panel |
| `/ban <id> [reason]` | Ban a user |
| `/unban <id>` | Unban a user |
| `/broadcast` | Wizard → preview → send to all |
| `/setwatermark on\|off` | Toggle global watermark |
| `/setwatermarktext <text>` | Set watermark text |
| `/setlimits <per_min> <per_day>` | Rate limits |
| `/forcesub_on` / `/forcesub_off` | Toggle gate |
| `/forcesub_add @channel` | Add public channel |
| `/forcesub_add -100xxx <link>` | Add private channel |
| `/forcesub_list` | Show configured channels |
| `/forcesub_del <chat_id>` | Remove a channel |
| `/audit` | Recent admin actions |
| `/health` | System health |

### Owner only
| Command | Description |
|---|---|
| `/owner` | Owner panel |
| `/addadmin <user_id>` | Grant admin |
| `/deladmin <user_id>` | Revoke admin |
| `/export users\|stats\|audit` | Export as CSV / JSON |
| `/maintenance on\|off [msg]` | Maintenance mode |
| `/purge <user_id>` | Hard-delete all user data |

---

## Adding a New Theme

Edit `assets/templates/themes.json` — **no code changes needed**:

```json
{
  "id": "my_theme",
  "name": "My Theme",
  "emoji": "🌊",
  "enabled": true,
  "bg": {"type": "gradient", "stops": ["#0F2027","#203A43","#2C5364"], "angle": 135},
  "qr_dark": "#FFFFFF",
  "qr_light": "#0F2027",
  "card_bg": "#ffffff08",
  "card_stroke": "#ffffff20",
  "title_color": "#FFFFFF",
  "subtitle_color": "#90CAF9",
  "accent": "#42A5F5",
  "amount_color": "#64B5F6",
  "watermark_color": "#1A3A4A",
  "badge_bg": "#0D2233",
  "badge_text": "#90CAF9",
  "font_title": "Poppins-SemiBold",
  "font_body": "Inter-Regular",
  "radius": 24,
  "padding": 56,
  "qr_ratio": 0.58
}
```

Redeploy (or just restart) to see the new theme in `/templates`.

---

## ForceSub Quick Setup

```
/forcesub_add @yourchannel
/forcesub_on
/forcesub_list
```

For a private channel:
```
/forcesub_add -1001234567890 https://t.me/+invitelink
```

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

All tests are pure-function tests — no database, no Telegram API needed.

---

## Security Notes

- **No secrets hardcoded** — everything via environment variables
- Webhook secret verified on every request (403 if mismatch)
- Owner ID stored in env var, not database — cannot be escalated
- All admin actions written to `audit_log` table
- VPA validation is **format-only** — no bank or payment network verification claimed
- Rate limits apply to generation commands only; admin/owner are exempt
- BanCheck runs before every update

---

## Health Endpoint Response

```json
{
  "status": "ok",
  "uptime_s": 3612.4,
  "memory_mb": 148.6,
  "db": {
    "status": "ok",
    "latency_ms": 1.9
  }
}
```

Returns `503` when DB is unreachable.
