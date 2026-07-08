# PROMPT — Analyse fonctionnelle & technique exhaustive de Syncbox
### Phase 1/2 : reverse-engineering en vue d'une réécriture propre

> **Mode d'emploi.** Ouvre une session Claude Code à la racine du dépôt et colle tout ce qui suit (à partir de « ── DÉBUT DU PROMPT ── »). Le résultat est un **document de spécification**, pas du code et pas une architecture. C'est l'intrant de la Phase 2 (choix d'architecture & approche de développement), qui fera l'objet d'un prompt séparé.

---

## ── DÉBUT DU PROMPT ──

### Contexte

Tu analyses **Syncbox**, une application desktop (Electron + Vue 3 + service Python FastAPI) qui synchronise des playlists Spotify vers la collection Rekordbox d'un DJ, télécharge les morceaux manquants via Deemix/Deezer, et entretient la collection (doublons, fichiers manquants, tags). L'app a été construite par prompts successifs et a accumulé des bugs, des incohérences et de la dette. Le but final est de **la réécrire de zéro, à l'identique fonctionnellement mais sans les défauts hérités**.

Cette analyse est la **première de deux étapes** :

1. **(toi, maintenant)** Comprendre exhaustivement ce que l'app fait, comment elle se comporte, comment elle est construite, ce qui est cassé, et **décider avec l'utilisateur ce qu'on garde / retire / change**. Produire une spécification fonctionnelle + technique.
2. **(plus tard, autre session)** À partir de ta spec, concevoir l'architecture cible et l'approche de développement.

### Ton rôle et ta posture

Tu es un analyste produit **et** un ingénieur de reverse-engineering senior. Tu es rigoureux, factuel et sceptique : tu décris ce qui *est*, pas ce qui *devrait être*. Tu ne te laisses pas impressionner par le code existant — c'est une source à auditer, pas une vérité.

### Règles d'or — NON NÉGOCIABLES

1. **Tu ne choisis PAS la stack ni l'architecture cible.** Pas de « il faudrait utiliser X », pas de « réécrivons en Y ». Tu peux *noter des observations techniques* et *lister des options ouvertes*, mais toute décision d'archi est différée à la Phase 2. Si tu te surprends à rédiger une recommandation de stack, arrête-toi et transforme-la en *question ouverte*.

2. **Au moindre doute, tu DEMANDES.** Dès qu'une fonctionnalité, un comportement ou une donnée pourrait raisonnablement être *gardé tel quel*, *retiré*, *simplifié* ou *modifié* — et que tu ne peux pas trancher seul avec certitude — tu poses la question à l'utilisateur (via `AskUserQuestion`, en lots groupés et thématiques). Tu ne supposes jamais à sa place sur ce qui a de la valeur pour lui. En cas d'hésitation entre « demander » et « décider seul » : demande.

3. **Tout est ancré dans le code réel.** Chaque fonctionnalité, règle ou contrat que tu affirmes doit pointer vers une preuve (`fichier:ligne`). Tu n'inventes aucune feature. Si quelque chose semble exister mais que tu ne le retrouves pas, tu le notes comme *à confirmer*, pas comme un fait.

4. **Tu sépares trois choses qui se confondent facilement :**
   - ce que l'app **fait aujourd'hui** (observable),
   - ce qui est **intentionnel** vs ce qui est un **bug / un effet de bord / de la dette**,
   - ce qu'on **veut** dans la réécriture (garder / retirer / changer).
   Ne jamais mélanger ces trois registres dans une même phrase sans le signaler.

5. **L'UI/UX est un sujet OUVERT, pas un acquis.** Décris l'organisation actuelle (pages, menus, navigation, états) et propose *des pistes*, mais ne verrouille rien : la répartition des pages, l'arborescence des menus et les parcours sont explicitement « à redéfinir en phase de design ». L'utilisateur n'est pas certain de leur pertinence — traite-les comme des hypothèses à challenger, pas comme des contraintes.

6. **Tu captures le CONTRAT DE COMPORTEMENT, pas l'implémentation.** Ce qui doit survivre à une réécriture, ce sont les *règles métier, invariants et cas limites* (ex. « les mutations Rekordbox sont bloquées si Rekordbox tourne », « les suppressions sont réversibles via backup »), pas la façon dont le code actuel les réalise. Décris le *quoi* et le *pourquoi*, laisse le *comment* à la Phase 2.

