# Tasks — exclude-spotify-streaming-from-missing

## 1. Shared primitives in spotify.py (D4, D5)

- [x] 1.1 Add `SPOTIFY_TRACK_PREFIX`, `spotify_id_from_path(path)`, and `scrub_obfuscated(text)` (the `$A` rule from `performances._clean`) to `sidecar/src/syncbox/spotify.py`, with unit tests in `test_spotify.py`
- [x] 1.2 Add `resolve_track_meta(ids, client, transport=None) -> dict[id, {title, artist}]` to `spotify.py`: batched `GET /tracks` (50/call) when a client is given; oEmbed fallback (title only, `_OEMBED_BATCH` cap, silent stop on network error) when client is None or the API ladder fails; move the oEmbed URL/constants there; tests cover connected / no-session / offline / partial-batch cases

## 2. Consume the resolver (spotify-track-resolution spec)

- [x] 2.1 Refactor `performances.resolve_spotify_titles` to delegate the network ladder to `resolve_track_meta`, keeping its signature, its `plays` persistence semantics (API pass fills title+artist and completes artist-less rows; oEmbed pass fills title-only), and retry-on-next-refresh; delete `_SPOTIFY_PREFIX`, `_clean`, `_OEMBED_URL`/`_OEMBED_BATCH` from performances.py; `test_performances` stays green unmodified except imports
- [x] 2.2 Rewire `api._track_resolver` onto `resolve_track_meta` (single id), preserving the `library_service._spotify_track` return shape; add a test: event add by Spotify id without a session yields the oEmbed title instead of an error
- [x] 2.3 Replace the remaining `spotify:track:` literals: `api.py` performance-export state check and `untagged.py` stub rule use the shared constant; grep-audit shows one definition site (tests excepted)

## 3. Snapshot semantics (D1, D2 — spotify-streaming-tracks spec)

- [x] 3.1 In `rb.load_snapshot`: extract `spotify_track_id` via `spotify_id_from_path`; for streaming rows set `resolved_path=None` and `file_missing=False`; scrub title/artist/remixer through `scrub_obfuscated`; add snapshot fixture tests with a streaming row (id extracted, not file-missing, nulled metadata) and a regression test for a plain absent-file row
- [x] 3.2 Reuse `scrub_obfuscated` in `performances.read_rb_plays` in place of `_clean`

## 4. Exclusions at call sites (D3)

- [x] 4.1 Verify `missing_service.list_missing('collection')` and the `api.py` missing-remove / acquisition-lookup guards reject streaming rows via the new `file_missing=False` semantics; add tests: streaming row absent from `/api/missing/collection`, acquisition/remove on its content_id → not-found/conflict, counts exclude it
- [x] 4.2 Filter streaming rows (`spotify_track_id is None`) from the dedup input and the sync match-candidates at their `api.py` call sites; tests: a streaming ISRC/title twin never matches a synced track (stays `missing`) and never joins a duplicate group

## 5. Verification

- [x] 5.1 Full sidecar test suite green; repo grep confirms `spotify:track:` and `$A` rules have single definition sites
- [x] 5.2 Manual pass against the dev sandbox (Syncbox-dev, never the real DB): Missing center collection tab shows no streaming rows, HealthPill count drops accordingly, history refresh still resolves Spotify titles
