## 1. Groundwork

- [x] 1.1 Create `docs/assets/` with a `.gitkeep` so screenshot slots have a real target path (design D3).
- [x] 1.2 Re-read `docs/USER_GUIDE.md`, `docs/PRIVACY.md`, and `docs/DISTRIBUTION.md`; write down the exact hedged wordings for acquisition, audio quality, and Rekordbox write safety that the README must reuse verbatim rather than paraphrase (design D2, Risks).
- [x] 1.3 Verify the four badge URLs resolve before using them: CI (`ci.yml`, pinned to `master`), latest release, MIT license, macOS platform (design D5).

## 2. Move contributor content out of the README

- [x] 2.1 Create `CONTRIBUTING.md` opening with the build block: prerequisites (pnpm, Rust, uv), the three build commands, and the resulting `.app` path — content carried over intact from the current README (design D6).
- [x] 2.2 Add the dev loop and test commands to `CONTRIBUTING.md` (tauri dev, sidecar pytest, UI test, UI typecheck, the `sidecar/dist/syncbox-sidecar` mkdir, cargo check) plus the `shell/harness/` packaging-harness pointer.
- [x] 2.3 Add the repository layout table to `CONTRIBUTING.md`, carried over from the current README.
- [x] 2.4 Add the contribution workflow to `CONTRIBUTING.md`: OpenSpec change pointer (`openspec/`), PR expectations — squash merge only, branch must be up to date with `master`, CI must be green.
- [x] 2.5 Create `SUPPORT.md` (~20 lines) routing question / bug / vulnerability, with the bug path asking for app version, macOS version, and the Doctor diagnostics bundle (design D7).

## 3. Rewrite README — top of page

- [x] 3.1 Write the hero: centered name, one-line tagline, badge row, existing hero screenshot (keep the current GitHub user-attachment URL). Drop the standalone "Current source version" line — the release badge replaces it (design D4).
- [x] 3.2 Write "What is Syncbox?" — 3–4 sentences, zero jargon, framing Spotify as where you find music and Rekordbox as where you play it.
- [x] 3.3 Write "Who it's for" — short bullet list of concrete DJ situations.
- [x] 3.4 Write "Before you download" — macOS 14+ Apple Silicon only, ad-hoc signed so macOS will warn on first launch, no auto-update, nothing leaves the machine except the Spotify calls you authorize. Stated as facts, not apologies.

## 4. Rewrite README — features

- [x] 4.1 Spotify → Rekordbox: problem-first, ≤2 paragraphs, define MyTag on first use, replace "ISRC" with the plain-language equivalent, add screenshot slot for the Library match review (design D2, D3).
- [x] 4.2 Events: problem-first, cover the re-apply-the-delta behaviour and the purchase-links-first posture with its existing hedged wording, add the Events screenshot slot.
- [x] 4.3 Collection health: duplicates, missing files, untagged, Smart Fixes — one short paragraph plus a compact list, keeping the audio-quality "uncertain / keeper-neutral" hedge verbatim; add the Duplicates screenshot slot.
- [x] 4.4 Performance history: problem-first, live tracklist while Rekordbox runs, export to `Historiques`; add the history screenshot slot.
- [x] 4.5 Backups & logs + French/English UI: short closing feature block. NOTE: the current README calls this "Doctor"; no such screen exists — the real surface is Collection Health -> "Backups & logs" (`ui/src/i18n/en.ts` `health.tabs.backups`). Use the real name.
- [x] 4.6 Grep the finished feature sections for `sidecar`, `PKCE`, `SSE`, `SQLCipher`, `master.db`, `Starlette`, `PyInstaller`, `Tauri` — none may appear (design D2).

## 5. Rewrite README — bottom of page

- [x] 5.1 Write "Your collection is safe" — ≤5 bullets, linking to `docs/USER_GUIDE.md` §Rekordbox write safety for the full six-point pipeline.
- [x] 5.2 Write Install — numbered steps: download the release asset, Gatekeeper "Open Anyway" with the Apple support link, then what onboarding asks for. Version appears exactly twice, both in this section (design D4).
- [x] 5.3 Write the FAQ as 6–8 `<details>` entries: Windows? does it cost anything? will it move or rename my files? does it need my Spotify password? Spotify Premium? can I undo a change? where is my data stored? how do I update?
- [x] 5.4 Write the Documentation link table for the five `docs/` files.
- [x] 5.5 Write Contributing & support linking `CONTRIBUTING.md`, `SUPPORT.md`, and `.github/SECURITY.md`.
- [x] 5.6 Write "Roadmap & current limits" — the deferred list (signing/notarization, Windows, auto-update, optional acquisition, later items) de-jargonized, keeping the acquisition hedges verbatim.
- [x] 5.7 Write the License section — short MIT line plus a pointer to the bundled third-party notices, keeping the "this summary is not a legal-compliance claim" disclaimer.

## 6. Verify

- [x] 6.1 Check every relative link in `README.md`, `CONTRIBUTING.md`, and `SUPPORT.md` resolves against the working tree; check every external link (release tag, Apple support article, rekordbox.com, badges) returns 200.
- [x] 6.2 Re-read the finished README against `docs/USER_GUIDE.md` and confirm no sentence over-claims relative to documented behaviour (design Risks).
- [x] 6.3 Confirm the README no longer contains build commands, the ASCII architecture diagram, or the repository layout table, and that each now lives in `CONTRIBUTING.md` or is linked from `docs/SPEC-UNIFIED.md`.
- [x] 6.4 Preview the rendered README (GitHub Markdown preview or the PR page) to confirm badges, `<details>`, and centering render correctly, and that empty screenshot slots are invisible.
- [x] 6.5 Run `openspec validate redesign-readme --strict`.
