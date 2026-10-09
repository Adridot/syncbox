# Verification — 2026-10-09

## 3.1 Production ISRC check (read-only preview)

Run against the owner's production data with the development build of
`event_source_reconcile.build_plan`, the application database opened with
SQLite `mode=ro` (no migration, no write) and master.db through
`rb.open_readonly`. Syncbox 0.9.0 was running, Rekordbox was closed.

- Application DB: `~/Library/Application Support/Syncbox/syncbox.db`
- Rekordbox: `~/Library/Pioneer/rekordbox/master.db`
- ISRC collision policy: `guarded`

| Figure | Value |
| --- | --- |
| Exact-source rows with an ISRC | 27 |
| Exact-source rows without an ISRC | 0 |
| ISRC rows with a collection candidate | 16 |
| Managed Deezer downloads in the collection without ISRC | 0 (list empty) |
| ISRCs containing non-alphanumerics (rows + collection) | 0 |
| Proposed `rematch` | 16 |
| Proposed `replace` / `cleanup` | 0 / 0 |
| Skipped `no_candidate` | 11 |

The "without ISRC" list is empty, so the stop condition does not apply. All 16
proposals are `ready` rows of the event "Thibault & Alix" (nothing from 0.9.0
was applied yet, hence no `replace`). Each was compared by hand with its
candidate: same title and artist in every case, 15 in `Collection` and 1 in
`Collection manuelle`. "Sweet Caroline (Party Remix)" by DJ Ötzi resolves to
the remix content, not to the Neil Diamond original: the ISRC keeps the two
recordings apart.

Not executed. Task 5.2 (execution on production and the Rekordbox check)
belongs to the owner, from Health > Backups on the released build.
