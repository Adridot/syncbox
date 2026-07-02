# PROMPT-03 — Construction de Syncbox (from scratch)

> **Comment l'utiliser.** Coller ce prompt dans une session Claude Code (**Fable**) **à la racine d'un dépôt neuf** contenant uniquement le kit de specs (`docs/` + `syncbox-ui-ux-design/`). Le mot **`ultracode`** active l'orchestration multi-agents. Le module **ponytail** reste actif (`/ponytail full`) — contrainte de réalisation, pas une option.
>
> **Ce prompt ne paraphrase pas les specs.** Il fixe la mission, la hiérarchie d'autorité, les portes et les libertés. Tout le détail — invariants, constantes, écrans, recherches — vit dans le kit : **il fait foi, pas ce prompt**. Si une phrase de ce prompt semble contredire une spec, la spec gagne.

---

ultracode — `/ponytail full`

## Mission

Build **Syncbox** — an open-source **macOS + Windows** desktop app that syncs Spotify playlists in read-only mode to a DJ's **Rekordbox** collection, maintains the collection (duplicates, missing files, tags, Smart Fixes, fake-320/FLAC diagnostics), and promotes a **legal purchase + manual relink path** for missing tracks. Build it **from scratch**, with clean code that implements the spec without legacy debt. No download/acquisition module is in v1.

## Step zero - read the entire kit

Before writing any code, read **all of** SPEC-UNIFIED.md, including **section 11 post-design amendments**, SPEC-DESIGN.md, SPEC-AI-WORKFLOWS.md, the `syncbox-ui-ux-design/project/Syncbox.dc.html` mockup, and the active research notes listed in SPEC-UNIFIED §10.

Do **not** read or implement deprecated download research during v1: `docs/_research/04_Acquisition.md`, `docs/_research/10_Acquisition-2026.md`, and `docs/_research/14_streamrip-embedding-Deezer-SoundCloud.md` are historical only after the legal scope update. Read `docs/_research/16_Legal-download-removal.md` instead. The full active corpus is authoritative; excerpts are not enough.

## Authority hierarchy

1. **[SPEC-UNIFIED.md](SPEC-UNIFIED.md)** — authoritative for **all product and architecture requirements**: non-negotiables (§3), domain model (§4), behavior invariants (§5), architecture and decided forks (§6/§7), de-risking order (§8), legal download removal (§6.5), and **Gate 3 amendments (§11)** as superseded by the legal scope update.
2. **[SPEC-AI-WORKFLOWS.md](SPEC-AI-WORKFLOWS.md)** — controls any model-backed workflow, prompt, refusal handling, fallback, sensitive-domain boundary, and human review gate. Syncbox v1 has **no approved AI workflow**. Do not add AI or cybersecurity automation unless a split spec under `docs/ai-workflows/` is approved first.
3. **[SPEC-DESIGN.md](SPEC-DESIGN.md) + mockup [`Syncbox.dc.html`](../syncbox-ui-ux-design/project/Syncbox.dc.html)** — authoritative for **UI implementation details** after applying the legal scope update: six destinations plus onboarding, real router with deep links (`#health/<tab>`, unknown route -> Dashboard), component inventory, and visual tokens. Reproduce the mockup's behavior and visual hierarchy, not its literal inline CSS. Ignore deprecated mockup controls for Deezer/SoundCloud download, ARL, download toggles, and download jobs. The build uses a real router and `en.ts`/`fr.ts` i18n. If mockup and spec conflict, the spec wins.
4. **Active research notes in SPEC-UNIFIED §10** — sourced state of the art behind each infrastructure choice. Re-read the relevant note **before** implementing the corresponding block: signature, transport, secrets, multi-OS, migrations, supervision, v1 additions, AI workflow safety, and legal download removal.
5. **[SPEC-01-syncbox.md](SPEC-01-syncbox.md)** — **constants appendix only**: weights, thresholds, and buckets. Use it only when §5 is not precise enough.

## Build à blanc (clean-room)

L'ancienne implémentation **n'existe pas ici, volontairement**. Ne jamais la chercher, la cloner ni en porter du code. Les références `fichier:ligne` et identifiants (`Bx`/`Fx`/`Tx`/`Dx`) dans les specs sont des étiquettes de traçabilité : le comportement correct est décrit **en toutes lettres** dans SPEC-UNIFIED §5/§11 — tu reproduis l'invariant, tu n'ouvres pas l'ancien code. Information manquante → tu la **demandes** (`AskUserQuestion`), tu ne la devines jamais.

## Principes de réalisation

