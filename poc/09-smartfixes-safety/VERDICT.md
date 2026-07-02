# POC #9 — A1 Smart Fixes: bulk-write safety (SPEC-UNIFIED 5.11, section 8 item 9)

**Verdict: GO-WITH-CAVEATS** — all six gate safety properties hold, measured on a real RB 7.x `master.db`; one measured SQLite/WAL behavior means the spec's freshness fingerprint "(mtime,size) of master.db(+wal)" MUST be implemented with a normalization (caveat 1), otherwise `mutate` spuriously aborts on every run (fail-closed, never unsafe — but functionally broken).

- Date: 2026-07-02
- Runner: `sidecar/.venv/bin/python poc/09-smartfixes-safety/harness.py` (Python 3.14, pyrekordbox 0.4.4, sqlcipher3-wheels, SQLAlchemy 2.0.51, psutil)
- Fixture: real `poc/testdata/master.db` (RB 7.2.14, 8107 djmdContent rows, 1417 active), worked on EXCLUSIVELY as fresh copies under `build/` (gitignored); originals verified byte-identical (sha256) after every run. Preflight aborts if `rekordbox`/`rekordboxAgent` runs (strict psutil filter).
- Result: **28/28 assertions PASS, repeatable across two clean runs** (~6.5 s/run). The fixture genuinely uses the spec section 4 storage layout: **1324/1417 active rows match the real protected path rule** `<storage_root>/rekordbox/Collection` — the protected guard was exercised on real paths, not a simulation.

## The six gate properties → measured evidence

| # | Property | Result | Evidence |
|---|---|---|---|
| a | dry-run preview == payload actually written, EXACTLY | PASS | Full-table diff (all 8107 rows incl. soft-deleted, independent sqlcipher connection) after mutate == the previewed payload field-by-field: 11 field writes, not one more, not one less. Only other DB change: `djmdArtist +3` (find-or-create for extracted/cleaned artist names, string IDs per POC #5); `PRAGMA integrity_check == ok` |
| b | idempotence: second dry-run after mutate is empty | PASS | Payload EMPTY after mutate (re-run = no-op); catalog also proven a fixpoint on real data: `compose(compose(x)) == compose(x)` for all 1417 active rows. Clean seeded row and already-conform fields emit NO no-op rows (`before != after` asserted on every payload row) |
| c | determinism under shuffled input | PASS | 5 shuffled passes over all 1417 snapshot rows → identical composed results; dry-run recomputed from a fresh disk read (cache invalidated) is identical to the cached one; fixed catalog order is load-bearing (URL strip MUST precede 'Artist - Title' extraction, else `"Track - www.x.com"` extracts "Track" as artist) |
| d | protected excluded by default; explicit non-persisted by-name opt-in | PASS | 237 protected tracks with pending diffs skipped by default and enumerated BY NAME; none in the payload. Opt-in for ONE track ({P7}) mutated only it; the NEXT default dry-run excluded protected again (P8 back in the skipped list — opt-in provably not persisted); remaining 236 fixed only via a second explicit opt-in; final dry-run (even with opt-in) fully empty |
| e | freshness guard: DB modified between dry-run and mutate → ABORT | PASS | External sqlcipher write between dry-run and mutate → `StaleSnapshotError` ("…Nothing was written. Please run a new dry-run…"), **no backup created, nothing written**; guard runs at `_mutate` entry, before backup/open |
| f | exception mid-mutation → rollback, DB == backup | PASS | Crash injected AFTER the payload was applied+flushed → original exception re-raised; full field dump + all table row counts identical to pre-mutate state AND to the step-(b) backup; integrity ok; a fresh dry-run→mutate afterwards completes and is idempotent |

## Unit-of-work `_mutate` mechanics (spec 3.1) — also verified

- **(a) RB closed + DB exists**: guard runs on every `_mutate` entry (counter-asserted); with a simulated running `rekordbox` process, mutate aborts BEFORE backup/open with the friendly message — asserted to contain no PID, no `/Applications/` path, no `--type=` flag.
- **Dry-run never requires RB closed**: the whole dry-run phase ran with the "rekordbox running" probe active and never called the guard; the snapshot connection is `mode=ro` at the SQLite level (a write attempt raises "attempt to write a readonly database"); master.db byte-stat untouched by dry-runs.
- **(b) timestamped backup** of `master.db(+wal/shm)`; same-second collision → suffix (`master.db.20260702-230835` then `…-2`), verified inside one wall-clock second.
- **(c/d/e) open → mutate → commit + snapshot-cache invalidation**: cache keyed on the normalized (mtime,size) fingerprint; second dry-run hits the cache (1 disk load); cache proven cleared at commit (next dry-run re-reads).

## Caveats (build-phase requirements; none blocks GO)

1. **The freshness/cache fingerprint must NORMALIZE the wal part — do not implement "(mtime,size) of master.db(+wal)" literally.** Measured on macOS/APFS + sqlcipher: closing the last rw connection checkpoints and DELETES `master.db-wal`; a subsequent `mode=ro` open RECREATES a 0-byte `-wal` (+`-shm`). A literal fingerprint therefore changes after every read and `_mutate` would abort with `StaleSnapshotError` on every run (fail-closed, never corrupting — but the feature would be unusable). Verified rule: fingerprint = master.db `(mtime_ns,size)` + wal `(mtime_ns,size)` **only when the wal is non-empty**; "wal absent" ≡ "wal empty" (an empty WAL carries no journal content). With this normalization the fingerprint is stable across reads and still trips on any real write (an external write flips the master.db part after checkpoint, or grows the wal).
2. **Keep the naive casing fix OUT of the v1 catalog** (evidence for the §5.11 ponytail note). This fixture has 13 all-caps titles that are legitimate stylizations (`DÁKITI`, `SNAP`, `#SELFIE`, `JCVD`…): an all-caps→title-case "fix" would overwrite clean user input. The POC catalog shipped 3 fixes (URL/junk strip, 'Artist - Title' extraction, whitespace/NBSP collapse) and on real data produced **zero false positives**: all 240 real-data diffs are genuine structural artifacts — 233 artist names with trailing/doubled whitespace (`'KAROL G '`, `'El Chojin          '`), 7 titles with doubled spaces/NBSP/trailing space.
3. **"Artist" field writes are `ArtistID` relinks** (find-or-create `djmdArtist` by exact cleaned name, string IDs per POC #5), not in-place edits of the artist row — the shared old dirty artist row is left behind unreferenced (or still referenced by other tracks); harmless, and it keeps a rename on one track from silently renaming every other track by the same artist. v1 should do the same.
4. **The real collection is dirtier on the protected side than expected**: 237 of the 246 tracks with pending fixes are protected under the path rule, so a default run only touches a handful of tracks. The §5.11 by-name enumeration of skipped protected tracks (and the opt-in listing them in the B10 confirm text) is not a corner case — it is the main UX path on this fixture.
5. pyrekordbox logs one warning per DB-playlist missing from `masterPlaylists6.xml` at every commit (fixture drift, known from POC #5 caveat 4) — harmless noise, silenced with logger level ERROR in the harness.

## Files

- `smartfix_core.py` — prototype kernel: `_mutate` unit-of-work, normalized fingerprint + read-only snapshot cache, FIXED 3-fix catalog (deterministic order, composed result), `dry_run`, `smartfix_mutate`
- `harness.py` — 28-assertion harness for the six properties + unit-of-work mechanics (re-runnable; recopies fixtures and reseeds each run)
- `probe_ro.py` — initial probe: `mode=ro` open on the WAL fixture, real dirty-data shapes
- `build/` — disposable working copies + timestamped backups (gitignored)
