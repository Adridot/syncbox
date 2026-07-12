# POC #7 — B2 Purchase-Link Browser Behavior

Date: 2026-07-12

## Objective and security boundary

Validate the fixed Beatport and Bandcamp search templates on representative
tracks. Syncbox only builds an HTTPS URL from the shared D19-normalized
artist/title and passes it to Tauri's external URL opener. The sidecar performs
no HTTP request, API call, scraping, result resolution, or credential use.

Templates:

```text
https://www.beatport.com/search?q={query}
https://bandcamp.com/search?q={query}&item_type=t
```

## Browser sample

The pages were opened with browser tooling on 2026-07-12. “Visible” below
means within the first five Beatport tracks or first three Bandcamp results.

| Track | Beatport | Bandcamp |
|---|---|---|
| Bicep — Glue | Original first; relevant | First visible results were bootlegs/edits |
| RÜFÜS DU SOL — Innerbloom | Page loaded; no track result | First visible results were edits/remixes |
| Charlotte de Witte — Roar | Original first; relevant | Original first; relevant |
| Aphex Twin — Xtal | Page loaded; no track result | First visible results were remixes |
| Björk — Jóga | Page loaded; no track result | First visible results were cover/remix/jam tracks |
| AC/DC — Thunderstruck | Page loaded; no track result | First visible results were remixes/edits |
| Above & Beyond — Sun & Moon | Original visible second; first result irrelevant | First visible results were edits/bootlegs |
| unavailable sentinel | Unrelated token matches were returned | Empty results |

Observed relevance:

- Beatport: the correct original appeared for 3/7 real tracks and was first
  for 2/7;
- Bandcamp: the correct original appeared and was first for 1/7 within the
  inspected result window;
- all 16 store pages loaded and retained the intended query;
- unavailable behavior differs: Beatport may return unrelated token matches,
  while Bandcamp may return an empty page.

These results validate navigation, not catalog coverage or a guaranteed first
result. Syncbox must not inspect the page to improve relevance because that
would break the zero-network sidecar boundary.

## Metadata limitations

D19 applies NFKD-to-ASCII normalization. Latin diacritics are transliterated:
`RÜFÜS` becomes `rufus` and `Björk — Jóga` becomes `bjork joga`. Characters
without an ASCII decomposition are removed. Fully CJK or emoji metadata can
therefore normalize to an empty string; Syncbox emits no purchase button in
that case. This is explicit and covered by tests.

`acquisition_failed` remains excluded because B1 is not implemented. Adding
that status before B1 would expose a state that the v1 app cannot currently
produce.

## Verification

```sh
cd sidecar
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -rs \
  -p no:cacheprovider tests/test_purchase_links.py
# 7 passed

cd ../ui
pnpm exec vitest run \
  src/screens/__tests__/missing-center.spec.ts \
  src/components/__tests__/chrome.spec.ts
# 9 passed
```

The focused tests pin the URL shapes, D19 behavior, store removal, status
gate, absence of sidecar network imports, and delegation of the UI click to
the external-browser bridge.

## Verdict

**GO with documented relevance and non-ASCII limits.** Both templates are
live and browser-safe. B2 remains visually primary. Result relevance is a
store/catalog property and is not elevated into a Syncbox correctness claim.

## Sources

- [Python `urllib.parse`](https://docs.python.org/3/library/urllib.parse.html)
- [Tauri opener plugin](https://v2.tauri.app/plugin/opener/)
- [Bandcamp search update](https://blog.bandcamp.com/2022/07/13/weve-improved-search/)
- [Beatport search](https://www.beatport.com/search)

The historical `docs/_research/13_Achat-legal-ISRC.md` file referenced by
older specifications is absent from this checkpoint and was not reconstructed.
