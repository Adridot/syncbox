# PROMPT-03 — Construction de Syncbox (from scratch)

> **Comment l'utiliser.** Coller ce prompt dans une session Claude Code (**Fable**) **à la racine d'un dépôt neuf** contenant uniquement le kit de specs (`docs/` + `syncbox-ui-ux-design/`). Le mot **`ultracode`** active l'orchestration multi-agents. Le module **ponytail** reste actif (`/ponytail full`) — contrainte de réalisation, pas une option.
>
> **Ce prompt ne paraphrase pas les specs.** Il fixe la mission, la hiérarchie d'autorité, les portes et les libertés. Tout le détail — invariants, constantes, écrans, recherches — vit dans le kit : **il fait foi, pas ce prompt**. Si une phrase de ce prompt semble contredire une spec, la spec gagne.

---

ultracode — `/ponytail full`

## Mission

Construire **Syncbox** — app desktop **macOS + Windows**, open-source : synchronise des playlists Spotify (lecture seule) vers la collection **Rekordbox** d'un DJ, entretient la collection (doublons, fichiers manquants, tags, Smart Fixes, détection faux-320/FLAC), propose un **chemin d'achat légal mis en avant** et un **module de téléchargement optionnel OFF par défaut** — **à partir de zéro**, le code le plus propre et épuré qui réalise la spec, sans la dette héritée.

## Étape zéro — lire TOUT le kit

Avant d'écrire une ligne : lis **intégralement** SPEC-UNIFIED.md (y compris **§11, amendements post-design**), SPEC-DESIGN.md, le mockup `syncbox-ui-ux-design/project/Syncbox.dc.html`, et parcours `docs/_research/00-14`. Tu raisonnes mieux avec le corpus complet qu'avec des extraits — c'est pour ça que ce prompt est court.

## Hiérarchie d'autorité

1. **[SPEC-UNIFIED.md](SPEC-UNIFIED.md)** — fait foi sur **tout** : non-négociables (§3), modèle de domaine (§4), invariants de comportement (§5), architecture et forks tranchés (§6/§7), ordre de dé-risquage (§8), **amendements Gate 3 (§11)** : SoundCloud borné à l'ajout event, cycle « modifié → ré-appliquer », readouts dashboard dérivés du snapshot.
2. **[SPEC-DESIGN.md](SPEC-DESIGN.md) + mockup [`Syncbox.dc.html`](../syncbox-ui-ux-design/project/Syncbox.dc.html)** — font foi sur le **COMMENT UI** : 6 destinations + onboarding, router réel avec deep-link (`#health/<tab>`, route inconnue → Dashboard), inventaire de composants, tokens visuels. Le mockup se reproduit en **comportement et hiérarchie visuelle**, pas en CSS littéral (il est inline-styled, tout-FR, navigation par état — le build fait router réel + i18n `en.ts`/`fr.ts`). Les correctifs de gardes §3/§5 sont déjà appliqués et validés dans le mockup ([SPEC-DESIGN §11.2](SPEC-DESIGN.md)). En cas de conflit mockup ↔ spec : la spec gagne.
3. **`docs/_research/00–14`** — l'état de l'art sourcé derrière chaque choix d'infra. À relire **avant** d'implémenter la brique correspondante (signature, transport, secrets, multi-OS, migrations, supervision, acquisition, ajouts v1).
4. **[SPEC-01-syncbox.md](SPEC-01-syncbox.md)** — **annexe de constantes uniquement** (pondérations, seuils, buckets), à consulter pour départager une constante quand §5 ne suffit pas.

## Build à blanc (clean-room)

L'ancienne implémentation **n'existe pas ici, volontairement**. Ne jamais la chercher, la cloner ni en porter du code. Les références `fichier:ligne` et identifiants (`Bx`/`Fx`/`Tx`/`Dx`) dans les specs sont des étiquettes de traçabilité : le comportement correct est décrit **en toutes lettres** dans SPEC-UNIFIED §5/§11 — tu reproduis l'invariant, tu n'ouvres pas l'ancien code. Information manquante → tu la **demandes** (`AskUserQuestion`), tu ne la devines jamais.

## Principes de réalisation

