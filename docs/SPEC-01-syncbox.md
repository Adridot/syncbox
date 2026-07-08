# Syncbox — Spécification fonctionnelle & technique (Phase 1/2)

> **Objet.** Reverse-engineering exhaustif de l'application **Syncbox** en vue d'une réécriture *à l'identique fonctionnellement, sans les défauts hérités*. Ce document décrit ce que l'app **fait** (observable), sépare l'**intentionnel** du **bug/dette**, et consigne les **décisions garder/retirer/changer** validées avec le propriétaire. Il est l'intrant de la Phase 2 (architecture & approche de dev — prompt séparé).
>
> **Méthode.** Lecture seule de l'intégralité du code (renderer Vue, Electron main, service Python, suite de tests, docs). Chaque affirmation pointe vers une preuve `fichier:ligne`. Les preuves détaillées par tranche vivent dans `docs/_analysis/` (16 fichiers, un par sous-système).
>
> **Registres** — pour éviter toute confusion, trois registres sont distingués partout :
> - *DOIT* / *FAIT* = comportement observable aujourd'hui ;
> - `[intentionnel]` vs `[bug]`/`[dette]` = nature du comportement ;
> - **Décision Dx** = ce qu'on veut dans la réécriture (voir §7).

---

## 0. Carte du dépôt & stack (P0)

**Trois couches**, un seul process Electron qui orchestre le tout :

| Couche | Emplacement | Rôle | Lignes |
|---|---|---|---|
| Renderer (UI) | `src/renderer/` | Vue 3 `<script setup>` + Pinia + TanStack vue-query + Tailwind 4 + vue-i18n | ~8 900 |
| Electron main | `electron/` | Spawn du service Python, pont IPC `window.desktop.*`, gestion Deemix, fenêtre | ~640 |
| Service | `service/app/` | FastAPI/uvicorn (Python ≥3.12), accès Rekordbox via pyrekordbox, SQLite app | ~11 300 |
| Tests | `service/tests/` | pytest — **contrat de comportement de référence** | ~4 500 |

**Points d'entrée** : renderer `src/renderer/main.ts` ; main `electron/main.ts` ; service `service/run_service.py` → `app.main:app`.

**Build** (`package.json:9-22`) : `electron-vite` (renderer+main+preload) + `PyInstaller --onedir` (service → binaire autonome) + `electron-builder` (DMG macOS). Le binaire Python est embarqué en `extraResources`, la DB seed copiée au 1er lancement.

**Dépendances externes incontournables** (toutes pilotées localement) :
- **pyrekordbox** (+ `sqlcipher3`) — lecture/écriture de `master.db` (SQLCipher).
- **mutagen** — lecture/écriture des tags audio.
- **rapidfuzz** — similarité title/artist (a remplacé `difflib`, cf. git `perf/phase-1-rapidfuzz`).
- **httpx** (+ `certifi`) — Spotify Web API, Deezer public API, Deemix local API.
- **Deemix Remastered** — app externe tierce, API locale `http://127.0.0.1:6595` (téléchargements Deezer via ARL). *N'est pas* un package Python ; pilotée en HTTP (`README.md:206`).
- **Spotify Web API** — OAuth + lecture playlists.

**État du dépôt** : `version 0.2.0` (`package.json:3`), mais `service/pyproject.toml:3` = `0.1.0` (skew, cf. D-tech). Build **non signé / non notarisé** (Gatekeeper bloque au 1er lancement). Auto-update electron-updater **présent mais dormant** (`publish:null`, `RBSYNC_ENABLE_UPDATES` requis — `DISTRIBUTION.md:119-126`).

---

## 1. Résumé exécutif

Syncbox est une app desktop macOS (à terme **macOS + Windows**, cf. §7-D2) qui maintient la collection **Rekordbox** d'un DJ en synchronisant des **playlists Spotify**, en **téléchargeant** les morceaux manquants via **Deezer/Deemix**, et en **entretenant la collection** (doublons, fichiers manquants, tags). Le principe directeur est la **sûreté** : aucune écriture dans `master.db` tant que Rekordbox tourne, un **backup horodaté avant chaque mutation**, des suppressions **réversibles** (soft-delete + restore), et **les fichiers ne sont jamais déplacés** (contrainte macOS TCC sur les dossiers cloud).

L'app expose ~9 écrans (Dashboard, My Library, Events, Download & Match, Duplicates, Missing Files, Untagged, Doctor, Settings) pilotés par un état Pinia (pas de routeur). Le service Python expose **~70 endpoints REST** + **un flux SSE** pour la progression des téléchargements. L'état applicatif (sources suivies, événements, jobs, réglages, tokens) vit dans **SQLite** ; Rekordbox est lu **une fois** en snapshot enrichi, mis en cache sur le mtime de `master.db`.

Le code a été construit par prompts successifs : il fonctionne mais porte de la dette caractéristique — une **migration vue-query inachevée** (double couche de données), un **fichier de configuration codé en dur sur la machine du développeur**, des heuristiques de nettoyage **personnalisées à une collection française**, une **double pile d'authentification Spotify** contradictoire, et une **reconstruction fragile du nom de fichier téléchargé** (source chronique de bugs « download bloqué »). Le cœur métier (sûreté Rekordbox, matching ISRC/fuzzy, dedup, soft-delete, résolution de chemins) est en revanche solide et **couvert par une suite de tests** qui en constitue le contrat de référence.

---

## 2. Inventaire fonctionnel (feature × écran × état × emplacement)

État : **OK** = complète · **½** = à moitié finie / partiellement câblée · **†** = morte/inutilisée dans son contexte.

### 2.1 Shell, navigation, dashboard
| Feature | Emplacement | État |
|---|---|---|
| Navigation 9 écrans sans routeur (état `ui.activeView`) | `stores/ui.ts:20,30-32`, `App.vue:58-66` | OK (Settings = `v-else` fourre-tout, cf. bug) |
| Lazy-loading des vues secondaires | `App.vue:8-17` | OK |
| Toasts (success/info/error, auto-dismiss 4/5/8 s) | `stores/ui.ts:13-46`, `ToastCenter.vue` | OK |
| Wrapper d'erreur global `withErrorToast`/`withLoading` | `stores/ui.ts:57-88` | OK (défauts, cf. §5) |
| Dashboard : 4 cartes + santé collection + statut système + events récents | `views/DashboardView.vue:84-272` | OK |
| Bandeau santé sidebar (API/Rekordbox/Deemix + chip téléchargements) | `components/AppShell.vue:98-159` | OK |
| i18n FR/EN (détection OS, persistance localStorage) | `i18n/index.ts:21-63` | OK |

### 2.2 My Library (sources Spotify permanentes)
| Feature | Emplacement | État |
|---|---|---|
| Master/détail des sources suivies | `views/LibraryView.vue:120-358`, `stores/library.ts` | OK |
| Suivre une playlist (modal Manage) + MyTags par défaut | `components/LibrarySetupModal.vue`, `stores/library.ts:141-166` | OK |
| Retirer une source suivie (RB tracks/tags conservés) | `stores/library.ts:117-136` | OK |
| Sync source / Sync all + auto-download des manquants | `stores/library.ts:86-115,228-241` | OK |
| Table de review (statuts new/matched/ready/imported/conflict/removed) | `components/TrackReviewTable.vue` | OK |
| Filtres actionable/ready/all, virtualisation | `TrackReviewTable.vue:27,81-82` | OK |
| Recherche Deezer → file de téléchargement (par track) | `stores/library.ts:286-326` | OK |
| Ignore/restore track | `stores/library.ts:328-356` | OK (restore→"new", bug) |
| Édition de tags en masse (barre basse) | `LibraryView.vue:288-336` | OK (sémantique union, bug) |
| Import vers Rekordbox (gated RB fermé) | `stores/library.ts:243-263` | OK |
| Accept-match / Assign-staged-file (table) | `TrackReviewTable.vue:278-296` | † en contexte Library (events-only) |
| Concept « tag rules » (table + repo séparés) | `stores/library.ts:23,56-60,272-284` ; `repositories/tags.py` | ½/† (vestigial → **D9 RETIRER**) |

### 2.3 Events (sets DJ temporaires)
| Feature | Emplacement | État |
|---|---|---|
| Création 3 modes : depuis playlist Spotify / vide / par lien | `components/EventCreatePanel.vue`, `stores/events.ts:128-221` | OK |
| Add-track au sein de l'event ouvert | `EventWorkspace.vue:51-72` | OK |
| Métriques (matched/ready/applied/missing/ambiguous) | `EventWorkspace.vue:141-152` | OK |
| Scan dossier staging | `stores/events.ts:240-257` | OK |
| Download Missing (retry manuel) | `stores/events.ts:293-304` | OK |
| Apply Ready Tracks (gated RB fermé) | `stores/events.ts:306-324` | OK |
| Delete event (aperçu + protégés conservés) | `stores/events.ts:326-355` | OK (pas de garde RB, bug) |
| Recherche Deezer + preview audio + queue | `components/DeezerSearchPanel.vue`, `stores/events.ts:412-450` | OK |
| **Live Import (M3U8)** — playlist sans écriture DB | `views/EventsView.vue:66-125`, `live_import.py` | OK → **D10 RETIRER** |

