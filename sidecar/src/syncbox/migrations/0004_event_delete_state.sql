-- 0004: durable state for idempotent post-commit event cleanup.

ALTER TABLE events ADD COLUMN delete_plan TEXT;
ALTER TABLE events ADD COLUMN delete_backup TEXT;
ALTER TABLE events ADD COLUMN delete_committed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE events ADD COLUMN delete_phase TEXT;
