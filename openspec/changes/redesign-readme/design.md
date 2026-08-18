## Context

See [proposal.md](proposal.md) — Why.

Constraints that shape the rewrite:

- **The facts already exist and are correct.** `docs/USER_GUIDE.md`,
  `docs/SPEC-UNIFIED.md`, `docs/DISTRIBUTION.md`, and `docs/PRIVACY.md` are
  accurate and maintained. The README's job is to route to them, not to
  restate them. Every claim in the new README must be traceable to one of
  those files or to the current code — no new promises.
- **Distribution is unusual and cannot be softened.** macOS 14+ Apple Silicon
  only, ad-hoc signed, not notarized, no auto-update. A reader who discovers
  the Gatekeeper prompt after downloading feels tricked; a reader who is told
  up front does not. This constraint is a headline, not a footnote.
- **The legal posture is load-bearing.** Purchase links come first; Deezer
  acquisition is an optional, separately distributed, disabled-by-default
  component. Marketing-flavoured wording here is a real risk, not a style
  preference.
- **One version string, several places.** The README currently hard-codes
  `0.7.2` three times (source version, asset filename, release tag). The
  release-prep recipe already bumps it; the rewrite must not multiply the
  number of places to bump.
- **Only one screenshot exists**, hosted as a GitHub user-attachment URL from
  a previous commit. New captures are Adrien's to produce.

## Goals / Non-Goals

**Goals:**

- A reader who has never heard of Syncbox understands, within the first
  screen, who it is for and what it does for them.
- The value proposition is legible **before** downloading — including the
  hard limits (platform, signing, no auto-update).
- Contributor material is present in the repo but out of the README.
- Prose survives a version bump: no feature description embeds a version.

**Non-Goals:**

- Not a docs reorganization. `docs/` keeps its current files and structure;
  only `README.md` content moves, and it moves into two new root files.
- Not a French translation, not a logo or banner redesign.
- Not producing the screenshots — the rewrite reserves their slots.
- Not changing `.github/SECURITY.md`, CI, or the release workflow.

## Decisions

### D1. README outline — fixed section order

The apply phase writes exactly these sections, in this order. This is the
contract; task items map one-to-one onto it.

| # | Section | Content | Source of truth |
|---|---|---|---|
| 1 | Hero | Name, one-line tagline, badge row, hero screenshot | — |
| 2 | What is Syncbox? | 3–4 sentences, no jargon: Spotify is where you find music, Rekordbox is where you play it, Syncbox is the bridge and the janitor | — |
| 3 | Who it's for | Short bullet list of DJ situations ("you crate-dig in Spotify", "your collection has grown past the point of hand-tagging") | — |
| 4 | Before you download | Platform, ad-hoc signing / Gatekeeper, no auto-update, your data stays local | README §Install, `docs/DISTRIBUTION.md` |
| 5 | Features | One subsection per feature, problem-first, each with a screenshot slot | `docs/USER_GUIDE.md` §Main screens |
| 6 | Your collection is safe | Short reassurance block, ≤5 bullets, linking to the full pipeline | `docs/USER_GUIDE.md` §Rekordbox write safety |
| 7 | Install | Numbered steps, download → Gatekeeper → onboarding | README §Install |
| 8 | FAQ | 6–8 `<details>` entries: Windows? free? does it touch my files? Spotify password? need Spotify Premium? can I undo? where's my data? | `docs/PRIVACY.md`, `docs/USER_GUIDE.md` |
| 9 | Documentation | Link table to the five `docs/` files | — |
| 10 | Contributing & support | Links to `CONTRIBUTING.md`, `SUPPORT.md`, `.github/SECURITY.md` | — |
| 11 | Roadmap & limits | The deferred list, trimmed and de-jargonized | README §Status & roadmap |
| 12 | License | Short MIT line + third-party notice pointer | README §License |

Alternative considered: keeping the current section order and only rewriting
prose. Rejected — the current order puts the safety model and architecture
above the feature list, which is exactly the inversion the change exists to
fix.

### D2. Feature sections are problem-first, two paragraphs maximum

