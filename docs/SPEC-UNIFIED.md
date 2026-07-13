# Syncbox — Spécification unifiée (SPEC-UNIFIED)

> **Objet.** Spec unique, cohérente et sans contradiction qui fusionne la spec fonctionnelle/technique ([SPEC-01-syncbox.md](SPEC-01-syncbox.md)) et la cible architecturale ([SPEC-02-architecture.md](SPEC-02-architecture.md)). Elle tranche **tous** les forks A–D et les 10 questions ouvertes (SPEC-01 §10), par recherche état-de-l'art **sourcée** (`docs/_research/`) et **validation du propriétaire** (deux gates, 2026-06-15). Elle est l'intrant de [PROMPT-03-build.md](PROMPT-03-build.md), le prompt de construction.
>
> **Source de vérité.** Pour toute décision d'architecture/produit, **ce document fait foi**. SPEC-01 reste la référence du **comportement observable** (preuves `fichier:ligne`, `docs/_analysis/`) ; SPEC-02 reste la **motivation** des arbitrages archi. SPEC-01 §10 et SPEC-02 §4 sont **clos** et renvoient ici (pas de double source de vérité — le principe vaut aussi pour la doc).
>
> **Périmètre/valeur.** [OVERHAUL-01-valeur-features.md](OVERHAUL-01-valeur-features.md) (2026-06-16) est la **trace des décisions de valeur et de périmètre produit** (audit des features, candidates, journal). Son **périmètre cible v1 est replié ici** (§4 modèle de domaine, §5.11–§5.13 invariants, §6.5/§6.12 archi, §7.4 journal, §8 POC), arbitré par deux gates supplémentaires (2026-06-16, cf. §0). **SPEC-UNIFIED reste la source de vérité archi+produit consolidée** ; OVERHAUL-01 ne fait foi que sur le *quoi/la valeur*, et est corrigé là où la recherche §10 l'a infirmé (licence Chromaprint, attribution cues/ANLZ). Son découpage v1/v2 est **raffiné par les Gates 1/2 (2026-06-16)** : **§7.4 ci-dessous fait foi sur le périmètre v1** (les listes pré-Gate-2 d'OVERHAUL-01 §1/§6/§7.2/§8 sont historiques).
>
> **Langue.** Français.

---

## 0. Statut des décisions

