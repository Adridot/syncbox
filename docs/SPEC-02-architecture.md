# Syncbox — Architectural Reassessment & Recommended Target (Phase 2, V1)

> **Historical design input only.** Forks and cross-platform assumptions in
> this document predate the macOS v1 owner override. The current implementation
> and release boundaries are defined by [SPEC-UNIFIED.md](SPEC-UNIFIED.md) and
> [DISTRIBUTION.md](DISTRIBUTION.md); Windows and Developer ID/notarization are
> deferred.

> **Purpose.** Challenge *every* architecture, technology, and “way of doing things” choice in the current app, and propose **a recommended target** optimized for the 3 validated priorities: **(1) robustness/safety** (zero Rekordbox corruption), **(2) lightweight footprint** (small binary, low RAM, fast startup), **(3) performance/responsiveness**. Maintainability has been *removed* from the priorities — I therefore accept increased complexity if it serves these three axes.
>
> **Status.** V1 = recommendation + **4 structuring forks submitted for validation** (§4). Product/feature choices are frozen in [SPEC-01-syncbox.md](SPEC-01-syncbox.md) (§7, log D1–D25). Source-backed factual research in `docs/_research/`.
>
> **Scoping constraints** (validated answers): open-source/public · **macOS + Windows** (Linux excluded) · web UI preserved · Spotify OAuth PKCE only · Deezer acquisition “all in one place” (to be arbitrated, fork D).

---

## 1. Method & Verdict in One Sentence

I verified through source-backed web research the 5 points that determine the architecture: (a) `master.db` access libraries by language, (b) Rekordbox exchange formats, (c) lightweight desktop shells, (d) packaging/transport of a Python sidecar, (e) Deezer acquisition. **Overall verdict:** keep Python **only** for the Rekordbox layer (this is the robustness choice, non-negotiable), **radically lighten everything else** (shell, transport, packaging, removal of the external Deemix process), and decide **one fundamental question** — write `master.db` in place (full fidelity) vs use exchange formats (maximum safety but loss of MyTags/smart playlists).

---

## 2. Reassessment, Layer by Layer

Format: **Current choice** → *Verdict (sourced)* → **Recommendation**.

### 2.1 — The 3-Process Split (Electron Main + Python Service + Renderer)

**Current choice.** 3 processes: Electron main (TS) spawning a FastAPI/uvicorn service (Python) and hosting a Vue renderer; renderer↔service communication over HTTP `127.0.0.1` + SSE, renderer↔main over IPC, main↔service via spawn (`electron/main.ts`, `service/app/main.py`).

