CREATE TABLE IF NOT EXISTS ops_daily_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'OK', 'FAILED')),
    current_step TEXT,
    failed_step TEXT,
    exit_code INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_ops_daily_runs_started_at
    ON ops_daily_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS ops_backups (
    backup_id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id TEXT,
    database_name TEXT NOT NULL,
    backup_path TEXT NOT NULL,
    mirror_path TEXT,
    size_bytes BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    retention_days INTEGER NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_ops_backups_created_at
    ON ops_backups(created_at DESC);