1. **Exhaustif sur le QUOI, libre sur le COMMENT.** Les invariants, forks et non-négociables sont des bornes dures ; **tout le reste est ta liberté** — les `reco` de la spec sont des défauts sourcés, pas des mandats. Tu peux faire mieux, en le justifiant.
2. **Ponytail à chaque brique** : (1) doit-elle exister ? (2) stdlib ? (3) natif OS ? (4) dépendance déjà là ? (5) une ligne ? (6) le minimum qui marche. Chaque simplification délibérée porte son `# ponytail:` (écarté + quand rajouter).
3. **Sûreté d'abord — rappel des gardes dures** (le détail qui fait foi est en §3/§5) : garde « RB/rekordboxAgent fermé » avant toute mutation · unit-of-work `_mutate` (assert → backup horodaté → muter → commit → invalider cache ; rollback sur exception) · soft-delete réversible, **entiers 256/258 à l'identique** · résolution de chemins volume-relatif/absolu · **ne jamais déplacer les fichiers** + quirk TCC (`Path.exists()`) · secrets jamais en clair (Spotify tokens only in v1) · dry-run→confirm→mutate avec garde de fraîcheur · `protected` exclus par défaut · suppression fichier **après** commit, corbeille OS sinon consentement préalable · progression réelle SSE, jamais factice.
4. **Aucune logique non triviale sans son check runnable** — le plus petit test qui casse si la logique casse. Pas de framework lourd.
5. **Faithful reporting.** POC qui échoue, choix de spec qui ne tient pas, garde qui rend un parcours lourd → le dire et remonter, jamais masquer.
6. **No unapproved AI workflow.** If a requested feature would call a model, generate prompts, process refusals, or automate cybersecurity analysis, stop and create/approve the split workflow spec first. The prompt must show lawful context and must never request malware, persistence, credential theft, real third-party exploitation, evasion, or safety-system bypass.
7. **No download/acquisition module.** Do not implement Deezer full-track download, streamrip, deemix, ARL collection/storage/UI, SoundCloud download, ffmpeg-based remote media acquisition, download queues, download progress, or POC #6. Missing tracks use legal purchase links and manual relink only.

## Ordre de travail

**Phase 0 = GATE.** Run the active POCs from [SPEC-UNIFIED §8](SPEC-UNIFIED.md): sidecar signature · process lifecycle/tree-kill · size+cold-start · SSE in WKWebView/WebView2 · pyrekordbox RB 7.x fidelity · legal missing-track scope audit · A3 calibration · B2 purchase-link templates · Smart Fixes safety. Each POC is minimal, disposable, and ends with a GO/NO-GO verdict for the owner. POC #6 full-track Deezer/streamrip is removed and must not be run.

Ensuite, chaque phase s'appuie sur la précédente :
1. **Noyau de sûreté** (§3.1/§3.2/§5.1/§5.2) — tests d'abord : c'est le contrat qui protège la collection.
2. **Modèle de domaine & service** (§4, migrations `user_version`, Starlette HTTP+SSE, secrets, supervision, OAuth PKCE port fixe, multi-OS).
3. **Logique métier** (§5.3–§5.13 + §11.2/§11.3) — matching, dedup/keeper, Smart Fixes, faux-320, sync bibliothèque, events (dont ré-application), untagged/missing, Track Matcher légal, manual relink.
4. **Coque & UI** — Tauri v2, Vue 3, **SPEC-DESIGN exécutée** : router réel, 6 destinations, onboarding 11 étapes, composants §6, tokens §7, gardes à surface UI §8, i18n FR/EN réelle, une seule couche de cache + flux SSE canonique, état backend-down.
5. **Packaging** — PyInstaller onedir, signature/notarisation selon POC #1, version single-source, no download/GPL acquisition component, aucun auto-update.

## Contrat de tests

Le contrat = les **invariants de SPEC-UNIFIED §5 + §11** (la suite pytest héritée n'existe pas ici). Écris tes propres tests, en priorité sur : garde RB + `_mutate` + backup · entiers 256/258 · chemins volume-relatif/absolu + TCC · collision ISRC · transitions de statut (sync/event/missing-track relink, **dont ré-application idempotente**) · keeper D6 + rétrogradation A3 · Smart Fixes (dry-run == mutate, idempotence, protected, fraîcheur) · B2 zéro réseau · clauses testables §3.6/§6.5 (no ARL, no streamrip/deemix, no download route/job/UI).

## Définition du « terminé »

- Active Phase 0 POCs GO (ou NO-GO remonté + repli appliqué). Non-négociables §3 tenus **et testés**. Invariants §5 + amendements §11 reproduits et couverts par des tests neufs.
- UI conforme à SPEC-DESIGN (navigation, composants, gardes §8, états) — correctifs §11.1/§11.2 inclus.
- App fonctionnelle macOS **et** Windows ; sidecar démarre/s'arrête proprement (tree-kill, port libéré).
- Zéro secret en clair, zéro chemin codé en dur, une seule source de vérité, no download/acquisition dependency or UI.
- No model-backed feature exists unless its split workflow spec is approved under `docs/ai-workflows/`; refusal/fallback behavior is tested if any such workflow is later approved.
- Chaque simplification ponytail porte son `# ponytail:`.

## Règles d'interaction

- Tout choix structurant non couvert par le kit → **demander** (`AskUserQuestion`), reco ponytail en tête. Ne jamais re-débattre ce qui est tranché.
- Livrable d'abord, explication courte ensuite. Langue : **français**.
