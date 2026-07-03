-- 0001: application schema bootstrap.
-- Settings are key-value JSON; defaults are applied at READ time, never
-- seeded or re-saved at boot (SPEC-UNIFIED 5.10, bug class B4).
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