### 2.4 Hygiène de collection
| Feature | Emplacement | État |
|---|---|---|
| Duplicates : scan ISRC/fuzzy + slider similarité | `views/DuplicatesView.vue`, `queries/useDuplicates.ts`, `dedup.py` | OK |
| Keeper auto + override + résolution (relink memberships) | `dedup.py:161-172`, `adapter.py:1197-1279` | OK → **D5/D6 CHANGER** |
| Auto-resolve bulk des groupes ISRC ≥99 % | `useDuplicates.ts:185-202` | OK → **D5 RETIRER (bulk)** |
| « Not a duplicate » (dismiss persistant) | `dedup.py`, `repositories/dedup.py` | OK |
| Missing Files : scan + re-download (ISRC/search) + re-link + remove | `views/MissingFilesView.vue`, `maintenance.py`, `collection_acquisition.py` | OK |
| Untagged : diagnostic 4 catégories + tag/remove en masse | `views/UntaggedView.vue`, `adapter.untagged_report`, `maintenance.py` | OK → **D7 GARDER-MAIS-CORRIGER** |
| Script CLI `cleanup_rekordbox.py` (one-shot, manifeste) | `service/scripts/`, `maintenance.py` | OK → **D8 RETIRER** |

### 2.5 Config, système, sûreté
| Feature | Emplacement | État |
|---|---|---|
| Settings : langue, Spotify, Deemix/ARL, chemins, backup/restore | `views/SettingsView.vue`, `stores/settings.ts` | OK |
| Spotify : app-only (secret+username) **et** OAuth PKCE | `spotify.py` | OK → **D3 SIMPLIFIER (PKCE only)** |
| Deemix : statut/launch/install (~140 Mo dmg GitHub) + ARL | `electron/deemix.ts`, `acquisition.py:386-403` | OK → **D4 À-RESEARCHER** |
| Doctor : diagnostics + backups RB (liste/prune/restore) + logs | `views/DoctorView.vue`, `diagnostics.py`, `adapter.py:171-318` | OK |
| Download & Match Center : queue jobs + conflits + contexte event | `views/DownloadMatchCenterView.vue` | OK (barre de progression factice, cf. §5) |
| Backup & restore (settings JSON / all-data sqlite VACUUM) | `repositories/_base.py:24-80`, `main.py:181-241` | OK |

---

## 3. Spécification comportementale par domaine (le cœur à préserver)

> C'est la partie la plus précieuse : les **règles métier, invariants, ordres d'opérations, cas limites** qui doivent survivre quelle que soit la techno. Sauf mention contraire, tout ci-dessous est `[intentionnel]` et **couvert par un test** (cf. `service/tests/`).

### 3.1 Sûreté Rekordbox (NON NÉGOCIABLE)

