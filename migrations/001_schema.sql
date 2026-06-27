-- 001_schema.sql — Full schema. Idempotent (safe to re-run).

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    user_id       BIGINT PRIMARY KEY,
    username      TEXT,
    full_name     TEXT NOT NULL DEFAULT '',
    language_code TEXT NOT NULL DEFAULT 'en',
    is_banned     BOOLEAN NOT NULL DEFAULT FALSE,
    ban_reason    TEXT,
    logo_file_id  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_gen     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Per-user settings
CREATE TABLE IF NOT EXISTS user_settings (
    user_id            BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    template           TEXT NOT NULL DEFAULT 'minimal_pro',
    output_size        TEXT NOT NULL DEFAULT '1080x1350',
    watermark_on       BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Admins
CREATE TABLE IF NOT EXISTS admins (
    user_id    BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    granted_by BIGINT NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ForceSub required chats
CREATE TABLE IF NOT EXISTS forcesub_chats (
    chat_id     BIGINT PRIMARY KEY,
    username    TEXT,
    invite_link TEXT,
    title       TEXT NOT NULL DEFAULT '',
    added_by    BIGINT NOT NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Global key-value settings
CREATE TABLE IF NOT EXISTS bot_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO bot_settings (key, value) VALUES
    ('forcesub_enabled',  'false'),
    ('watermark_enabled', 'true'),
    ('watermark_text',    '@myqrro_bot'),
    ('maintenance',       'false'),
    ('maintenance_msg',   'Bot is under maintenance. Please try again soon.'),
    ('rate_per_min',      '10'),
    ('rate_per_day',      '200')
ON CONFLICT (key) DO NOTHING;

-- Saved payees
CREATE TABLE IF NOT EXISTS saved_payees (
    id         SERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    label      TEXT NOT NULL,
    vpa        TEXT NOT NULL,
    name       TEXT NOT NULL,
    amount     NUMERIC(12,2),
    note       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, vpa, label)
);
CREATE INDEX IF NOT EXISTS idx_payees_uid ON saved_payees(user_id);

-- History
CREATE TABLE IF NOT EXISTS history (
    id         SERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    qr_type    TEXT NOT NULL,
    payload    TEXT NOT NULL,
    template   TEXT NOT NULL,
    size       TEXT NOT NULL,
    file_id    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_history_uid ON history(user_id, created_at DESC);

-- Audit log
CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    actor_id   BIGINT NOT NULL,
    action     TEXT NOT NULL,
    target_id  BIGINT,
    note       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);

INSERT INTO schema_migrations (version) VALUES (1) ON CONFLICT DO NOTHING;