7. **Tu n'écris pas de code et tu ne modifies rien.** Lecture seule. Le seul artefact que tu produis est le document de spécification (+ les questions posées à l'utilisateur).

### Méthode (phases d'analyse)

Travaille dans cet ordre. Tu peux paralléliser l'exploration, mais respecte la séquence logique des livrables.

**P0 — Reconnaissance.** Cartographie le dépôt : couches (renderer / Electron main / service Python), arborescence, points d'entrée, scripts de build, dépendances et leur rôle. Confirme/complète l'appendice de départ ci-dessous au lieu de repartir de zéro.

**P1 — Décomposition fonctionnelle.** Inventorie *toutes* les fonctionnalités exposées à l'utilisateur (les fichiers de locale `en.ts`/`fr.ts` sont un excellent index de features). Pour chacune : ce qu'elle fait, où elle vit, son état (complète / à moitié finie / morte). Recense les écrans, la navigation, les parcours end-to-end clés.

**P2 — Spécification comportementale (le « cœur » à préserver).** Pour chaque domaine, extrais les **règles métier, invariants, garanties de sécurité et cas limites** : conditions de blocage, ordres d'opérations, réversibilité, gestion des conflits, priorités de tri, stratégies de matching, etc. C'est la partie la plus précieuse de la spec.

**P3 — Reverse-engineering technique.** Documente les couches et surtout les **contrats internes** : canaux IPC (renderer↔main), endpoints HTTP (renderer↔service), flux SSE, variables d'environnement de spawn, formes de payload. Documente la couche de données (persistance, caches, sources de vérité) et l'accès Rekordbox/Spotify/Deemix. Décris *les contrats*, pas la qualité du code (ça vient en P4).

**P4 — Catalogue des bugs & douleurs (ce qu'il NE FAUT PAS reproduire).** Liste les défauts, classés : `bug` (comportement incorrect) / `fragile` (race, gestion d'erreur absente, hypothèse cachée) / `dette` (incohérence, duplication, complexité non justifiée) / `inachevé` (feature à moitié faite). Pour chacun : symptôme observable, `fichier:ligne`, cause probable, et impact sur l'utilisateur. Utilise l'appendice « dette connue » comme point de départ, vérifie-le et étends-le.

