# Phase 3 Handoff — Conservative Smart Fixes

Date: 2026-07-12

## Verdict

**READY FOR PHASE 4 IMPLEMENTATION, NOT READY FOR RELEASE ACCEPTANCE.**

The fixed Smart Fixes catalog, safety hardening, synthetic integration tests,
API/UI behavior, and i18n are complete. The real copied-Rekordbox POC remains
**BLOCKED BY PRIVATE FIXTURE AVAILABILITY** and is still a release gate. No
private fixture was fabricated and no missing real validation was weakened.

## Completed Scope

### Fixed conservative catalog

The catalog remains server-owned, ordered, and non-configurable. It applies to
`title`, `artist`, and `remixer` without inspecting file ownership.

Scalar cleanup runs first:

1. repair selected common UTF-8-read-as-latin-1/Windows-1252 mojibake
   signatures only when one unique reverse decode strictly reduces those
   signatures; repeated recognized corruption is repaired to a fixpoint in
   the same run;
2. decode only the exact semicolon-terminated XML entities `&amp;`, `&quot;`,
   `&apos;`, `&lt;`, and `&gt;`;
3. normalize canonically to Unicode NFC, never NFKC;
4. collapse characters recognized by Python as Unicode whitespace and remove
   a leading BOM, while preserving ZWJ and other meaningful format controls;
5. remove a terminal HTTP(S), `www.` URL, or wrapped domain only when an
   explicit separator or balanced wrapper proves it is site junk;
6. remove only the separator made orphaned by a recognized URL or featured
   credit extraction.

Structural credit extraction runs on the composed scalar values:

- one balanced terminal `(feat. Name)`, `(ft. Name)`, `(featuring Name)`, or
  square-bracket equivalent is moved to an existing non-empty artist credit;
  artist-name casing is preserved and only the structural join marker is
  canonicalized;
- featured extraction is refused when it would repeat the current artist,
  leave no alphanumeric base title, or exceed the Rekordbox artist-name limit
  of 255 characters;
- one balanced terminal `(Known Name Remix)` or square-bracket equivalent may
  fill an empty remixer only when the candidate resolves to exactly one known
  artist/remixer name in the current snapshot;
- remixer extraction never changes the remix title or other extra title
  information;
- an existing remixer, conflicting feature credit, unknown or ambiguous name,
  nested syntax, or multiple recognized blocks remains unchanged.

### Determinism and exact-payload enforcement

- Planner output is sorted by string `content_id`, then fixed field order
  `title`, `artist`, `remixer`.
- Execute now compares the submitted payload to the complete canonical plan by
  exact list/dictionary equality before `_mutate`.
- Partial, reordered, duplicated, enriched, type-changed, added, or modified
  payloads are rejected before backup or write.
- Empty direct plans still require Rekordbox to be closed, then return a no-op
  without opening the database, creating a backup, or invalidating the cache.
- The existing cache fingerprint check remains before planning, and `_mutate`
  independently rechecks the database fingerprint before backup.
- Every non-empty execute still uses the single guarded `_mutate` path:
  Rekordbox-running guard, timestamped backup, open, ordered writes, commit,
  cache invalidation, close; exceptions before commit roll back and retain the
  backup.

### Rekordbox compatibility

- The read-only snapshot now exposes the current remixer through
  `DjmdContent.RemixerID` and a separate `djmdArtist` join.
- The writer can reassign `RemixerID` through the existing
  `find_or_create_artist` helper. It never renames a shared artist row.
- Existing ownership classification and event migration behavior were not
  changed.

### UI and i18n

- The Smart Fixes screen advertises exactly three fixed families: conservative
  cleanup, reversible encoding cleanup, and conservative credit extraction.
- The UI explicitly states that generic casing is not performed, stylized
  uppercase/mixed-case names are preserved, and ambiguous patterns are skipped.
- The dry-run CTA remains available while Rekordbox is open; execute remains
  disabled until Rekordbox is closed and is still guarded server-side.
- The confirmation modal handles `before: null` and empty strings, localizes
  title/artist/remixer labels, shows the exact content ID for every change,
  and echoes only `{payload, fingerprint}`.
- Dialog naming, stale/error announcements, busy states, and the dismiss
  button have accessible semantics.
- English/French key parity is preserved.

### Source hygiene

- All executable-source Ponytail markers were removed while retaining useful
  load-bearing technical comments.
- `rg -n "ponytail" sidecar/src ui/src shell/src-tauri/src` is empty.
- No dependency, generic rules engine, acquisition code, packaging work, or v2
  infrastructure was added.

## Unsupported Cases Kept Unchanged