1. **Blocage des mutations si Rekordbox tourne.** `assert_rekordbox_can_mutate()` lance `pgrep -fl "rekordbox|rekordboxAgent"`, re-filtre strictement (le chemin doit contenir `/rekordbox.app/`/`/rekordboxagent.app/` ou finir par `/rekordbox`/`/rekordboxagent`) et lève `RekordboxRunningError` si trouvé · `safety.py:20-80`, testé `test_safety.py:26-58`. **Toute écriture passe par cette garde.** Le message d'erreur est « amical » : ne contient ni PID, ni chemin `/Applications/`, ni flag `--type=` ; mentionne « Rekordbox » et « rekordboxAgent » (qui survit à la fermeture de la fenêtre).
2. **Unit-of-work `_mutate()`.** Ordre imposé : (a) assert mutation-ready (RB fermé + DB existe) → (b) **backup horodaté** → (c) ouvrir DB → (d) yield → (e) commit + **invalider le cache snapshot** ; sur exception : rollback + re-raise ; `finally` close · `adapter.py:505-534`.
3. **Backup avant chaque mutation.** Copie `master.db` (+ `-wal`/`-shm`) vers `…/_rekordbox_sync/backups/rekordbox-db-<timestamp>/` ; collision même-seconde → suffixe `-<n>` · `adapter.py:171-193`. **Rotation** : garde les N plus récents (défaut **15**, `0` = illimité) · `adapter.py:52,202-210`.
4. **Restore réversible.** `restore_backup` valide le nom (rejette vide/`/`/`\`/`.`/`..` et tout chemin hors racine backups), **snapshote la DB courante d'abord** (donc le restore est lui-même réversible → laisse 2 backups), efface WAL/SHM puis copie · `adapter.py:274-318`, testé `test_rekordbox.py:176-231,330-339`. **Exige RB fermé.**
5. **Suppressions = soft-delete.** `rb_local_deleted=1`, `rb_local_synced=0`, `rb_data_status=258`, `rb_local_data_status=0` · `content.py:350-356`. Réactivation : `256` au lieu de `258`, `rb_local_deleted=0` · `content.py:341-347`. **Ces entiers magiques sont load-bearing** (sémantique de sync Rekordbox 6/7) — à reproduire à l'identique sous peine de corrompre la sync de l'utilisateur · testé `test_rekordbox.py:385-450`. Toutes les lectures filtrent les lignes soft-deleted.
6. **Les fichiers ne sont jamais déplacés.** TCC macOS bloque les opérations de fichiers sur les dossiers cloud (Dropbox/iCloud) depuis le service ; l'apply référence les fichiers **en place** · `adapter.py:758-761`. La consolidation vers `rekordbox/Collection` est un script séparé (`migrate_collection.py`).
7. **Quirk Dropbox/TCC.** Le *listing* d'un dossier cloud échoue, mais `Path.exists()` sur un chemin précis fonctionne ; **tout le file-matching est bâti autour de `Path.exists()`** et d'un `fresh=True` qui bypasse le cache · testé `test_event_import.py:344-390`, `test_audio.py:68-90`.

### 3.2 Résolution de chemins Rekordbox (load-bearing)

- **Règle de relativisation** : un fichier **sous `<storage_root>/rekordbox/…`** est stocké **volume-relatif** (`/<NomVolume>/…`, le nom du volume = basename de `storage_root`) ; **tout le reste** (staging d'event sous `_rekordbox_sync/events/`, permanent, importé d'un device, ou pas de storage_root) est stocké en **absolu** — sinon Rekordbox affiche « file could not be found » · `paths.py:58-74`, `content.py:294-297`, `adapter.py:1318-1321`, testé `test_rekordbox.py:49-58,493-516`. *(Cf. mémoire projet « rekordbox-path-resolution ».)*
- **Égalité de chemins** : volume-relatif et absolu sont traités comme **égaux et hash-égaux** ; `path_lookup_keys` émet les formes raw / volume-résolu / expanduser / `.resolve()` / volume-relatif pour qu'un chemin absolu de staging matche une ligne DB volume-relative · `paths.py:138-174`, testé `test_rekordbox.py:342-382`.

### 3.3 Matching Spotify → Rekordbox

- **Ordre** : ISRC exact **d'abord**, puis fuzzy · `matching.py:83-85`.
- **ISRC** : comparé en majuscules ; match → `confidence=100`, `method="isrc"`, `status="matched"`. **Garde de collision** : un match ISRC est **rejeté seulement si** `|Δdurée| > 15000 ms` **ET** similarité de titre `< 82` ; donc un même-titre/durée-différente reste matché (autre edit), et une durée manquante (`0`/`None`) fait confiance à l'ISRC aveuglément · `matching.py:64-101`, testé `test_matching.py:9-116`.
- **Fuzzy** : `confidence = title*0.52 + artist*0.36 + duration*0.12`, arrondi ; seuil défaut `minimum_confidence=82` ; en dessous → `status="missing"`, `confidence=0` · `matching.py:109-120`.
- **Ambiguïté** : si `(best − second) < 6` → `status="ambiguous"` (retourne quand même le meilleur `content_id`, mais flag pour revue manuelle) · `matching.py:124-132`.
- **Buckets de durée** : ≤1500 ms→100, ≤5000→80, ≤12000→55, sinon 0 · `matching.py:47-57`.
- **Normalisation (côté matching)** : NFKD→ASCII (accents tombés), minuscule, parenthèses/crochets retirés, `&`→`and`, non-alphanumérique→espace ; similarité `fuzz.token_sort_ratio` (insensible à l'ordre des mots) · `matching.py:27-44`.
- ⚠️ **Deux normalisations divergentes** coexistent (matching vs dedup) — cf. §5 [dette] et **D19 SIMPLIFIER**.

### 3.4 Détection de doublons (dedup)

- **Stratégies** sélectionnées par l'appelant (`isrc` et/ou `fuzzy`) · `dedup.py:238-249`.
- **ISRC** : bucket par ISRC strip+upper (vide ignoré). Confiance : tous-ISRC + titres cohérents → **99** ; tous-ISRC + titres divergents → **60 + note d'avertissement** (mauvais ISRC partagé) ; fuzzy → **80** · `dedup.py:302-315`, testé `test_dedup.py:48-73`. Les groupes 60 sont **exclus du bulk** et flaggés à l'UI.
- **Fuzzy** : seuil défaut `0.87`, tolérance durée 2000 ms ; si une durée est inconnue le seuil monte à `max(seuil, 0.93)` ; signature = `artist_normalisé + " " + title_normalisé` · `dedup.py:106-107,210-271`. Bucketing par durée (taille `max(tol,1000)`, compare bucket + voisin droit) ; tracks sans durée comparés à **tous** (O(n²), cf. §5).
- **Normalisation (côté dedup)** : map de ligatures (`œ`→`oe`, `ø`, `ß`…), strip `feat.`, drop parenthèses « bruit » sélectif, `&`→`and` · `dedup.py:67-115`, testé `test_dedup.py:33-42`.
- **Clé de groupe** (et clé de dismiss) = set trié unique des contentIds joint par `|` (indépendant de l'ordre) · `dedup.py:201-203`. Groupes <2 membres droppés ; groupes dismissed droppés. Tri : confiance desc puis taille desc ; intra-groupe : keeper d'abord puis `qualityScore` desc · `dedup.py:318-334`.
- **« Not a duplicate »** persisté dans `dedup_dismissed(group_key)`, insert idempotent · `repositories/dedup.py:20-31`.
- **Choix du keeper (AUJOURD'HUI)** : `max` par `quality_score` puis date la plus **ancienne** puis contentId. `quality_score` est une **somme pondérée** : lossless +300, bitRate/10, sampleRate/1000, bitDepth×5, fileSize/1 Mo, analysed +50, bpm>0 +20, cueCount×10, playlistCount×15, tagCount×8, rating×5, **protected +500**, **fileMissing −1000** · `dedup.py:125-172`. ⚠️ La somme ne garantit pas l'ordre documenté « lossless > cues > permanent » : un gros fichier ou beaucoup de playlists peuvent dominer (cf. §5 [bug]). → **D6 : remplacer par une échelle de priorité explicite, sans préférence lossless (qualité = bitrate)**.
- **Plan de résolution / sûreté fichiers** : jamais supprimer le keeper ; suppression de fichier seulement si `allow_file_delete` ET pas fileMissing ET pas protégé (sinon `skipped_protected`) ET a un `filePath` · `dedup.py:402-412`. **Ordre de résolution** : relink memberships → soft-delete losers (dans la txn) → **supprimer fichiers seulement APRÈS commit réussi** · `adapter.py:1254-1277`. Le relink réaffecte playlists+MyTags du loser vers le keeper (si déjà membre, soft-delete la ligne de membership) · `adapter.py:1349-1395`.

### 3.5 Acquisition / téléchargement (Deezer + Deemix)

- **Trois scopes de jobs** : `event` / `library` / `collection` (re-download de fichier manquant), unifiés dans une liste globale et le flux SSE · `repositories/acquisition.py:260-384`.
- **Statuts** (event/library) : `pending → resolved → queued → downloading → downloaded → ready`, plus `acquisition_failed`, `acquisition_ambiguous` · `acquisition.py:599,767-784`. Collection : idem sans `ambiguous`.
- **Résolution Deezer** : ISRC d'abord (`GET /track/isrc:{isrc}` → confiance 100, method `isrc`) ; sinon recherche métadonnée. Deux requêtes tentées (`artist:"X" track:"Y"` puis `X Y`, limit 10) ; meilleur score gagne. Pondération : `title 0.55 + artist 0.35 + duration 0.10`. **Seuils** : ≥85 → résolu ; 70–85 → **ambigu (revue manuelle)** ; <70 → échec · `acquisition.py:32-33,268-349`, testé `test_acquisition.py:250-308`.
- **Pilotage Deemix** (API locale `:6595`) : `POST /api/auth/login {arl}`, `POST /api/settings` (downloadPath, `quality=MP3_320`, dossiers plats, `overwriteFiles:"rename"`, template `%artist% - %title%`), `POST /api/download/batch {trackIds, playlistName}`, `GET /api/queue` · `acquisition.py:164-202,834-849`. Retry 3× backoff 0.5→4 s ±jitter sur erreurs transport + {429,500,502,503,504}.
- **ARL appliqué une fois par process** (`_applied_arl` global) ; statut Deemix mis en cache 25 s ; 429 → garde le dernier état authentifié connu · `acquisition.py:103-162,386-403`.
- **`downloaded → ready` exige un scan dossier + fichier localisé sur disque** (`mark_ready_tracks_after_scan` / `find_downloaded_file`+relink) · `acquisition.py:624-625`, `collection_acquisition.py:170-189`.
- **Re-download de collection + relink** : résout (ISRC), télécharge dans le dossier **permanent**, puis **re-link la ligne Rekordbox existante** (préserve cues/tags/playlists) ; si le relink échoue (RB ouvert) le job reste `downloaded` et est retenté plus tard (le fichier est gardé) · `collection_acquisition.py:31-191`, testé `test_collection_acquisition.py:86-128`.
- **Réconciliation idempotente** : un track `ready` avec fichier force son job à `ready` ; un job `ready` dont le fichier a disparu repasse `acquisition_failed` (« Downloaded file is missing… ») · `acquisition.py:701-719`. La recreation d'un job n'est permise que si absent ou statut ∈ {pending, failed, ambiguous} ; les jobs en vol et `ready` ne sont jamais re-résolus · `acquisition.py:781-784`.
- ⚠️ **Localisation du fichier téléchargé = reconstruction manuelle du nom Deemix** (`%artist% - %title%`, gestion des caractères illégaux→`_`, dash-suffixe→parenthèses, point final retiré, suffixes `(1)`, préfixes `001/002/003`…) · `audio.py:58-195`. C'est la **source chronique de bugs** « download bloqué » → **D18 CHANGER** (lire le vrai chemin de sortie depuis le downloader).

### 3.6 Sync de bibliothèque (sources permanentes)

- **Diffing & transitions de statut** par track lors d'un sync · `library.py:45-263` :
  - Doublon de track Spotify dans une même playlist → `ignored` (1re occurrence traitée) ;
  - `ignored`/`ready` existants : reportés tels quels (jamais re-matchés) ;
  - `imported`/`matched` : **réconciliés** (re-vérifie le lien RB) ;
  - match frais : `matched`→`matched`, `ambiguous`→**`conflict`**, sinon→`new` (sauf si l'existant était `missing` → conservé) ;
  - track absent de la playlist active → `removed_from_source` (idempotent).
- **Tags par défaut** : `new`/`conflict`/`matched` héritent de `source.tags` ; les reportés gardent leurs tags · `library.py:164-191`.
- **Snapshot Spotify** : `snapshot_id` stocké sur la source ; sert à détecter les changements et compter `removedTracks` · testé `test_library.py:36-74`.
- **Téléchargement** : éligibles = statut ∈ {new, missing} ET pas de job actif (resolved/queued/downloading/downloaded/ready) ; si Deemix indispo → tous en `acquisition_failed` ; qualité **MP3_320 codée en dur** ; dossier de sortie = **permanent** · `library.py:400-549`.
- **Apply vers Rekordbox** : seuls les statuts `matched`/`ready` sont importés/taggés (sinon 409) ; retourne `{imported, tagged, warnings}` · `adapter.py:918-973`, `main.py:715-722`. **Les MyTags de la bibliothèque doivent pré-exister** (lève en listant les manquants, pas d'auto-création — contrairement à events/untagged) · `adapter.py:938-945`.
- **Retirer une source** : arrête le suivi seulement ; les tracks RB importés et leurs MyTags sont **conservés** · `repositories/library.py:148-159`.

### 3.7 Événements (sets DJ temporaires)

- **3 modes de création** : depuis playlist Spotify / vide / par lien. L'event scaffold crée toujours un **dossier unique** (slug collision → `-2`, `-3`…) via `mkdir(exist_ok=False)` atomique · `event_import.py:43-128`, `live_import.py:30-39`.
- **`default_tag` = le nom de l'event** (MyTag auto à l'apply, catégorie **« Situation »**) ; event manuel → `spotify_playlist_id = "manual:<slug>"` (ne matchera jamais une source permanente) · `event_import.py:54,116-122`.
- **Matching event ≠ library** : `ambiguous`→`ambiguous` (pas `conflict`), pas de tags par défaut · `event_import.py:190-227` (→ **D-tech : unifier le vocabulaire**).
- **Staging / claim de fichiers** : un fichier déjà claim ne peut être partagé qu'entre deux tracks de **même ISRC non vide** (vrai doublon listé 2×) ; deux tracks distincts ne partagent jamais un fichier · `event_import.py:305-345`, testé `test_event_import.py:524-642`. Auto-match métadonnée à `minimum_confidence=85`.
- **Apply event** (`adapter.apply_event_import`) : résout/importe les tracks `matched`/`ready`, assigne le MyTag d'event, **crée/répare un smart playlist** sous un dossier « Event Imports » (placé seq 1), restaure le XML ; retourne `{imported, tagged, smart_playlist}` · `adapter.py:793-849`. Statut event après apply : `applied` si plus aucun matched/ready/missing/ambiguous, sinon `partially_applied`.
- **Delete event** : aperçu read-only (marche RB ouvert) puis suppression. **Protection** : un contenu taggé est protégé (non supprimé) s'il porte **un autre MyTag non-event** OU si son chemin est sous permanent/manual_collection ; seuls les contenus *uniquement-event* et non-protégés sont soft-deleted · `content.py:431-442`, `adapter.py:851-916`. Nettoyage du playlist par nom courant **et** legacy `"<name> - Smart"`. ⚠️ L'aperçu doit être lu **dans** la session de mutation (lire `.Title` après commit lève « instance not bound to a Session » — régression historique qui transformait toute suppression en 409, testé `test_rekordbox.py:61-122`).
- **Smart playlist** : `SmartList = "<playlistId>:<tagId>"` (opérateur 8 = « contains ») ; les IDs > 2³¹ sont convertis en **signé 32 bits** (`"2662450573"`→`"-1632516723"`) — load-bearing · `content.py:185-189`, testé `test_rekordbox.py:461-463`.
- **Écriture Rekordbox** : nouvelles lignes content/artist/playlist créées avec un **ID string** (pyrekordbox `generate_unused_id` renvoie un int, mais des PK int+string mélangées crashent SQLAlchemy au flush) ; `add_rekordbox_content` met `ID=MasterSongID=rb_file_id` ; self-heal d'un artiste soft-deleted à chaque apply (bug « artiste caché ») · `content.py:240-277`, `adapter.py:787-790`, testé `test_rekordbox.py:466-489`. Le `masterPlaylists6.xml` est snapshoté avant apply et réécrit après commit (pyrekordbox peut l'écraser).

### 3.8 Untagged & Missing Files

- **Untagged report** : liste les tracks `tagCount==0`, classés en 4 catégories triées **junk(0) < dup_of_tagged(1) < alt_version(2) < review(3)** puis artist, title · `adapter.py:561-647`, testé `test_rekordbox.py:854-873`. Classification (`maintenance.py`) :
  - **junk** : `folder_path` ne commençant pas par `/` (stub `spotify:track:`), artiste == `rekordbox` (samples démo), titre vide, + motifs **personnels/français** (`discours`, `psg`, `bereal`, `cash machine`, regex cue `(\d+s)`…) → **D7 : remplacer ces motifs par règles structurelles + configurables** ;
  - **dup_of_tagged** : même `song_key` qu'un track déjà taggé → tout le groupe supprimé ;
  - **alt_version** : garder une « base » (titre le plus propre), supprimer le reste ;
  - **review/unique_mainstream** : track unique sans équivalent taggé → garder.
- ⚠️ `song_key = (normalize_artist, normalize_title)` où **l'artiste ne garde que le 1er token** (« Daft Punk »→« Daft ») — sur-regroupe des artistes différents (cf. §5 [bug]).
- **Tag untagged** : applique/crée un MyTag (catégorie défaut « Genre ») ; backup d'abord.
- **Delete untagged** : **soft-delete** ; ⚠️ **n'applique PAS la garde protégé** (retourne `skipped_protected:0` codé en dur) → **D15 GARDER-MAIS-CORRIGER**.
- **Missing Files** : liste les lignes dont le fichier a disparu (`fileMissing`), triées artist/title · `adapter.py:1027-1068`. Actions par track : **re-download** (job collection, cf. §3.5), **re-link** (cherche un fichier sur disque, score ISRC→100 puis title/name ≥70, cap 8 candidats), **remove** (soft-delete). Le re-link préserve cues/tags/playlists · `adapter.py:1099-1195`.

### 3.9 Spotify (auth & lecture)

- **Deux modes coexistent AUJOURD'HUI** (→ **D3 : ne garder que PKCE**) :
  - **App-only (Client Credentials)** : `client_id`+`client_secret` → token bearer, catalogue/playlists **publiques** seulement, via `/users/{username}/playlists` ;
  - **User OAuth (Authorization Code + PKCE, S256)** : déverrouille privé/collaboratif/suivi, via `/me/playlists`. Scopes **lecture seule** (`playlist-read-private`, `playlist-read-collaborative`) — l'app n'écrit jamais vers Spotify.
- **Sélection de token** : `use_user_token=None` → user token si un compte est connecté, sinon app token · `spotify.py:317-340`. « Compte connecté » = `spotify_user_refresh_token` non vide.
- **Auth endpoint** conditionnelle : si `client_secret` présent → HTTP Basic (client confidentiel, refresh token stable) ; sinon PKCE public (refresh token rotatif). Sur refresh, un `refresh_token` absent de la réponse est **préservé** · `spotify.py:485-513`.
- **Retry HTTP** (4 tentatives) : 429 → sleep `Retry-After + attempt` ; 401 → force refresh une fois (seulement `attempt==0`) ; ≥400 → raise avec status_code ; 204 → `{}`.
- **404 = playlist privée/inaccessible** (Spotify renvoie 404, pas 403) → traduit en message actionnable « connectez votre compte » (HTTP 404, pas 401) · `spotify.py:215-234`, `main.py:123-129`, testé `test_main_routing.py:16-60`.
- **Redirect URI** : forcé au callback local du service, ignore la valeur client · `main.py:850-872`. ⚠️ Le callback documenté est `http://127.0.0.1:8765/...` (port fixe) alors que « le port n'est pas un réglage, Electron le choisit » — contradiction (§5).

### 3.10 Réglages, persistance, backup/restore

- **Settings** persistés en **SQLite** (`settings(key,value)`), exposés via `GET/POST /api/settings`. **Jamais re-sauvés au démarrage** (les défauts ne sont appliqués qu'à la lecture, pour ne pas blanchir les credentials) · `main.py:136-138`. **Protection blank** : un POST avec champ credential vide **préserve** la valeur stockée (`spotify_client_id/secret/username`, `deemix_arl`) · `repositories/settings.py:103-137`, testé `test_db.py:25-55`. ⚠️ Les **chemins** ne sont PAS blank-protégés (un save partiel peut les effacer — §5).
- **Miroir electron-store** : `electron/settings-store.ts` garde une copie JSON durable de 9 champs, lue instantanément au boot. **Réconciliation** : 1er lancement → *pull* depuis le service (migration) ; ensuite → *push* electron-store→service. `settings:set` n'écrit **pas** dans le service (le renderer est censé avoir déjà POST) · `main.ts:80-105,239-246`. → **D-tech : source de vérité unique** (cf. §10).
- **Export/import settings** (JSON, type `syncbox-settings`) : exclut l'état OAuth transitoire, **inclut** les tokens Spotify · `repositories/settings.py:16-57`, testé `test_data_backup.py`. **Export/import all-data** : `VACUUM INTO` (1 fichier cohérent), validé (doit contenir une table `settings`), **backup de sécurité avant remplacement** · `repositories/_base.py:24-69`.

---

## 4. Carte technique & contrats internes

### 4.1 IPC renderer ↔ main (`window.desktop.*`, preload `electron/preload.ts`)

| Canal | Args | Retour | Source |
|---|---|---|---|
| `app:get-api-base-url` | — | `string` (base URL service) | `main.ts:231` |
| `settings:get` | — | `AppConfig` (9 champs) | `main.ts:234-238` |
| `settings:set` | `Partial<AppConfig>` | `AppConfig` | `main.ts:239-246` |
| `settings:reload` | — | `AppConfig` | `main.ts:247-256` |
| `app:open-external` | `url` (http/https only) | `void` | `main.ts:257-263` |
| `app:open-path` | `path` (absolu only) | `void` | `main.ts:264-272` |
| `app:open-logs` | — | `string` (dir logs) | `main.ts:273-278` |
| `deemix:status` | — | `{installed, running, appPath, port}` | `main.ts:281` |
| `deemix:launch` | — | `DeemixStatus` | `main.ts:282-287` |
| `deemix:install` | — | `DeemixStatus` | `main.ts:288-296` |
| `deemix:progress` (push) | — | `{stage, percent\|null}` | `main.ts:291-293` |

**`AppConfig`** (camelCase, electron-store + wire `/api/settings`) : `spotifyClientId, spotifyClientSecret, spotifyUsername, rekordboxDatabaseDir, storageRoot, permanentPath, manualCollectionPath, deemixArl` (string) + `backupRetention` (number) · `settings-store.ts:15-25`.

### 4.2 Spawn main → service

- Dev : `uv run uvicorn app.main:app` ; packagé : binaire PyInstaller `process.resourcesPath/syncbox-service/syncbox-service` · `main.ts:131-189`.
- **Env passé** : `RBSYNC_DATA_DIR` (=userData), `RBSYNC_SERVICE_PORT` (défaut 8765), `RBSYNC_APP_VERSION` (=`app.getVersion()`), `RBSYNC_LOG_DIR` · `main.ts:138-146`.
- `waitForService` poll `GET /api/health` toutes les 500 ms jusqu'à 30 s ; timeout → continue silencieusement (pas de signal de dégradation au renderer — §5).
- Tué par **SIGTERM** seul sur `before-quit` (pas de SIGKILL fallback — §5).
- Autres env service : `RBSYNC_REKORDBOX_DATABASE_DIR`, `RBSYNC_STORAGE_ROOT`, `RBSYNC_LOG_LEVEL`, `RBSYNC_SERVICE_HOST`, `RBSYNC_EXTERNAL_SERVICE=1` (escape hatch dev) · `config.py:36-46`, `run_service.py`.

### 4.3 HTTP renderer ↔ service (~70 endpoints, base `/api`)

Port `config.api_port` ; CORS limité aux origines loopback (`http://(127.0.0.1|localhost):\d+`, `allow_credentials=False`) ; `lifespan` : `database.migrate()` + `ensure_deemix_authenticated` au startup · `main.py:132-158`. Mapping d'erreurs **par route** (try/except → HTTPException) ; **RB-running / conflit → 409** partout (restore/resolve/remove/relink/redownload/tag/delete/apply).

Table maîtresse (méthode · chemin · → réponse · délégué) — extrait représentatif, table complète dans `docs/_analysis/07_S1.md` :

| Domaine | Endpoints clés |
|---|---|
| Système | `GET /health`, `GET /rekordbox/status`, `GET /rekordbox/collection-stats`, `GET /diagnostics` |
| Settings/data | `GET·POST /settings`, `GET /settings/export`·`POST /settings/import`, `GET /data/export` (FileResponse sqlite)·`POST /data/import` (octet-stream) |
| Backups | `GET /rekordbox/backups`, `POST /rekordbox/backups/prune`, `POST /rekordbox/backups/{name}/restore` |
| Doublons | `GET /rekordbox/duplicates?strategies=&fuzzyThreshold=` (clampé 0.5–1.0, défaut 0.87), `POST /rekordbox/duplicates/resolve` |
| Missing | `GET /rekordbox/missing`, `POST …/{cid}/remove`, `GET …/{cid}/relink-candidates`, `POST …/{cid}/relink`, `POST …/{cid}/redownload` |
| Untagged | `GET /rekordbox/untagged`, `POST …/tag`, `POST …/delete` |
| Storage | `POST /storage/ensure`, `GET /storage/layout`, `GET /storage/validate-path?path=` |
| Library | `GET·POST /library/sources`, `DELETE …/{id}`, `POST …/{id}/sync`, `POST …/sync-all`, `GET …/{id}/review`, `POST /library/tracks/update`, `POST /library/tracks/download`, `GET /library/search-deezer`, `POST …/{id}/tracks/{tid}/queue-deezer`, `POST …/{id}/apply` |
| Rekordbox tags | `GET /rekordbox/tags` |
| Deemix | `GET /providers/deemix/status`, `POST /providers/deemix/login` |
| Acquisition | `GET /acquisition/jobs?scope=&status=&source=`, `DELETE /acquisition/jobs/clear?scope=`, **`GET /acquisition/stream` (SSE)** |
| Spotify | `POST /spotify/test`, `GET /spotify/status`, `POST /spotify/auth-url`, `POST /spotify/disconnect`, `GET /spotify/callback`, `GET /spotify/playlists?limit=&offset=` |
| Events | `GET /events`, `POST /events/spotify/analyze`, `POST /events`, `POST …/{id}/tracks/spotify`, `GET …/{id}/review`, `GET …/{id}/delete-preview`, `POST …/{id}/delete`, `POST …/{id}/staging/scan`, `POST …/{id}/acquisition/auto`, `GET …/{id}/acquisition/jobs`, `POST …/{id}/matches`, `POST …/{id}/apply`, `GET …/{id}/search-deezer`, `POST …/{id}/tracks/{tid}/queue-deezer` |
| Live import | `POST /live-imports` → **D10 RETIRER** |

### 4.4 SSE — `GET /api/acquisition/stream` · `main.py:802-837`

- `Content-Type: text/event-stream` ; headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- Événement : `event: jobs\ndata: <json>\n\n` où `<json>` = tableau de `GlobalAcquisitionJob.model_dump(by_alias=True)`. Keepalive `: keepalive\n\n` quand inchangé. **Tick = 4 s** (`ACQUISITION_STREAM_INTERVAL_S`). Sort sur `request.is_disconnected()` ; erreurs de refresh n'interrompent pas le flux (réémet le dernier payload ou `"[]"`).
- ⚠️ Le client (`useAcquisitionStream.ts`) parse sans validation de schéma, reconnect fixe 3 s sans jitter, et **écrit seulement dans le store `events`** (le store `library` a sa propre copie non alimentée par SSE — §5).

### 4.5 APIs externes

- **Spotify** : `accounts.spotify.com` (token/authorize), `api.spotify.com/v1` (playlists/tracks/search).
- **Deezer public** : `api.deezer.com` — `GET /track/isrc:{isrc}`, `/track/{id}`, `/search?q=&limit=`.
- **Deemix Remastered** : `127.0.0.1:6595` — health/auth/settings/download.batch/queue (cf. §3.5).

### 4.6 Schéma SQLite app (`repositories/_base.py:84-313`)

Tables : `settings(key,value)` · `tag_rules` *(legacy → **D9**)* · `spotify_tracks` · `rekordbox_tracks` · `track_links` · `event_playlists` *(distinct d'`event_imports`, possiblement mort)* · `event_imports` · `event_import_tracks` (FK CASCADE, UNIQUE(event,track)) · `event_staging_files` · `event_acquisition_jobs` · `schema_migrations` · `library_sources` (UNIQUE spotify_playlist_id) · `library_source_runs` · `library_tracks` (+ ALTER `pending_deezer_track_id`, `pending_deezer_isrc`) · `library_acquisition_jobs` · `dedup_dismissed(group_key)` · `collection_acquisition_jobs`. Les 3 tables de jobs partagent une forme quasi identique (clé d'unicité `(fk, spotify_track_id, provider)` ou `(content_id, provider)`).

⚠️ **Migration non versionnée au-delà de v1** : `CREATE TABLE IF NOT EXISTS` + ALTER ad-hoc via `PRAGMA table_info`, `schema_migrations` ne contient que la v1 ; et **le seed `tag_rules → library_sources` re-tourne à CHAQUE `migrate()`** (donc à chaque boot), écrasant les éditions utilisateur (§5).

### 4.7 Modèles de payload (pydantic, `models.py`)

~50 modèles, alias camelCase. Familles : `AppSettings`, `SettingsBackup`, `StorageLayout`, `RekordboxStatus`/`…CollectionStats`, `RekordboxBackup(s)`/`BackupPrune/Restore`, `Diagnostic(s)`, `Duplicate(Track/Group/ScanResult/Resolution…)`, `Missing(Track/Report/Relink/Action)`, `Untagged(Track/Report/Tag/Delete)`, `Spotify(Connection/AuthUrl/Playlist…)`, `Library(Source/TrackReview/Review/Download/Apply)`, `Event(Review/TrackReview/Apply/Delete/Acquisition/Summary)`, `AcquisitionJob`/`GlobalAcquisitionJob`, `LiveImport*`, `SpotifyTrack`, `RekordboxTrack`, `ProposalType`. Détail exhaustif des champs : `docs/_analysis/13_S7.md`.

> **Note `ProposalType`** (`models.py:504`) énumère `add_to_rekordbox | add_to_spotify | remove_from_rekordbox | remove_from_spotify | manual_match | protect_manual_track`. Les variantes `*_to_spotify` sont **mortes** (scopes Spotify en lecture seule). Les « proposals » documentés dans le README ne sont **pas** matérialisés par une table dédiée (pas de `repositories/proposals.py` ; concept dilué dans library/acquisition) — cf. §5 docs-vs-code.

---

## 5. Catalogue des défauts (ce qu'il NE FAUT PAS reproduire)

`bug` = comportement incorrect · `fragile` = race/erreur non gérée/hypothèse cachée · `dette` = incohérence/duplication · `inachevé` = à moitié fait.

### 5.1 Correctness (bugs avérés — priorité haute)

| # | Type | Symptôme · `fichier:ligne` · cause · impact |
|---|---|---|
| B1 | bug | **Re-download collection prend le 1er hit Deezer sans seuil** et l'auto-relink sur une vraie ligne de collection · `collection_acquisition.py:60-62` · `results[0]` quand ISRC échoue · le mauvais audio remplace la référence d'un track existant (cues/playlists préservés mais pointant le mauvais fichier). → **D14** |
| B2 | bug | **`delete_untagged` ignore la protection** (`skipped_protected:0` codé en dur) · `adapter.py:716-723` · un track permanent/manual peut être soft-deleted sans garde. → **D15** |
| B3 | bug | **Batch « remove tag » peut AJOUTER le tag à d'autres tracks sélectionnés** · `LibraryView.vue:84-116`, `library.ts:180-193` · `selectedTagNames` = union, et l'update écrase les tags de chaque track sélectionné avec l'union. → **D16** |
| B4 | bug | **Seed `library_sources` re-tourne à chaque `migrate()`** et force-upsert name/tags/enabled depuis `tag_rules` · `_base.py:339-371` · les éditions utilisateur (renommage/tags/disable) sont **révertées au prochain boot**. → **D9** |
| B5 | bug | **`song_key` ne garde que le 1er token d'artiste** · `maintenance.py:89-93` · conflate « David Bowie » et « David Guetta » ; risque de classer/supprimer un titre légitimement différent. → **D7** |
| B6 | bug | **ISRC fallback sur le tag `barcode`** · `audio.py:35` · un code-barres (UPC/EAN) est stocké comme « ISRC », polluant tout le matching ISRC. → **D20** |
| B7 | bug | **`feat.*$` greedy sur texte minusculé** · `maintenance.py:83` · « Defeat », « Feather » tronqués → clé de chanson corrompue. → **D7** |
| B8 | bug | **Apply affiché en rouge « error » dès qu'il y a des warnings**, même sur succès · `events.ts:315-322`, `library.ts:254-261` · ton dérivé du seul `warnings.length`. → **D17** |
| B9 | bug | **`restore (unignore)` remet le statut à `new`** · `library.ts:343-356` · un track matched/ready avant ignore revient « new » → re-résolution/re-download forcés. |
| B10 | bug | **Confirm dedup peut promettre l'inverse de l'action** · `DuplicatesView.vue:34-44` vs `useDuplicates.ts:128` · le texte calcule l'éligibilité de suppression mais le payload envoie le flag brut. |
| B11 | bug | **Suppression d'événement mutile la collection sans garde `mutationAllowed`** · `EventWorkspace.vue:128-136`, `events.ts:326-355` · peut tenter une écriture RB ouvert. |
| B12 | bug | **Champ `importForm.eventName` partagé** entre le formulaire create-from-playlist et le live-import · `EventsView.vue:93-94` · taper dans l'un pollue l'autre. *(Résolu par **D10** qui supprime le live import.)* |

### 5.2 Fragile (races, erreurs avalées, hypothèses)

| # | Symptôme · `fichier:ligne` |
|---|---|
| F1 | **Localisation de fichier par reconstruction de nom** (préfixes `001-003`, copies `(1)-(7)`, dash→parenthèses…) · `audio.py:58-195` · chaque nouvel edge = un bug « download bloqué ». → **D18** |
| F2 | **Mapping download-id ↔ track par index de liste** · `acquisition.py:537-544`, `library.py:534-549` · suppose que Deemix renvoie les ids dans l'ordre 1:1 ; débordement → `download_id=None`. |
| F3 | **Globals process** (`_applied_arl`, `_STATUS_CACHE`, `_SCAN_CACHE`) + `downloadPath` Deemix mutée par batch · `acquisition.py:59,104-111,522-524` · races entre téléchargements concurrents (fichier dans le mauvais dossier). |
| F4 | **Parsing heuristique du payload Deemix** (`queue`/`items`/`downloads`, sous-chaînes de statut) · `acquisition.py:899-920` · un changement de version Deemix fige silencieusement les jobs en `queued`. |
| F5 | **SSE n'alimente que le store events** · `useAcquisitionStream.ts:49` vs `library.ts:24` · la liste de jobs de la vue Library cesse de se mettre à jour en live (poll suspendu pendant SSE). |
| F6 | **Double polling** : `useRefreshManager` (setInterval) + `useSystemStatusQuery` (vue-query) couvrent des données qui se chevauchent · `useRefreshManager.ts:49-98`, `useSystemStatusQuery.ts:24-34`. |
| F7 | **`parse` renvoie `null` typé `T`** sur corps non-JSON/vide/204 · `client.ts:417-422` · déréférencement null silencieux en aval. |
| F8 | **Reconnect SSE sans jitter/backoff** (fixe 3 s, seulement sur CLOSED) · `useAcquisitionStream.ts:55-63`. |
| F9 | **Échappement chemin/query incohérent** (`queueDeezerTrack`/`clearAcquisitionJobs` interpolent brut) · `client.ts:265,286,385`. |
| F10 | **Race d'événements** : `summaries`/`globalAcquisitionJobs` assignés AVANT la garde `requestedEventId` ; pas d'abort des fetchs en vol · `events.ts:78-79,97-98`. |
| F11 | **`find_relink_candidates` = `rglob("*")` non borné** sur 5 racines (lit les métadonnées de chaque fichier) · `adapter.py:1155-1193` · lent sur grosses libs cloud. |
| F12 | **Lectures sans retry** : `list_tags`, `content_meta`, `preview_event_delete` ouvrent la DB hors `_read_rekordbox` · `adapter.py:542,861,1078` · peuvent échouer « database is locked » là où le snapshot retenterait. |
| F13 | **Service tué SIGTERM-only, sans timeout/SIGKILL** ; pas de redémarrage si crash · `main.ts:183-189` · binaire orphelin, port 8765 bloqué. |
| F14 | **Migration boot invisible si service down** : `settingsReady` résolu en `finally` → UI débloquée avec champs vides, migration silencieusement non faite · `main.ts:95-104`. |
| F15 | **Validation de chemin seulement sur permanent/manual (au blur)** ; rekordbox-dir et storage-root (les 2 plus critiques) **non validés** · `SettingsView.vue:339-352`. |
| F16 | **Barre de progression du Download Center factice** (largeur dérivée du ton, pas du % réel) · `DownloadMatchCenterView.vue:136-139`. |
| F17 | **Suppression audio = `unlink()` irréversible** (seule op non réversible ; la DB est backupée, pas l'audio) · `adapter.py:1270-1277`. → **D12** |

### 5.3 Dette (incohérences, duplication, hardcoding)

| # | Symptôme · `fichier:ligne` |
|---|---|
| T1 | **Chemins du dev codés en dur** : `DEFAULT_REKORDBOX_DIR=/Users/adriendidot/…`, `DEFAULT_STORAGE_ROOT=…/Dropbox-CloudOptionDJteam/Jockey Tricolore/Musique` · `config.py:15-19` ; idem `settings.ts:14-17` et `.env.example:3-4`. → **D1** |
| T2 | **Heuristiques junk personnalisées/françaises** · `maintenance.py:103-114`. → **D7** |
| T3 | **Deux normalisations divergentes** matching vs dedup · `matching.py:27-44` vs `dedup.py:67-115` · jugent « identique » différemment, double maintenance. → **D19** |
| T4 | **Double couche de données** (vue-query partielle + Pinia+HTTP manuel) = migration inachevée · git `phase-2a→2d` · 2 modèles de polling, source de vérité ambiguë. → §10 |
| T5 | **Double store de settings** (electron-store JSON + SQLite) avec réconciliation push/pull manuelle, `settings:set` ne push pas le service · `main.ts:80-105,239-246`. → §10 |
| T6 | **`tag_rules` (table+repo) vestigial** superseded par `source.tags` · `repositories/tags.py`, `library.ts:23`. → **D9** |
| T7 | **Vocabulaire matching divergent** library `conflict` vs event `ambiguous` pour le même phénomène ; row-builders quasi-dupliqués · `library.py` vs `event_import.py`. |
| T8 | **`delete_event_import` laisse le dossier/audio/`.m3u8` orphelins sur disque** · `events.py:63-80`. |
| T9 | **`formatBytes` sans palier Go** ; **`formatDate` suppose epoch secondes** alors que l'API renvoie surtout ISO/ms · `format.ts:16,21`. |
| T10 | **Strings codés en anglais** dans des dialogues `window.confirm` malgré l'i18n (delete source/event) · `library.ts:121-125`, `events.ts:333-340`. |
| T11 | **`backupRetention` sans contrôle UI dans Settings** (édité seulement via Doctor) · `settings.ts:20`. |
| T12 | **`.xml.bak-<ts>` jamais purgés** à chaque delete event · `adapter.py:1403-1404`. |
| T13 | **Version triple-source non synchronisée** : `package.json`=0.2.0, `pyproject.toml`=0.1.0, `version.py` · README prétend « single-source ». |
| T14 | **`StatusBadge` 6 tons, 2 utilisés** ; `body{min-width:980px}` + sidebar `md:hidden` contradictoires · `StatusBadge.vue`, `styles.css:61`, `AppShell.vue:37`. |
| T15 | **Docs-vs-code** : README cite `sync.py` et un repo `proposals` **inexistants** ; `migrate_collection.py`/`cleanup_rekordbox.py` à confirmer ; callback OAuth `:8765` fixe vs « port dynamique ». |

### 5.4 Inachevé

| # | Symptôme · `fichier:ligne` |
|---|---|
| I1 | **Auto-update electron-updater dormant** (`publish:null`, env requis) · `DISTRIBUTION.md:119-126`. → §7-D (retirer) |
| I2 | **Pas de route DELETE pour `tag-rules`** (CRUD incomplet) · `main.py:508-517`. *(résolu par D9)* |
| I3 | **`clearDownloads`/`globalJobStats`/`updateTrackTags`** exportés mais non câblés dans leur tranche · `events.ts:44-52,371-396`, `library.ts:195-209`. |
| I4 | **Re-download dans Missing Files se verrouille en « queued » à vie** (aucun signal de complétion ne revient à la vue) · `useMissing.ts:103-114`. |
| I5 | **Migration Pinia→vue-query partielle** : `useSystemStatusQuery` écrit dans le store en façade · `useSystemStatusQuery.ts:14-17,41-50`. |

---

## 6. Modèle de domaine & données (socle réutilisable)

Entités qui survivent quelle que soit la techno :

- **Source de bibliothèque** (`library_sources`) — playlist Spotify suivie *en permanence*. Attributs : `spotify_playlist_id` (identité), nom, `snapshot_id` (détection de changement), `tags` (MyTags par défaut), `enabled`, `status`. Cycle : `pending → synced` ; runs historisés (`library_source_runs`).
- **Track de bibliothèque** (`library_tracks`) — 1 ligne par (source, spotify_track_id). **Statuts** : `new → matched|conflict|ready|imported`, `missing`, `removed_from_source`, `ignored`, `acquisition_failed`. Porte le lien Rekordbox (`rekordbox_content_id`), `match_method`, `confidence`, `staging_file_path`, tags, `pending_deezer_*`.
- **Événement** (`event_imports`) — import temporaire (mariage, soirée). Attributs : nom, slug, `default_tag` (= nom, catégorie « Situation »), `spotify_playlist_id` (ou `manual:<slug>`), `event_dir`/`audio_dir`/`playlist_path`, `status` (`pending → applied|partially_applied`). Tracks (`event_import_tracks`, statuts `matched/ambiguous/missing/ready/applied/ignored`) + fichiers de staging (`event_staging_files`).
- **Job d'acquisition** — 3 scopes (`event`/`library`/`collection`), unifiés en `GlobalAcquisitionJob`. **Cycle de vie** : `pending → resolved → queued → downloading → downloaded → ready` ; échecs `acquisition_failed`/`acquisition_ambiguous`. Clé : (fk, spotify_track_id|content_id, provider). Provider = `deemix`.
- **Track Rekordbox** (snapshot, non persistant) — `content_id`, title, artist, isrc, durationMs, filePath, fileType, bitRate/sampleRate/bitDepth/fileSize, bpm, rating, analysed, cueCount, playlistCount, tagCount, `protected` (sous permanent/manual), `fileMissing`, dateCreated. Lu **une fois**, mis en cache sur `(mtime,size)` de `master.db(+wal)`.
- **MyTag** — système de tags Rekordbox (catégories → tags). Catégorie « Situation » pour les events, « Genre » par défaut pour library/untagged.
- **Groupe de doublons** — ≥2 contents = même enregistrement (ISRC) ou métadonnées proches (fuzzy), avec un *keeper* (à choisir). Identité de groupe = set trié de contentIds.
- **Dismiss dedup** (`dedup_dismissed`) — « pas un doublon », clé = set de contentIds.
- **Backup Rekordbox** — dossier horodaté sous `_rekordbox_sync/backups/`, contient `master.db(+wal/shm)`. Rotation N.
- **Réglages** (`settings` k/v) — credentials Spotify, ARL Deemix, 4 chemins, `backup_retention`, tokens OAuth.

**Identités de matching** : (1) **ISRC** (exact, prioritaire) ; (2) **fuzzy** (title/artist normalisés + compatibilité de durée, `rapidfuzz.token_sort_ratio`). Les deux exigent une **normalisation** unique (à unifier, D19).

**Storage layout** : `<storage_root>/rekordbox/{Collection, Collection manuelle}` (protégés) + `<storage_root>/_rekordbox_sync/{inbox, events, backups, manual_collection}`. App DB : `~/Library/Application Support/Syncbox/syncbox.sqlite3` (packagé).

---

## 7. Journal de décisions (garder / retirer / changer)

Taxonomie : `GARDER` · `GARDER-MAIS-CORRIGER` · `SIMPLIFIER` · `CHANGER` · `RETIRER` · `À-RESEARCHER` (Phase 2).

### 7.1 Décisions validées avec le propriétaire (P6)

| # | Sujet | Décision | Détail / justification |
|---|---|---|---|
| **D1** | Public cible | **CHANGER** | **Open-source / public**. Conséquences obligatoires : retirer tous les chemins perso (`config.py:15-19`, `settings.ts:14-17`, `.env.example`), tout rendre configurable, hygiène secrets/`.env`, licence. |
| **D2** | Plateforme | **CHANGER (élargir)** | **macOS + Windows**. Linux exclu (Rekordbox n'y tourne pas). Abstraire par OS : résolution de chemins, détection du process Rekordbox (pgrep → équivalent Windows), opérations fichiers, dossiers système (`~/Library` vs `%APPDATA%`), `hdiutil`/install Deemix. |
| **D3** | Auth Spotify | **SIMPLIFIER** | **OAuth PKCE uniquement**. Retirer le mode app-only (Client Secret + username, `/users/{username}/playlists`) et toute la logique Basic-vs-PKCE conditionnelle (`spotify.py:485-498`). Corrige aussi `connection_status` (B-spotify). |
| **D4** | Téléchargement / Deemix | **À-RESEARCHER (Phase 2)** | Objectif : « tout au même endroit, de la meilleure manière ». Étudier : **packager/embarquer** le downloader, ou **réimplémenter** l'acquisition Deezer nativement, au lieu de piloter une app Deemix externe sur `:6595`. Inclut la **dimension légale** (ARL/Deezer, licence GPL de Deemix) à documenter. Supprime de facto l'auto-install dmg non vérifié (`deemix.ts`). |
| **D5** | Doublons — automatisation | **CHANGER** | Garder le keeper **suggéré** mais **confirmation par groupe** ; **retirer le bulk 1-clic auto-resolve** (`useDuplicates.ts:185-202`). |
| **D6** | Choix du keeper | **CHANGER** | **Échelle de priorité explicite + raison affichée** (predictable, explicable). **Retirer la préférence lossless/FLAC** : la qualité se mesure par **bitrate** (FLAC pas toujours supporté par le matériel DJ). Remplace la somme pondérée `dedup.py:125-172`. |
| **D7** | Diagnostic Untagged | **GARDER-MAIS-CORRIGER** | Garder les **4 catégories** (junk / dup_of_tagged / alt_version / review). Remplacer le vocabulaire junk perso/français par des **règles structurelles universelles** (stub `spotify:track:`, titre vide, artiste `rekordbox`) **+ motifs configurables par l'utilisateur**. Corriger aussi B5 (artiste 1-token) et B7 (regex feat). |
| **D8** | Script CLI cleanup | **RETIRER** | `cleanup_rekordbox.py` supprimé — couvert par Duplicates + Untagged (avec backups/soft-delete). |
| **D9** | `tag_rules` (table héritée) | **RETIRER** | Supprimer la table/pont legacy (cause de B4). **Conserver le concept** : MyTags par défaut portés par la source (`source.tags`). |
| **D10** | Live Import M3U8 | **RETIRER** | Supprimer entièrement (`live_import.py`, UI live import, `POST /live-imports`). Toujours exiger Rekordbox fermé et écrire la collection directement. Élimine aussi B12. |
| **D11** | Suppression d'événement | **CHANGER** | **Toujours demander, avec aperçu exact** (tracks + fichiers qui seront supprimés). L'aperçu serveur existe déjà (`delete-preview`). |
| **D12** | Suppression de fichiers audio | **CHANGER** | **Corbeille OS** (macOS Trash / Windows Recycle Bin) au lieu d'`unlink()` (F17). Réversible via l'OS. S'applique à dedup et delete-event. |
| **D13** | i18n | **GARDER** | FR/EN conservés, fichiers de locale structurés pour ajout de langues. |

### 7.2 Décisions prises sans question (preuve sans ambiguïté — corrections de bugs)

| # | Sujet | Décision | Détail |
|---|---|---|---|
| **D14** | Re-download collection (top hit) | **GARDER-MAIS-CORRIGER** | Appliquer le seuil 70/85 + état `ambiguous` comme le flux event ; jamais d'auto-relink sous le seuil (B1). |
| **D15** | `delete_untagged` protection | **GARDER-MAIS-CORRIGER** | Appliquer la garde permanent/manual (skip + report réel) (B2). |
| **D16** | Tags en masse | **GARDER-MAIS-CORRIGER** | Sémantique **add/remove par delta**, jamais d'écrasement par union (B3). |
| **D17** | Apply avec warnings | **GARDER-MAIS-CORRIGER** | État distinct « appliqué avec avertissements » (pas rouge/erreur) (B8). |
| **D18** | Localisation du téléchargement | **CHANGER** | **Lire le vrai chemin de sortie** depuis le downloader ; locator par reconstruction seulement en fallback (F1). |
| **D19** | Normalisation matching/dedup | **SIMPLIFIER** | **Une seule pipeline** de normalisation partagée (ligatures, feat, parenthèses), testée (T3). |
| **D20** | ISRC fallback barcode | **RETIRER** | Ne jamais utiliser le tag `barcode` comme ISRC ; absent → `None` (B6). |
| **D21** | Réversibilité globale | **GARDER** | Conserver soft-delete + backups + restore Doctor ; **étendre** à la corbeille fichiers (D12). |
| **D22** | Restore `unignore` | **GARDER-MAIS-CORRIGER** | Restaurer le statut antérieur, pas « new » (B9). |
| **D23** | Garde RB sur delete event | **GARDER-MAIS-CORRIGER** | Gater la suppression sur `mutationAllowed` comme l'apply (B11). |
| **D24** | Auto-update | **RETIRER** | Supprimer le scaffolding electron-updater dormant (cohérent avec la mémoire « no auto build/release ») (I1). |
| **D25** | Tables/champs morts | **RETIRER** | `event_playlists` (legacy), `ProposalType.*_to_spotify`, tons `StatusBadge` inutilisés, branche responsive `md:hidden` — après confirmation d'absence de consommateur. |

---

## 8. UI/UX — état des lieux + pistes ouvertes

> **L'UI/UX est un sujet OUVERT** (règle d'or 5). Tout ci-dessous est *l'existant* + des *hypothèses à challenger en phase design*, pas des contraintes.

### 8.1 État des lieux

- **9 écrans, navigation par état Pinia** (`ui.activeView`), pas de routeur, pas de deep-link, pas de back navigateur, pas de persistance de l'écran courant entre lancements. Settings est le `v-else` fourre-tout (un `activeView` invalide y atterrit silencieusement).
- **Sidebar** : 7 items primaires + Doctor/Settings en bas + bandeau santé (API/Rekordbox/Deemix + chip téléchargements). Fenêtre non redimensionnable sous 980 px, scroll par panneau.
- **Deux composants partagés** : `TrackReviewTable` (filtres, virtualisation, ignore/restore) et `DeezerSearchPanel` (covers + preview 30 s) entre Library et Events.
- **Incohérences UI relevées** : compteurs téléchargements divergents sidebar vs dashboard ; condition « Deemix prêt » différente (sidebar `available` seul vs dashboard `available && authenticated`) ; tons de statut event divergents carte vs workspace ; barre de progression factice ; sélection cross-filtre dans Untagged pouvant agir sur des lignes cachées.

### 8.2 Pistes ouvertes (à valider en design, NON tranchées)

- **Piste A — conserver 9 écrans + navigation par état**, mais : persister l'écran courant, remplacer le `v-else` Settings par un défaut explicite, dériver tous les compteurs santé d'un seul sélecteur canonique.
- **Piste B — regrouper par tâche** : fusionner « Download & Match », « Missing » et la partie acquisition de Library/Events en **un seul centre d'acquisition** (les jobs sont déjà unifiés côté données) ; regrouper Duplicates/Untagged/Missing sous un **hub « Santé de collection »** (Doctor).
- **Piste C — flux guidés** : un parcours « onboarding » (connecter Spotify → Deemix → chemins → Doctor vert) et des parcours linéaires « sync source » / « créer un event » plutôt que des écrans-tiroirs.
- **Questions de design ouvertes** : faut-il un vrai routeur (deep-link/back) ? la barre de tags en masse est-elle le bon modèle d'édition ? le Download Center et le contexte event se chevauchent-ils inutilement ? la santé système mérite-t-elle un écran dédié ou un simple indicateur ?

---

## 9. Contraintes & non-négociables (à respecter quoi qu'il arrive)

1. **Sûreté Rekordbox** (§3.1) : blocage si RB/`rekordboxAgent` tourne, unit-of-work `_mutate`, **backup avant chaque mutation**, soft-delete réversible, restore avec snapshot préalable. Les **entiers de statut** (256/258, `rb_data_status`) sont load-bearing.
2. **Résolution de chemins** (§3.2) : volume-relatif sous `rekordbox/`, absolu ailleurs ; égalité des deux formes. À reproduire exactement (mémoire projet).
3. **Ne jamais déplacer les fichiers** ; gérer le quirk TCC (listing cloud KO mais `Path.exists()` OK).
4. **Dépendances externes incontournables** : pyrekordbox (+ sqlcipher3) pour `master.db` ; Spotify Web API (OAuth PKCE) ; Deezer/Deemix pour l'acquisition (forme à décider, D4) ; mutagen ; rapidfuzz.
5. **Packaging** : service Python embarqué autonome (binaire), DB seed copiée au 1er lancement, CA bundle (certifi) embarqué pour TLS. **Cross-OS** (D2) : équivalent Windows du spawn/binaire et des chemins système.
6. **Local-first** : aucun backend cloud ; tout l'état en SQLite local ; settings dans un dossier survivant aux mises à jour.
7. **Identités Spotify** : tokens OAuth stockés localement — **à protéger au repos** (open-source ⇒ pas de secret en clair dans un repo ; refresh tokens chiffrés/keychain, cf. §10).
8. **i18n FR/EN** maintenu (D13).
9. **Contrat de comportement** : la suite `service/tests/` encode les invariants — toute réécriture doit reproduire ces garanties (ou les amender explicitement via le journal).

---

## 10. Questions ouvertes pour la Phase 2 (architecture & produit)

> **⚠️ CLOS — résolu dans [SPEC-UNIFIED.md](SPEC-UNIFIED.md) §7.2.** Les 10 questions ci-dessous ont été tranchées (8 par recherche sourcée + validation, 2 — §10.9 UI/UX et §10.10 matching configurable — déléguées à la phase design). Cette section est conservée comme **historique de Phase 1** ; la décision faisant foi est dans SPEC-UNIFIED. Ne pas re-trancher ici.

Décisions **non tranchées** (état d'origine, avant unification) :

1. **Stack cible** — non décidée ici (règle d'or 1). À choisir en Phase 2 : langage/runtime du service, framework UI, mécanisme desktop (Electron ou alternative), en tenant compte de **macOS + Windows** (D2).
2. **Acquisition Deezer/Deemix (D4)** — **la grande question** : embarquer/packager le downloader, réimplémenter l'acquisition Deezer nativement, ou continuer à piloter une app externe ? Évaluer faisabilité technique, **légalité (ARL, GPL Deemix)**, robustesse (lire le vrai chemin de sortie — D18), et concurrence des téléchargements (retirer les globals process, F3).
3. **Couche de données / source de vérité** — la double couche (vue-query + Pinia, T4) et le double store de settings (electron-store + SQLite, T5) sont à **converger** vers une source de vérité unique. Modèle de polling vs push (un seul flux de jobs canonique alimenté par SSE, F5/F6).
4. **Protection des secrets au repos** — tokens OAuth Spotify et ARL : keychain OS vs DB chiffrée vs clair (inacceptable en open-source). À décider en Phase 2.
5. **Stratégie de migration de schéma** — remplacer le `IF NOT EXISTS` + ALTER ad-hoc (T-migration) par des migrations versionnées ordonnées.
6. **Abstraction multi-OS** — modèle de détection du process Rekordbox, des chemins système, des opérations de corbeille (D12) et de fichiers, portable macOS/Windows.
7. **Port du service & callback OAuth** — réconcilier « port dynamique » et redirect URI fixe `:8765` (T15) : port fixe pour OAuth, ou redirect dynamique enregistré.
8. **Robustesse du service** — superviser/redémarrer le service (F13), exposer un état « backend indisponible » au renderer (F14).
9. **UI/UX** — structure des écrans, navigation (routeur ?), regroupements (§8.2) : entièrement ouverte, à concevoir en phase design.
10. **Modèle de matching configurable** — exposer (ou non) les seuils (82 / marge 6 / pondérations) ; unifier la normalisation (D19) ; politique unique de collision ISRC entre matching et dedup.

---

## Annexes

- **Preuves détaillées par sous-système** : `docs/_analysis/00_R1.md` … `15_D1.md` (16 fichiers, chaque affirmation ancrée `fichier:ligne`).
- **À CONFIRMER** (non vérifiables en lecture seule sans exécution) : existence/contenu de `service/scripts/cleanup_rekordbox.py` et `migrate_collection.py` ; binding host/port uvicorn (hors `main.py`) ; consommateurs externes de `move_to_permanent`/`playlist_exists` ; usage réel de la table `event_playlists` ; comportement du champ `items.total` Spotify en prod.
