# POC #5 — pyrekordbox write fidelity on a real Rekordbox 7.x master.db

**Verdict: GO-WITH-CAVEATS** (all load-bearing mechanics behave exactly as specified when implemented per spec; one pyrekordbox library default deviates and must be owned by Syncbox — see caveat 1).

- Date: 2026-07-02
- Runner: `sidecar/.venv/bin/python poc/05-pyrekordbox-fidelity/harness.py` (Python 3.14, pyrekordbox 0.4.4, SQLAlchemy 2.0.51, sqlcipher3-wheels, psutil)
- Fixture: real `poc/testdata/master.db` — RB 7.x (masterPlaylists6.xml written by **rekordbox 7.2.14**), 8107 djmdContent rows (1417 active / 256, 29 × 258, 6661 × 262), 263 playlists, 160 MyTags, 1289 cues. Harness works exclusively on fresh copies under `build/` (gitignored); originals verified byte-identical (sha256) after every run.
- Result: **26/26 assertions PASS**, repeatable across two clean runs. Preflight aborts if `rekordbox`/`rekordboxAgent` is running (strict psutil filter, SPEC-UNIFIED 5.1 pattern) — verified absent.

## Acceptance criteria → measured evidence

| # | Mechanic (SPEC ref) | Result | Evidence |
|---|---|---|---|
| 1 | SQLCipher open, public constant key (00_RB.md) | PASS | `deobfuscate(BLOB) == 402fd482…8497` — pyrekordbox 0.4.4 embeds the key, no `download-key` call needed; `Rekordbox6Database(path, db_dir, key, unlock=True)` opens the copy |
| 2 | 11.3 readout fields (SPEC-UNIFIED 11.3) | PASS | Real row `ID='119070569'`: `KeyID='721950857'→DjmdKey.ScaleName='4A'`, `DJPlayCount=4`, `StockDate='2024-01-05'`, `GenreID='1384990285'→DjmdGenre 'Electro'`, `BitRate=192`, 2 cues; 263 playlists / 5623 song-playlist rows readable. `DjmdContent.ID` is `str` |
| 3 | MyTag + smart playlist, operator 8, signed 32-bit IDs (SPEC-01 1.7) | PASS | Spec example holds in code **and** in RB-written data: `signed32(2662450573) == -1632516723`, and the real 'Pop / Dance' playlist stores `ValueLeft="-1632516723"` for MyTag 2662450573 ('Pop Dance'); real playlist 3644759451 stored as `Id="-650207845"`; IDs < 2^31 stay positive (`Id="1248102774"`). New MyTag (string ID > 2^31) created under Situation category (`ID='3'`, `ParentID='root'`, `Attribute=1`); smart playlist with forced ID > 2^31 written with signed payload, XML structure shape-identical to the RB-written row; payload round-trips (`parse` → unsigned) and `filter_clause()` resolves exactly the tagged content |
| 4 | String-ID rows (SPEC-01 1.6) | PASS | Artist, content (`ID = MasterSongID = rb_file_id`, all the same string), playlist + song row all flushed and committed cleanly with string IDs |
| 5 | Soft-delete / reactivate tuples (SPEC-01 1.1) | PASS | On-disk via independent sqlcipher connection: soft-delete = `(rb_local_deleted, rb_local_synced, rb_data_status, rb_local_data_status) = (1, 0, 258, 0)`; reactivate = `(0, 0, 256, 0)`; Syncbox-side read filter (`rb_local_deleted == 0`) excludes then re-includes the row |
| 6 | masterPlaylists6.xml snapshot/restore (SPEC-01 1.6) | PASS | pyrekordbox rewrote the XML at commit (3 new hex playlist IDs present) — confirming the mechanic is needed; restore is byte-identical (sha256) to the pre-mutation snapshot |
| 7 | Non-regression | PASS | `PRAGMA integrity_check == ok` through sqlcipher after re-open; table deltas exactly `{djmdMyTag:+1, djmdSongMyTag:+1, djmdPlaylist:+3, djmdSongPlaylist:+1, djmdArtist:+1, djmdContent:+1}`; the 40 other tables (incl. agentRegistry, uuidIDMap, djmdCue, contentCue, djmdSongHistory) unchanged; local USN advanced 228086 → 228103 by updating the existing agentRegistry row |

## Caveats (build-phase requirements, none blocks GO)

1. **Syncbox must own the NODE `Id` signed-32 conversion — do not trust `SmartList.to_xml()` for playlist IDs < 2^31.** pyrekordbox 0.4.4 applies the `-2^32` shift **unconditionally** (`smartlist.left_bitshift`), while real RB 7.x rows only shift IDs > 2^31. Since pyrekordbox generates 28-bit playlist IDs, **every** native `create_smart_playlist()` call writes an out-of-signed-32-range NODE Id (measured: playlist `'165767081'` → `Id="-4129200215"`). This is the residual issue-#110-family behavior the gate asked about. Verified workaround (in harness): apply the conditional conversion `x - 2^32 if x >= 2^31 else x` to the payload after creation, or build the payload yourself — output then matches RB-written rows byte-shape-exactly. Symmetrically, `SmartList.parse()` adds `+2^32` unconditionally, so it mis-parses positive NODE Ids < 2^31 (real RB rows like 'Pop / Dance'); parse only negative-Id payloads or own the parsing too.
2. **Mixed int+string PK flush crash is not reproducible on SQLAlchemy 2.0.51 / Python 3.14** (probed: int+str inserts, insert+update mix, autoflush query — all no crash; see `crash_probe.py`). The string-ID rule stays mandatory anyway: pyrekordbox's own `add_artist`/`add_content` still pass **int** IDs, and probe s4 shows SQLite TEXT affinity silently coerces an int PK to the same stored text value (UNIQUE collision with the existing string row) — int IDs are a latent corruption/identity-map hazard, not a safe alternative.
3. **`get_content()`/`get_playlist()` do NOT filter soft-deleted rows** — the "all reads filter soft-deleted rows" invariant is entirely Syncbox-side, as the spec already states.
4. **Fixture XML drift is a real-world condition**: the RB-written masterPlaylists6.xml holds 45 nodes vs 263 DB playlists; pyrekordbox logs a warning per missing playlist at every commit (harmless, no write amplification). The spec's snapshot/restore approach neutralizes this entirely.
5. **`DjmdContent.DJPlayCount` is mapped `VARCHAR` but reads back as `int`** on this real DB — the 11.3 "never played" NULL/0 semantics hold; just don't assume `str` in code.

## Files

- `harness.py` — the assert-based harness (re-runnable; recopies fixtures each run)
- `crash_probe.py` — mixed int+string PK probe (5 scenarios)
- `explore.py` — initial read-only exploration of the fixture
- `build/` — disposable working copies (gitignored)
