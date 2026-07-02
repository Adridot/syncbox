# POC #1 — Sidecar signing + notarization under Tauri (macOS)

**Status: DEFERRED — owner decision, 2026-07-02.**

## Context

SPEC-UNIFIED §8 item 1 ranks this as de-risking priority #1 (Tauri issue #11992: with
`externalBin`, Apple notarization fails unless each sidecar binary is manually signed —
hardened runtime + entitlements — in a POST-bundle step, before Tauri signs the bundle and
notarizes via `notarytool`).

## Why deferred

The dev machine has **no Apple Developer ID** (`security find-identity -v -p codesigning`
returns 0 valid identities), so the POC cannot run end-to-end. Owner decision: build on
Tauri **unsigned for now**; do not switch to the Electron fallback (that fallback is
specified only if this POC *fails*, not while it is pending).

## Consequences while deferred

- Secrets at rest follow the **unsigned path** of SPEC-UNIFIED §6.7: encrypted store
  (sqlcipher3/Fernet), not `keyring` (macOS returns `errSecInteractionNotAllowed -25308`
  to unsigned PyInstaller binaries, and unstable identities invalidate Keychain ACLs).
- The Electron fallback remains documented and unexercised.

## Exit criteria (to run as soon as a Developer ID exists — at the latest before M5 Packaging)

1. Build the PyInstaller onedir sidecar (see `poc/03-bundle-size-coldstart/`).
2. Bundle it as a Tauri v2 `externalBin`; sign the sidecar binaries manually in a
   post-bundle step (hardened runtime + entitlements), then let Tauri sign the bundle.
3. Notarize with `notarytool`; verdict GO = notarization accepted and the app launches
   with the sidecar spawning correctly on a clean macOS account.
4. NO-GO → documented fallback: Electron shell (Fork B fallback, SPEC-UNIFIED §6.2).