- Generic title case, lowercasing, acronym correction, or any transformation
  of names such as `DAKITI`, `SNAP`, `#SELFIE`, `deadmau5`, `CamelPhat`, or
  `t.A.T.u.`.
- Automatic `Artist - Title` splitting. Current industry tooling requires the
  user to choose both separator and segment position, which is incompatible
  with this fixed universal catalog.
- NFKC, transliteration, diacritic removal, width folding, ligature folding,
  ZWJ/variation-selector deletion, or emoji rewriting.
- Numeric, unterminated, unknown, or case-variant entities.
- Mojibake containing replacement characters, mixed ambiguous encodings,
  unrecognized Greek/Cyrillic/CJK signature families, or encodings outside the
  narrow latin-1/Windows-1252 reversal.
- Bare domains without a wrapper, URLs without a separating structure, and
  promotional text that is not an explicit URL.
- Unbracketed, nested, multiple, or conflicting featured credits.
- Featured credits that repeat the current artist, exceed the 255-character
  artist-name limit, or would leave a separator/symbol-only base title.
- Unknown/non-unique remixers, a pre-existing remixer, unparenthesized remix
  text, and heuristic removal of `Extended`, `Dance`, `Club`, `Mix`, `Edit`,
  `Rework`, `Bootleg`, or `VIP` qualifiers.

## Files Changed

### Smart Fixes backend and Rekordbox bridge

- `sidecar/src/syncbox/smartfixes.py`
- `sidecar/src/syncbox/smartfixes_run.py`
- `sidecar/src/syncbox/rb.py`
- `sidecar/src/syncbox/rb_write.py`

### Backend tests

- `sidecar/tests/test_smartfixes.py`
- `sidecar/tests/test_api.py`
- `sidecar/tests/test_rb.py`
- `sidecar/tests/test_rb_write.py`

### UI, types, i18n, and UI tests

- `ui/src/api/types.ts`
- `ui/src/screens/health/SmartFixesTab.vue`
- `ui/src/components/DryRunModal.vue`
- `ui/src/components/ModalShell.vue`
- `ui/src/i18n/en.ts`
- `ui/src/i18n/fr.ts`
- `ui/src/screens/__tests__/health-tabs.spec.ts`
- `ui/src/components/__tests__/dryrun.spec.ts`
- `ui/src/components/__tests__/chrome.spec.ts`

### Documentation and POC index

- `README.md`
- `poc/README.md`
- `docs/_handoffs/phase-03-smart-fixes.md`

### Source-hygiene-only comment updates

- `sidecar/src/syncbox/api.py`
- `sidecar/src/syncbox/relink.py`
- `sidecar/src/syncbox/settings.py`
- `sidecar/src/syncbox/secrets.py`
- `sidecar/src/syncbox/purchase_links.py`
- `sidecar/src/syncbox/server.py`
- `sidecar/src/syncbox/safety/process_guard.py`
- `ui/src/lib/usePathFields.ts`
- `shell/src-tauri/src/main.rs`

## Exact Validation Performed

### Backend

```sh
cd sidecar
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  -p no:cacheprovider tests/test_smartfixes.py
```

Result: **19 passed**.

```sh
cd sidecar
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -rs \
  -p no:cacheprovider tests/test_smartfixes.py tests/test_api.py
```

Result: **86 passed**.

```sh
cd sidecar
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -rs \
  -p no:cacheprovider tests/test_smartfixes.py tests/test_api.py \
  tests/test_rb.py tests/test_rb_write.py
```

Result: **97 passed, 5 skipped**. The skips are the focused real-Rekordbox
nodes whose private `master.db` fixture is unavailable.

```sh
cd sidecar
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -rs \
  -p no:cacheprovider
```

The final run, with loopback permission for the existing port-collision test,
reported:

- **461 passed**;
- **11 skipped**;
- no failures.

The 11 skips are the ten existing private `master.db` integration nodes plus
the retained-event migration manifest node. No skip was added to hide a Phase
3 failure.

### UI

```sh
cd ui
pnpm test
pnpm typecheck
pnpm build
```

Results:

- **19 test files, 65 tests passed**;
- typecheck passed;
- production Vite build passed, 194 modules transformed;
- existing non-failing Intlify global-scope warnings remain visible in tests.

### Rust and hygiene

```sh
cd shell/src-tauri
cargo check
```

Result: passed.

```sh
rg -n "ponytail" sidecar/src ui/src shell/src-tauri/src
```

Result: empty.

The focused source scan found no personal path or generated acquisition
configuration. The only `ARL` occurrence is an existing comment stating that
the deferred acquisition field is not built.

