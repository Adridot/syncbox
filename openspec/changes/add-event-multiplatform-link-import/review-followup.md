# Review follow-up — 2026-09-08

## Scope and outcome

Reviewed the two local Fable session reports and the eight follow-up commits
through `886d228`, then inspected the event import, event row/acquisition, and
component settings UI together. PR #59 had no GitHub review comments. This
report supersedes older test counts and release blockers in `verification.md`.
OpenSpec progress is **33/35**; tasks **7.1 and 7.3 remain open**.

The existing changes correctly address Deezer pagination beyond 400 entries,
SoundCloud API stub identities, individual Spotify 400/404 failures, serialized
token refresh/disconnect, pending-preview limits, provenance retention during
adoption, and fair history metadata retries. The UI redesign retains the
application's table and typography conventions. No architectural replacement
or additional dependency was needed.

## Additional corrections

- Serialize encrypted secret-store connection initialization, reads, writes,
  and close independently of the API lock. Metadata workers share this store.
- Move history Spotify network resolution outside the application DB lock;
  serialize metadata batches and discard results after DB replacement/reset.
  Unrelated settings and live-history requests remain responsive.
- Keep import history accessible after dismissing a preview and identify each
  import by provider, state, and URL. Hide the old selection while opening a
  different snapshot, preventing confirmation of an unintended snapshot.
- Retry failed snapshot reads/history restoration without creating another
  import, including recovery to an empty history. Ignore superseded responses
  and stop displaying a progress spinner after a polling failure.
- Apply the successful confirmation response immediately, refresh event rows,
  and return focus to the input without depending on another successful GET.
  Add input labels, visible focus, selection announcements, title tooltips,
  reduced-motion support, and wrapping controls for narrow windows.
- Preserve measured audio properties after acquisition publication while
  showing the event row's current status instead of a stale download badge.
- Disable component installation until readiness is known, handle invalid or
  unavailable manifests, catch settings status errors, and restore the toggle
  after a failed settings save.
- Replace the stale 0.8.0 Deezer manifest with the exact 0.9.0 artifact from
  hosted Release Pin run `34144584253` (artifact `10027230077`). Archive SHA-256:
  `acd8be0c6ff870372befbe00511a8e79625f82d48835d97d8c80e00ee569d072`.
  This corrects the baseline version check and hosted-manifest mismatch;
  it does not publish the archive.

## Findings not changed

- Spotify entries without ISRC still have manual Deezer selection; the report's
  claim that they cannot be acquired does not match the current implementation.
- Provider response bodies are read in bounded chunks. DNS capacity remains
  reserved until an outstanding system lookup finishes; releasing it on caller
  timeout would defeat the bound on outstanding lookups.
- Repeated file hashing can be expensive, but it currently enforces exact-source
  integrity. Measure a real large-library workload before choosing a cache that
  changes this guarantee.
- Some SoundCloud stub rows retain an API URL for their external source link.
  Permalink enrichment remains a small usability follow-up; identities and
  acquisition must not depend on inventing a human-facing URL.
- The later commits mark the Deno/native inventories complete and materialize
  generated notices at build time. The older 41-missing-notice blocker is stale.
  This follow-up does not independently certify every upstream notice or replace
  the native packaging evidence recorded in `component-evidence.md`.

## Validation

| Check | Result |
| --- | --- |
| Full sidecar suite | 809 passed, 11 skipped |
| Full UI suite | 143 passed across 32 files |
| UI build | Vue/TypeScript checking and production build passed |
| Full web-audio wrapper suite | 31 passed |
| Concurrent regression cases | Secret-store persistence, responsive API during history resolution, late-result rejection after reset |
| Import UI regression cases | History dismissal/reopen, failed polling and initial history reads, superseded requests, safe pending history switch, confirmation without a follow-up GET |
| Settings UI regression cases | Unknown/invalid readiness and failed-toggle rollback |
| Production browser UI | 24-entry preview with repeated/unavailable/existing/removed rows; mouse subset confirmation; focus restored after confirmation and dismissal; older committed import reopened |
| Narrow browser layout | 900 × 760 viewport; main client/scroll width both 637 px; screenshot visually inspected |
| Component settings browser UI | Unavailable-release explanation and disabled installation control |

Browser checks used controlled API fixtures and the production bundle. They
establish UI behavior, not real provider downloads or native Rekordbox writes.
The existing real-provider/frozen-component evidence retains its recorded build
and date; those downloads were not rerun for this follow-up.

## Remaining delivery work

CI, Release Pin, and CodeQL passed for `4527e05`. Alerts #3 and #4 cover the
fixed synthetic ECB round-trip in `scripts/run_b1_deezer_acquisition.py::_check`
and were dismissed as used in tests. Alert #1 was dismissed as a false positive:
the flagged packaging diagnostic value is `OAUTH_CALLBACK_PORT = 8765`, not a
stored credential. This corrects the earlier provisional SQLCipher-key
explanation. Alert #2 remains open on `master`; the PR checks are green.

1. Complete task 7.1 through the normal component release process, with matching
   published archives and manifests and the required packaging checks.
2. Finish the installed native acceptance run documented in
   [native-verification.md](native-verification.md): nine acquisitions, initial
   Apply/reapply, restart persistence, authenticated Spotify collections, and
   the Rekordbox-open guard passed. Final playlist navigation in Rekordbox
   remains visually unverified despite matching database records. SoundCloud
   collection titles and stale-snapshot error recovery need correction.

   These two defects were subsequently corrected in source and verified by
   automated regressions and a real frozen SoundCloud metadata run. Current
   evidence is in the follow-up section of `native-verification.md`.

Keep the PR in draft until these delivery gates are satisfied. No release asset,
tag, or native distribution was published as part of this follow-up.