1. **Exhaustif sur le QUOI, libre sur le COMMENT.** Les invariants, forks et non-négociables sont des bornes dures ; **tout le reste est ta liberté** — les `reco` de la spec sont des défauts sourcés, pas des mandats. Tu peux faire mieux, en le justifiant.
2. **Ponytail à chaque brique** : (1) doit-elle exister ? (2) stdlib ? (3) natif OS ? (4) dépendance déjà là ? (5) une ligne ? (6) le minimum qui marche. Chaque simplification délibérée porte son `# ponytail:` (écarté + quand rajouter).
3. **Sûreté d'abord — rappel des gardes dures** (le détail qui fait foi est en §3/§5) : garde « RB/rekordboxAgent fermé » avant toute mutation · unit-of-work `_mutate` (assert → backup horodaté → muter → commit → invalider cache ; rollback sur exception) · soft-delete réversible, **entiers 256/258 à l'identique** · résolution de chemins volume-relatif/absolu · **ne jamais déplacer les fichiers** + quirk TCC (`Path.exists()`) · secrets jamais en clair (tokens Spotify + ARL) · dry-run→confirm→mutate avec garde de fraîcheur · `protected` exclus par défaut · suppression fichier **après** commit, corbeille OS sinon consentement préalable · progression réelle SSE, jamais factice.
4. **Aucune logique non triviale sans son check runnable** — le plus petit test qui casse si la logique casse. Pas de framework lourd.
5. **Faithful reporting.** POC qui échoue, choix de spec qui ne tient pas, garde qui rend un parcours lourd → le dire et remonter, jamais masquer.

## Ordre de travail

**Phase 0 = GATE.** Les **9 POC de [SPEC-UNIFIED §8](SPEC-UNIFIED.md)** (signature sidecar · cycle de vie/tree-kill · taille+cold-start · SSE en WKWebView/WebView2 · fidélité pyrekordbox RB 7.x · full-track Deezer streamrip · calibration A3 · templates B2 · sûreté Smart Fixes), minimaux et jetables, chacun conclu par un verdict **GO/NO-GO remonté au propriétaire** avec son repli spécifié (B1→v1.1, A3→A3-lite/v2, Tauri→Electron). Au POC #5, confirmer aussi les champs des readouts §11.3 (`KeyID/ScaleName`, `DJPlayCount`, `StockDate`) sur un `master.db` réel — 10 lignes.

Ensuite, chaque phase s'appuie sur la précédente :
1. **Noyau de sûreté** (§3.1/§3.2/§5.1/§5.2) — tests d'abord : c'est le contrat qui protège la collection.
2. **Modèle de domaine & service** (§4, migrations `user_version`, Starlette HTTP+SSE, secrets, supervision, OAuth PKCE port fixe, multi-OS).
3. **Logique métier** (§5.3–§5.13 + §11.2/§11.3) — matching, dedup/keeper, Smart Fixes, faux-320, sync bibliothèque, events (dont ré-application), untagged/missing, Track Matcher légal, acquisition optionnelle.
4. **Coque & UI** — Tauri v2, Vue 3, **SPEC-DESIGN exécutée** : router réel, 6 destinations, onboarding 11 étapes, composants §6, tokens §7, gardes à surface UI §8, i18n FR/EN réelle, une seule couche de cache + flux SSE canonique, état backend-down.
5. **Packaging** — PyInstaller onedir, signature/notarisation selon POC #1, version single-source, module GPL-3 **hors artefact de base**, aucun auto-update.

## Contrat de tests

Le contrat = les **invariants de SPEC-UNIFIED §5 + §11** (la suite pytest héritée n'existe pas ici). Écris tes propres tests, en priorité sur : garde RB + `_mutate` + backup · entiers 256/258 · chemins volume-relatif/absolu + TCC · collision ISRC · transitions de statut (sync/event/acquisition, **dont ré-application idempotente**) · keeper D6 + rétrogradation A3 · Smart Fixes (dry-run == mutate, idempotence, protected, fraîcheur) · B2 zéro réseau · clauses testables §3.6/§6.5 (ARL jamais sur disque, streamrip jamais chargé au boot, TLS certifi).

## Définition du « terminé »

- 9 POC GO (ou NO-GO remonté + repli appliqué). Non-négociables §3 tenus **et testés**. Invariants §5 + amendements §11 reproduits et couverts par des tests neufs.
- UI conforme à SPEC-DESIGN (navigation, composants, gardes §8, états) — correctifs §11.1/§11.2 inclus.
- App fonctionnelle macOS **et** Windows ; sidecar démarre/s'arrête proprement (tree-kill, port libéré).
- Zéro secret en clair, zéro chemin codé en dur, une seule source de vérité, GPL-3 hors artefact de base.
- Chaque simplification ponytail porte son `# ponytail:`.

## Règles d'interaction

- Tout choix structurant non couvert par le kit → **demander** (`AskUserQuestion`), reco ponytail en tête. Ne jamais re-débattre ce qui est tranché.
- Livrable d'abord, explication courte ensuite. Langue : **français**.