Each of the five feature subsections (Spotify → Rekordbox, Events, Collection
health, Performance history, Doctor & backups) opens with the DJ-facing
problem in one sentence, then what Syncbox does. Mechanism detail (ISRC-first
then fuzzy, MyTag + smart playlist, spectral cutoff heuristics) is at most one
clause, or a link.

Vocabulary rule: `ISRC` → "the track's unique recording ID"; `MyTag` stays
(it is Rekordbox's own term) but is defined on first use; `master.db` →
"your Rekordbox database"; sidecar, PKCE, SSE, and SQLCipher do not appear in
the README at all.

Alternative considered: a compact feature table instead of prose sections.
Rejected — a table has nowhere to put screenshots, and screenshots are the
main reason a reader believes the feature list.

### D3. Screenshots — placeholders now, `docs/assets/` later

The hero keeps the existing GitHub user-attachment URL (it works, it is
already on the README, and re-hosting it is not this change's job). The four
new per-feature slots are HTML comments naming the intended capture and the
target path:

```html
<!-- screenshot: Library — match review. Drop at docs/assets/library.png and
     replace this comment with: ![Library](docs/assets/library.png) -->
```

`docs/assets/` is created with a `.gitkeep` so the path exists.

Alternative considered: committing the placeholder images themselves.
Rejected — a repo with four "screenshot coming soon" boxes reads worse than
a repo with none.

### D4. Version string appears exactly twice, both inside the Install steps

Current README states the version in a standalone "Current source version"
line, in the asset filename, and in the release tag URL. The standalone line
is dropped (the release badge carries it, always accurate, zero maintenance);
the asset filename and the tag URL stay because they must be literal for
copy-paste to work. Net: three hard-coded occurrences → two, both adjacent,
both inside the same numbered step.

### D5. Badge row — four badges, shields.io, no vanity metrics

CI status (`workflows/ci.yml`), latest release, license MIT, platform
`macOS 14+ Apple Silicon`. No stars, no downloads, no coverage — the repo has
no coverage gate and star counts on a single-author repo read as padding.

### D6. `CONTRIBUTING.md` absorbs the build content verbatim where possible

Build prerequisites, the three build commands, the dev loop block, the test
commands, the packaging-harness pointer, and the repository-layout table move
across with their content intact; only the surrounding framing is new (how to
propose a change, the OpenSpec workflow pointer, PR expectations — squash
merge only, branch must be up to date with `master`).

### D7. `SUPPORT.md` is a routing file, ~20 lines

Question → GitHub Discussions if enabled, otherwise an issue with the
`question` label. Bug → issue with version, macOS version, and the Doctor
diagnostics bundle. Vulnerability → `.github/SECURITY.md` private reporting,
never a public issue.

## Risks / Trade-offs

- **Plain-language rewriting drifts into over-claiming** → Every feature
  sentence is checked against `docs/USER_GUIDE.md` during apply. The
  acquisition, audio-quality, and safety wordings keep their existing hedges
  ("uncertain", "purchase links remain first", "disabled by default")
  verbatim rather than being paraphrased.
- **Moving build instructions out breaks a contributor's muscle memory** →
  The README's Contributing section links `CONTRIBUTING.md` explicitly, and
  `CONTRIBUTING.md` opens with the build block so it is the first thing on
  screen.
- **A long README with `<details>` FAQ renders differently on mobile GitHub**
  → `<details>` is natively supported by GitHub Flavored Markdown on all
  clients; no custom HTML/CSS is used beyond `<details>`, `<summary>`, `<img>`,
  and `<p align="center">`.
- **Badges can 404 or go red** → Only badges pointing at things that exist
  are used; the CI badge is pinned to the `master` branch so a red PR does not
  redden the README.
- **Empty screenshot slots stay empty forever** → They are HTML comments, so
  an unfilled slot is invisible to readers; the cost of never filling them is
  zero.

## Migration Plan

Single commit on a branch, no runtime impact, no CI change. Rollback is
`git revert`. `openspec validate redesign-readme --strict` must pass
(the change declares `skip_specs: true`). Every link in the new README is
checked to resolve against the working tree before the branch is pushed.
