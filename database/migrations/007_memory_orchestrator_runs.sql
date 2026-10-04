CREATE TABLE IF NOT EXISTS memory_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'OK', 'FAILED')),
    failed_step TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_memory_runs_started_at
    ON memory_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS memory_run_steps (
    step_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL
        REFERENCES memory_runs(run_id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    step_name TEXT NOT NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('OK', 'FAILED')),
    exit_code INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    duration_ms BIGINT NOT NULL,
    output_tail TEXT,
    UNIQUE (run_id, step_name)
);

CREATE INDEX IF NOT EXISTS ix_memory_run_steps_run_order
    ON memory_run_steps(run_id, step_order);
