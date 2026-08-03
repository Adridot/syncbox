# Design — exclude-spotify-streaming-from-missing

## Context

See proposal.md for motivation. Load-bearing current-state facts:

- `rb.py:load_snapshot()` computes `file_missing = not tcc_exists(resolved) if resolved else True`; a `spotify:track:<id>` FolderPath resolves to a bogus `$CWD/spotify:track:…` path, so every streaming row is file-missing. Title/artist arrive `$A7:v1:…`-obfuscated (djmdContent for streaming rows); only `performances._clean` knows about `$A`.
- Snapshot consumers: `missing_service.list_missing('collection')` filters `row["file_missing"]`; `api.py` missing-remove (~L1110) and acquisition lookup (~L1298) re-check `row["file_missing"]` directly against the cache; dedup ranks on `file_missing`; quality is already neutral for non-existent paths; sync/matching consumes snapshot rows as candidates.
- The full ID→title ladder (batched `GET /tracks`, oEmbed fallback, 50-id API cap, `_OEMBED_BATCH=50`) lives in `performances.resolve_spotify_titles`, interleaved with `UPDATE plays` statements. `api._track_resolver` does a separate single-track `GET /tracks/{id}` for event adds, no fallback. `spotify.py`'s docstring claims all outbound network calls live there — already false because of oEmbed.
- The `spotify:track:` literal exists in `performances.py:57`, `api.py:2196`, and as a title-stub rule in `untagged.py:38`.

## Goals / Non-Goals

**Goals:**
- Streaming rows carry `spotify_track_id` from the snapshot on; everything downstream keys off that one field (`spotify_track_id is not None` IS the streaming predicate — no extra boolean).
- The missing/acquisition/remove/dedup/matching exclusions fall out of snapshot semantics plus at most one-line filters at call sites.
- One table-agnostic resolver in `spotify.py`; `performances` and `_track_resolver` become consumers.

**Non-Goals:**
- No persistence of resolved titles for collection streaming rows (no new cache table, no app-DB column). The Missing fix doesn't need it — rows are excluded, not decorated. Revisit only if a UI surface later needs streaming titles from the snapshot.
- No UI changes; no i18n additions; no changes to library/event missing scopes (their statuses come from matching, which is fixed at the candidates side).
- No generic multi-provider streaming detection (Tidal/Beatport URIs): only `spotify:track:` is observed in real master.db data. The single-constant design makes adding prefixes later trivial.
- Untagged behavior unchanged: scrubbed-to-null titles still classify as junk (empty-title rule), same category as today's stub rule.

## Decisions

**D1 — Represent streaming in the snapshot as `spotify_track_id` + `file_missing=False` + `resolved_path=None`.**
Rationale: "no file to miss" is the truthful semantics; `missing_service` then needs zero changes for the list, and missing-remove/acquisition guards (`if not row["file_missing"]`) reject streaming rows for free. Alternative considered: keep `file_missing=True` and filter at every consumer — more touch points, and every future consumer inherits the bug by default.
Consequences audited: quality already returns `file_missing_neutral` on the bogus path regardless; dedup's keeper-ranking change is moot because streaming rows are removed from its input (D3); `classify_ownership` already yields `external` for these paths.

**D2 — Scrub `$A…` metadata at snapshot load.**
Move the `$A` predicate next to the new prefix constant (one helper, e.g. `scrub_obfuscated`), apply it to title/artist/remixer in `load_snapshot`, and reuse it in `performances.read_rb_plays` (replacing `_clean`). Null titles are what the rest of the pipeline already handles (matching normalize, untagged junk, UI `?? untitled`).

**D3 — Exclude streaming rows at the two file-centric call sites.**
Dedup input and sync match-candidates get a `if not r.get("spotify_track_id")` filter where the cache rows are handed over (api.py call sites). Alternative: filter inside `find_duplicate_groups`/`match` — rejected, those are pure functions over dicts and shouldn't know about streaming.

**D4 — Resolver extraction: `spotify.resolve_track_meta(ids, client, transport=None) -> dict[id, {"title", "artist"}]`.**
Pure with respect to storage: no DB access, returns a mapping; callers persist. Ladder preserved exactly: batches of 50 via `client.get("/tracks?ids=…")` when a client is given; on `NotConnectedError`/`SpotifyApiError` or `client=None`, oEmbed for up to `_OEMBED_BATCH` ids (title only); network errors stop the oEmbed loop silently. `performances.resolve_spotify_titles` keeps its signature and its two-pass persistence (API pass fills title+artist, oEmbed pass fills title-only rows) by calling the resolver twice at most — or once with the returned partials; keep whichever reads simpler, behavior is what tests pin. `_track_resolver` calls it with one id and maps to the `library_service._spotify_track` shape it must keep returning (duration/isrc absent from oEmbed results → nullable, already tolerated by `add_track`). oEmbed URL/transport move into `spotify.py`, restoring the "only outbound calls here" docstring.

**D5 — One constant, one extractor.**
`spotify.py` exports `SPOTIFY_TRACK_PREFIX = "spotify:track:"` and `spotify_id_from_path(path) -> str | None`. Consumers: `rb.py` (new), `performances.py` (replaces `_SPOTIFY_PREFIX`), `api.py:2196` (performance export states), `untagged.py:38` (stub rule keeps checking the title field, but via the shared constant). No import-cycle risk: `spotify.py` imports nothing from these modules.

## Risks / Trade-offs

- [Streaming rows vanish from Missing with no trace — a user who saw them yesterday may wonder where they went] → They were displayed as `$A…` garbage, not as recognizable tracks; release note line suffices. If visibility is ever wanted, the snapshot field makes a "Streaming" badge/tab cheap.
- [Event add via oEmbed produces artist-less, ISRC-less tracks that match worse] → Same data the user gets today only by connecting Spotify first; matching already tolerates null artist/isrc (fuzzy/similarity paths). Better than today's hard failure without a session.
- [Some hidden consumer relies on streaming rows being file_missing] → Repo-wide `file_missing` consumer audit done (missing_service, api ×2, dedup, quality, UI DuplicateGroupCard); tests over snapshot fixtures with streaming rows pin the new contract.
- [performances behavior drift during extraction (batching, retry-on-next-refresh, artist-less completion)] → Existing `test_performances` suite pins it; the refactor keeps `resolve_spotify_titles`'s signature and persistence semantics.

## Migration Plan

Pure sidecar change, no schema migration, no data rewrite: the snapshot is recomputed per fingerprint, and `plays` rows already resolved stay resolved. Rollback = revert the commit.