| Bloc | Statut |
|---|---|
| Ampleur du chantier | **Tranché** — réécriture *from scratch* |
| Forks A, B, C, D | **Tranchés** (§7.1). Lib acquisition = **streamrip tranchée** (fallback deemix-fork documenté, Gate 2) ; restent **POC/packaging-gated** : viabilité full-track Deezer (POC #6) et signature macOS du sidecar (POC #1) |
| Questions §10.1–§10.8 | **Tranchées** (§7.2), sourcées + vérifiées (revue adversariale Phase 2) |
| Questions §10.9 (UI/UX) & §10.10 (matching configurable) | **Délégués à la phase design** (§9) — c'est la décision |
| Décisions D1–D25 | **Intégrées** (§7.3) |
| Non-négociables SPEC-01 §9 | **Préservés** (§3), avec reframing du contrat de tests |
| Périmètre produit (OVERHAUL-01, 2026-06-16) | **Intégré** (§4, §5.11–§5.13, §6.5, §6.12, §7.4, §8). macOS v1 includes A1 Smart Fixes, A3 faux-320/FLAC, B1 optional Deezer/streamrip acquisition, and B2 legal Track Matcher (+ D7 déjà spécifié §5.8). B1 returned `GO` on 2026-07-13 after a real full-track Deezer POC with a local one-shot Premium ARL. **Gate 2 (2026-06-16)** : A2 dedup-empreinte (Chromaprint) **différée v2** (résiduel étroit + binaire LGPL, POC-gated) ; SoundCloud **différé v2/B4** (tire ffmpeg). Recherche : [_research/11–14](_research/) |

---

## 1. Identité produit & résumé

Syncbox est une app desktop **macOS + Windows** (Linux exclu : Rekordbox n'y tourne pas) qui maintient la collection **Rekordbox** d'un DJ : elle synchronise des **playlists Spotify** (lecture seule), **entretient la collection** (doublons, fichiers manquants, tags, **nettoyage de métadonnées en masse**, **détection faux-320/FLAC**), propose pour les morceaux manquants un **chemin légal** mis en avant (liens d'achat Beatport/Bandcamp, sans réseau côté app), and can optionally run Deezer/streamrip acquisition after explicit enablement. Open-source.

Le principe directeur est la **sûreté** : aucune écriture dans `master.db` tant que Rekordbox tourne, **backup horodaté avant chaque mutation**, suppressions **réversibles** (soft-delete + restore), et **les fichiers ne sont jamais déplacés** (contrainte macOS TCC sur les dossiers cloud).

**Cœur de valeur** : l'écriture **en place** de `master.db` — MyTags + **smart playlists** (le « Event Imports » et la bibliothèque taggée *sont* la valeur de Syncbox). Sans elle, Syncbox ne serait qu'un downloader Deezer de plus (cf. Fork A).

**Ce que la réécriture corrige** vs l'app actuelle : chemins codés en dur sur la machine du dev, double pile d'auth Spotify, double couche de données + double store de réglages, reconstruction fragile du nom de fichier téléchargé, heuristiques de nettoyage francophones, migrations qui écrasent les éditions utilisateur. Le **cœur métier** (sûreté, matching ISRC/fuzzy, dedup, soft-delete, résolution de chemins) est solide et est porté ici comme **contrat d'invariants** (§5).

---

## 2. Priorités & principe de rédaction

**Priorités, dans l'ordre** : **(1) robustesse/sûreté** (zéro corruption Rekordbox) > **(2) empreinte légère** (petit binaire, peu de RAM, démarrage rapide) > **(3) performance/réactivité**, **avec la maintenabilité réintroduite comme garde-fou co-égal** (correction explicite de SPEC-02 qui l'écartait). Concrètement : une « complexité choisie » n'est retenue que si elle sert ces axes **et** survit à la question *« vs ce qui marche déjà, ce changement doit-il avoir lieu ? »*.

**Principe d'altitude (demande du propriétaire).** Cette spec est **exhaustive sur le QUOI** (invariants, modèle de domaine, non-négociables, forks tranchés, contrat de comportement) et **permissive sur le COMMENT** : les recommandations techniques marquées `reco` sont des **défauts conseillés et sourcés**, pas des mandats — le modèle de construction garde la liberté de choisir mieux dans les contraintes. Seuls les **non-négociables** (§3) et les **forks tranchés** (§7.1) sont contraignants.

**Minimal-design lens.** Pour chaque brique : (1) doit-elle exister ? (2) la stdlib le fait ? (3) une feature native OS/plateforme ? (4) une dépendance déjà installée ? (5) une ligne ? (6) le minimum qui marche. Deliberate simplifications carry a `Minimal-design note` stating what is excluded and when to reconsider it.

---

## 3. Non-négociables (à respecter quoi qu'il arrive)

### 3.0 — Syncbox v1 macOS owner override (2026-07-11)

This subsection is authoritative for Syncbox v1 and overrides conflicting text in sections 3–8.

- v1 targets macOS on Apple Silicon. Windows is deferred to v2, Linux remains out of scope, and v1 must not add unused Windows infrastructure.
- v1 is delivered without Developer ID signing or notarization. Apple Silicon executables retain the ad-hoc signatures required to run locally. Developer ID signing, notarization, stapling, auto-update, and Keychain integration are deferred. The encrypted local secret store remains the v1 storage path.
- The universal track-level `protected` rule is removed. File ownership is classified as `app_managed` (Syncbox working directories), `permanent_library` (`<storage_root>/rekordbox/`), or `external` (all other user-owned locations).
- Safety follows the operation: event deletion may remove app-managed event artifacts; `permanent_library` and `external` audio survive event deletion; duplicate resolution may operate on any ownership class after exact per-group confirmation; keeper selection is path-neutral; untagged removal remains a reversible Rekordbox soft-delete and never deletes audio; missing-file removal may soft-delete the Rekordbox row regardless of its former location; Smart Fixes do not filter by file location.
- When an event is deleted, an app-managed staging track with another active MyTag other than the event MyTag is migrated to `<storage_root>/rekordbox/Collection/` before event cleanup. This is the only intentional v1 file-move exception.
- Windows validation, Developer ID signing, notarization, and Chromaprint are deferred rather than failed POCs. The authoritative nine-item v1 POC index is maintained in `poc/README.md`.
- B1 Deezer/streamrip acquisition is included in macOS v1 after the 2026-07-13 Phase 5 `GO`. It is optional, OFF by default, Deezer-only, subordinate to B2 purchase links, and installed as a separate pinned component after explicit enablement. The base artifact must remain fully functional without streamrip and must not import or bundle streamrip at application boot.
- SoundCloud acquisition, ffmpeg bundling, AcoustID/MusicBrainz enrichment, automatic cues, beatgrid editing, a cloud backend, and a mobile app are deferred beyond v1.
- Ponytail remains an implementation discipline, not an annotation system. No new Ponytail rationale markers may be added, and executable source must have zero such markers at overall completion.

### 3.1 — Sûreté Rekordbox
Blocage de **toute** mutation si `rekordbox` **ou** `rekordboxAgent` tourne (détection stricte, anti-faux-positif, message « amical » **sans PID, sans chemin `/Applications/`, sans flag `--type=`**). Unit-of-work de mutation : assert RB fermé + DB existe → **backup horodaté** → ouvrir → muter → commit + invalider le cache snapshot ; rollback + close sur exception. Suppressions = **soft-delete réversible**. **Entiers de statut load-bearing** (256 = actif, 258 = supprimé, `rb_data_status`/`rb_local_*`) à reproduire **à l'identique** (sémantique de sync Rekordbox 6/7) sous peine de corrompre la sync de l'utilisateur. Restore qui snapshote d'abord la DB courante (réversible lui-même). Toutes les lectures filtrent les lignes soft-deleted. **Toute écriture en masse (Smart Fixes, §5.11) emprunte ce même unit-of-work `_mutate` — aucune échappatoire.** **Limite ANLZ (documentée, cf. §5.1)** : le backup couvre `master.db` ; les cues vivent aussi dans les fichiers ANLZ, que pyrekordbox **ne sait pas écrire** (§3.4) — Syncbox ne les modifie donc jamais et ses mutations restent intégralement réversibles via le backup `master.db`.

### 3.2 — Résolution de chemins (load-bearing)
Un fichier **sous `<storage_root>/rekordbox/…`** est stocké **volume-relatif** (`/<NomVolume>/…`) ; **tout le reste** est stocké en **absolu** — sinon Rekordbox affiche « file could not be found ». Volume-relatif et absolu sont traités comme **égaux et hash-égaux** (cf. mémoire `rekordbox-path-resolution`).

### 3.3 — Ne jamais déplacer les fichiers
Gérer le **quirk TCC** : le *listing* d'un dossier cloud (Dropbox/iCloud) échoue depuis le service, mais `Path.exists()` sur un chemin précis fonctionne — tout le file-matching est bâti autour de `Path.exists()` + un bypass de cache.

### 3.4 — Dépendances incontournables
`pyrekordbox` (+ `sqlcipher3-wheels`) pour `master.db` (seule lib mûre qui écrit la collection chiffrée — cf. [00_RB.md](_research/00_RB.md) ; **écrit `master.db`, ne sait PAS écrire les ANLZ** — borne la réversibilité, cf. §3.1/§5.1) ; Spotify Web API **OAuth PKCE** (lecture seule) ; `mutagen` (tags) ; `rapidfuzz` (similarité). B1 Deezer acquisition uses streamrip only as a separate optional component; the macOS v1 base app must not depend on streamrip or any Deezer acquisition package.

**Ajouts v1 (périmètre OVERHAUL-01)** : `miniaudio` (décodeur PCM, MIT, wheels précompilées cross-OS, ~2-3 Mo) + `numpy.fft` pour la détection faux-320/FLAC (A3, §5.12 — numpy **déjà bundlé transitivement via pyrekordbox** ; **à déclarer en dépendance directe** pour ne pas dépendre d'un transitif fragile) ; `urllib.parse` **stdlib** pour les liens d'achat (B2, §5.13, **zéro dépendance, zéro réseau côté app**). **Différé v2** : `fpcalc`/Chromaprint (A2 dedup empreinte — binaire natif tiers **LGPL 2.1**, FFmpeg statique ; cf. [11_Chromaprint-empreinte.md](_research/11_Chromaprint-empreinte.md)).

### 3.5 — Local-first
Aucun backend cloud ; tout l'état applicatif en **SQLite local** ; réglages dans un dossier survivant aux mises à jour. Appels **HTTPS sortants** (Spotify/Deezer) conservés → **CA bundle (`certifi`) embarqué** reste non-négociable (≠ « pas de serveur entrant »).

### 3.6 — Secrets au repos protégés
Tokens OAuth Spotify **jamais en clair** (incompatible open-source). Voir §6.7 (deux chemins documentés). Deezer ARL follows the same rule when optional B1 is enabled; no acquisition library may serialize it to disk.

### 3.7 — Cross-OS macOS + Windows
Détection process RB, chemins système, corbeille, kill d'arbre, packaging — tous abstraits par OS (§6.9). **Binaires natifs v1 base artifact** : A3 (`miniaudio`+`cffi`) est le **seul AJOUT v1 introduisant un nouveau binaire natif dans le bundle de base** (sqlcipher3/numpy sont déjà présents) ; wheels pré-compilées mac arm64+x86_64 **et** Windows **confirmées** ([12_FFT-faux-320](_research/12_FFT-faux-320.md)), à revalider POC #3 ; à défaut, **A3 est dégradable (repli A3-lite, §5.12) sans bloquer la release**. B1/streamrip est un composant optionnel séparé, installé seulement après activation explicite. A2/`fpcalc` (binaire tiers) reste hors v1.

### 3.8 — i18n FR/EN
Maintenu (locales structurées, parallèles ; cf. mémoire `i18n-fr-en`).

### 3.9 — Contrat de comportement = invariants, pas le code de test
Les garanties observables (sûreté, matching, dedup, résolution de chemins, soft-delete, transitions de statut) sont la référence et sont énumérées en **§5**. **Décision propriétaire :** la suite `service/tests/` actuelle est **trop restrictive comme contrainte d'architecture** — elle vaut **documentation de référence** du comportement, **pas** contrat d'implémentation. La réécriture **reproduit les invariants §5** et **écrit ses propres tests** (couvrant ces invariants) librement.

---

## 4. Modèle de domaine (socle réutilisable, techno-agnostique)

Entités qui survivent quelle que soit la techno (détail SPEC-01 §6) :

- **Source de bibliothèque** — playlist Spotify suivie *en permanence*. Attributs : `spotify_playlist_id` (identité), nom, `snapshot_id` (détection de changement), `tags` (MyTags par défaut), `enabled`, `status` (`pending → synced`). Runs historisés.
- **Track de bibliothèque** — 1 ligne par (source, spotify_track_id). Statuts : `new → matched|conflict|ready|imported`, plus `missing`, `removed_from_source`, `ignored`, `acquisition_failed`. Porte le lien Rekordbox, `match_method`, `confidence`, `staging_file_path`, tags. Un statut `missing`/`acquisition_failed` expose des **liens d'achat** dérivés (B2, §5.13) — non persistés, calculés à l'affichage.
- **Événement** — import temporaire (mariage, soirée). Attributs : nom, slug, `default_tag` (= nom, catégorie **« Situation »**), `spotify_playlist_id` (ou `manual:<slug>`), dossiers, `status` (`pending → applied|partially_applied`). Tracks (`matched/ambiguous/missing/ready/applied/ignored`) + fichiers de staging.
- **B1 acquisition job** — optional macOS v1 Deezer acquisition after the Phase 5 `GO`. It covers 3 scopes (`event`/`library`/`collection`) unified in one job table with `queued → downloading → downloaded → ready` plus `failed`, `relink_blocked`, and `relinked` terminal states as implemented. B2 purchase links remain primary and available even when B1 is disabled.
- **Job Smart Fixes** (A1, v1) — nettoyage de métadonnées en masse (extraction artiste/remixer depuis le titre, casse, caractères/URL parasites, encodage). Cycle **`dry-run` (aperçu exact, sans écriture) → `confirm` → `mutate`**. Écrit `master.db` via `_mutate` (§3.1/§5.11). Réutilise la **normalisation unique D19** (§5.3) — améliore en retour la précision du matching fuzzy.
- **Track Rekordbox** (snapshot non persistant) — `content_id`, title, artist, isrc, durationMs, filePath, fileType, bitRate/sampleRate/bitDepth/fileSize, bpm, rating, analysed, cueCount, playlistCount, tagCount, `protected`, `fileMissing`, dateCreated. Lu **une fois**, mis en cache sur `(mtime,size)` de `master.db(+wal)`. **Verdict qualité** (A3, §5.12) : `quality_verdict` ∈ `ok` / `lossy_source_probable` / `incertain` — diagnostic spectral **non persistant** qui **rétrograde d'un cran** la piste dans l'échelle de priorité explicite du keeper D6 (§5.4 ; règle de rétrogradation en §5.12). La fréquence de coupure estimée est une **valeur intermédiaire** du verdict (§5.12), non persistée — seul `quality_verdict` est exposé.
- **MyTag** — système de tags Rekordbox (catégories → tags). « Situation » pour les events, « Genre » par défaut sinon.
- **Groupe de doublons** — ≥2 contents identiques (ISRC) ou proches (fuzzy), avec un *keeper*. Identité de groupe = set trié de contentIds. *(A2 dedup par **empreinte audio** est **différée v2** — aucune intégration prévue en v1 ; clé de groupe inchangée. Cf. [11_Chromaprint-empreinte.md](_research/11_Chromaprint-empreinte.md).)*
- **Backup Rekordbox** — dossier horodaté sous `_rekordbox_sync/backups/`, contient `master.db(+wal/shm)`. Rotation N (défaut 15, 0 = illimité).
- **Réglages** — Spotify credentials, 4 paths, `backup_retention`, OAuth tokens (encrypted, §6.7), and the optional `deezer_acquisition_enabled` flag. The Deezer ARL is never a setting; it is stored only in encrypted secrets.

**Storage layout** : `<storage_root>/rekordbox/{Collection, Collection manuelle}` (protégés) + `<storage_root>/_rekordbox_sync/{inbox, events, backups, manual_collection}`. DB applicative dans le dossier de données OS (§6.9).

---

## 5. Contrat de comportement — invariants à reproduire

> Ce sont les règles métier, invariants et cas limites qui **doivent survivre** quelle que soit la techno. Le détail prouvé `fichier:ligne` est dans SPEC-01 §3 et `docs/_analysis/`. **La réécriture les reproduit et les couvre par ses propres tests.**
>
> Les **constantes numériques** citées ci-dessous (pondérations, buckets, seuils) sont **reportées de SPEC-01 §3** : SPEC-01 reste la **source canonique** en cas de divergence, et leur éventuelle **exposition/configurabilité** est une décision design (§10.10).

**5.1 Sûreté Rekordbox** — cf. §3.1. La garde de mutation re-filtre strictement le process (le chemin contient `/rekordbox.app/`·`/rekordboxagent.app/` ou finit par `/rekordbox`·`/rekordboxagent` sur macOS ; `rekordbox.exe`·`rekordboxAgent.exe` sur Windows). `rekordboxAgent` survit à la fermeture de la fenêtre → toujours vérifié. Backup avant mutation, rotation N, collision même-seconde → suffixe. Restore valide le nom (rejette chemins hors racine backups), snapshote d'abord, exige RB fermé.

**5.2 Résolution de chemins** — cf. §3.2. `path_lookup_keys` émet les formes raw / volume-résolu / expanduser / `.resolve()` / volume-relatif pour qu'un chemin absolu de staging matche une ligne DB volume-relative.

**5.3 Matching Spotify → Rekordbox.** Ordre : **ISRC exact d'abord**, puis fuzzy. ISRC en majuscules → `confidence=100`, `status="matched"`. **Garde de collision ISRC** : un match ISRC est rejeté **seulement si** `|Δdurée| > 15000 ms` **ET** similarité de titre `< 82` (durée manquante = confiance aveugle à l'ISRC). Fuzzy : `confidence = title*0.52 + artist*0.36 + duration*0.12`, seuil défaut **82** ; en dessous → `missing`. **Ambiguïté** : si `(best − second) < 6` → `ambiguous` (retourne quand même le meilleur `content_id`). Buckets de durée : ≤1500 ms→100, ≤5000→80, ≤12000→55, sinon 0. Normalisation : NFKD→ASCII, minuscule, parenthèses/crochets retirés, `&`→`and`, `fuzz.token_sort_ratio`. **D19 : une seule pipeline de normalisation partagée** matching/dedup (corrige les deux normalisations divergentes actuelles).

**5.4 Doublons & keeper.** ISRC : bucket par ISRC strip+upper. Tous-ISRC + titres cohérents → **99** ; tous-ISRC + titres divergents → **60 + avertissement** (exclu du bulk). Fuzzy : seuil 0.87, tolérance durée 2000 ms (monte à 0.93 si durée inconnue) ; signature = `artist_norm + " " + title_norm` ; **groupe fuzzy → confiance 80** (canonique SPEC-01, `dedup.py`), éligible au bulk via D5 (confirmation par groupe) comme les groupes ISRC. Clé de groupe = set trié de contentIds. **« Not a duplicate »** persisté (dismiss idempotent).
- **D5** : keeper **suggéré** mais **confirmation par groupe** ; **retirer le bulk 1-clic auto-resolve**.
- **D6** : remplacer la somme pondérée par une **échelle de priorité explicite ORDONNÉE, à critères discrets, avec raison affichée** (prévisible, explicable). Critères **dans l'ordre** : (1) `protected` (jamais supprimé, toujours keeper) ; (2) fichier **présent** > `fileMissing` (rétrogradé) ; (3) **qualité = bucket de bitrate** (préférence lossless/FLAC **retirée** — pas toujours supporté par le matériel DJ) ; (4) départage stable (ex. `dateCreated`). Le **« cran » d'A3** (§5.12) agit au critère (3) : un verdict `lossy_source_probable` place la piste **sous toute copie non-flaggée de bitrate ≥**, le **verdict primant sur le bitRate déclaré** (cas faux-FLAC à bitrate élevé trompeur).
- **Sûreté fichiers** : jamais supprimer le keeper ; **ordre** = relink memberships → soft-delete losers (dans la txn) → suppression de fichier **seulement APRÈS commit réussi** (cf. §6.9 corbeille). Relink réaffecte playlists+MyTags du loser vers le keeper.
- **Sûreté UX (corrige B10)** : le texte de confirmation d'une action destructive reflète **exactement** le payload exécuté (jamais l'inverse de l'action).
- **A3 × keeper (D6)** : un verdict `lossy_source_probable` (faux-FLAC **ou** faux-320) fait **perdre à la piste le critère qualité D6** face à toute copie non-flaggée de bitrate déclaré ≥ — le **verdict prime sur le bitRate déclaré**, jamais un score numérique, jamais une décision seule. **Règle canonique + cas `incertain`/`ok` : §5.12** (source unique pour éviter la divergence).

**5.5 Acquisition.** Statuts `pending → resolved → queued → downloading → downloaded → ready` (+ `acquisition_failed`/`acquisition_ambiguous`). Résolution Deezer : **ISRC d'abord** (`/track/isrc:{isrc}` → confiance 100) sinon recherche métadonnée ; pondération `title 0.55 + artist 0.35 + duration 0.10` ; seuils **≥85 résolu / 70–85 ambigu / <70 échec**. `downloaded → ready` **exige un scan + fichier localisé sur disque**. Re-download collection + relink préserve cues/tags/playlists (cues `master.db` ; **limite ANLZ §3.1** — un re-download qui **remplace** le fichier peut désaligner les cues côté ANLZ → **avertissement + consentement avant le remplacement** (miroir de la garde « consentement avant unlink » §6.9 ; hors garantie de réversibilité §3.1)) ; si relink échoue (RB ouvert) le job reste `downloaded` et est retenté (fichier gardé). Réconciliation idempotente (`ready` sans fichier → `acquisition_failed`).
- **D14** : re-download collection applique le **seuil 70/85 + état `ambiguous`** comme le flux event ; **jamais d'auto-relink sous le seuil** (corrige B1).
- **D18** : **lire le vrai chemin de sortie** depuis le downloader (réalise la synergie avec Fork D) ; la reconstruction de nom n'est qu'un **fallback** (tue F1).
- **Moteur (B1, §6.5)** : **streamrip** est installé uniquement comme composant optionnel séparé (pin git **v2.2.0** + commit exact), puis invoqué via un runner JSON court-vivant. Le sidecar de base n'importe jamais streamrip. Le runner lit le **vrai chemin de sortie** depuis `track.download_path` (D18), porte ARL + dossier par job, efface le fichier ARL one-shot, et n'écrit jamais `config.toml`. **v1 = Deezer uniquement** (FLAC/MP3 servi direct, **pas de ffmpeg**) ; SoundCloud → v2/B4 (HLS, exige ffmpeg).
- **D20** : ne **jamais** utiliser le tag `barcode` comme ISRC (absent → `None`) (corrige B6).
- **Concurrence (corrige F2/F3)** : corrélation download→track par **identité explicite** (`track_id` résolu), **jamais par index de liste** ; **aucun état d'acquisition mutable partagé** entre jobs concurrents — ARL et `downloadPath` portés par **job/requête**, pas en global de process.
- **Progression réelle (corrige F16)** : la progression affichée dérive du **flux SSE de jobs**, jamais du ton/statut.

**5.6 Sync bibliothèque.** Diffing par track : doublon Spotify dans une playlist → `ignored` ; `ignored`/`ready` reportés tels quels ; `imported`/`matched` réconciliés ; match frais → `matched`/`conflict` (si ambigu)/`new` ; absent de la playlist → `removed_from_source`. Tags par défaut hérités de `source.tags`. Snapshot Spotify (`snapshot_id`) détecte les changements. Apply : seuls `matched`/`ready` importés/taggés (sinon 409) ; **les MyTags de la bibliothèque doivent pré-exister**. Retirer une source = arrêt du suivi seulement (tracks RB + MyTags conservés). **D9** : supprimer la table `tag_rules` legacy (cause de B4) ; concept conservé via `source.tags`.

**5.7 Événements.** 3 modes (depuis playlist / vide / par lien). Dossier unique atomique (`mkdir(exist_ok=False)`, slug collision → `-2`…). `default_tag` = nom de l'event (catégorie « Situation »). Matching event : `ambiguous`→`ambiguous` (pas `conflict`), pas de tags par défaut. Staging/claim : un fichier partagé seulement entre deux tracks de **même ISRC non vide**. Apply : crée/répare un **smart playlist** sous « Event Imports », restaure le XML après commit. **Smart playlist** : `SmartList = "<playlistId>:<tagId>"` (opérateur 8 = contains) ; IDs > 2³¹ convertis en **signé 32 bits** — **load-bearing**. Écriture RB : nouvelles lignes avec **ID string** (PK int+string mélangées crashent SQLAlchemy au flush) ; self-heal d'un artiste soft-deleted. Aperçu de delete lu **dans** la session de mutation. **D10** : supprimer le Live Import M3U8 (UI + `live_import.py` + route) ; toujours exiger RB fermé et écrire la collection directement (élimine B12). **D11/D23** : delete event **toujours avec aperçu exact** + **gardé sur `mutationAllowed`** comme l'apply (corrige B11). **Nettoyage (corrige T8/T12)** : la suppression d'un event efface ses **artefacts disque** (dossier de staging, audio, snapshots `.xml.bak`) — pas d'orphelins.

**5.8 Untagged & Missing Files.** Untagged : 4 catégories triées **junk < dup_of_tagged < alt_version < review**. **D7** : remplacer les motifs junk perso/français par des **règles structurelles universelles** (stub `spotify:track:`, titre vide, artiste `rekordbox`) **+ motifs configurables par l'utilisateur** ; corriger B5 (artiste 1-token, `song_key` doit garder l'artiste complet) et B7 (regex `feat.` greedy). **D15** : `delete_untagged` **applique la garde protégé** (skip + report réel, corrige B2). Missing Files : re-download (job collection) / re-link (score ISRC→100 puis title/name ≥70, cap candidats, **`rglob` borné** — corrige F11) / remove (soft-delete) ; re-link préserve cues/tags/playlists (cues `master.db` ; limite ANLZ §3.1).

**5.9 Spotify (auth & lecture).** **D3 : OAuth PKCE uniquement** (S256), scopes **lecture seule** (`playlist-read-private`, `playlist-read-collaborative`) — retirer le mode app-only (client secret + username) et toute la logique Basic-vs-PKCE conditionnelle. Sur refresh, un `refresh_token` absent de la réponse est **préservé**. Retry borné (**4 tentatives**) : 429 → `Retry-After + attempt` ; **401 → force refresh une seule fois, et uniquement à la 1re tentative** (`attempt==0`, sinon boucle de refresh) ; 204 → corps vide `{}` ; ≥400 → erreur avec `status_code` préservé. **404 = playlist privée/inaccessible** → message actionnable « connectez votre compte ». **Callback** : voir §6.10 (port fixe `127.0.0.1:8765`). **Durcissement Web API 2026 (annotation, OVERHAUL-01 §9.1 + F1)** : Syntaxe inchangée — seuls les scopes `playlist-read-private`/`playlist-read-collaborative` sont utilisés et **aucun endpoint déprécié n'est requis** (`audio-features` tué le 2024-11-27, `recommendations`), cohérent avec « pas d'analyse locale ». La lecture de playlists (le périmètre Syncbox) **reste disponible** malgré la vague de restrictions tierces (fév. 2026) ; **risque plateforme à surveiller**, pas une dépendance morte.

**5.10 Settings, persistence, and backup/restore.** Settings are persisted in SQLite and are **never re-saved at startup**; defaults are applied when reading so stored credentials cannot be blanked. **Blank protection:** a credential update with an empty value preserves the stored value. Rekordbox and storage paths are validated. Settings JSON exports and all-data SQLite exports **exclude OAuth tokens entirely**; encryption at rest does not make a readable export safe. All-data export uses `VACUUM INTO` for one coherent file, and import validates and migrates a staged copy before atomic replacement while preserving a safety backup of the current database. The UI reads one canonical settings store.
- **Doctor (F9, GARDER v1)** : centre de diagnostics exposant la **liste / restore / rotation N des backups** (§4, §5.1) et l'accès aux **logs**. La **mécanique** vit ici (§5.1/§5.10, déjà spécifiée) ; seule la **surface UI** est déléguée au design (§9, hub « Santé de collection »). Aucune analyse de collection (orphelins/jamais-joués) en v1 — c'est le différé v2 (§7.4).

**Corrections de bugs transverses tranchées** (D14–D25, déjà intégrées ci-dessus ou ci-après) : **D16** tags en masse en **delta add/remove** (jamais d'écrasement par union, corrige B3) ; **D17** état distinct « appliqué avec avertissements » (pas rouge/erreur, corrige B8) ; **D22** restore `unignore` restaure le **statut antérieur** (pas `new`, corrige B9) ; **D24** aucun auto-update (cohérent mémoire `no-auto-build-release`) ; **D25** retirer tables/champs morts (`event_playlists`, `ProposalType.*_to_spotify`, tons inutilisés) ; **D21** réversibilité globale conservée (soft-delete + backups + restore), **étendue** à la corbeille fichiers (§6.9).

---

### Invariants des ajouts v1 (périmètre OVERHAUL-01)

> Mêmes règles que ci-dessus : comportement observable à reproduire, couvert par des tests neufs. Constantes/seuils à **calibrer en POC** (§8), pas figés ici. Each addition carries a `Minimal-design note`.

**5.11 Smart Fixes (A1) — nettoyage de métadonnées en masse.** Cycle strict **`dry-run` → `confirm` → `mutate`** : le `dry-run` produit un **aperçu exact** (par track : champ, avant → après) **sans aucune écriture** — il **lit le snapshot caché (§4) en lecture seule, n'ouvre jamais `master.db`, et N'EXIGE PAS RB fermé** (seule l'étape `mutate` l'exige) ; le `confirm` exécute **exactement** le payload prévisualisé (sûreté UX type B10 — le texte reflète la mutation réelle). **Garde de fraîcheur** : à l'entrée de `_mutate`, ré-assertion que le snapshot ayant servi au dry-run est toujours valide (même `(mtime,size)` de `master.db(+wal)`) — si la DB a changé (RB a écrit entre-temps), **ABORT + invite à relancer un dry-run**, jamais d'application aveugle (lié à l'invalidation de cache §3.1, garantit B10). L'écriture passe **sans échappatoire** par l'unit-of-work `_mutate` (§3.1 : garde RB fermé + backup horodaté + commit + invalidation cache snapshot + rollback sur exception). **Catalogue FIXE de correctifs structurels universels** (extraction artiste/remixer depuis le titre, casse, retrait caractères/URL parasites, fix encodage) — **pas de motifs perso/FR** (cohérent D7/§5.8). Réutilise la **normalisation unique D19** (§5.3) — donc améliore en retour le matching fuzzy. **Ordre déterministe** : les correctifs d'un run s'appliquent dans un ordre fixe ; le dry-run reflète le **résultat composé final** (plusieurs correctifs sur un même champ → un seul résultat prévisualisé) ; un champ déjà conforme = **pas de no-op affiché** (idempotence). **Tracks `protected` = EXCLUS par défaut** des écritures Smart Fixes — la sémantique de `protected` couvre **aussi l'écriture de métadonnées**, pas seulement la suppression (§5.4) ; jamais mutés en silence. L'inclusion exige un **opt-in nommé** qui **n'est jamais l'état par défaut ni mémorisé entre runs** (ré-armement explicite à chaque run) ; le dry-run **énumère nommément** les tracks protégées touchées et le texte de confirmation B10 les liste. `protected` reste une **garde dure de SUPPRESSION** (§5.4) : l'opt-in ne dé-protège **que l'écriture de métadonnées**, jamais le soft-delete/relink ; tout reste réversible via le backup §3.1. **Pas d'écrasement d'édition utilisateur** : le filet est l'**aperçu dry-run == payload exact** (l'utilisateur voit et confirme chaque champ) + la **réversibilité backup §3.1**. *(Minimal-design note: pas de détection d'« édition manuelle » en v1 — Rekordbox ne stocke aucun drapeau de provenance, et le catalogue FIXE+structurel ne modifie que des champs malformés (un champ déjà propre ne produit aucun diff) ; la rajouter seulement si un POC montre un correctif écrasant une saisie propre observée.)* **i18n §3.8** : libellés user-facing (noms de correctifs, opt-in, aperçu avant→après, états dry-run/confirm/mutate) en parallèle `en.ts`/`fr.ts`. Validé par **POC #9** (§8). *(Minimal-design note: réutiliser le pattern filter→dry-run→confirm→mutate de `rekordbox-bulk-edit` sur pyrekordbox ; **catalogue fixe — pas d'éditeur de motifs custom ni de moteur de règles générique en v1** ; rajouter quand un DJ réel réclame une règle manquante.)*

**5.12 Détection faux-320 / faux-FLAC (A3) — diagnostic spectral, lecture seule.** Décodage PCM **read-only** via `miniaudio` sur le **chemin résolu** (§3.2), `Path.exists()`/`stat` d'abord (pattern TCC-safe), ouverture en lecture par **chemin résolu exact — jamais d'énumération du dossier parent (bypass cache §3.3)**, **fichier jamais déplacé/copié** (§3.3). **100 % local** (décodage + FFT, aucun appel réseau — §3.5 ; tout enrichissement réseau type AcoustID est hors v1, relève d'A5/v2). Dépend de `numpy.fft` → **numpy DOIT figurer en dépendance directe (§3.4)**, jamais reposer sur le transitif pyrekordbox (sa disparition ne doit pas désarmer A3 en silence). Analyse : `numpy.fft.rfft` fenêtrée Hann sur ~30-60 s, spectre moyen, **fréquence de coupure (rolloff)** mappée aux seuils LAME — **seuils heuristiques, à calibrer POC #7** (≥~20 kHz ≈ 320/V0 ; ~19,4 kHz ≈ 256 ; ~18,6-19,2 kHz ≈ 192/V2 ; <18 kHz = lossy franc ; coupure nette <22 kHz dans un conteneur lossless ⇒ `lossy_source_probable` — **seuil heuristique, faux positifs masters band-limités à arbitrer POC #7** ; fenêtre 30-60 s non sourcée, à valider). **Verdict en 3 niveaux de confiance, jamais binaire** : zone **`incertain`** explicite à la frontière 320/V0 (limite physique). Libellés du verdict + raison de rétrogradation affichée en parallèle `en.ts`/`fr.ts` (§3.8). **N'est JAMAIS appelé dans `_mutate`** (diagnostic pur, n'ouvre jamais `master.db` en écriture). **Branchement keeper D6 (§5.4, critère qualité ordonné)** : `lossy_source_probable` (faux-FLAC **ou** faux-320) fait **perdre à la piste le critère qualité D6** face à toute copie non-flaggée de bitrate déclaré ≥ — le **verdict prime sur le bitRate déclaré** (faux-FLAC à bitrate élevé), **sans** score numérique ni « débit-source estimé » continu. **En v1, l'effet keeper est binaire** : `lossy_source_probable` (pénalisé) vs neutre — `incertain`/`ok` ⇒ aucune pénalité, identiques pour le keeper ; `incertain` est une **nuance d'affichage conservatrice** (« on n'accuse pas dans le doute »), **jamais** une pénalité. Verdict **non persisté**, calculé à la demande au scan doublons ; si A3 n'a pas tourné, ou format **non décodable** (AAC/m4a/opus — y compris fichiers préexistants), ou **échec de lecture cloud** → **`ok`/neutre par défaut** (jamais d'exception non gérée). POC #7 calibre la **frontière de bascule** lossy/neutre, pas une magnitude de score. **Trou AAC assumé, sans impact v1** : AAC/m4a/opus non décodés par miniaudio — **sans conséquence en v1** car l'acquisition v1 (Deezer, §6.5) sert du FLAC/MP3 décodable ; un upgrade B2→iTunes (AAC, v2) ou SoundCloud (v2) **rouvrirait le trou** et exigerait ffmpeg **système optionnel**, jamais embarqué. *(Minimal-design note: numpy.fft gratuit (déjà bundlé) ; miniaudio = plus petit décodeur cross-OS qui débloque (~2-3 Mo) ; pas de ffmpeg embarqué (+40-80 Mo), pas de ML (+200-500 Mo). v1 = **signal binaire (un cran) vers D6**, pas de score gradué — rajouter un score continu seulement si un cran s'avère insuffisant. **Repli** : si POC #7 ne calibre pas de frontières exploitables, ou si le delta bundle/trou-AAC est jugé inacceptable, replier sur **A3-lite** (incohérence `fileSize`/`bitRate`/durée sur les champs du snapshot §4, **sans décodage ni dépendance native**, pour la même rétrogradation d'un cran) ou différer A3 en v2 — repli symétrique à A2.)*

**5.13 Track Matcher légal (B2) — liens d'achat, lecture/affichage pure.** Consomme la liste des manquants déjà calculée (statuts `missing`/`acquisition_failed` uniquement — `removed_from_source` exclu, §4) ; **n'écrit rien** (aucune txn `_mutate`, aucun backup requis). Construit des **URL de recherche profondes** vers **Beatport** et **Bandcamp** par **pur templating** (`urllib.parse.quote`, stdlib) à partir de `artist+title` **normalisé via D19/§5.3** (pas de normalisation ad-hoc). **Aucun appel réseau depuis l'app** : c'est le navigateur de l'utilisateur qui ouvre l'URL → **§3.5/certifi non sollicité, §3.6/secrets non sollicité**. **Interdiction explicite** de tout fetch/scraping/résolution d'URL côté sidecar (réactiverait §3.5 et heurterait le 403 anti-bot Beatport). **Catalogue FIXE** (constante de build, **pas une entité du modèle §4**) : liste littérale `{nom, template_url}` (Beatport, Bandcamp) — **pas d'éditeur utilisateur** en v1, **aucun sondage réseau** (cohérent §3.5 : l'app ne contacte aucune boutique). Deux modes de défaillance, **tous deux borne-safe** (B2 = lecture pure, jamais de corruption) : (a) **boutique disparue** ⇒ on **retire son entrée** au prochain build ⇒ bouton **absent** (*Juno Download fermé le 2026-06-01*) ; (b) **format d'URL périmé mais boutique vivante** ⇒ l'URL atterrit au pire sur une page générique. Maintenir le catalogue = **éditer la liste au build**, pas le code. Libellés des boutons en parallèle `en.ts`/`fr.ts` (§3.8). Robustesse des templates validée POC #8 (§8). *(Minimal-design note: stdlib suffit (~5 lignes) ; **catalogue fixe 2 boutiques, pas d'éditeur utilisateur en v1** — rajouter une boutique = ajouter une entrée si un DJ la réclame ; pas d'API Beatport v4 (portail de facto fermé) ni d'agrégateur tiers ; **upgrade iTunes Search API = hors v1 / v2 uniquement** (réactiverait §3.5, re-validation du non-négociable réseau requise), marqué « AAC 256k » si prix+lien exact un jour requis. **En v1, B2 ne fait STRICTEMENT aucun appel réseau.**)*

---

## 6. Architecture cible (tranchée)

Optimisée **robustesse > légèreté > perf**, maintenabilité garde-fou ; UI web conservée ; macOS + Windows. Sources : [_research/05–10](_research/).

### 6.1 Vue d'ensemble

```
┌──────────────────────────────────────────────────────────────┐
│  COQUE : Tauri v2 (Rust, webview natif WKWebView/WebView2)    │   Fork B
│   • héberge l'UI web (Vue 3)                                   │
│   • spawn + SUPERVISE le sidecar Python (restart borné,       │
│     tree-kill, single-instance)                               │
│   • signe le binaire sidecar (POC #1, macOS)                  │
└───────────────┬───────────────────────────┬──────────────────┘
                │ HTTP REST + SSE            │ spawn + cycle de vie
                │ (127.0.0.1, loopback)      │ (shutdown propre → tree-kill)
                ▼                            ▼
   ┌────────────────────────┐   ┌────────────────────────────────────┐
   │ UI : Vue 3 (conservée)  │   │ SIDECAR Python (HTTP+SSE minimal)   │   Fork C
   │  • UNE couche de cache  │   │  • Starlette + sse-starlette        │
   │    réactive (convergée) │   │    (PAS FastAPI/Pydantic v2)        │
   │  • 1 flux SSE jobs       │   │  • pyrekordbox → master.db (MIT)    │   Fork A
   │    canonique             │   │  • SQLite app + migrations user_ver │
   │  • i18n FR/EN            │   │  • Spotify OAuth PKCE (port fixe)    │
   └────────────────────────┘   │  • [opt., OFF défaut] acquisition   │   Fork D
                                  │    Deezer (lib pinée, isolée)        │
                                  └────────────────────────────────────┘
   Sûreté (non négociable) : garde « RB fermé », backup avant mutation,
   soft-delete, corbeille OS (fallback §6.9), résolution de chemins.
```

**Ce qui change vs l'app actuelle** : Electron→**Tauri** (coque ~3–10 Mo vs 100–150 Mo) ; FastAPI/uvicorn→**Starlette+sse-starlette** minimal ; process Deemix externe→**lib embarquée optionnelle** ; double couche de données→**une seule** ; double store réglages→**une source** ; reconstruction de nom→**vrai chemin** ; migrations ad-hoc→**versionnées** ; tokens en clair→**chiffrés**.
**Ce qui ne change pas** : Python + pyrekordbox pour Rekordbox ; UI Vue ; **HTTP + SSE en localhost** ; la colonne vertébrale de sûreté ; le modèle de domaine.

> Minimal-design note: la taille finale est **dominée par le sidecar Python** (numpy non-excludable + sqlcipher3 ≈ 95–120 Mo), pas par la coque. Le gain Tauri sur la coque (~140 Mo) est réel mais secondaire ; le **vrai levier de taille** est le sidecar (mesure POC #3). On ne survend pas le « −140 Mo ».
>
> Minimal-design note: **budget des ajouts v1** : A1 Smart Fixes et B2 Track Matcher = **0 Mo** (pyrekordbox/stdlib déjà là) ; A3 faux-320 = **~2-3 Mo** (`miniaudio`+`cffi`+`pycparser` ; la FFT numpy est gratuite) ; **A2 dedup empreinte = 0 Mo en v1 car différée** (sinon `fpcalc` +~1,8-2,6 Mo **LGPL 2.1** à notariser). On évite délibérément les barreaux lourds : **ffmpeg embarqué** (+40-80 Mo, écarté → SoundCloud en v2) et le ML (écarté). Mesure non compressée à confirmer au POC #3.

### 6.2 Coque — Tauri v2 (Fork B)

`reco` Tauri v2 (stable, MIT+Apache-2.0, webview natif), sidecar via `externalBin` (binaire suffixé target-triple) + plugin Shell. **SSE servie en HTTP localhost** (fonctionne en WKWebView), **jamais** via le custom-protocol `tauri://` (pas de transport SSE natif). **Repli Electron** documenté **uniquement** si la signature sidecar macOS s'avère bloquante en POC #1.

**Condition dure (sourcée, [05_Signature](_research/05_Signature-notarisation.md)).** L'issue Tauri **#11992 est toujours ouverte (juin 2026)** : avec `externalBin`, la notarisation Apple échoue. Il faut **signer manuellement chaque binaire sidecar** (hardened runtime + entitlements) dans une **étape POST-bundle** (le hook `beforeBundleCommand` tourne **avant** que `Contents/MacOS/` existe — ne pas y signer le sidecar), puis laisser Tauri signer le bundle et notariser via `notarytool`. C'est le **dé-risquage n°1**.

> Minimal-design note: ne pas attendre un fix amont (pari sans échéance) ni le détour « frameworks auto-signés » (macOS-only, ne signe pas l'exécutable). `codesign`/`notarytool` sont des features OS natives → pas de dépendance, juste une étape de build documentée.

### 6.3 Sidecar Python & transport HTTP+SSE (Fork C)

`reco` **Starlette + `sse-starlette`**, servi par **uvicorn 1 worker lancé programmatiquement dans la boucle asyncio principale**. On **garde HTTP REST + SSE en localhost** (décision tranchée) et on **rejette le JSON-RPC stdio**. On **retire FastAPI/Pydantic v2** (cause documentée du cold-start ; le bug uvicorn multi-workers sous PyInstaller est évité avec 1 worker).

**Non-négociable de transport.** Le serveur loopback **bind `127.0.0.1`** uniquement, **restreint les origines aux loopback** (`http://(127.0.0.1|localhost):\d+`, `allow_credentials=False`) — aucune origine non-loopback acceptée (le serveur porte aussi `/callback` OAuth, §6.10). **Invariant SSE dur** : arrêt **propre** du flux SSE (générateurs fermés proprement, jamais coupés brutalement) + **graceful-timeout borné**.

**Conditions (sourcées, [06_Transport](_research/06_Transport-HTTP-SSE-OAuth.md)).** `reco` pour tenir l'invariant SSE : lancer uvicorn **dans la boucle asyncio principale** (jamais dans un thread aux signal handlers désactivés — sinon le shutdown SSE de `sse-starlette` casse). **Convergence data-layer** : une seule couche de cache réactive côté UI + un **flux SSE de jobs canonique** (corrige T4/F5/F6 ; le maintien vue-query+Pinia de la mémoire `dual-data-layer-kept` visait l'app existante — pour le rewrite on **converge**).

> Minimal-design note: Starlette nu suffit pour ~quelques dizaines de routes loopback + 1 flux SSE. On écarte Granian (extension Rust, packaging PyInstaller non dé-risqué) et le SSE-maison (réinvente keepalive/reconnexion). Rajouter une validation de payload type Pydantic **seulement** si un besoin réel apparaît. POC : cold-start réel sous PyInstaller + EventSource en WKWebView/WebView2 réels.

### 6.4 Écriture Rekordbox (Fork A)

**Écriture `master.db` en place, sans mode XML.** (Le label « A2 » de SPEC-02 était ambigu — il est **abandonné** ; la décision unique est : *master.db en place, seul*.) MyTags + smart playlists + mise à jour en place préservés ; surface minimale ; **aucune échappatoire « zéro écriture »**. La sûreté repose **entièrement** sur la colonne vertébrale §3.1/§5.1 (garde RB fermé, backup, soft-delete, corbeille). pyrekordbox (MIT) est la seule lib mûre ; la clé SQLCipher est une constante publique (pas un verrou) — cf. [00_RB.md](_research/00_RB.md).

> Minimal-design note: pas de mode « export XML » optionnel (le XML ne porte ni MyTags ni smart playlists, l'import RB est additif/buggé — il amputerait le cœur produit). Rajouter seulement si un usage « bridge » non destructif émerge.

### 6.5 Acquisition — B2 primary, optional B1 in macOS v1

**Current macOS v1 default path:** **Chemin légal (B2, par défaut, §5.13)** — Track Matcher : liste les manquants + **liens d'achat** Beatport/Bandcamp (URL de recherche, **stdlib, zéro réseau côté app**). Mis en avant comme alternative ToS-propre. The UI exposes a single purchase action per missing track; when several providers are available, that action opens the provider choices.

**Optional B1 path:** Phase 5 returned `GO` on 2026-07-13 after a real full-track Deezer POC with a local one-shot Premium ARL. B1 is included for macOS v1 only as an optional, Deezer-only module that is OFF by default and requires explicit enablement plus ARL entry. It is never on the critical `master.db` write path; collection relink failures retain the downloaded file and surface a blocked state instead of deleting the output.
   - **Confinement GPL — clause dure, testable** : streamrip est **GPL-3.0-only**. Le sidecar de base **n'importe JAMAIS streamrip au boot** and the base distribution artifact must not include streamrip or deemix-fork code. streamrip is installed as a separate, pinned optional component after explicit enablement and is invoked through a short-lived subprocess runner with JSON output. The base distributed app remains functional without the component; only the optional component loads GPL code after activation. Same rule for deemix-fork if ever used as a fallback.

**Candidate lib = streamrip, Deezer-only** (sources/API : [14_streamrip-embedding-Deezer-SoundCloud.md](_research/14_streamrip-embedding-Deezer-SoundCloud.md), [10_Acquisition](_research/10_Acquisition-2026.md)).
- **streamrip component**: pin git **v2.2.0** at exact commit `189acda489927719aa8591f6acdd7d67aecf929b` — **PAS PyPI 2.1.0**. The dedicated runner uses the proven API path `Config.defaults()` per job → `client.login()` → `PendingSingle.resolve()` → `track.rip()` → **`track.download_path`** (D18 without filename reconstruction). `Config` per job ⇒ **zéro état global** (corrige F2/F3). ARL is passed through an encrypted secret to a one-shot `0600` temp file consumed by the runner, then cleared from memory as soon as practical. **Clause TLS dure (testable, miroir §3.6)** : certifi is pinned and TLS verification must remain enabled.
- **Generic streamrip CLI remains excluded** : Syncbox does not call the human CLI output. It calls the dedicated JSON runner so the real output path comes from streamrip internals instead of reconstructed filenames.
- **deemix-fork (vietsman) = fallback documenté only if streamrip breaks later**: no v1 implementation unless streamrip becomes unmaintainable or fails a future bump POC. **Risque dominant** : the streamrip internal API is fragile to upgrades → **pin commit strict + integration tests surviving a bump** (garde-fou maintenabilité §2).

**SoundCloud → v2/B4** : il sert du HLS MP3 et **exige ffmpeg externe** (+40-80 Mo/plateforme, packaging cross-OS §3.7) qui doublerait quasi le sidecar (§2 légèreté). Deezer (FLAC/MP3 servi direct) **n'exige pas ffmpeg** → v1 reste léger. SoundCloud reviendra idéalement en **plugin téléchargeable hors sidecar de base**.

**Validated gate (POC #6).** The Phase 5 rerun proved full-track Deezer download on macOS Apple Silicon with a real Premium ARL: ISRC `USQX91300105`, Deezer track id `67238732`, catalogue duration `337 s`, measured duration `337.56 s`, `track.download_path` source, `13,520,081` bytes, and output cleanup. B1 downloads by numeric Deezer ID resolved from ISRC, never by short URL (#865). The Phase 6 rerun validated the separate self-contained packaged component in source, frozen, and Tauri hosts; the base bundle imports and contains no streamrip distribution or real ARL.

### 6.6 Cycle de vie & supervision (§10.8)

`reco` **superviseur maison dans le process Tauri** : boucle sur les événements de sortie du sidecar (plugin Shell + `async_runtime`), **restart borné** (~N=3, backoff 1/2/4 s), puis émission d'un event **`backend-down`** vers l'UI (corrige F13/F14 : l'épuisement du compteur **est** le signal « backend indisponible »). Bouton « Relancer » manuel après épuisement. **Anti-double-instance** via le plugin single-instance officiel.

**Conditions dures (sourcées, [09_Supervision](_research/09_Supervision-sidecar.md)).** Le **tree-kill est sur le chemin critique** : `child.kill()` ne tue que le bootstrap PyInstaller et laisse le worker **tenant le port 8765 orphelin** → au re-spawn le port est pris → `backend-down` permanent. **Tuer l'arbre** (`taskkill /T` Windows, kill du process group macOS) + **handshake d'arrêt propre** (commande shutdown → attendre la fermeture de la connexion SQLCipher → kill de secours). Distinguer crash vs arrêt volontaire par un **flag d'intention interne** (pas par code/signal de sortie, non garantis cross-OS). **Toujours consommer** le flux d'événements du sidecar (sinon il crashe). Le callback single-instance **ne doit pas** re-spawner un 2e sidecar.

### 6.7 Secrets au repos (§10.4)

Deux chemins documentés (le **choix se fait au packaging**, §7.2 — décision propriétaire) :
- **`reco` (si signé)** : lib Python **`keyring`** (délègue au Keychain macOS / Windows Credential Locker-DPAPI), ~3 lignes, un service-name par secret. Le non-négociable secrets **§3.6** (et SPEC-01 §9 item 7) est satisfait par construction (aucune clé maître côté app).
- **(si non signé)** : **petit store chiffré** (sqlcipher3 — déjà dépendance — ou `cryptography`/Fernet) pour éviter les re-prompts.

**Conditions dures (sourcées, [07_Secrets](_research/07_Secrets-au-repos.md)).** keyring **dépend d'un Developer ID stable** : sur macOS Tahoe, un binaire PyInstaller non signé Apple reçoit `errSecInteractionNotAllowed -25308` **même keychain déverrouillé** (cause = code-signing) ; et sans identité stable, **chaque release invalide l'ACL** → re-prompt. Donc : **signé → keyring** ; **non signé → store chiffré**. Dans tous les cas : **ne jamais écrire de secret en clair** ; chiffrer seulement the real v1 secrets, currently Spotify OAuth tokens and the optional Deezer ARL. The Deezer ARL must use the same encrypted secret path and must never appear in a streamrip `config.toml`, settings JSON, plaintext export, logs, or command-line arguments. Do not encrypt the entire DB; **figer le chemin d'extraction** (onedir ou `--runtime-tmpdir` stable). Côté Windows, DPAPI fonctionne tel quel.

### 6.8 Migrations de schéma (§10.5)

`reco` **`PRAGMA user_version` natif + scripts SQL ordonnés** (`0001_*.sql`…) appliqués via stdlib `sqlite3`, **zéro dépendance**. Chaque migration dans une **transaction explicite** (`BEGIN`/`COMMIT` pilotés — **jamais** `executescript` combiné à `autocommit=False`). **Le seed devient la migration `0001`** → supprime mécaniquement le re-seed à chaque boot (corrige **B4**). Remplace l'actuelle table applicative `schema_migrations` par le slot natif.

> Minimal-design note: ~18 tables, mono-utilisateur, local-first → yoyo/Alembic ne paient pas leur coût (deps + packaging). Pas de rollback/downgrade : le **backup horodaté** §3 est le filet. La DB migrée est la **SQLite applicative en clair** (pas `master.db`) → aucune garde §9 ni chiffrement dans cette couche. Rajouter yoyo (Apache-2.0) **seulement** si un vrai besoin de downgrade/multi-dev émerge. Sourcé : [08_MultiOS-corbeille-migrations](_research/08_MultiOS-corbeille-migrations.md).

### 6.9 Abstraction multi-OS (§10.6, D2, D12)

`reco` **`psutil`** (déjà bundlé via pyrekordbox) pour la détection process RB + **`send2trash`** pour la corbeille + **stdlib** (`os`/`pathlib`/`sys`) pour les chemins. Détection RB : réimplémenter le **filtre strict §5.1** par-dessus `psutil` (catcher `NoSuchProcess`/`AccessDenied`/`ZombieProcess`), pas la fonction laxiste de pyrekordbox. Chemins système : dossier de données app `~/Library/Application Support/Syncbox` (macOS) vs `%APPDATA%/Syncbox` (Windows) ; emplacement DB Rekordbox par OS ; résolution de volumes (`/Volumes` macOS vs lettres Windows) pour la règle volume-relatif/absolu.

**Suppression de fichier — décision propriétaire (sourcée, send2trash #80/#2).** Sur **dossiers cloud (Dropbox) et exFAT**, la corbeille OS échoue (~50 % `OSError`) ou supprime définitivement. **Comportement retenu : tenter la corbeille OS ; en cas d'échec, suppression définitive — précédée d'un AVERTISSEMENT UI requérant un CONSENTEMENT EXPLICITE préalable** (l'audio sera irréversiblement perdu sur ce volume). Pas de notification après coup : le consentement est demandé **avant** l'unlink. La **DB reste toujours réversible** (backup + soft-delete) ; seul **l'audio** est irréversiblement perdu sur ces volumes. Suppression de fichier **uniquement après commit réussi** (§5.4).

> Minimal-design note: pas de plugin Tauri trash (crate Rust côté coque → casse l'ordonnancement « delete-après-commit » du sidecar Python) ; pas de corbeille applicative `.trash` (déplacer un fichier sur cloud peut aussi échouer TCC **et** contredit « ne jamais déplacer les fichiers »). Rajouter une corbeille applicative **seulement** si un usage multi-volume **non-cloud** émerge où `send2trash` échoue **et** où le déplacement intra-volume est sûr (TCC OK). POC : format exact des chemins `master.db` sous Windows (lettre/UNC/volume-relatif Pioneer).

### 6.10 Callback OAuth Spotify (§10.7)

`reco` **port FIXE** : enregistrer `http://127.0.0.1:8765/callback` au dashboard Spotify ; ajouter une route `GET /callback` au serveur HTTP loopback **déjà servi par le sidecar** (pas de listener ni de process en plus). Authorization Code + **PKCE (S256)**, aucun client secret. Tranche §10.7 **en faveur du port fixe**.

**Conditions dures (sourcées, [06_Transport](_research/06_Transport-HTTP-SSE-OAuth.md)).** Conformité Spotify (durcissement avril 2025) : **IP loopback littérale `127.0.0.1`** (pas `localhost`, banni), match **exact** du redirect URI. **Coder en dur `http://127.0.0.1:8765/callback`** dans les deux appels (authorize **et** token), **binder sur 127.0.0.1**, et **répondre indépendamment du Host** de la requête (le navigateur peut réécrire `127.0.0.1`→`localhost` → casserait le login si le `redirect_uri` était dérivé de la requête).

> Minimal-design note: pas de port dynamique RFC 8252 (validation dashboard fragile, complexité injustifiée). Collision `:8765` improbable en mono-instance ; si le port est déjà pris au lancement → **échec propre + message** (le `redirect_uri` doit rester exactement `:8765` pour matcher le dashboard Spotify — **pas** de rotation de port côté callback, qui casserait l'OAuth).

### 6.11 Packaging du sidecar

`reco` **PyInstaller `--onedir`** (pas `--onefile` : ré-extraction à chaque démarrage → cold-start lent, et chemin d'extraction instable nuisible aux secrets). **Mesurer empiriquement** (POC #3) la taille + le cold-start sur le venv réel (numpy + sqlcipher3 + pyrekordbox + downloader) ; **Nuitka** seulement si la mesure montre un gain décisif. `sqlcipher3-wheels` vendorisé (SQLCipher 4, pas de toolchain C). Version applicative **single-source** (une source canonique injectée au build — clôt le skew T13).

> Minimal-design note: Nuitka = **overbuilt** par défaut (gain marginal une fois le plancher numpy payé, build lent, cross-build arm64 fragile). PyOxidizer abandonné. Trancher net : **onedir** (cold-start + chemin keychain stables) ; si `externalBin` exige **un fichier unique** par target-triple, résoudre par un wrapper/bundling compatible — à confirmer en POC #1/#3, **sans** rouvrir onefile. Sourcé : [03_Sidecar.md](_research/03_Sidecar.md), [05_Signature](_research/05_Signature-notarisation.md).

### 6.12 Hygiène avancée — place des ajouts v1 A1/A3/B2 (l'acquisition/sourcing B1 est traitée en §6.5)

Trois ajouts v1 vivent **dans le sidecar Python**, sans nouvelle coque ni service. Place et isolation :
- **A1 Smart Fixes (§5.11)** — module métier sur **pyrekordbox** (déjà là). Écriture en masse **uniquement** via l'unit-of-work `_mutate` (§3.1) ; aucune dépendance nouvelle. Pattern filter→dry-run→confirm→mutate (réf. `rekordbox-bulk-edit`).
- **A3 faux-320/FLAC (§5.12)** — module **diagnostic read-only** : `miniaudio` décode le PCM (wheels cross-OS, `_cffi_backend` à déclarer en `hiddenimport`, **garder `optimize=0`** dans le `.spec` sinon cffi casse), `numpy.fft` (déjà bundlé) calcule le rolloff. **Jamais** dans `_mutate`. Sort un verdict qui **rétrograde d'un cran** le keeper D6 (§5.4 ; invariant complet et règle de rétrogradation en §5.12). Sources : [12_FFT-faux-320.md](_research/12_FFT-faux-320.md).
- **B2 Track Matcher légal (§5.13)** — pur **constructeur d'URL stdlib** (`urllib.parse`), **aucun appel réseau côté app**, aucune dépendance, aucun secret. UI : boutons « Acheter sur … » sur les manquants. Sources : [13_Achat-legal-ISRC.md](_research/13_Achat-legal-ISRC.md).
- **A2 dedup empreinte — différée v2** (flag OFF) : binaire `fpcalc` LGPL 2.1 + comparaison numpy (`fpcalc -raw -signed`, pas de lib dynamique/ctypes), **après** un POC mesurant le volume réel de doublons ratés par ISRC+fuzzy (justifie l'existence) et la notarisation du binaire tiers. Sources : [11_Chromaprint-empreinte.md](_research/11_Chromaprint-empreinte.md).

> Minimal-design note: aucun de ces ajouts n'introduit de coque, de service réseau entrant, ni de moteur de règles générique. A1/B2 = 0 Mo ; A3 = ~2-3 Mo (miniaudio, pas ffmpeg) ; **A2 = 0 Mo (différée v2 — aucune intégration prévue en v1)**.

---

## 7. Journal de décisions consolidé (traçable)

### 7.1 Forks A–D — tranchés, libellé unique

| Fork | Décision (unique, sans ambiguïté) | Statut | Réf. |
|---|---|---|---|
| **A — Écriture RB** | **`master.db` en place, sans mode XML** (l'ancien double-sens « A2 » est abandonné) | **Tranché** | §6.4 |
| **B — Coque** | **Tauri v2** ; repli Electron documenté si signature sidecar bloquante en POC #1 | **Tranché** (POC-gated) | §6.2 |
| **C — Transport** | **Garder HTTP + SSE localhost** (Starlette+sse-starlette, uvicorn 1 worker) ; **rejeter JSON-RPC stdio** | **Tranché** | §6.3 |
| **D — Acquisition** | **Optional module, OFF by default**, with B2 purchase links kept primary. streamrip is a separately distributed component pinned to v2.2.0 and an exact commit; the Syncbox interface is Deezer-only. Deemix remains a documented fallback only; SoundCloud and ffmpeg are deferred beyond v1. | **Resolved** (Phase 5 full-track POC #6 and the Phase 6 packaged boundary are `GO` for local Apple Silicon artifacts; public asset/notices remain gated) | §6.5 |

### 7.2 Réponses aux 10 questions §10

| § | Question | Réponse tranchée |
|---|---|---|
| 10.1 | Stack cible | Tauri v2 + UI Vue + sidecar Python (Starlette HTTP+SSE) + pyrekordbox. §6 |
| 10.2 | Deezer acquisition | Optional module, **OFF by default**; streamrip is a separate self-contained component pinned to v2.2.0 and the exact commit. Phase 5 full-track POC #6 and the Phase 6 packaged installer/base-exclusion rerun are `GO` for local Apple Silicon artifacts. Public asset and license-notice gates remain. §6.5 |
| 10.3 | Couche données / source de vérité | **Convergence** : une couche de cache UI + un flux SSE canonique + un store de réglages unique. §6.3, §5.10 |
| 10.4 | Secrets au repos | `keyring` (si signé) **ou** store chiffré sqlcipher (si non signé) — choix au packaging. §6.7 |
| 10.5 | Migration de schéma | `PRAGMA user_version` + scripts SQL stdlib ; seed = migration 0001. §6.8 |
| 10.6 | Abstraction multi-OS | `psutil` (process) + `send2trash` (corbeille, fallback suppression+avertissement) + stdlib (chemins). §6.9 |
| 10.7 | Port + callback OAuth | **Port fixe** `127.0.0.1:8765/callback`, redirect_uri codé en dur, PKCE. §6.10 |
| 10.8 | Robustesse / supervision | Superviseur Tauri maison (restart borné + `backend-down`), tree-kill critique, single-instance. §6.6 |
| 10.9 | UI/UX | **Délégué à la phase design** (§9) — c'est la réponse. |
| 10.10 | Matching configurable | **Délégué à la phase design** (§9) ; invariants d'algo (§5.3) préservés ; D19 normalisation unique. |

### 7.3 Décisions D1–D25 — intégration

| # | Statut | Intégrée en |
|---|---|---|
| D1 open-source / retirer chemins perso | CHANGER | §1, §2 (configurable, hygiène secrets) |
| D2 macOS+Windows | CHANGER | §6.9 |
| D3 Spotify PKCE only | SIMPLIFIER | §5.9, §6.10 |
| D4 acquisition | RÉSOLU (= Fork D) | §6.5 |
| D5 dedup confirmation par groupe | CHANGER | §5.4 |
| D6 keeper échelle explicite, qualité=bitrate | CHANGER | §5.4 |
| D7 untagged règles structurelles + configurables | GARDER-MAIS-CORRIGER | §5.8 |
| D8 retirer script CLI cleanup | RETIRER | (couvert par Duplicates+Untagged) |
| D9 retirer `tag_rules` | RETIRER | §5.6 |
| D10 retirer Live Import M3U8 | RETIRER | §5.7 |
| D11 delete event avec aperçu | CHANGER | §5.7 |
| D12 corbeille OS | CHANGER | §6.9 |
| D13 i18n FR/EN | GARDER | §3.8 |
| D14 re-download seuil 70/85 | GARDER-MAIS-CORRIGER | §5.5 |
| D15 `delete_untagged` garde protégé | GARDER-MAIS-CORRIGER | §5.8 |
| D16 tags en masse delta | GARDER-MAIS-CORRIGER | §5.10 |
| D17 apply avec warnings | GARDER-MAIS-CORRIGER | §5.10 |
| D18 vrai chemin de sortie | CHANGER | §5.5, §6.5 |
| D19 normalisation unique | SIMPLIFIER | §5.3 |
| D20 ISRC fallback barcode | RETIRER | §5.5 |
| D21 réversibilité globale (+corbeille) | GARDER | §5.10, §6.9 |
| D22 restore unignore | GARDER-MAIS-CORRIGER | §5.10 |
| D23 garde RB sur delete event | GARDER-MAIS-CORRIGER | §5.7 |
| D24 retirer auto-update | RETIRER | §5.10 |
| D25 tables/champs morts | RETIRER | §5.10 |

### 7.4 Périmètre OVERHAUL-01 — ajouts v1 & différés (Gate 1/2, 2026-06-16)

| # | Statut | Intégrée en |
|---|---|---|
| A1 Smart Fixes (nettoyage métadonnées) | **AJOUTER v1** | §4 (Job Smart Fixes), §5.11, §6.12 |
| A2 dedup par empreinte (Chromaprint) | **DIFFÉRÉ v2** (Gate 2 : résiduel étroit + binaire LGPL, flag OFF, POC-gated) | §4 (note), §6.12, [_research/11](_research/11_Chromaprint-empreinte.md) |
| A3 détection faux-320/FLAC | **AJOUTER v1** (repli A3-lite ou v2 si POC #7 ne calibre pas, cf. §5.12) | §4 (`quality_verdict`), §5.12, §6.12, [_research/12](_research/12_FFT-faux-320.md) |
| B1 backend streamrip (Deezer-only) | **AJOUTER v1** after Phase 5 `GO`: optional OFF by default, Deezer-only, exact pinned optional component, ARL in encrypted secrets only, base artifact without streamrip/GPL code. SoundCloud → v2/B4 | §5.5, §6.5, §7.1 Fork D, [_research/14](_research/14_streamrip-embedding-Deezer-SoundCloud.md), [_handoffs/phase-05-b1-acquisition.md](_handoffs/phase-05-b1-acquisition.md) |
| B2 Track Matcher légal (liens d'achat ISRC) | **AJOUTER v1** | §4 (mention sur Track de bibliothèque : liens dérivés non persistés), §5.13, §6.5/§6.12, [_research/13](_research/13_Achat-legal-ISRC.md) |
| D7 untagged structurel + configurable | déjà tranché (GARDER-MAIS-CORRIGER) | §5.8 |

> **Corpus GARDER v1 inchangé** (OVERHAUL-01 §7.2 : F1 Spotify sync, F2 Match ISRC+fuzzy, F4 Events simplifié, F5 Duplicates, F6 Missing Files, F7 Untagged/D7, **F8 Sûreté/Backup** (verdict OVERHAUL « couvrir ANLZ » **corrigé Gate-1** → limite ANLZ documentée, §3.1/§5.1), **F9 Doctor** — diagnostics + gestion/rotation des backups + logs, mécanique §5.1/§5.10, surface UI §9 —, F10 Settings/i18n) — porté par §3/§5, non re-débattu ici. (**F3 Acquisition = B2 primary + optional B1 Deezer in macOS v1** after the Phase 5 `GO`.)
> Exclusions OVERHAUL-01 §7.3 préservées (analyse locale energy/key/vocal, set-prep harmonique, ReplayGain, auto-cues, conversion cross-app, mobile/cloud, édition beatgrid, streaming jouable). v2/SHOULD : A2 empreinte, A4 keeper-merge, A5 enrichissement ISRC (AcoustID→MusicBrainz), F1 analytics Doctor (orphelins/jamais-joués), E1 export setlist, B4 SoundCloud.

---

## 8. Ordre de dé-risquage (POC avant tout engagement)

1. **Signature + notarisation du sidecar Python sous Tauri macOS** (#11992) — étape POST-bundle (`codesign` + `notarytool`). *Le* point de friction n°1. Si bloquant → repli Electron (Fork B).
2. **Cycle de vie du process** — tree-kill (mac **et** Windows) + fermeture propre SQLCipher + libération du port 8765 + single-instance (risque de corruption #1 côté packaging).
3. **Taille réelle du bundle + cold-start** du sidecar (PyInstaller onedir, mesure ; Nuitka seulement si gain décisif) — lèvera/confirmera le gain de légèreté. **Inclure `miniaudio`+`cffi`+`pycparser` (A3) dans le venv mesuré** (`hiddenimports += ["_cffi_backend"]`, **garder `optimize=0`**) ; `fpcalc`/Chromaprint (A2) **hors mesure v1** (différé).
4. **`EventSource`/SSE dans WKWebView + WebView2 réels** (Starlette+sse-starlette sur HTTP localhost) — quirk de buffering initial WebKit.
5. **Fidélité d'écriture pyrekordbox sur RB 7.x** (smart playlists/MyTags, bug résiduel #110) — harnais de tests de non-régression sur le schéma `master.db` **avant** déploiement.
6. **Acquisition — B1 validated gate**: Phase 5 is `GO` after a real full-track Deezer download with a local one-shot Premium ARL on macOS Apple Silicon. Evidence: ISRC `USQX91300105`, numeric Deezer id `67238732`, catalogue duration `337 s`, measured duration `337.56 s`, output from `track.download_path`, and no retained POC output. Phase 6 also passed packaged optional-component installation, base-bundle streamrip exclusion, provider-client confinement, and no-credential scans. SoundCloud and ffmpeg remain outside v1.
7. **A3 faux-320/FLAC — calibration & branchement** : delta bundle réel (`miniaudio`+`cffi`+`pycparser`, voir #3) ; calibration du rolloff sur jeu étiqueté, **zone `incertain` à la frontière 320/V0** ; faux positifs légitimes (masters band-limités) ; **branchement A3→D6** (verdict = signal qui **rétrograde d'un cran l'échelle D6**, jamais un score ni une décision seule). Trou AAC assumé.
8. **B2 liens d'achat — robustesse des templates** : tester les URL Beatport/Bandcamp sur 5-10 morceaux réels (taux de bon 1er résultat) ; valider le **fallback « boutique disparue »** (entrée retirée du catalogue au build → bouton absent — *leçon Juno, fermé 2026-06-01*). **A2 dedup empreinte (différée v2)** : avant toute promotion, POC mesurant le **volume réel de doublons ratés** par ISRC+fuzzy (justifie l'existence) + notarisation du binaire `fpcalc` tiers.
9. **A1 Smart Fixes — sûreté de l'écriture en masse** (seul ajout v1 qui mute `master.db`, donc le plus risqué) : (a) **dry-run == payload réellement écrit** (champ avant→après) sur échantillon ; (b) **ordre déterministe** des correctifs composés → résultat stable et **idempotent** (re-run = no-op) ; (c) garde **`protected` exclus par défaut**, l'opt-in nommé (non mémorisé) étant l'unique chemin d'inclusion ; (d) **passage exclusif par `_mutate`** (garde RB fermé + backup + rollback, aucune échappatoire) ; (e) **garde de fraîcheur** : ré-validation du snapshot `(mtime,size)` à l'entrée de `_mutate`, ABORT si la DB a changé. Cf. §5.11.

---

## 9. Hors-périmètre de cette spec — délégué à la phase design

Conformément à la décision Gate 1 (« trancher l'infra, déléguer le design »), **deux sujets restent ouverts par choix** et seront conçus en phase design, hors recherche lourde :

- **§10.9 — UI/UX.** Structure des écrans, navigation (routeur/deep-link ? regroupements §8.2 de SPEC-01 : centre d'acquisition unifié, hub « Santé de collection » ; flux guidés/onboarding). L'existant (9 écrans, navigation par état) et les incohérences relevées (SPEC-01 §8) sont l'intrant ; rien n'est figé.
- **§10.10 — Matching configurable.** Exposer ou non les seuils (confidence 82, marge 6, pondérations) à l'utilisateur ; politique d'unification de la collision ISRC. Les **invariants d'algorithme** (§5.3) et la **normalisation unique** (D19) sont préservés ; seule l'**exposition/configurabilité** est une décision de design.

> Minimal-design note: ne pas figer l'UI/UX ni un panneau de réglages de matching maintenant — YAGNI tant que le design n'a pas tranché les parcours. Les invariants de comportement (§5) tiennent quel que soit le design.

---

## 10. Annexes

- **Recherche sourcée & datée** : [_research/00_RB](_research/00_RB.md) · [01_Formats](_research/01_Formats.md) · [02_Coques](_research/02_Coques.md) · [03_Sidecar](_research/03_Sidecar.md) · [04_Acquisition](_research/04_Acquisition.md) · [05_Signature](_research/05_Signature-notarisation.md) · [06_Transport](_research/06_Transport-HTTP-SSE-OAuth.md) · [07_Secrets](_research/07_Secrets-au-repos.md) · [08_MultiOS-corbeille-migrations](_research/08_MultiOS-corbeille-migrations.md) · [09_Supervision](_research/09_Supervision-sidecar.md) · [10_Acquisition-2026](_research/10_Acquisition-2026.md).
- **Recherche ajouts v1 (OVERHAUL-01, 2026-06-16)** : [11_Chromaprint-empreinte](_research/11_Chromaprint-empreinte.md) (A2, différée v2) · [12_FFT-faux-320](_research/12_FFT-faux-320.md) (A3) · [13_Achat-legal-ISRC](_research/13_Achat-legal-ISRC.md) (B2) · [14_streamrip-embedding-Deezer-SoundCloud](_research/14_streamrip-embedding-Deezer-SoundCloud.md) (B1).
- **Preuves comportementales `fichier:ligne`** : `docs/_analysis/00_R1.md` … `15_D1.md` (référence du comportement existant à reproduire — §5).
- **Remaining POC gates**: real pyrekordbox fidelity on Rekordbox 7.x; Windows `master.db` paths and Windows packaging in v2; public download-back of the exact optional Release asset; live owner-consented OAuth completion; and, before v2, a measured missed-duplicate volume that could justify A2. The macOS arm64 cold-start, size, native bundle, optional component, base exclusion, A3 fallback, and B2 browser-template gates have recorded evidence.