**P5 — Modèle de domaine & données.** Décris le domaine qui doit survivre quelle que soit la techno : entités (source/playlist, track, event, job d'acquisition, tag, backup…), leurs relations, leurs cycles de vie et statuts, les identités de matching (ISRC, fuzzy). C'est le socle métier réutilisable.

**P6 — Décisions garder / retirer / changer (INTERACTIF).** Pour chaque feature et chaque comportement notable, propose une décision et — au moindre doute — **demande à l'utilisateur**. Consigne chaque réponse dans un *journal de décisions*. Vois la taxonomie et le protocole ci-dessous.

**P7 — UI/UX : état des lieux + pistes ouvertes.** Décris l'organisation actuelle, puis propose 2-3 pistes alternatives de structuration (sans trancher), et liste les questions de design ouvertes. Marque tout comme « hypothèse à valider en phase design ».

**P8 — Contraintes & non-négociables.** Ce que la réécriture *devra* respecter quoi qu'il arrive : sûreté Rekordbox (SQLCipher, blocage si RB ouvert, backups), dépendances externes incontournables (pyrekordbox, Deemix, Spotify OAuth), contraintes de packaging (binaire Python embarqué), plateforme (macOS), etc.

**P9 — Questions ouvertes pour la Phase 2.** La liste explicite des décisions d'architecture et de produit *non tranchées*, prêtes à être reprises par le prompt d'architecture. C'est la passerelle vers l'étape suivante.

### Protocole d'interaction (quand et comment demander)

- **Groupe tes questions par thème** et pose-les avec `AskUserQuestion` (max 4 par appel). N'inonde pas l'utilisateur d'une question à la fois.
- **Pose une question dès que la réponse change ce qu'on garde/retire/change**, c.-à-d. quand : (a) une feature est ambiguë en valeur, (b) un comportement actuel pourrait être un bug *ou* une intention, (c) deux features se chevauchent (laquelle garder ?), (d) une complexité existe sans justification visible (la retirer ?), (e) une feature semble inachevée (la finir, la couper, ou la repenser ?).
- **Ne demande PAS** ce que le code répond sans ambiguïté, ni des micro-détails d'implémentation, ni des choix de stack (différés). Pour le reste, recommande une option par défaut *et* demande confirmation.
- **Chaque réponse va au journal de décisions**, avec sa justification.

### Taxonomie des décisions (à appliquer à chaque feature/comportement)

`GARDER` (tel quel) · `GARDER-MAIS-CORRIGER` (le comportement reste, le bug saute) · `SIMPLIFIER` (garder l'intention, réduire la surface) · `CHANGER` (revoir le comportement) · `RETIRER` · `À-DÉCIDER` (question posée à l'utilisateur).

### Livrable attendu

Un seul document Markdown structuré, dense et navigable — la **spécification fonctionnelle & technique de Syncbox** — comprenant au minimum :

1. Résumé exécutif (ce qu'est l'app, en 10 lignes).
2. Inventaire fonctionnel (features × état × emplacement).
3. Spécification comportementale par domaine (règles, invariants, cas limites).
4. Carte technique & contrats internes (IPC, HTTP, SSE, données, externes).
5. Catalogue des défauts (bug / fragile / dette / inachevé) avec `fichier:ligne`.
6. Modèle de domaine & données.
7. **Journal de décisions** garder/retirer/changer (avec les réponses de l'utilisateur).
8. UI/UX : état des lieux + pistes ouvertes.
9. Contraintes & non-négociables.
10. **Questions ouvertes pour la Phase 2 (architecture).**

Le document doit pouvoir être lu seul par quelqu'un qui n'a jamais vu le code, et suffire à réécrire l'app à l'identique fonctionnellement. Reste factuel ; signale explicitement tout ce qui est supposé ou à confirmer.

---

## Appendice A — Carte de départ (à vérifier et approfondir, pas à recopier)

> Ceci est un point de départ issu d'une première exploration. Confirme chaque élément dans le code, corrige ce qui est faux, et **complète** — ne te contente pas de le reprendre.

### Écrans (~9, navigation par état Pinia `useUiStore`, pas de Vue Router)
Dashboard · My Library (suivi de playlists Spotify, master-détail) · Events (sets DJ, création 3 modes, « Live Import » M3U8) · Download & Match (queue Deemix, résolution de conflits) · Duplicates (scan ISRC/fuzzy, auto-résolution) · Missing Files (re-download / re-link / soft-delete) · Untagged (diagnostic + suggestions + tagging de masse) · Doctor (diagnostics, backups Rekordbox, restore, logs) · Settings (Spotify, Deemix/ARL, chemins, langue EN/FR, backup/restore).

### Domaines fonctionnels
Synchronisation & acquisition (suivi de playlists, sync source/all, auto-tag MyTags) · Événements/DJ sets (analyse Spotify, workspace, staging, Live Import sans écriture DB) · Téléchargement & matching (Deemix, statuts de jobs, résolution de conflits ambigus via recherche Deezer) · Gestion de collection (doublons, fichiers manquants, untagged) · Config & accès (langue, OAuth Spotify, chemins, backup/restore) · Système & monitoring (santé API/Rekordbox/Deemix/Spotify, stats collection, diagnostics).

### Stack
Electron 42 (main TS, preload CJS) · Vue 3 + Pinia 3 (~6 stores) **et** TanStack vue-query 5 (cohabitation assumée mais partielle) · vue-i18n 11 (FR/EN) · Tailwind 4 · electron-store 8 · Service Python 3.12+ FastAPI/uvicorn · pyrekordbox 0.4.4 (master.db SQLCipher) · mutagen · rapidfuzz · httpx · pydantic · build : Vite/electron-vite + PyInstaller + electron-builder (DMG macOS, binaire Python en extraResources).

### Communication entre couches
Renderer↔Main : IPC via `window.desktop.*` (settings get/set/reload, getApiBaseUrl, openExternal/openPath/openLogs, deemix status/launch/install/onProgress). Renderer↔Service : HTTP fetch (`/api/...`) sur port `RBSYNC_SERVICE_PORT` (8765), base URL obtenue par IPC. Main↔Service : `child_process.spawn` (dev : `uv run uvicorn` ; packagé : binaire PyInstaller) avec env `RBSYNC_DATA_DIR / _SERVICE_PORT / _APP_VERSION / _LOG_DIR`. Temps réel : SSE `/api/acquisition/stream` (refresh 4s, reconnect côté client).

### Sources de vérité / données
electron-store (`syncbox-settings.json`, lecture sync instantanée) ↔ SQLite service (`syncbox.sqlite3`, vérité pour OAuth/tasks/metadata, seedée au 1er run) ↔ vue-query (cache réseau) ↔ caches mémoire de `RekordboxAdapter` (clé = mtime+size de master.db). Réconciliation settings au boot par *pull* unidirectionnel depuis le service.

## Appendice B — Dette connue (à vérifier, étendre et chiffrer en P4)

- **Split data-layer incohérent** : Duplicates/Doctor/Missing/Untagged en vue-query ; Events/Library/Settings en Pinia + HTTP manuel. `useSystemStatusQuery` écrit directement dans le store, `useRefreshManager` poll en parallèle → double polling, invalidation incohérente, source de vérité ambiguë.
- **Réconciliation settings au boot fragile** (`electron/main.ts` ~75-105) : pull unidirectionnel ; si le service est down au 1er boot, risque d'écrasement de config sans merge.
- **Spawn du service sans garde-fou** (`electron/main.ts` ~131-180) : pas de vérif d'existence de `uv`/binaire, pas de handler d'erreur, logs non maîtrisés ; `waitForService` 30s puis dégradation silencieuse (`api = null`).
- **Races d'événements** (`stores/events.ts` ~68-101) : `requestedEventId` limite le flash UI mais pas les requêtes lentes obsolètes (pas d'abort des in-flight).
- **Invalidation de cache Rekordbox par mtime** (`rekordbox/adapter.py` ~58-63) : hit erroné si RB écrit pendant une lecture ; retries fixes ~3.6s max.
- **Gestion d'erreurs générique** (`stores/ui.ts` withErrorToast ; `lib/api/client.ts` parse) : `.message` sans contexte ; parse qui casse si le service renvoie du non-JSON (ex. page d'erreur Deemix).
- **Chemins** : `DEFAULT_STORAGE_ROOT` codé en dur pour cet utilisateur (Dropbox) ; symlinks/mounts mal gérés ; `validatePath` côté service seulement, pas de feedback précoce côté renderer ; voir aussi la mémoire projet sur la résolution des chemins Rekordbox (paths relatifs au volume vs absolus).
- **SSE / refresh d'acquisition** : pas de validation de payload avant parse ; reconnect sans jitter ; boucle de refresh 4s qui sert des données périmées en silence si une passe échoue.
- **Installeur Deemix** (`electron/deemix.ts`) : best-effort, pas de retry, pas de nettoyage du `.dmg` en cas d'échec.
- **Payloads de jobs opaques** (`models.py`/`acquisition.py`) : `payload: dict` sans schéma → casse silencieuse côté front si la forme change.
- **Backups sur stockage cloud** : partiellement cassés en build dev (macOS bloque l'accès terminal aux dossiers cloud) ; OK en app packagée.

## Appendice C — Décisions probablement à soumettre à l'utilisateur (P6)

Liste de départ des points à clarifier — à compléter au fil de l'analyse :

- Garder la **cohabitation Pinia + vue-query** ou converger ? (la mémoire projet indique qu'elle est *volontaire* — à reconfirmer dans le contexte d'une réécriture).
- **Live Import M3U8** (contournement de l'écriture DB quand RB est ouvert) : feature à conserver ? centrale ou secondaire ?
- Complexité du **diagnostic Untagged** (catégories junk/duplicate/alt/à-revoir) : tout garder ou simplifier ?
- **Auto-résolution des doublons** : garder le « keeper » automatique (lossless > cues > permanent) ou tout passer en revue manuelle ?
- **Réversibilité** (soft-delete + backups + restore via Doctor) : périmètre à garder ?
- **Installation de Deemix depuis l'app** : conserver, ou supposer Deemix déjà installé ?
- **Bilingue FR/EN** : maintenu ? d'autres langues ?
- **OAuth Spotify in-app** vs mode app-only : les deux ou un seul ?
- **Rétention des backups**, stats de collection, dashboard de santé : niveau de détail souhaité ?
- Périmètre **plateforme** : macOS seul, ou viser Windows/Linux (impacte fortement la Phase 2) ?

## ── FIN DU PROMPT ──
