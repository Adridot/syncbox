# Remarques à intégrer aux specs

Liste de points relevés à trancher puis à reporter dans [SPEC-UNIFIED.md](SPEC-UNIFIED.md). Une remarque = un point. Cocher une fois intégrée.

Deux parties : **remarques** (R#, à trancher/spécifier) et **bugs résolus** (B#, trace complète des correctifs déjà appliqués — exigence : garder une trace de toute résolution d'erreur).

---

# Bugs résolus (trace complète)

## B1 — Le scan doublons « ne fait rien » au clic

- **Symptôme.** Clic sur « Scanner les doublons » → aucune réaction visible.
- **Cause.** [`DuplicatesTab.vue`](../ui/src/screens/health/DuplicatesTab.vue) appelait `duplicates.scan()` sans `try/catch` ni surface d'erreur → toute erreur backend (400, 423, 500, NetworkError) partait en *unhandled rejection*, invisible ; le `finally` remettait juste `scanning` à false.
- **Fix.** `try/catch` + ligne `.scan-error` affichant le message backend ; clé i18n `duplicates.scanError` (en/fr). Test : [`duplicates-tab.spec.ts`](../ui/src/screens/__tests__/duplicates-tab.spec.ts).
- **Statut.** Corrigé. A permis de révéler B2.

## B2 — `~` (tilde) non expansé dans le chemin `master.db`

- **Symptôme.** `Le scan a échoué : [Errno 2] No such file or directory: '~/Library/Pioneer/rekordbox/master.db'`. Le bon chemin résolu est `/Users/<user>/Library/Pioneer/rekordbox/master.db`.
- **Cause.** `settings_update` valide avec `Path(db_path).expanduser()` (donc le ✓ s'affichait, le vrai fichier existe) **mais persiste la valeur brute `~/...`**. Ensuite `Deps.db_path` la renvoyait telle quelle à sqlite/`open_readonly`, qui **n'expansent pas `~`** → ENOENT au scan.
- **Fix.** Expansion au **point unique** de lecture : helper `_expanduser` appliqué dans les propriétés `Deps.db_path` et `Deps.storage_root` ([`api.py`](../sidecar/src/syncbox/api.py)), donc tous les consommateurs (sqlite, cache snapshot, `backups_root`) reçoivent un chemin réel. Falsy (`""`/`None`) préservé = sentinelle « pas encore configuré ». Test : `test_db_path_expands_tilde` dans [`test_api.py`](../sidecar/tests/test_api.py).
- **Statut.** Corrigé (52 pytest verts).

## B3 — Tick de validation ✓ affiché même quand la collection est introuvable

- **Symptôme.** Le champ chemin montrait un ✓ alors que le scan ne trouvait pas la collection.
- **Cause.** Dans [`SettingsScreen.vue`](../ui/src/screens/SettingsScreen.vue) le tick était `pathErrors ? '✕' : value ? '✓' : ''` : il s'affichait pour **toute** valeur non vide, sans re-valider au chargement (la validation serveur ne tournait qu'au moment d'un `savePath` déclenché par une édition). Un défaut pré-rempli passait donc ✓ sans preuve.
- **Fix.** Re-validation des chemins stockés au `onMounted` (via `savePath`, qui valide côté serveur et pose `✕` + message si introuvable). Un ✓ ne s'affiche plus que pour un chemin réellement trouvé.
- **Statut.** Corrigé (typecheck + settings.spec verts).
- **À spécifier (lien R3).** Message d'erreur « collection introuvable » clair et localisé côté champ. Quand R3 éclatera les chemins (collection / collection manuelle / Syncbox), la même règle « pas de ✓ sans validation réelle » s'applique aux 3 + au chemin `master.db`.

## B4 — Aperçu Smart Fixes : diffs « avant → après » d'apparence identique

- **Symptôme.** Dans l'aperçu Smart Fixes, des lignes montrent `Carole Fredericks → Carole Fredericks` (avant/après visuellement identiques) — incompréhensible.
- **Cause (pas un bug backend).** [`smartfixes.py`](../sidecar/src/syncbox/smartfixes.py) ne produit **jamais** de no-op : une ligne n'existe que si `after != before`. La différence était **réelle mais invisible** — `collapse_whitespace` retire un espace final, un espace double ou un espace insécable (NBSP), qui se rendent à l'identique à l'écran. L'aperçu n'était donc pas « exact » au sens §5.11.
- **Fix.** [`DryRunModal.vue`](../ui/src/components/DryRunModal.vue) : helper `segments()` qui découpe chaque valeur et **surligne en rouge, façon git diff** (span `.ws-mark`, `·` sur fond rouge) tout espace suspect (début/fin, doublé, NBSP/unicode) dans avant **et** après, + légende `smartfixes.dryrun.wsLegend` (en/fr) avec sa pastille rouge. Les espaces inter-mots normaux restent intacts. Test : [`dryrun.spec.ts`](../ui/src/components/__tests__/dryrun.spec.ts).
- **Statut.** Corrigé (typecheck + dryrun.spec + parité i18n verts).

---

## R1 — Champ Client ID Spotify saisi par l'utilisateur

- [ ] Intégrée

**Constat.** Le Client ID Spotify ne doit pas être embarqué dans l'app (open-source, et c'est le compte perso du propriétaire). Chaque utilisateur enregistre sa propre app Spotify et fournit son Client ID.

**À ajouter aux specs.**
- **Réglages (§4 « Réglages », §6.7)** : ajouter `spotify_client_id` (saisi par l'utilisateur, stocké en clair — ce n'est pas un secret, ≠ tokens OAuth). Pas de client secret (PKCE, cf. §5.9 D3).
- **UI (SPEC-DESIGN)** : champ texte « Spotify Client ID » dans les réglages, avec un lien/popup d'aide expliquant **où et comment** le récupérer :
  1. Aller sur le [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
  2. *Create app* → nom/description au choix
  3. Redirect URI : `http://127.0.0.1:8765/callback` (port fixe, cf. §6.10) — **doit correspondre exactement**
  4. Copier le **Client ID** (pas le secret) et le coller dans Syncbox
- **Garde** : tant que `spotify_client_id` est vide, le bouton « Connecter Spotify » est désactivé avec un message actionnable pointant vers l'aide.

**Ponytail :** popup = simple bloc d'aide inline (details/summary natif ou modale déjà présente), pas de composant dédié. Skipped : validation du format de l'ID côté app — Spotify renverra l'erreur au moment de l'auth ; add when les utilisateurs collent souvent des IDs malformés.

---

## R2 — Icône « Synchroniser les sources » trop petite

- [ ] Intégrée

**Constat.** Le rond de l'icône de synchro paraît trop petit dans l'app comparé au mockup.

**Vérifié.** Le glyphe est **déjà identique** au mockup : `↻` (U+21BB), couleur accent — cf. [`DashboardScreen.vue:159`](../ui/src/screens/DashboardScreen.vue:159), [`LibraryScreen.vue:172`](../ui/src/screens/LibraryScreen.vue:172) et mockup [`Syncbox.dc.html:119`](../syncbox-ui-ux-design/project/Syncbox.dc.html:119). L'écart vient du **rendu de police** (le mockup tourne en police système du navigateur ; l'app charge une autre police où `↻` sort plus fin/petit), pas du caractère.

**À faire.** Agrandir/épaissir l'icône dans la classe `.btn-icon` pour retrouver le rendu du mockup — p. ex. `font-size: 1.15em` (+ éventuellement `font-weight`). Fix CSS local, pas de swap de glyphe ni d'asset. Si on veut un rendu garanti cross-police, passer à une petite SVG inline.

---

## R3 — Explication + aide pour les chemins `master.db` et `storage_root`

- [ ] Intégrée

**Constat.** Dans les réglages, les deux champs de chemin (base Rekordbox + racine de stockage) ne sont pas assez explicites. Il faut une aide inline qui dise ce que c'est et comment trouver le bon, avec le défaut macOS pré-rempli pour `master.db`.

**À ajouter aux specs / UI (SPEC-DESIGN + §5.10 « Réglages »).**

- **Champ `master.db` (base Rekordbox)** — texte d'aide : « Base chiffrée où Rekordbox garde ta collection (morceaux, playlists, cues, MyTags). Syncbox la lit et y écrit les MyTags/smart playlists. »
  - **Défaut pré-rempli** (macOS, >95 % des installs) : `~/Library/Pioneer/rekordbox/master.db`
  - Windows : `%APPDATA%\Pioneer\rekordbox\master.db`
  - Aide « le trouver » : Rekordbox → *Préférences → Avancé → Base de données* affiche le dossier.
  - Note d'implémentation : pyrekordbox sait auto-détecter ce chemin → l'utiliser pour pré-remplir plutôt qu'un littéral en dur.

- **Éclater `storage_root` en 3 dossiers explicites** (au lieu d'une racine unique dont Syncbox dérive `rekordbox/…` + `_rekordbox_sync/…`). L'arborescence dérivée actuelle suppose le layout du propriétaire (`<root>/rekordbox/Collection`, `<root>/rekordbox/Collection manuelle`, `<root>/_rekordbox_sync`) — **ça ne colle pas au reste des utilisateurs**, qui rangent leur musique autrement. Trois chemins indépendants, chacun avec son aide :

  1. **Dossier de collection** — « Le dossier où sont tes fichiers audio principaux, ceux déjà dans ta collection Rekordbox. Protégé : Syncbox n'y supprime/déplace jamais rien. » (ex-`<root>/rekordbox/Collection`.)
  2. **Dossier de collection manuelle** — « Le dossier des morceaux que tu ajoutes à la main, hors sync Spotify. Protégé également. » (ex-`<root>/rekordbox/Collection manuelle`.)
  3. **Dossier Syncbox** — « Le dossier de travail de Syncbox : imports en attente (inbox), events, et backups de ta base avant chaque modification. C'est le seul dossier que Syncbox gère activement. » (ex-`<root>/_rekordbox_sync` — **à renommer « Syncbox », plus « rekordbox sync »** ; sous-dossiers `inbox`/`events`/`backups` créés dedans.)

  - **Pas de défaut universel** pour les trois : au choix de l'utilisateur (souvent un SSD DJ externe type `/Volumes/DJ-SSD`, ou un dossier Musique). Le champ « Dossier Syncbox » peut proposer un défaut à côté de la collection une fois celle-ci choisie.

**⚠️ Implication à trancher (propriétaire).** La règle chemin **volume-relatif** (§3.2/§5.2) dérive aujourd'hui le nom de volume du basename de `storage_root` unique. Avec 3 dossiers potentiellement sur des **volumes différents**, il faut :
  - soit résoudre le nom de volume **par chemin réel** de chaque dossier (basename du point de montage `/Volumes/<X>`), pas d'un root commun ;
  - soit contraindre les 3 dossiers à vivre sur le **même volume** (garde de validation, message clair).
  À arbitrer avant d'intégrer — touche la sémantique load-bearing de résolution de chemins (`rekordbox-path-resolution`). Valider les 3 chemins (existe + accessible), extension de F15/§5.10.

**Impact code (M4 déjà livré).** [`SettingsScreen.vue`](../ui/src/screens/SettingsScreen.vue) passe de 2 champs (`rekordbox_db_path` + `storage_root` + lignes dérivées) à 4 champs éditables (db + 3 dossiers) ; réglages/validation backend §5.10 à ajuster ; i18n `en.ts`/`fr.ts`.

**Ponytail :** aide = texte court sous chaque champ + éventuel `details/summary` natif, pas de wizard. Défaut `master.db` via l'auto-détection pyrekordbox (rung 4 : dépendance déjà présente), pas de littéral codé en dur. Ne pas ré-introduire de dérivation cachée : 3 champs = 3 valeurs stockées, pas de magie de sous-dossiers imposée.

---

## R4 — Aperçu audio des morceaux dans l'analyse de doublons

- [ ] Intégrée

**Constat.** Dans l'analyse de doublons, pouvoir **écouter un extrait** de chaque morceau du groupe pour départager le keeper à l'oreille (utile quand deux fichiers ont les mêmes tags mais un contenu/qualité différents).

**À ajouter aux specs / UI.**
- Un bouton lecture par membre de groupe dans [`DuplicateGroupCard.vue`](../ui/src/components/DuplicateGroupCard.vue), lisant le fichier **local** via `resolved_path` (déjà exposé dans `DuplicateMember`).
- **Portée** : lecture seule, fichier jamais déplacé/copié (cohérent §3.3 et A3 §5.12) ; pas de streaming réseau.
- **Contraintes à trancher** :
  - Accès au fichier depuis la WebView : soit via un endpoint stream du sidecar (`GET /api/audio?content_id=…`, lecture seule, borné au `resolved_path` résolu), soit via le protocole asset Tauri. À arbitrer (le sidecar sert déjà le loopback → réutilisable).
  - Formats : le `<audio>` natif ne décode pas tout (FLAC selon plateforme, AIFF, ALAC/m4a variables). Cohérent avec le « trou AAC » de §5.12 → dégrader proprement (bouton désactivé + tooltip « format non prévisualisable ») plutôt qu'ajouter ffmpeg.
  - Fichiers cloud/TCC : `Path.exists()` d'abord (pattern TCC-safe §5.12), échec de lecture → bouton désactivé, pas d'exception.

**Ponytail :** `<audio controls>` natif pointant sur un endpoint stream du sidecar (rung 3 : feature plateforme native) ; pas de lib de lecture, pas de waveform, pas de transcodage v1. Ajouter le décodage étendu seulement si un DJ réel bute sur un format courant.

---

## R5 — Choisir une source depuis sa bibliothèque Spotify (pas seulement par lien)

- [ ] Intégrée

**Constat.** Pour ajouter une source de bibliothèque, aujourd'hui il faut coller un lien de playlist. Je veux aussi **sélectionner une playlist directement dans ma bibliothèque Spotify** (liste de mes playlists).

**À ajouter aux specs / UI (§5.6 « Sync bibliothèque » + SPEC-DESIGN).**
- Nouveau mode d'ajout de source : **picker** listant les playlists du compte connecté, en plus du collage de lien existant (les deux chemins cohabitent).
- **Endpoint** : `GET /me/playlists` (paginé). **Aucun nouveau scope requis** — `playlist-read-private` + `playlist-read-collaborative` (§5.9 D3) le couvrent déjà. Route sidecar type `GET /api/spotify/playlists` (le client Spotify + retry borné §5.9 existent déjà).
- Le picker renvoie le `spotify_playlist_id` → même chemin d'ajout de source qu'aujourd'hui (identité, `snapshot_id`, tags par défaut). Rien à changer en aval.
- **États** : compte non connecté → picker désactivé + CTA « connecter Spotify » (déjà géré) ; pagination pour les grosses bibliothèques ; recherche/filtre par nom (nice-to-have).

**Ponytail :** réutiliser le client Spotify + la route d'ajout de source existants ; une route liste + un modal picker, pas de cache local des playlists en v1 (fetch à l'ouverture). Le collage par lien reste (playlists d'autrui / non suivies). Skipped : synchro auto de la liste, add when la bibliothèque est trop grosse pour un fetch à la volée.
