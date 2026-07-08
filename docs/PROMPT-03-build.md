# PROMPT-03 — Construction de Syncbox (from scratch)

> **Comment l'utiliser.** Coller ce prompt dans une session Claude Code **à la racine d'un dépôt neuf** (ou du dépôt actuel si tu repars de zéro dedans). Le mot **`ultracode`** active l'orchestration multi-agents si tu la veux. Le module **ponytail** doit rester actif (`/ponytail full`) — il est une **contrainte de réalisation**, pas une option. La spec qui fait foi est [SPEC-UNIFIED.md](SPEC-UNIFIED.md) : **ne pas la re-débattre**, l'**exécuter**.

---

ultracode — `/ponytail full`

## Mission

Construire **Syncbox** — app desktop **macOS + Windows**, open-source, qui synchronise des playlists Spotify vers la collection **Rekordbox** d'un DJ, **entretient la collection** (doublons, fichiers manquants, tags, **Smart Fixes**, **détection faux-320/FLAC**), propose un **chemin d'achat légal** (liens Beatport/Bandcamp) et un **module de téléchargement optionnel OFF par défaut** (Deezer via streamrip) — **à partir de zéro**, en suivant [SPEC-UNIFIED.md](SPEC-UNIFIED.md).

**Le but** : le code **le plus propre, fonctionnel et épuré** qui réalise la spec, sans la dette héritée. Cette réécriture est volontairement *from scratch* : le code de test existant (`service/tests/`) n'est **pas** une contrainte d'architecture — seuls comptent les **invariants de comportement** ([SPEC-UNIFIED §5](SPEC-UNIFIED.md)). Tu écris **tes propres tests**.

## Build à blanc (clean-room) — règle d'isolation

Tu construis dans un dépôt **NEUF et VIDE**. L'ancienne implémentation de Syncbox **n'existe pas ici, volontairement**. Tu ne dois **JAMAIS** la chercher, la cloner, l'importer, ni porter son code — ni `service/`, ni `electron/`, ni `src/` d'origine, ni `docs/_analysis/`. Les références `fichier:ligne` et les identifiants de bugs (`Bx`/`Fx`/`Tx`/`Dx`) que tu croises dans les specs sont de **simples étiquettes de traçabilité** : le comportement correct est **décrit en toutes lettres** dans [SPEC-UNIFIED §5](SPEC-UNIFIED.md) — tu **reproduis l'invariant, tu n'ouvres pas l'ancien code**. Si une information manque, tu la **demandes** (`AskUserQuestion`) ; tu ne la devines **jamais** depuis un dépôt existant.

## Intrants (hiérarchie d'autorité)

1. **[SPEC-UNIFIED.md](SPEC-UNIFIED.md)** — **fait foi** pour toute décision d'archi/produit : forks tranchés (§7.1), réponses §10 (§7.2), D1–D25 (§7.3), non-négociables (§3), modèle de domaine (§4), invariants de comportement (§5), architecture (§6), ordre de dé-risquage (§8).
2. **`docs/_research/00–14`** — l'**état de l'art sourcé et daté** derrière chaque choix. À relire avant d'implémenter une brique d'infra (signature, transport, secrets, multi-OS, migrations, supervision, acquisition) ou un ajout v1 (Chromaprint/11, faux-320/12, achat légal/13, streamrip/14). Recherche externe — ne référence aucun code existant.
3. **[SPEC-01-syncbox.md](SPEC-01-syncbox.md)** — **annexe de constantes UNIQUEMENT** (pondérations, seuils, buckets). À consulter seulement pour **départager une constante** quand §5 ne suffit pas. ⚠️ Les `fichier:ligne` qu'elle cite **ne sont PAS dans ce dépôt** : **ne les cherche pas**, ne tente pas de lire le code cité.

