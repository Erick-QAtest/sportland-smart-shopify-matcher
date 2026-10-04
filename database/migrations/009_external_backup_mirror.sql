ALTER TABLE ops_backups
    ADD COLUMN IF NOT EXISTS mirror_sha256 TEXT;

ALTER TABLE ops_backups
    ADD COLUMN IF NOT EXISTS mirror_size_bytes BIGINT;

ALTER TABLE ops_backups
    ADD COLUMN IF NOT EXISTS mirror_verified BOOLEAN;

ALTER TABLE ops_backups
    ADD COLUMN IF NOT EXISTS mirror_required BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE ops_backups
    ADD COLUMN IF NOT EXISTS mirror_retention_days INTEGER;

CREATE INDEX IF NOT EXISTS ix_ops_backups_mirror_verified
    ON ops_backups(mirror_verified, created_at DESC);
