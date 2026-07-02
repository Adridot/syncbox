# SPEC-01 — Annexe de constantes & mécaniques load-bearing

> **Rôle.** Annexe de départage de [SPEC-UNIFIED.md](SPEC-UNIFIED.md). SPEC-UNIFIED §5 **fait foi** sur le comportement ; ce document ne conserve que (a) les **constantes numériques exactes** (pondérations, seuils, buckets) comme backstop de départage, et (b) les **mécaniques load-bearing précises** que §5 référence sans les détailler (tuples d'entiers de statut, conversions de format, quirks pyrekordbox). Tout le reste de la spec fonctionnelle vit dans SPEC-UNIFIED / SPEC-DESIGN.
>
> **Isolation clean-room.** Cette annexe est **auto-suffisante** : elle décrit des invariants en toutes lettres. Elle ne cite **aucun fichier de code** — il n'y a pas d'ancien code à lire dans ce dépôt.

---

## 1. Mécaniques load-bearing (à reproduire à l'identique)

### 1.1 Soft-delete / réactivation Rekordbox — tuples d'entiers exacts

**Ces entiers portent la sémantique de sync Rekordbox 6/7. Les reproduire à l'octet près, sous peine de corrompre la sync de l'utilisateur.**

- **Soft-delete** d'une ligne content : `rb_local_deleted = 1`, `rb_local_synced = 0`, `rb_data_status = 258`, `rb_local_data_status = 0`.
- **Réactivation** (restaurer un content soft-deleted) : `rb_data_status = 256` (au lieu de 258), `rb_local_deleted = 0`.
- **Toutes les lectures filtrent les lignes soft-deleted.**

### 1.2 Ordre de l'unit-of-work `_mutate`

(a) assert mutation-ready (RB fermé **et** DB existe) → (b) **backup horodaté** → (c) ouvrir la DB → (d) yield (muter) → (e) commit + **invalider le cache snapshot** ; sur exception : rollback + re-raise ; `finally` : close.

### 1.3 Backup & restore

- Backup avant **chaque** mutation : copier `master.db` (+ `-wal`/`-shm`) vers `…/_rekordbox_sync/backups/rekordbox-db-<timestamp>/` ; collision même-seconde → suffixe `-<n>`.
- **Rotation** : garder les N plus récents (défaut **15** ; `0` = illimité).
- **Restore** : valider le nom (rejeter vide / `/` / `\` / `.` / `..` et tout chemin hors racine backups) ; **snapshoter d'abord la DB courante** (le restore est donc lui-même réversible → laisse 2 backups) ; effacer WAL/SHM puis copier. **Exige RB fermé.**

### 1.4 Résolution de chemins — `path_lookup_keys`

Un fichier **sous `<storage_root>/rekordbox/…`** est stocké **volume-relatif** (`/<NomVolume>/…`, NomVolume = basename de `storage_root`) ; **tout le reste** en **absolu**. Volume-relatif et absolu sont **égaux et hash-égaux**. Pour matcher un chemin absolu de staging contre une ligne DB volume-relative, émettre les formes : **raw / volume-résolu / expanduser / `.resolve()` / volume-relatif**.

### 1.5 Quirk TCC (dossiers cloud)

Le *listing* d'un dossier cloud (Dropbox/iCloud) échoue depuis le service, mais `Path.exists()` sur un chemin précis fonctionne. Tout le file-matching est bâti sur `Path.exists()` + un bypass de cache (`fresh=True`).

### 1.6 Écriture Rekordbox — quirks pyrekordbox

- **ID string** : créer les nouvelles lignes content/artist/playlist avec un **ID de type string** (des PK int+string mélangées crashent SQLAlchemy au flush). `add_rekordbox_content` : `ID = MasterSongID = rb_file_id`.
- **Self-heal artiste** : ré-activer un artiste soft-deleted à chaque apply (sinon bug « artiste caché »).
- **`masterPlaylists6.xml`** : snapshoté avant apply, réécrit après commit (pyrekordbox peut l'écraser).

### 1.7 Smart playlist — format `SmartList` & conversion 32-bit signé

- `SmartList = "<playlistId>:<tagId>"`, opérateur **8** = « contains ».
- Les IDs `> 2³¹` sont convertis en **entier signé 32 bits** — **load-bearing**. Exemple : `"2662450573"` → `"-1632516723"`.

### 1.8 Aperçu de delete event

L'aperçu doit être lu **dans** la session de mutation (lire `.Title` après commit lève « instance not bound to a Session »). Protection : un content taggé est **protégé** (non supprimé) s'il porte un autre MyTag non-event **ou** si son chemin est sous permanent/manual_collection ; seuls les contents *uniquement-event* et non-protégés sont soft-deleted. Nettoyer le playlist par nom courant **et** legacy `"<name> - Smart"`.

---

## 2. Constantes numériques (backstop de départage)

> Reprises telles quelles par SPEC-UNIFIED §5. En cas de divergence apparente, **ces valeurs font foi**.

### 2.1 Matching Spotify → Rekordbox

- Ordre : **ISRC exact d'abord**, puis fuzzy.
- ISRC : comparé en **majuscules** → `confidence = 100`, `method = "isrc"`, `status = "matched"`.
- **Garde de collision ISRC** : rejeté **seulement si** `|Δdurée| > 15000 ms` **ET** similarité de titre `< 82`. Durée manquante (`0`/`None`) → confiance aveugle à l'ISRC.
- **Fuzzy** : `confidence = title*0.52 + artist*0.36 + duration*0.12`, arrondi ; seuil défaut `minimum_confidence = 82` ; en dessous → `status = "missing"`, `confidence = 0`.
- **Ambiguïté** : `(best − second) < 6` → `status = "ambiguous"` (retourne quand même le meilleur `content_id`).
- **Buckets de durée** : `≤1500 ms → 100`, `≤5000 → 80`, `≤12000 → 55`, sinon `0`.
- **Normalisation** : NFKD→ASCII (accents tombés), minuscule, parenthèses/crochets retirés, `&`→`and`, non-alphanumérique→espace ; similarité `fuzz.token_sort_ratio`. **D19 : une seule pipeline partagée** matching/dedup.

### 2.2 Doublons (dedup)

- **ISRC** : bucket par ISRC strip+upper (vide ignoré). Tous-ISRC + titres cohérents → **99** ; tous-ISRC + titres divergents → **60 + avertissement** (exclu du bulk) ; fuzzy → **80**.
- **Fuzzy** : seuil défaut `0.87`, tolérance durée `2000 ms` ; si une durée est inconnue, seuil monte à `max(seuil, 0.93)` ; signature = `artist_normalisé + " " + title_normalisé`.
- **Clé de groupe** = set trié unique de contentIds joint par `|`. Groupes `<2` membres droppés ; groupes dismissed droppés.
- **Keeper** : **D6 remplace** la somme pondérée historique par une **échelle de priorité ordonnée discrète** (protégé > fichier présent > qualité = **bucket de bitrate**, préférence lossless **retirée** > départage `dateCreated`). Le verdict A3 `lossy_source_probable` rétrograde d'un cran au critère qualité (prime sur le bitRate déclaré). Voir SPEC-UNIFIED §5.4/§5.12.

### 2.3 Acquisition Deezer

- Statuts : `pending → resolved → queued → downloading → downloaded → ready` (+ `acquisition_failed`, `acquisition_ambiguous`).
- Résolution : **ISRC d'abord** (`/track/isrc:{isrc}` → confiance 100) sinon recherche métadonnée. Pondération : `title 0.55 + artist 0.35 + duration 0.10`. **Seuils** : `≥85 → résolu` ; `70–85 → ambigu` ; `<70 → échec`.
- `downloaded → ready` **exige un scan dossier + fichier localisé sur disque**.
- **D18** : lire le **vrai chemin de sortie** du downloader (reconstruction de nom = fallback seulement).
- **D20** : ne **jamais** utiliser le tag `barcode` comme ISRC (absent → `None`).

### 2.4 Untagged & Missing

- **Untagged** : 4 catégories triées `junk(0) < dup_of_tagged(1) < alt_version(2) < review(3)`, puis artist, title.
- **D7** : `song_key = (normalize_artist, normalize_title)` doit **garder l'artiste complet** (pas le 1er token) ; corriger la regex `feat.` greedy. Motifs junk = **règles structurelles universelles** (stub `spotify:track:`, titre vide, artiste `rekordbox`) + motifs **configurables**.
- **Missing / re-link** : score ISRC → 100 puis title/name `≥70`, cap candidats (≈8), `rglob` **borné**. Re-link préserve cues/tags/playlists.

### 2.5 Spotify (auth)

- **D3 : OAuth PKCE uniquement** (S256), scopes **lecture seule** (`playlist-read-private`, `playlist-read-collaborative`).
- Refresh : un `refresh_token` absent de la réponse est **préservé**.
- Retry borné (**4 tentatives**) : 429 → `Retry-After + attempt` ; 401 → force refresh **une seule fois** (`attempt == 0`) ; 204 → `{}` ; ≥400 → erreur avec `status_code`.
- **404 = playlist privée/inaccessible** → message actionnable « connectez votre compte ».
- **Callback** : port fixe `http://127.0.0.1:8765/callback` (redirect_uri codé en dur).

### 2.6 Storage layout

`<storage_root>/rekordbox/{Collection, Collection manuelle}` (protégés) + `<storage_root>/_rekordbox_sync/{inbox, events, backups, manual_collection}`. DB applicative dans le dossier de données OS (`~/Library/Application Support/Syncbox` macOS / `%APPDATA%/Syncbox` Windows).
