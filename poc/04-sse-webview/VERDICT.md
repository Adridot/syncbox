# POC #4 — EventSource/SSE in the REAL WKWebView (Tauri v2, macOS) — VERDICT: GO

Date: 2026-07-02 · macOS (Darwin 25.5.0, arm64) · WKWebView UA `AppleWebKit/605.1.15` ·
shell = Tauri v2 debug build (shared POC #2 shell, `frontendDist` page → origin
`tauri://localhost`) · SSE servers = POC #3 PyInstaller sidecar (:8899, no CORS) +
venv-run twin app `sidecar_cors.py` (:8897, Starlette + sse-starlette + uvicorn 1 worker,
programmatic, main asyncio loop — same non-negotiable topology as SPEC-UNIFIED §6.3).
Scope: SPEC-UNIFIED §8 item 4, **macOS/WKWebView half** (WebView2/Windows still open).

**GO** — SSE streams **incrementally** in the real WKWebView over HTTP localhost; the
feared WebKit initial-buffering quirk did **not** manifest; mid-stream sidecar death
surfaces as a prompt `error` event, no hang. **One spec amendment required (see below):
the §6.3 CORS allowlist as written blocks the app's own UI.**

## How to reproduce

```
export PATH="$HOME/.cargo/bin:$PATH"
sidecar/.venv/bin/python poc/04-sse-webview/run_poc.py   # exit 0 = all assertions pass
```

Fully automated: overlays a test `main.rs`/`index.html` onto the POC #2 shell (originals
restored on exit), cargo-builds (warm cache, 2.3 s), starts the three loopback servers,
launches the app; the page runs 4 EventSource phases and POSTs measurements to a results
endpoint (:8898). Artifacts (gitignored): `build/result.json`, `build/origins.jsonl`,
`build/events.jsonl`. Run twice with consistent numbers.

## Measured evidence

| Phase | Setup | Result |
|---|---|---|
| A | EventSource → compiled sidecar :8899/sse, response has **no CORS headers** (what the current §6.3 allowlist yields for this page) | **Blocked**: single `error` event at 133 ms, `readyState` 2 (CLOSED), `onopen` never fired, **0 events delivered**. Failure is immediate and clean (not a hang), but the UI would be dead. |
| B1 | EventSource → :8897/sse, CORS ok, 3 `tick` events, server sleeps 400 ms between them | All 3 arrived, in order, **incrementally**: inter-event gaps **401/401 ms** (run 1: 402/402) vs 400 ms server delay; total spread 802 ms; first event **0 ms after `onopen`**. **No initial-buffering burst.** |
| B2 | Same + **2 KB `:` comment preamble** (the padding workaround from research 06) | Identical: gaps 402/402 ms, first event 0 ms after open. **Padding is unnecessary** on this stack (sse-starlette/uvicorn, HTTP/1.1 chunked, loopback, macOS WebKit 605.1.15). |
| C | EventSource → :8897/sse-long (tick/500 ms); orchestrator **SIGKILLs** the server process group after the 2nd tick | `error` event **7 ms** after SIGKILL (run 1: 5 ms), `readyState` 0 (CONNECTING → EventSource auto-reconnect pending). No hang; `close()` then yields state 2. |
| readyState sanity | all phases | 0 (constructed) → 1 (`onopen`) → messages at 1 → 2 after `close()`. Phase A: 0 → 2 without open. Sane per WHATWG semantics. |
| Teardown | orchestrator | 0 leftover pids, POC ports (8897/8898/8899) all released. macOS note: `killpg` on the GUI shell can return `EPERM` (unsignalable WebKit XPC group member) — direct-pid kill fallback needed. |

## Observed Origin header (the deliverable for the spec amendment)

Every request the WKWebView page issued — EventSource GETs **and** fetch POSTs — carried
exactly:

```
Origin: tauri://localhost
```

(`location.origin === "tauri://localhost"`, `isSecureContext === true`.)

**Spec gap, confirmed empirically (Phase A):** SPEC-UNIFIED §6.3 restricts CORS origins
to `http://(127.0.0.1|localhost):\d+`. `tauri://localhost` does **not** match, so a
spec-compliant sidecar sends no `Access-Control-Allow-Origin` to the production UI and
WKWebView kills the EventSource instantly (and would equally kill REST `fetch`). The UI
would receive nothing at all.

**Required amendment (reported, NOT silently applied):** §6.3 must extend the origin
allowlist with the shell webview's own origin — measured `tauri://localhost` on macOS
WKWebView; per Tauri v2 docs the Windows WebView2 equivalent is `http://tauri.localhost`
(**not measured here** — verify in the WebView2 half of §8 item 4). Keep the exact-match
allowlist style and `allow_credentials=False`; do not wildcard.

## Caveats / still open

- **Windows/WebView2 half untested** (this gate is macOS; Windows before M5 per Phase 0
  decisions). Re-verify there: incrementality, the `http://tauri.localhost` origin, and
  whether padding stays unnecessary.
- After a sidecar death the EventSource sits in CONNECTING and **auto-reconnects ~every
  few seconds**; production UI must `close()` on intentional shutdown (pairs with the
  §6.6 intent flag) or expect reconnect churn until the sidecar returns.
- Buffering was probed at 3×400 ms / SSE event sizes of a few bytes; not a throughput
  test (irrelevant in loopback per research 06).
- Test-harness-only quirk, not product-relevant: stock `http.server` `server_bind()`
  calls `socket.getfqdn()`, which hangs in DNS-less sandboxes before `listen()` —
  the POC results server overrides it (uvicorn is unaffected).