*Verdict.* The **UI / logic** split is sound and driven by necessity (pyrekordbox is Python, the UI is web). However, **the triple bridge** (IPC + HTTP + SSE) and the **double settings store** (electron-store ↔ SQLite, manual push/pull reconciliation, cf. SPEC-01 §5 T5) are complexity that is *endured*, not *chosen*. The full web service (FastAPI/uvicorn) is oversized for local IPC: **slow cold start** (up to several seconds; Pydantic v2 multiplies boot time by 2–4×) and **known uvicorn+PyInstaller bug** (workers fail to start ~50% of the time) · [FastAPI cold starts](https://medium.com/@hadiyolworld007/fastapi-cold-starts-explained-why-your-containers-feel-slow-and-the-optimization-order-that-dcac906ffe2b), [uvicorn #1820](https://github.com/Kludex/uvicorn/discussions/1820).

**Recommendation.** Keep the **web UI ↔ Python core** separation, but: (a) **remove the double settings store** (single source of truth, read by the UI); (b) **replace FastAPI/uvicorn with a minimal Python worker** (cf. §2.5); (c) reduce bridges to **one** command channel + **one** event channel (cf. fork C).

### 2.2 — The Electron Shell

**Current choice.** Electron 42 (bundled Chromium). Footprint ~100–150 MB binary, 200–300 MB RAM at idle · [pkgpulse 2026](https://www.pkgpulse.com/guides/electron-vs-tauri-2026), [raftlabs](https://dev.to/raftlabs/tauri-vs-electron-23d1).

*Verdict.* Directly opposed to priority **#2 (footprint)**. **Tauri v2** (stable 2024-10-02, MIT+Apache, audited) produces binaries of **~3–10 MB** and uses **~30–100 MB RAM**, via native webview (WKWebView macOS / WebView2 Windows), and provides a **first-class sidecar mechanism** (`externalBin` + Shell plugin) explicitly intended for **a Python server bundled via PyInstaller** · [Tauri 2.0](https://v2.tauri.app/blog/tauri-20/), [Tauri sidecar](https://v2.tauri.app/develop/sidecar/). Two concrete risks: (1) **macOS notarization bug with `externalBin`** (#11992, open since Dec. 2024) → each sidecar binary must be **manually signed**; (2) **heterogeneous webview** (WKWebView ≠ WebView2 ≠ Chromium) → CSS/JS tests per OS · [Tauri #11992](https://github.com/tauri-apps/tauri/issues/11992), [Tauri webviews](https://dev.to/shrsv/exploring-system-webviews-in-tauri-native-rendering-for-efficient-cross-platform-apps-9hl). SSE in `EventSource` **works** in WKWebView over HTTP localhost (do NOT route it through the Tauri custom protocol) · [Apple forums #104901](https://developer.apple.com/forums/thread/104901).

**Recommendation.** **Tauri v2** (footprint gain ~10×, RAM ~5×). **Electron fallback** only if the macOS sidecar signing/notarization chain proves blocking in POC. ⚠️ **De-risk first** (cf. §5). → **Fork B**.

### 2.3 — The Service Runtime: Python + pyrekordbox

**Current choice.** Python service, `master.db` access through **pyrekordbox** (read/write SQLCipher).

*Verdict (landscape analysis, requested).* **Crypto is NOT a lock-in**: the `master.db` SQLCipher key is a **known public constant**, identical across all installs (Rekordbox 6.6.5+ obfuscation only breaks *automatic extraction*, not the key) · [pyrekordbox #97](https://github.com/dylanljones/pyrekordbox/discussions/97), [liamcottle](https://github.com/liamcottle/pioneer-rekordbox-database-encryption). Any language with a SQLCipher binding (Rust `rusqlite`, Node `better-sqlite3-multiple-ciphers`, .NET, Go) can therefore open the database. **The real lock-in is the business logic for coherent writes** (FKs, `rb_local_*` codes, smart playlists, MyTags), which **only pyrekordbox encapsulates maturely**:

| Lib | Language | Reads/writes master.db | Maturity | License | OS | Note |
|---|---|---|---|---|---|---|
| **pyrekordbox** | Python | **Yes** (8 tables, tested RB 7.0.9) | **Mature** (v0.4.4 2025, 415★) | **MIT** | Win+mac | Pulls `numpy` (eager, non-excludable) → floor ~30-50 MB |
| rbox | Rust | Yes (ORM) | **Experimental**, broken build | GPL-3.0 | Win+mac | Too risky for “zero corruption” |
| RDBManager | Node | Yes (cues/BPM only) | Very small project | GPL-3.0 | **Windows only** | Writes too partial |
| rekordcrate / crate-digger | Rust / Java | **No** (USB exports only) | Active | MPL / — | — | Out of scope (device export) |
| Go / .NET / Swift / C++ | — | **No business library** | — | — | — | Rewrite from scratch |

Sources: [pyrekordbox](https://github.com/dylanljones/pyrekordbox), [rbox crates.io](https://crates.io/crates/rbox), [RDBManager](https://github.com/l3x04/RDBManager), [rekordcrate](https://github.com/Holzhaus/rekordcrate).

**Recommendation.** **Keep Python + pyrekordbox** for the Rekordbox layer — this is the tradeoff **robustness (priority #1) > lightweight footprint (#2)**. Reimplementing writes in Rust/Node would be *the* corruption risk, for a size gain that can be recovered elsewhere (shell + transport + acquisition). We **pay the numpy floor (~30-50 MB)** and optimize the rest. *(The full-Rust option via rbox remains a future path if rbox matures; not recommended today.)*

### 2.4 — Rekordbox Write Strategy: `master.db` In Place vs Exchange Formats

**Current choice.** Direct `master.db` writes (apply library/event, dedup, relink, soft-delete), + a secondary M3U8 “Live Import” (removed by SPEC-01 D10).

*Verdict (the most structuring point).* Writing `master.db` provides **full fidelity**: MyTags, **smart playlists** (the “Event Imports” + tagged library *are* Syncbox’s value), update **in place**, with no manual action. Cost: SQLCipher dependency, **“Rekordbox closed” lock**, and corruption risk (currently mitigated by backup-before-mutation + soft-delete). **The “exchange formats” path is safer and lighter** but **amputates the product core**:

| Path | Corruption possible? | RB closed lock? | MyTags | Smart playlists | In place? | Manual action? |
|---|---|---|---|---|---|---|
| **master.db (pyrekordbox)** | Yes (mitigated by backup) | **Yes** | **Yes** | **Yes** | **Yes** | No |
| **XML import** | **No** | **No** | **No** | **No** (flattened) | No (Bridge pane) | **Yes** (manual RB import, additive/buggy) |
| **M3U8** | No | No | No | No | No | Yes |

XML export was **removed from the UI as of RB 6** (only import remains), lands in a separate “Bridge” pane, and its upsert is **additive/buggy** on existing tracks · [spec XML PDF](https://cdn.rekordbox.com/files/20200410160904/xml_format_list.pdf), [Engine DJ thread](https://community.enginedj.com/t/no-more-xml-export-in-rekordbox-6-blocks-denon-prime-users/21170), [Mixo import bug](https://www.mixo.dj/guides/rekordbox-xml-import-bug). pyrekordbox can **write XML** (`rbxml.save()`, cues + beatgrid carried over, MIT) but **not** MyTags/smartlists (absent from the format) · [pyrekordbox rbxml](https://raw.githubusercontent.com/dylanljones/pyrekordbox/master/pyrekordbox/rbxml.py).

**Recommendation.** **Keep `master.db` writes as the primary path** (without them, Syncbox is just another Deezer downloader), relying on the already specified safety backbone (mandatory backup, soft-delete, RB closed guard, OS Trash — SPEC-01 §3.1/D12). **Validated decision: A2 — `master.db` writes *only*, with no XML mode** (product core intact, minimal surface area, no “zero-write” escape hatch). → **Fork A** (cf. §4 validated decisions).

### 2.5 — Transport (HTTP + SSE + Polling) & UI Data Layer

**Current choice.** UI ↔ service over **HTTP REST + SSE**; **two refresh engines** (partial vue-query + `useRefreshManager` setInterval); SSE feeds **only one** of the two job stores (SPEC-01 §5 F5/F6/T4). FastAPI/uvicorn on the service side.

*Verdict.* (a) On the UI side, the **double data layer is an unfinished migration** (git `phase-2a→2d`), not a choice — to **converge on one** (cf. project memory “dual data layer kept”: status to reconfirm in a rewrite; here we decide for lightweight/perf → **convergence**). (b) On the service side, **FastAPI/uvicorn is oversized** for local IPC: a **bare Python worker using JSON-RPC over stdin/stdout** starts almost instantly, is lighter, and **removes the loopback network surface to secure** · [JSON-RPC stdio vs HTTP](https://medium.com/ingeniouslysimple/building-an-electron-app-from-scratch-part-4-5d0906897bf1). (c) The **manual reconstruction of the downloaded filename** (SPEC-01 §5 F1/D18) must disappear in favor of the **real output path** read from the downloader.

**Recommendation.** **A single reactive cache layer on the UI side** (query-cache style, unified refetch intervals, canonical event stream for jobs). On the core side, **minimal Python worker**, **driven by JSON-RPC**; job progress pushed to the UI through **a single event channel**. The exact transport choice (stdin/stdout brokered by Tauri **vs** preserved HTTP+SSE localhost) = **Fork C**.

### 2.6 — Python Sidecar Packaging

**Current choice.** PyInstaller `--onedir` (standalone binary), bundled in Electron `extraResources`.

*Verdict.* `--onedir` is the right mode (`--onefile` re-extracts on every startup → slow, to be avoided given the startup priority) · [PyInstaller docs](https://pyinstaller.org/en/stable/usage.html). Alternatives: **Nuitka** (smaller binary ~60 MB, runtime 2-4× faster, but slow build and compiles all of numpy); **python-build-standalone (Astral)** (cross macOS arm64 + Windows, maintained) · [x321 benchmark](https://x321.org/empirical-pyinstaller-vs-nuitka-vs-cx_freeze/), [astral.sh](https://astral.sh/blog/python-build-standalone). **PyOxidizer is abandoned** (exclude it) · [PyOxidizer #737](https://github.com/indygreg/PyOxidizer/discussions/737). **The real robustness risk is not the packager but the lifecycle**: a PyInstaller binary spawns **2 processes**; a naive `kill()` leaves an **orphan holding the SQLCipher transaction open** → corruption · [Tauri #11686](https://github.com/tauri-apps/tauri/issues/11686). `sqlcipher3-wheels` (bundled SQLCipher 4) covers opening master.db without a C toolchain on the user’s machine · [sqlcipher3-wheels](https://pypi.org/project/sqlcipher3-wheels/).

**Recommendation.** **PyInstaller `--onedir`** (safe, fast to ship) initially; **Nuitka** as a size/perf upgrade if necessary. **Robustness imperative**: clean shutdown = **RPC “shutdown” handshake → wait for DB closure → kill process tree** (`taskkill /T` Windows, process-group macOS), + anti-double-instance guard. Empirically measure numpy+sqlcipher3 weight and cold start (the #1 levers for size/startup).

### 2.7 — Deezer/Deemix Acquisition (External Process on :6595)

**Current choice.** Control of an **external Deemix app** (Electron/Node) over HTTP `127.0.0.1:6595`, ARL pushed by the app (SPEC-01 §3.5). A **second full runtime**, fragile (heuristic parsing of the queue, process globals).

*Verdict.* The **`deemix` library (Python, GPL-3.0)** is **embeddable** (API designed for this), with **5 lightweight dependencies** (`click, pycryptodomex, mutagen, requests, deezer-py`) — **no numpy** · [pypi deemix](https://pypi.org/project/deemix/), [setup.py](https://gitlab.com/RemixDev/deemix-py/-/raw/main/setup.py). Embedding it **in the existing Python sidecar removes the external Node/Electron process** → **net gain in footprint/RAM/startup** (“all in one place”). **But**: the library has been **frozen on PyPI since 2022**, periodically breaks as Deezer API changes (fix forks: DeemixFix 2024), **`streamrip`** is better maintained (4.7k★, 2026) but CLI-oriented · [streamrip](https://github.com/nathom/streamrip). Two costs to accept: (1) **GPL-3.0 contaminates the entire distributed binary** (acceptable because open-source, blocking for proprietary); (2) **documented DMCA/takedown risk** (2021 Deezer complaint targeting `deemix-gui`; historical GitHub removals) → embedding the downloader **increases the main repository’s takedown surface** · [DMCA Deezer 2021](https://github.com/github/dmca/blob/master/2021/02/2021-02-10-deezer.md), [TorrentFreak](https://torrentfreak.com/deezer-targets-pirate-apps-maliciously-retrieving-publishing-encryption-keys-210212/).

**Recommendation.** **Embed a Python download library** (deemix or streamrip) in the sidecar, **isolated behind a thin interface**, **pinned version**, **never on the `master.db` write critical path**. Seriously consider shipping it as an **optional module/plugin** (the user activates it + provides their ARL) to **limit legal exposure** of the main repository. → **Fork D**.

### 2.8 — Recurring “Ways of Doing Things” (Cross-Cutting)

| Current practice | Verdict | Target |
|---|---|---|
| Reconstruction of the downloaded filename (`audio.py`) | Chronic source of bugs (SPEC-01 F1) | **Read the real output path** from the downloader (D18) |
| Process globals (`_applied_arl`, mtime caches) | Races, state leaks (F3) | State carried by instance/request; no shared mutable global |
| Navigation without router (`ui.activeView`, Settings = `v-else`) | OK for desktop but no deep-link/persistence, dangerous catch-all | Keep screen state (lightweight) but **explicit default** + persistence, or a mini-router |
| Generic error handling (raw `error.message`, null parse) | Backend text leak, silent null (F7) | Error→i18n message mapping; schema validation at the edge |
| 2 matching/dedup normalizations | Divergent “identical” judgments (T3) | **One** shared normalization pipeline (D19) |
| Ad-hoc SQLite migration + re-seed on every boot | Overwrites user edits (B4) | **Ordered versioned migrations**; seed strictly on first run |
| OAuth tokens in plaintext in SQLite | Unacceptable in open-source | **OS Keychain / encrypted DB** |

---

## 3. Recommended Target Architecture (Summary)

Optimized for **robustness > lightweight footprint > performance**; web UI preserved; macOS + Windows.

```
┌──────────────────────────────────────────────────────────────┐
│  Shell: TAURI v2 (Rust, ~3-10 MB, native WKWebView/           │
│  WebView2 webview)                                            │
│   • hosts the web UI   • spawns + supervises the Python sidecar│
│   • signs the sidecar binary (macOS chain to de-risk)          │
└───────────────┬──────────────────────────────┬───────────────┘
                │ (1 command channel +          │ (spawn + lifecycle:
                │  1 event channel)             │  clean shutdown,
                ▼                                ▼  kill tree)
   ┌────────────────────────┐      ┌────────────────────────────────┐
   │ UI: Vue 3 (preserved)   │      │ CORE: minimal Python sidecar    │
   │  • ONE reactive cache   │      │  (NO FastAPI/uvicorn)           │
   │    layer (converged)    │      │  • pyrekordbox (master.db, MIT) │
   │  • 1 canonical job      │      │  • Deezer acquisition (embedded │
   │    event stream         │      │    library, isolated, pinned)   │
   │  • FR/EN i18n           │      │  • app SQLite (state) + versioned│
   └────────────────────────┘      │    migrations                   │
                                    │  • Spotify OAuth PKCE only       │
                                    └────────────────────────────────┘
   Safety (unchanged, non-negotiable): “RB closed” guard, backup
   before every mutation, soft-delete, OS Trash, relative-to-volume/
   absolute path resolution (SPEC-01 §3.1-3.2 / §9).
```

**What changes vs today**: Electron→Tauri (−~140 MB); FastAPI/uvicorn→minimal Python worker with JSON-RPC stdin/stdout (cold start); external Deemix process→embedded library **as optional module** (−1 runtime when enabled); double data layer→single layer; double settings store→single source; filename reconstruction→real path; ad-hoc migrations→versioned; tokens→encrypted.
**What does not change**: Python+pyrekordbox for Rekordbox; Vue UI; safety backbone; domain model (SPEC-01 §6).

---

## 4. The 4 Major Forks to Validate

> **⚠️ CLOSED — decided in [SPEC-UNIFIED.md](SPEC-UNIFIED.md) §7.1.** The 4 forks are decided: **A** = `master.db` in place **without** XML mode (the double meaning of the “A2” label is abandoned); **B** = Tauri v2 (signature POC #11992); **C** = **keep HTTP+SSE localhost**, reject JSON-RPC; **D** = embedded library as **optional module** + ARL (library delegated to the POC). This section and the “Validated Decisions” table below are preserved as **history**; the authoritative decision is in SPEC-UNIFIED.

> Recommendation shown first; these are the structuring choices where your validation is required.

**Fork A — Rekordbox Write Strategy.**
- **A1 (reco)**: `master.db` in place as the primary path (MyTags + smart playlists + in place), supported by backup/soft-delete/Trash safety. Optionally, add a safe “XML export” mode.
- A2: Exchange formats only (XML/M3U8) — zero corruption, no RB lock, but **loss of MyTags + smart playlists** + manual import. Turns Syncbox into a simple downloader.
- *Why it matters*: this is product identity vs absolute safety.

**Fork B — Desktop Shell.**
- **B1 (reco)**: Tauri v2 (footprint ~10×, RAM ~5×), Electron fallback if macOS sidecar signing blocks.
- B2: Stay on Electron (homogeneous rendering, sidecar already in place, zero webview surprises) at the cost of footprint.
- *Why it matters*: priority #2 vs risk/effort of the Tauri signing chain.

**Fork C — Core ↔ UI Transport.**
- **C1 (reco)**: minimal Python worker over **JSON-RPC stdin/stdout**, brokered by Tauri, jobs pushed as **Tauri events** (lightest/fastest, no network surface).
- C2: keep **HTTP + SSE localhost** (smoother migration, SSE proven in WKWebView) with minimal Python but a mini-server.
- *Why it matters*: lightweight/perf purity vs transport rewrite effort.

**Fork D — Deezer Acquisition.**
- **D1 (reco)**: embed a Python library (deemix/streamrip) in the sidecar, isolated + pinned; **ship it as an optional module/plugin** (the user enables it + ARL) to limit DMCA exposure and GPL coupling of the core.
- D2: keep an **external** downloader controlled over HTTP (robust isolation, but 2nd runtime, “not in one place”).
- D3: rewrite acquisition **natively** (Rust/Go, ARL+Blowfish, permissive license, no 2nd runtime) — more maintenance against Deezer changes.
- *Why it matters*: “all in one place” vs robustness/maintenance vs license/legality.

### Validated Decisions (Forks A–D)

| Fork | Decision | Effect on the target |
|---|---|---|
| **A — RB Writes** | **A2 — `master.db` in place *only*** (no XML mode) | Product core (MyTags + smart playlists + in place) intact; minimal surface area; no “zero-write” escape hatch — safety relies **entirely** on the backup / soft-delete / OS Trash / RB closed guard backbone. ⇒ makes POCs §5.2 (process lifecycle) and §5.5 (schema non-regression) even more critical. |
| **B — Shell** | **B1 — Tauri v2** (Electron fallback if macOS sidecar signing blocks) | −~140 MB binary, ~5× lower RAM. De-risk macOS sidecar signing/notarization (#11992) as **POC #1**. |
| **C — Transport** | **C1 — minimal Python worker, JSON-RPC stdin/stdout** + jobs pushed as Tauri events | No FastAPI/uvicorn, no loopback network surface, minimal cold start. The UI↔core bridge goes through the Tauri broker; transport must be rewritten (no SSE/HTTP). |
| **D — Acquisition** | **D1 — embedded Python library, shipped as an *optional* module/plugin** (the user enables it + provides their ARL) | Removes the external process **when enabled**; isolated behind a thin interface, pinned version, **never on the `master.db` critical path**; limits DMCA exposure and confines GPL copyleft to the optional module rather than the core. |

---

## 5. Risks & De-Risking Order (POC Before Any Commitment)

1. **Signing + notarization of the Python sidecar under Tauri macOS** (#11992) — *the* #1 friction point; prototype **first**. If blocking → Electron fallback (Fork B).
2. **Process lifecycle** (tree kill + clean SQLCipher connection close) — #1 packaging-side corruption risk; validate on mac **and** Windows.
3. **Actual bundle size** (numpy + sqlcipher3 + download library) and **cold start** of the Python worker — measure empirically (will lift/confirm the lightweight gain).
4. **`EventSource`/transport in real WKWebView** (if Fork C2) — test on macOS device, not only in Chromium/Electron.
5. **pyrekordbox write fidelity on target RB 7.x** (smart playlists/MyTags, residual bugs #110) — non-regression test harness on the `master.db` schema **before** any deployment.
6. **Acquisition**: validate that a deemix/streamrip fork works with the **current** Deezer API + `pycryptodomex` packaging.

---

## Appendix — Main Sources

RB libraries: [pyrekordbox](https://github.com/dylanljones/pyrekordbox) · [SQLCipher key #97](https://github.com/dylanljones/pyrekordbox/discussions/97) · [rbox](https://crates.io/crates/rbox) · [RDBManager](https://github.com/l3x04/RDBManager) · [rekordcrate](https://github.com/Holzhaus/rekordcrate).
Formats: [XML spec PDF](https://cdn.rekordbox.com/files/20200410160904/xml_format_list.pdf) · [pyrekordbox rbxml](https://pyrekordbox.readthedocs.io/en/latest/formats/xml.html) · [import bug](https://www.mixo.dj/guides/rekordbox-xml-import-bug).
Shells: [Tauri 2.0](https://v2.tauri.app/blog/tauri-20/) · [Tauri sidecar](https://v2.tauri.app/develop/sidecar/) · [notarization #11992](https://github.com/tauri-apps/tauri/issues/11992) · [Wails](https://wails.io/).
Packaging: [PyInstaller](https://pyinstaller.org/en/stable/usage.html) · [Nuitka vs PyInstaller](https://x321.org/empirical-pyinstaller-vs-nuitka-vs-cx_freeze/) · [python-build-standalone](https://astral.sh/blog/python-build-standalone) · [orphan #11686](https://github.com/tauri-apps/tauri/issues/11686).
Acquisition: [deemix lib](https://pypi.org/project/deemix/) · [streamrip](https://github.com/nathom/streamrip) · [DMCA Deezer 2021](https://github.com/github/dmca/blob/master/2021/02/2021-02-10-deezer.md).

Detailed research by axis: `docs/_research/00_RB.md` … `04_Acquisition.md`.
