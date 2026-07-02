# POC #8 — B2 purchase-link template robustness

**Status: GO — 2026-07-02.**

## What was tested (`b2_templates.py`, stdlib only, zero network in the builder)

1. **Encoding edge cases** — all assertions pass: accents/diacritics (NFKD→ASCII fold),
   ampersands (`&`→`and`), `feat.`/dots, slashes, apostrophes, 300-char fields, empty
   artist, emoji-only, CJK-only. Every produced URL is well-formed https with no raw
   spaces.
2. **Degradation rule** — input that normalizes to nothing (CJK-only, emoji-only, empty)
   yields `[]` (no buttons → `purchase_link_unavailable` upstream), never a crash or a
   junk URL.
3. **Store-disappeared fallback is data-driven** — removing the Beatport entry from the
   literal catalog removes its button with zero code change (Juno lesson, §5.13).
4. **D19 normalization shared with matching** — same pipeline shape as §5.3 (NFKD→ASCII,
   lowercase, parens/brackets stripped, `&`→and, non-alphanumeric→space).

## Owner spot-check (first-result quality)

The app never fetches stores (§5.13 hard rule), so first-result quality is a human
browser check. 8 sample URLs are printed by `b2_templates.py` (Daft Punk, Charlotte de
Witte, Amelie Lens, Bicep, Rüfüs Du Sol, Peggy Gou, Âme, Fred again..) — open a few in
a browser and confirm the track lands in the first results.

## Caveats

- **CJK/non-Latin metadata produces no purchase link** (D19 normalization drops
  non-ASCII). Acceptable for v1 (electronic-music catalogs are overwhelmingly Latin);
  revisit only if a real user hits it — would need a normalization exception for B2,
  not a change to matching.
- Beatport is known to 403 bots; that only affects automated checks, not the user's
  browser.