## POC Status

```sh
sidecar/.venv/bin/python poc/run_real_rekordbox_tests.py --list
```

Result: the ten-node contract still includes
`tests/test_rb_write.py::test_smartfixes_runner_end_to_end`.

That node now verifies:

- repeatable preview before execution;
- every previewed field equals the value read back from the copied database;
- one timestamped backup exists;
- the next preview is empty;
- a stale preview aborts.

```sh
sidecar/.venv/bin/python poc/run_real_rekordbox_tests.py --check
```

Result: expected exit **2**, missing private `poc/testdata/master.db`.

```sh
sidecar/.venv/bin/python poc/run_event_migration_tests.py --check
```

Result: expected exit **2**, missing private
`poc/testdata/event-migration.json` and its audio/ANLZ fixtures.

Therefore:

- Smart Fixes POC #8: **BLOCKED BY FIXTURE AVAILABILITY**;
- retained-event migration POC #9: **BLOCKED BY FIXTURE AVAILABILITY**;
- both remain release gates;
- Phase 4 implementation may proceed independently under the owner's explicit
  acceptance of synthetic/unit integration work.

## Safety Findings Resolved

1. The previous membership-set validation accepted partial, reordered,
   duplicated, and enriched payloads; exact full-plan equality now rejects all
   of them before backup.
2. The previous plan inherited unspecified SQL row order; planner sorting now
   makes preview and execution ordering deterministic.
3. The previous URL helper stripped trailing separators even when no URL was
   removed and could erase a URL-only value; contextual matching now preserves
   both cases.
4. The previous mojibake helper missed common Windows-1252 punctuation
   signatures and needed another run for double encodings; strict candidate
   selection now reaches a fixpoint for the selected signatures.
5. The previous snapshot/writer could not preserve or fill `RemixerID`; both
   paths now handle the shared artist reference explicitly.
6. Earlier source comments claimed a Smart Fixes POC had succeeded. Those
   claims were removed; the real POC remains explicitly blocked.
7. Cross-track remixer resolution could otherwise need a second run after a
   featured credit changed another artist name. The planner now completes all
   scalar and featured-credit changes before compiling the known-name map.
8. Malformed or nested bracket structures, multiple recognized feature/remix
   blocks, multiple trailing URL suffixes, and URLs exposed by credit removal
   now resolve conservatively in one pass or remain unchanged.
9. Featured-credit expansion now refuses duplicate artist/guest values,
   separator-only base titles, and generated artist names above 255 characters.
10. The direct empty-plan execution path now applies the Rekordbox-running
    guard while still avoiding database open, backup, write, and invalidation.

## Research Basis

- [Unicode UAX #15](https://www.unicode.org/reports/tr15/) and
  [Python 3.14 `unicodedata`](https://docs.python.org/3.14/library/unicodedata.html)
  support NFC canonical normalization and warn against blind compatibility
  folding.
- [Python `str.title`](https://docs.python.org/3.14/library/stdtypes.html#str.title)
  documents its language-independent lowercasing behavior and apostrophe
  failure modes, supporting exclusion of generic title case.
- [MusicBrainz Artist Credits](https://musicbrainz.org/doc/Style/Artist_Credits)
  places featured artists in artist credits rather than titles.
- [MusicBrainz remix guidance](https://musicbrainz.org/doc/Style/Specific_types_of_releases/Remixes_and_mashups)
  requires preserving remix extra-title information.
- [Lexicon Extract Remixer](https://www.lexicondj.com/manual/smartfix-extract-remixer)
  fills a remixer tag without changing the title, while
  [Lexicon Extract Artist From Title](https://www.lexicondj.com/manual/smartfix-extract-artist-from-title)
  requires user-selected separator and result position.
- The installed pyrekordbox 0.4.4 schema exposes `DjmdContent.RemixerID` as a
  separate foreign key to `DjmdArtist`.
- [WAI-ARIA modal dialog guidance](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/),
  [WCAG status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html),
  and [Vue fallthrough attributes](https://vuejs.org/guide/components/attrs)
  support the focused accessibility changes.

## Remaining Release Actions

1. Supply only local private Rekordbox fixtures and run the copied-fixture
   harness with zero skips.
2. Open the copied result in the target Rekordbox 7.x version and verify the
   previewed title, artist, and remixer values, search behavior, playlists,
   cues, and collection integrity.
3. Run the accepted retained-track audio/ANLZ POC and manual reopen/playback
   checks before release acceptance.

No A3/B2 validation, B1 acquisition, packaging, Windows, signing, Keychain, or
deferred v2 work was performed.