En cas de conflit : SPEC-UNIFIED > SPEC-01 (constantes) > research. (`docs/_analysis/` est **hors du kit** — voir la règle d'isolation.)

## Principes de réalisation (non négociables)

1. **Ponytail à chaque brique.** Remonter l'échelle : (1) doit-elle exister ? (2) stdlib ? (3) feature native OS/plateforme ? (4) dépendance déjà installée ? (5) une ligne ? (6) le minimum qui marche. Le diff le plus court qui passe les tests gagne. Marquer chaque simplification délibérée d'un `# ponytail:` (ce qui est écarté + quand le rajouter).
2. **Altitude : exhaustif sur le QUOI, libre sur le COMMENT.** La spec fixe les invariants, les forks et les non-négociables ; **le reste est ta liberté** — choisis la meilleure implémentation dans ces bornes. Les recommandations `reco` de la spec sont des défauts sourcés, pas des mandats : tu peux faire mieux, en le justifiant.
3. **Sûreté d'abord.** Les non-négociables [§3](SPEC-UNIFIED.md) sont des **gardes dures**, jamais simplifiables : garde « RB/rekordboxAgent fermé » avant toute mutation, `_mutate` (assert → backup → muter → commit → invalider cache ; rollback sur exception), soft-delete réversible, **entiers de statut load-bearing** (256/258, `rb_data_status`) à reproduire à l'identique, résolution de chemins volume-relatif/absolu, **ne jamais déplacer les fichiers** + quirk TCC, secrets jamais en clair.
4. **Aucune simplification sans son test.** Toute logique non triviale (branche, boucle, parser, chemin sûreté/argent) laisse **un** check runnable qui casse si la logique casse. Pas de framework lourd, pas de fixtures inutiles.
5. **Faithful reporting.** Si un POC échoue ou révèle qu'un choix de la spec ne tient pas, **le dire** et remonter la décision — ne pas masquer un blocage.

## Stack tranchée (forks A–D — [SPEC-UNIFIED §7.1](SPEC-UNIFIED.md))

- **A — Écriture Rekordbox** : `master.db` **en place, sans mode XML**, via **pyrekordbox** (Python, MIT). Cœur produit = MyTags + smart playlists.
- **B — Coque** : **Tauri v2** (webview natif), sidecar Python en `externalBin`. Repli Electron **seulement** si le POC #1 (signature) bloque.
- **C — Transport** : **HTTP REST + SSE en localhost** (sidecar = **Starlette + `sse-starlette`**, uvicorn 1 worker dans la boucle asyncio principale). **Pas** de JSON-RPC stdio. Serveur bindé `127.0.0.1`, origines restreintes aux loopback.
- **D — Acquisition** : **module OPTIONNEL, OFF par défaut** ; **chemin légal B2 mis en avant** (liens d'achat Beatport/Bandcamp, **stdlib `urllib`, zéro réseau côté app**). Téléchargement = **streamrip importé comme lib** (pin git **v2.2.0**, SHA figé, **Deezer-only v1**), interface mince `DeezerAcquirer.download(track_id) -> Path`, **jamais sur le chemin critique `master.db`** ; **code GPL-3 non embarqué dans l'artefact de base** (composant séparé). **deemix-fork = fallback documenté** ; SoundCloud → v2 (ffmpeg). full-track = **POC #6**, choix de lib **tranché (streamrip)**.

**Ajouts v1 (périmètre OVERHAUL-01, [§7.4](SPEC-UNIFIED.md))** : A1 Smart Fixes, A3 faux-320/FLAC, B2 Track Matcher légal (+ D7 untagged). **Différés v2** : A2 dedup empreinte Chromaprint (binaire LGPL, POC), SoundCloud (B4, ffmpeg), A5 AcoustID.

**Conditions dures à respecter** (sourcées, [§6](SPEC-UNIFIED.md)) : signature sidecar macOS en **étape POST-bundle** (#11992 ouverte) ; `redirect_uri` OAuth **codé en dur** `http://127.0.0.1:8765/callback` + réponse indépendante du Host ; **tree-kill** du worker PyInstaller (sinon port 8765 orphelin) ; migrations **`PRAGMA user_version` + scripts stdlib** (seed = migration `0001`) ; secrets **`keyring` si signé / store chiffré si non signé** (tokens Spotify **ET** ARL Deezer) ; suppression fichier cloud/exFAT = corbeille OS **sinon suppression définitive avec consentement préalable**. **Ajouts v1** : Smart Fixes (A1) écrit `master.db` **uniquement via `_mutate`** (dry-run→confirm→mutate, garde de fraîcheur du snapshot, `protected` exclus par défaut) ; faux-320 (A3) **read-only** (`miniaudio`+`numpy.fft`, jamais dans `_mutate`) ; Track Matcher (B2) = **zéro réseau côté app** ; lib d'acquisition force le **bundle `certifi`** (TLS jamais désactivé) et **n'écrit jamais l'ARL en clair** (pas de `config.toml`).

## Ordre de travail — POC d'abord (dé-risquage avant tout engagement)

> **Phase 0 = GATE.** Ne pas construire l'app complète avant d'avoir levé les 9 risques de [SPEC-UNIFIED §8](SPEC-UNIFIED.md) (6 infra + 3 ajouts v1). Chaque POC est minimal, jetable, et conclut par un verdict GO/NO-GO remonté au propriétaire.

**Phase 0 — POC de dé-risquage** (dans l'ordre) :
1. **Signature + notarisation du sidecar PyInstaller sous Tauri macOS** (#11992, étape POST-bundle `codesign`+`notarytool`). NO-GO → repli Electron (Fork B).
2. **Cycle de vie du process** : spawn + supervision + **tree-kill** (mac process-group **et** Windows `taskkill /T`) + fermeture propre SQLCipher + libération du port 8765 + single-instance.
3. **Taille bundle + cold-start** mesurés (PyInstaller `--onedir`, venv réel numpy+sqlcipher3+pyrekordbox+**miniaudio/cffi (A3)**+downloader ; `fpcalc`/A2 hors v1).
4. **`EventSource`/SSE dans WKWebView + WebView2 réels** (Starlette+sse-starlette sur HTTP localhost), pas en Chromium/Electron.
5. **Fidélité d'écriture pyrekordbox sur RB 7.x** (smart playlists/MyTags, bug #110) — harnais de non-régression sur le schéma `master.db`.
6. **Acquisition (B1) — porte bloquante** : full-track **Deezer** avec **ARL Premium réel** (vs preview 30 s) via **streamrip lib** (pin git v2.2.0, SHA figé), par **ID numérique résolu de l'ISRC** ; wrapper `DeezerAcquirer` via `PendingSingle.resolve()→track.download_path` (D18, ARL **en mémoire**, `Config`/job, F2/F3) ; packaging `pycryptodomex`(Blowfish)/`mutagen` mac+Win. **Bascule deemix-fork** si coût aiohttp / fragilité d'API bloquante. NO-GO → **B1 différé v1.1, B2 (légal) reste le chemin manquants, le reste livrable**.
7. **Faux-320/FLAC (A3)** : delta bundle réel `miniaudio`+`cffi`+`pycparser` mac+Win (`hiddenimport _cffi_backend`, **`optimize=0`**, numpy en dép directe) ; calibration rolloff (frontière 320/V0 = zone `incertain`) + faux positifs masters band-limités ; branchement A3→D6 (rétrogradation du critère qualité, jamais dans `_mutate`). NO-GO/non-calibrable → repli **A3-lite** (champs snapshot, 0 dépendance native) ou v2.
8. **Track Matcher légal (B2)** : URL Beatport/Bandcamp sur 5-10 morceaux réels (taux de bon 1er résultat) ; fallback « boutique disparue » (entrée retirée du catalogue au build → bouton absent). **Zéro réseau côté app.**
9. **Smart Fixes (A1)** : `dry-run` == payload réellement écrit ; ordre déterministe + **idempotence** (re-run = no-op) ; garde `protected` exclus par défaut (opt-in nommé non mémorisé) ; **garde de fraîcheur** (ré-validation `(mtime,size)` à l'entrée de `_mutate`, ABORT si la DB a changé) ; passage exclusif par `_mutate`.

**Phase 1 — Noyau de sûreté** (le plus précieux) : `pyrekordbox` + la colonne vertébrale §3.1/§5.1 (garde RB fermé, `_mutate`, backup, soft-delete, restore, résolution de chemins §3.2/§5.2). **Tests d'abord** sur ces invariants — c'est le contrat qui protège la collection de l'utilisateur.

**Phase 2 — Modèle de domaine & service** : entités §4, SQLite app + migrations `user_version`, transport Starlette HTTP+SSE, secrets au repos (§6.7), supervision (§6.6), OAuth PKCE port fixe (§6.10), abstraction multi-OS (§6.9).

**Phase 3 — Logique métier** : matching ISRC/fuzzy (§5.3, normalisation unique D19), dedup + keeper explicite (§5.4, D5/D6 **échelle ordonnée discrète**), **Smart Fixes (A1, §5.11 — dry-run→confirm→mutate via `_mutate`, catalogue FIXE structurel, `protected` exclus, garde de fraîcheur)**, **détection faux-320/FLAC (A3, §5.12 — read-only `miniaudio`+`numpy.fft`, verdict → rétrogradation keeper D6)**, sync bibliothèque (§5.6), événements + smart playlists (§5.7), untagged/missing (§5.8), **Track Matcher légal (B2, §5.13 — URL Beatport/Bandcamp `urllib` stdlib, zéro réseau côté app)**, acquisition (§5.5, **streamrip Deezer-only**, vrai chemin de sortie D18, concurrence sans global F2/F3) — **module optionnel OFF par défaut**.

**Phase 4 — Coque & UI** : Tauri v2, UI Vue 3 (i18n FR/EN), **une seule** couche de cache + un flux SSE de jobs canonique, single-instance, état « backend indisponible ».

**Phase 5 — Packaging** : PyInstaller `--onedir`, signature/notarisation (selon POC #1), version single-source ; **`miniaudio`/`cffi`/`pycparser` bundlés (A3, `optimize=0`, numpy en dépendance directe)** ; module acquisition GPL-3 **livré séparément** (hors artefact de base) ; **aucun auto-update** (cohérent mémoire `no-auto-build-release`).

> L'UI/UX détaillée (§10.9) et le matching configurable (§10.10) sont **délégués à la phase design** (SPEC-UNIFIED §9) — ne pas les figer ici ; concevoir les parcours quand le reste tient.

## Contrat de tests

Le contrat est l'ensemble des **invariants de comportement** ([SPEC-UNIFIED §5](SPEC-UNIFIED.md)), pas la suite pytest héritée. **Écris tes propres tests**, couvrant en priorité : la garde RB + `_mutate` + backup (sûreté), les entiers de statut 256/258, la résolution de chemins volume-relatif/absolu, le quirk TCC (`Path.exists()`), la garde de collision ISRC, les transitions de statut (sync/event/acquisition), le keeper explicite (échelle ordonnée D6 + rétrogradation A3 primant sur le bitRate déclaré), la suppression réversible. **Ajouts v1** : Smart Fixes (dry-run == mutate, idempotence, ordre déterministe, `protected` exclus, garde de fraîcheur, passage `_mutate`) ; faux-320 (verdict, jamais dans `_mutate`, `ok`/neutre par défaut si non analysé) ; Track Matcher (URL construites correctement, **zéro appel réseau côté app**). Pas de fixtures lourdes ; un check runnable par invariant non trivial.

## Définition du « terminé »

- Les 9 POC de Phase 0 sont GO (ou leur NO-GO est remonté avec le repli appliqué : B1→v1.1, A3→A3-lite/v2).
- Tous les non-négociables §3 sont tenus et **testés**.
- Les invariants §5 (dont §5.11–§5.13) sont reproduits et couverts par des tests neufs.
- **Les 4 ajouts v1 sont livrés et testés** : A1 Smart Fixes (via `_mutate`), A3 faux-320/FLAC (read-only), B2 Track Matcher légal (zéro réseau côté app), B1 streamrip Deezer-only **si POC #6 GO** (sinon différé v1.1 sans bloquer la release — B2 couvre les manquants). **A2 dedup empreinte et SoundCloud sont hors v1** (différés v2).
- L'app tourne sur macOS **et** Windows ; le sidecar démarre/s'arrête proprement (tree-kill, pas d'orphelin, port libéré).
- Zéro secret en clair (tokens Spotify + ARL Deezer chiffrés, aucun `config.toml` streamrip) ; zéro chemin codé en dur ; une seule source de vérité (données + réglages) ; code GPL-3 d'acquisition **non embarqué dans l'artefact de base**.
- Chaque simplification ponytail porte son `# ponytail:` (ce qui est écarté + quand le rajouter).

## Règles d'interaction

- **Tout choix structurant non couvert par la spec → demander** (`AskUserQuestion`), reco ponytail en tête.
- Ponytail actif : livrable d'abord, explication courte ensuite ; la simplification se justifie par sa brièveté.
- Langue : **français**.
