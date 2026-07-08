# Syncbox — Rapport d'overhaul produit (analyse de valeur des features)

> **Objet.** Analyse de valeur objective de **toutes** les fonctionnalités de Syncbox, carte de redondance vs Rekordbox natif et concurrents, catalogue de candidates issu d'une recherche web/GitHub approfondie, puis **overhaul du périmètre produit** pour aboutir à une app « utile à tous les DJs ».
>
> **Statut.** Sortie du prompt [`PROMPT-01b-analyse-valeur-features-overhaul.md`](PROMPT-01b-analyse-valeur-features-overhaul.md). Lecture seule, aucun code modifié. Intrant : l'inventaire fonctionnel de [`SPEC-01-syncbox.md`](SPEC-01-syncbox.md) (preuves `fichier:ligne`) + [`SPEC-UNIFIED.md`](SPEC-UNIFIED.md) (architecture déjà tranchée : Tauri + sidecar Python, acquisition optionnelle). **Le présent document décide le PÉRIMÈTRE et la VALEUR, pas la stack** (règle d'or 6).
>
> **Méthode.** Recherche multi-agents (8 clusters web/GitHub, vérification adversariale, critique de complétude — 17 agents, 158 items sourcés). Chaque jugement cite sa preuve : `fichier:ligne`, URL, ou capacité native identifiée. *Fait* / *inférence* / *opinion* séparés. Les arbitrages de goût ont été posés au propriétaire (§8).

---

> ⚠️ **MISE À JOUR — Gates 1/2 (2026-06-16, repli dans [SPEC-UNIFIED.md](SPEC-UNIFIED.md)).** Ce rapport reste la **trace** de l'analyse de valeur. Deux décisions postérieures **prévalent** sur les listes v1/v2 ci-dessous : (1) **A2 dedup par empreinte (Chromaprint) → différée v2** (résiduel étroit après ISRC+fuzzy + binaire `fpcalc` **LGPL 2.1** à notariser — cf. §5 corrigé et [_research/11](_research/11_Chromaprint-empreinte.md)) ; (2) **SoundCloud → v2/B4** (tire ffmpeg, ~+40-80 Mo). **Périmètre v1 réel = 4 ajouts** : A1 Smart Fixes, A3 faux-320/FLAC, B1 streamrip **Deezer-only**, B2 Track Matcher légal (+ D7). **Fait foi sur le périmètre v1 : [SPEC-UNIFIED §7.4](SPEC-UNIFIED.md).** Les §1, §6, §7.2 et §8 ci-dessous gardent leur verdict **pré-Gate-2** (A2 listée en v1) à titre historique — ne pas les lire comme le périmètre courant.

## 1. Résumé exécutif (le verdict)

Syncbox doit se positionner comme **le couteau suisse gratuit, open-source et local-first du DJ Rekordbox** — celui qui fait deux choses que personne ne fait gratuitement et localement à la fois :

1. **Transformer une playlist Spotify en vrais fichiers possédés, taggés et jouables sur CDJ/USB.** L'intégration Spotify native (re-ajoutée 24 sept. 2025) est **streaming-only** : pas de download, pas d'offline, pas d'export USB, pas d'import dans la collection ([rekordbox.com](https://rekordbox.com/en/2025/09/rekordbox-for-mac-win-spotify-support/), [TechCrunch 24/09/2025](https://techcrunch.com/2025/09/24/spotify-now-integrates-directly-with-dj-software-from-rekordbox-serato-and-djay/)). C'est exactement la lacune que Syncbox comble.
2. **Entretenir la collection mieux que le natif, sans abonnement ni cloud.** Le dedup natif est rudimentaire (recherche par titre, manuel, sans empreinte — [source](https://www.clonefileschecker.com/blog/how-to-remove-duplicate-songs-on-rekordbox-software-playlist/)), le Relocate natif est filename-only et abandonne sur les homonymes ([FAQ rekordbox](https://rekordbox.com/en/support/faq/v6/)), et le Backup natif est manuel, grossier et destructif à la restauration ([deejayplaza](https://www.deejayplaza.com/en/articles/rekordbox-backup)). Les outils qui font mieux sont **payants** (Lexicon $199–399 à vie, RCT, Music Library Doctor).

**Décisions structurantes (validées avec le propriétaire, §8) :**

| Axe | Décision |
|---|---|
| Portée | **Companion Rekordbox-only.** Pas de conversion cross-app (Lexicon possède déjà ce terrain). Profondeur Rekordbox + sourcing comme angle. |
| Téléchargement | **Module optionnel, OFF par défaut**, moteur **streamrip** (deemix se meurt, cf. §5). Mise en avant du **chemin légal ISRC → achat lossless**. |
| Gratuit vs Pro | **Oui** : offrir gratuitement et localement ce que Rekordbox gate (backup versionné réversible — déjà fait, à conserver). |
| Différenciation | **Hygiène + sync solides d'abord.** Le propriétaire a **écarté** l'analyse locale (energy/key/vocal), l'ordonnancement harmonique, ReplayGain et les auto-cues. La différenciation vient du **cœur fait mieux et gratuit**, pas de nouvelles couches d'analyse. |
| Analyse audio | **Aucune analyse locale.** On lit seulement les valeurs key/energy déjà fournies par Rekordbox ou un import MIK. |

**Ce qu'on GARDE** (cœur solide, couvert par tests) : Spotify sync, Match ISRC+fuzzy, Events, Duplicates, Missing Files, Untagged, Sûreté/Backup, Doctor, Settings, i18n FR/EN.
**Ce qu'on AJOUTE en v1** : dedup par **empreinte audio (Chromaprint)** *(→ **différé v2** par Gate 2, voir bannière en tête)*, **Smart Fixes** (nettoyage métadonnées en masse), **détection faux-320/faux-FLAC**, **Track Matcher légal** (lister les manquants + liens d'achat ISRC), bascule acquisition vers **streamrip** *(Deezer-only en v1 ; SoundCloud → v2)*.
**Ce qu'on RETIRE** : Live Import M3U8, `tag_rules` legacy, script CLI cleanup, auto-update dormant (déjà acté D8/D9/D10/D24).
**Ce qu'on EXCLUT explicitement** : analyse locale, set-prep harmonique, ReplayGain, auto-cues, transition-tagging, conversion cross-app, mobile/cloud, édition de beatgrid, streaming jouable in-app (bloqué par les licences).

---

## 2. Personas & cadre d'évaluation

### 2.1 Personas DJ (largeur d'audience)

| # | Persona | Workflow | Douleur principale | Ce qu'il valorise |
|---|---|---|---|---|
| **P1** | **DJ mobile / open-format** (mariages, soirées privées) | Gros catalogue multi-genres, beaucoup d'imports depuis playlists clients (Spotify), Rekordbox + contrôleur/USB | Sourcer vite des titres demandés ; bibliothèque qui gonfle et se salit | Sync Spotify→fichiers, events par soirée, hygiène |
| **P2** | **DJ club électronique / mixage harmonique** | Rekordbox + CDJ, achète sur Beatport, key/energy importants | Précision analyse, prépa de set, garder le matos lossless | Fichiers lossless possédés, USB fiable, cues préservés |
| **P3** | **Collectionneur / digger** multi-genres | Très grosse bibliothèque, multi-sources, disques externes | **Doublons, fichiers manquants après déplacement de disque, métadonnées incohérentes** | Hygiène avancée, dedup par empreinte, relocate robuste |
| **P4** | **DJ débutant** | Rekordbox Free, petit budget, peu sûr de lui | **Peur de casser/perdre sa base**, ne comprend pas « références vs fichiers » | Sûreté, backup automatique, simplicité |
| **P5** | **DJ pro multi-appareils** | Plusieurs machines, USB/CDJ, historique de jeu | Portabilité, sauvegarde, fiabilité du « jamais joué » | Backup versionné, intégrité, export USB sûr |
| **P6** | **Producteur-DJ** | Joue ses prods + edits, SoundCloud/Bandcamp, tags custom | Métadonnées custom, sources hors-catalogue (SC/Bandcamp) | Tags personnels, sourcing flexible, pas d'écrasement |

Échelle **Largeur d'audience** : 0 = un seul persona, 5 = tous. La douleur **n°1 du marché est l'hygiène de bibliothèque** (validée : *« My DJ collection is a complete mess »* est l'une des questions les plus fréquentes — [Digital DJ Tips](https://www.digitaldjtips.com/dj-library-is-a-mess/) ; tout un marché payant dessus : Lexicon, RCT, Music Library Doctor).

### 2.2 Barème de scoring

Chaque critère noté **0–5** (5 = meilleur, y compris pour *Effort* où 5 = faible effort, et *Risque* où 5 = risque négligeable). Le **score global** est un jugement pondéré explicité, pas une moyenne aveugle (pondération indicative : Utilité ×2, Audience ×2, Complémentarité ×2, Différenciation ×1.5, Effort ×1, Risque ×1.5).

- **Utilité** — valeur réelle pour le DJ ciblé.
- **Largeur d'audience** — combien de personas (0–5).
- **Complémentarité au natif** — 5 = comble une vraie lacune Rekordbox ; 0 = doublon total d'une fonction native gratuite (inverse de la redondance).
- **Différenciation** — vs Lexicon, MIK, DJ.Studio, Mixxx, RCT, Music Library Doctor…
- **Effort** — 5 = faible, 0 = très lourd (indicatif, sans décider la techno).
- **Risque** — légal / technique / maintenance — 5 = négligeable, 0 = bloquant.

Verdicts : `GARDER` · `GARDER-MAIS-CORRIGER` · `SIMPLIFIER` · `FUSIONNER` · `CHANGER` · `RETIRER` · `À-DÉCIDER`.

### 2.3 Invariants du domaine (vrais quel que soit le périmètre)

1. **Sûreté Rekordbox** : aucune écriture si Rekordbox/`rekordboxAgent` tourne ; **backup horodaté avant chaque mutation** ; unit-of-work `_mutate` ; suppressions = soft-delete réversible ; restore avec snapshot préalable (`safety.py:20-80`, `adapter.py:505-534`, [SPEC-01 §3.1](SPEC-01-syncbox.md)).
2. **Résolution de chemins** : volume-relatif sous `rekordbox/`, absolu ailleurs ; les deux formes égales (`paths.py:58-74`, mémoire projet `rekordbox-path-resolution`).
3. **Ne jamais déplacer les fichiers** (TCC macOS sur dossiers cloud ; listing KO mais `Path.exists()` OK).
4. **Préserver cues / beatgrids / My Tags à chaque écriture.** Les cues vivent dans **master.db (`djmdCue`) ET dans les fichiers ANLZ** ([pyrekordbox docs](https://pyrekordbox.readthedocs.io/en/latest/tutorial/anlz.html), [Deep Symmetry](https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/exports.html)). ⚠️ **CORRECTION (2026-06-16, repli SPEC-UNIFIED)** : la version initiale attribuait à [SPEC-01 §3.1](SPEC-01-syncbox.md) la phrase « les cues vivent dans `DjmdCues`, pas dans les ANLZ » — **cette phrase n'existe pas dans SPEC-01** (zéro occurrence « ANLZ ») ; c'était une paraphrase erronée. **Décision Gate 1 (tranchée)** : pyrekordbox **n'écrit jamais les ANLZ** (cf. invariant 6) → Syncbox ne les modifie pas, et ses mutations restent **intégralement réversibles** via le backup `master.db`. Le backup F8 **ne couvre pas les ANLZ** (limite **documentée**, pas étendue — cf. [SPEC-UNIFIED §3.1/§5.1](SPEC-UNIFIED.md)) ; un restore peut désynchroniser des cues que **Rekordbox lui-même** aurait écrits côté ANLZ entre deux opérations Syncbox — cas de bord assumé.
5. **Fichiers locaux jouables sur CDJ/USB** (la raison d'être face au streaming).
6. **Limite d'écriture pyrekordbox** : écrit `master.db` (DjmdContent/MyTag/Cues/Playlist/Key/Color) mais **ne crée pas les fichiers ANLZ** (parse seulement) — [readthedocs](https://pyrekordbox.readthedocs.io/en/latest/tutorial/anlz.html). Borne la faisabilité de toute écriture de cues/beatgrids.

---

## 3. Audit de valeur des features existantes

> Inventaire source : [SPEC-01 §2](SPEC-01-syncbox.md). Scores selon §2.2. Les correctifs de bugs déjà actés (D1–D25) ne sont pas re-débattus ; on ajoute la **dimension valeur/marché**.

### F1 — Sync de playlists Spotify (sources permanentes + MyTags par défaut)
`library.py:45-263`, `stores/library.ts`, `event_import.py`. Suivre une playlist Spotify, diffing par track (new/matched/ready/imported/missing/removed), héritage des MyTags de la source à l'import.
- **Utilité / personas** : cœur du flux d'alimentation. P1 (mobile, playlists clients), P6 (prods/edits), un peu P2/P3.
- **Redondance vs natif** : **complément fort.** Spotify natif = streaming-only, pas d'import collection, pas d'auto-tag depuis une source ([rekordbox.com](https://rekordbox.com/en/2025/09/rekordbox-for-mac-win-spotify-support/)). Le natif n'a **aucune** notion de « suivre une playlist et la matérialiser en fichiers taggés ».
- **Vs concurrents** : Lexicon **Track Matcher** est metadata/fuzzy-only, **sans ISRC et sans download** ([manual](https://www.lexicondj.com/manual/track-matcher)) ; Music Library Doctor fait un import Spotify→crate similaire mais payant ([site](https://musiclibrarydoctor.com/)) ; Trackmatch (OSS) s'arrête au diff sans acquérir ([repo](https://github.com/L3-N0X/Trackmatch)).
- ⚠️ **Risque plateforme** : Spotify a durci l'accès Web API (vague de restrictions, fév. 2026 — [Headphonesty](https://www.headphonesty.com/2026/02/spotify-crackdown-thousands-third-party-music-apps/)) ; **mais la lecture basique de playlists (le scope de Syncbox) reste disponible**. Minimiser la dépendance aux endpoints sensibles.
- **Scores** : Util 5 · Audience 4 · Complément 5 · Diff 4 · Effort 3 · Risque 3 → **Global : ÉLEVÉ**.
- **Verdict : GARDER** (OAuth PKCE only, D3). Ne dépend d'aucun endpoint déprécié.

### F2 — Matching Spotify → Rekordbox (ISRC exact puis fuzzy)
`matching.py:27-132`. ISRC d'abord (confiance 100), puis fuzzy `title*0.52+artist*0.36+duration*0.12`, seuil 82, flag `ambiguous`.
- **Utilité / personas** : moteur transversal (sync, events, dedup, missing). Tous personas.
- **Redondance vs natif** : **aucun équivalent natif.** Complément total.
- **Vs concurrents** : l'**ISRC-first** est un vrai edge — Lexicon Track Matcher est fuzzy-only ([manual](https://www.lexicondj.com/manual/track-matcher)). OneTagger fait de l'ISRC-first matching mais écrit des tags de fichier, pas dans master.db ([repo](https://github.com/Marekkon5/onetagger)).
- **Scores** : Util 5 · Audience 5 · Complément 5 · Diff 5 · Effort 3 · Risque 4 → **Global : TRÈS ÉLEVÉ** (joyau, à préserver tel quel + D19 normalisation unifiée).
- **Verdict : GARDER.**

### F3 — Acquisition / téléchargement (Deezer + Deemix → **streamrip**)
`acquisition.py`, `collection_acquisition.py`, `electron/deemix.ts`. Résolution Deezer (ISRC puis recherche, seuils 85/70), pilotage Deemix `:6595`, jobs SSE.
- **Utilité / personas** : forte valeur d'usage (Spotify→fichier jouable), surtout P1. **Mais** : les pros (P2/P5) achètent en lossless ; zone légale grise.
- **Redondance vs natif** : **complément** (le natif ne télécharge pas).
- ⚠️ **Faisabilité (recherche, critique)** : **deemix se meurt en 2026** — Deezer a changé son API/login, les ARL échouent souvent, et Deezer mène une **campagne DMCA active contre les downloaders ARL** ([TorrentFreak](https://torrentfreak.com/deezer-targets-pirate-apps-maliciously-retrieving-publishing-encryption-keys-210212/)). **streamrip** est mieux maintenu, multi-services (Qobuz/Tidal/Deezer/SoundCloud), avec dedup d'historique ([repo](https://github.com/nathom/streamrip)).
- **Vs concurrents** : DJ.Studio « legalize » fait l'achat Beatport puis remplace la version streaming ([help.dj.studio](https://help.dj.studio/en/articles/12332505-beatport-beatsource-streaming-vs-shop-in-dj-studio)) ; Lexicon Beatport auto-replace ([manual](https://www.lexicondj.com/manual/beatport-integration)). Le chemin **légal ISRC→achat** est sous-exploité et propre côté ToS (Beatport API v4 — [docs](https://api.beatport.com/v4/docs/)).
- **Scores** : Util 4 · Audience 3 · Complément 5 · Diff 4 · Effort 2 · Risque 1 → **Global : MITIGÉ** (forte valeur, fort risque).
- **Verdict : CHANGER.** Module **optionnel, OFF par défaut**, moteur **streamrip** ; ajouter le **Track Matcher légal** (lister les manquants + liens d'achat ISRC) comme alternative mise en avant. Lire le vrai chemin de sortie du downloader (D18), retirer les globals process (F3-spec).

### F4 — Events (sets DJ temporaires + smart playlist + MyTag)
`event_import.py`, `EventWorkspace.vue`. Création 3 modes, staging, apply qui crée un **smart playlist Rekordbox natif** + un MyTag d'event (catégorie « Situation »).
- **Utilité / personas** : P1 surtout (une soirée = un event), un peu P2.
- **Redondance vs natif** : **complément.** Le smart playlist natif existe ([deejayplaza](https://www.deejayplaza.com/en/articles/rekordbox-intelligent-playlist)) — et Syncbox **l'émet** plutôt que de le réimplémenter (bon réflexe). La valeur Syncbox = scaffolding playlist Spotify → event → tags + smart playlist auto.
- **Vs concurrents** : DJ.Studio prépare des sets et écrit dans Rekordbox, mais c'est un set-builder payant ([dj.studio](https://dj.studio/automix)).
- **Scores** : Util 4 · Audience 3 · Complément 4 · Diff 3 · Effort 3 · Risque 3 → **Global : MOYEN-ÉLEVÉ**.
- **Verdict : GARDER-MAIS-SIMPLIFIER.** Retirer **Live Import M3U8** (D10), gater le delete sur `mutationAllowed` (D23), aperçu exact avant suppression (D11).

### F5 — Duplicates (ISRC + fuzzy, keeper, soft-delete)
`dedup.py`, `adapter.py:1197-1279`, `DuplicatesView.vue`.
- **Utilité / personas** : **douleur n°1**, tous personas, surtout P3.
- **Redondance vs natif** : **complément fort.** Le dedup natif = taper « duplicate » dans la barre de recherche (titre-string, manuel, sans empreinte, sans auto-delete — [source](https://www.clonefileschecker.com/blog/how-to-remove-duplicate-songs-on-rekordbox-software-playlist/)).
- **Vs concurrents** : Lexicon « Find Duplicates » et RCT utilisent l'**empreinte audio** (cross-format) que Syncbox **n'a pas** ([Lexicon manual](https://www.lexicondj.com/manual/find-duplicates), [RCT](https://atgr-production-team.sellfy.store/p/rct/)) ; l'OSS koraysels/rekordbox-library-fixer aussi ([repo](https://github.com/koraysels/rekordbox-library-fixer)). C'est le **gap de différenciation** → on ajoute Chromaprint (cf. C-B).
- **Scores** : Util 5 · Audience 5 · Complément 5 · Diff 3 (→4 avec empreinte) · Effort 3 · Risque 3 → **Global : ÉLEVÉ**.
- **Verdict : GARDER + CHANGER keeper (D5/D6) + AJOUTER couche empreinte.**

### F6 — Missing Files (relink / redownload / remove)
`maintenance.py`, `adapter.py:1027-1195`.
- **Utilité / personas** : douleur majeure (déplacement de disque), P3/P5.
- **Redondance vs natif** : **complément partiel.** Le Relocate natif existe mais est **filename-only et abandonne sur les homonymes** ([FAQ](https://rekordbox.com/en/support/faq/v6/) ; confirmé par le comportement de [rekordbox-repair](https://github.com/edkennard/rekordbox-repair)). Le scoring ISRC/nom de Syncbox est meilleur.
- **Vs concurrents** : Lexicon « Find Lost Tracks », RCT relocate, rekordbox-repair (OSS, refuse les matchs ambigus — bon principe à conserver).
- ⚠️ Bug B1 (redownload prend le 1er hit sans seuil) → **D14**.
- **Scores** : Util 5 · Audience 5 · Complément 4 · Diff 3 · Effort 3 · Risque 3 → **Global : ÉLEVÉ**.
- **Verdict : GARDER-MAIS-CORRIGER** (seuils + ambiguous comme le flux event).

### F7 — Untagged (diagnostic 4 catégories)
`maintenance.py`, `adapter.py:561-647`. junk / dup_of_tagged / alt_version / review.
- **Utilité / personas** : hygiène de métadonnées, P3/P6.
- **Redondance vs natif** : **aucun équivalent natif** → complément total.
- **Vs concurrents** : adjacent à librarydojo/Sensei (suggestions de smart playlists/tags pour Rekordbox — [librarydojo](https://librarydojo.com/)) et Choon (auto-tag IA → MyTags — [choon.app](https://choon.app/)), mais ceux-ci sont des suggesteurs IA payants ; Syncbox = diagnostic déterministe.
- ⚠️ Heuristiques junk **personnelles/françaises** (`discours`, `psg`, `bereal`…) + bug artiste 1-token (B5) + regex `feat` greedy (B7) → **D7**.
- **Scores** : Util 4 · Audience 4 · Complément 5 · Diff 4 · Effort 3 · Risque 2 → **Global : ÉLEVÉ**.
- **Verdict : GARDER-MAIS-CORRIGER.** Règles **structurelles universelles** (stub `spotify:track:`, titre vide, artiste `rekordbox`) **+ motifs configurables par l'utilisateur** ; corriger B5/B7.

### F8 — Sûreté & Backup (garde RB, backup avant mutation, soft-delete, restore)
`safety.py:20-80`, `adapter.py:171-318,505-534`, `DoctorView.vue`.
- **Utilité / personas** : **invariant + joyau.** Adresse la **peur n°1** (base corrompue / cues perdus — fils Pioneer forum récurrents : [exemple](https://community.pioneerdj.com/hc/en-us/community/posts/22979193547545)). Tous personas, surtout P4/P5.
- **Redondance vs natif** : **complément fort.** Le Backup Library natif est **manuel, grossier (tout master.db), et destructif à la restauration** ([deejayplaza](https://www.deejayplaza.com/en/articles/rekordbox-backup)). Syncbox = automatique, horodaté, avant **chaque** mutation, rotation N, soft-delete réversible, restore réversible.
- **Vs concurrents** : la sauvegarde DB de Lexicon est **cloud et payante (Ultimate $399)** ([features](https://www.lexicondj.com/features)) ; le local versionné de Syncbox est sans doute **plus sûr et plus granulaire** pour l'usager Rekordbox. **C'est l'application directe de la décision « offrir gratuitement l'équivalent Pro ».**
- ⚠️ Voir correction §2.3-4 : cues aussi dans ANLZ — vérifier la complétude du backup en Phase 2.
- **Scores** : Util 5 · Audience 5 · Complément 5 · Diff 4 · Effort 3 · Risque 4 → **Global : TRÈS ÉLEVÉ**.
- **Verdict : GARDER** (étendre la suppression de fichiers à la **corbeille OS** D12 ; couvrir ANLZ).

### F9 — Doctor (diagnostics + gestion backups + logs)
`diagnostics.py`, `DoctorView.vue`.
- **Redondance vs natif** : complément (le natif n'a pas de centre de diagnostic).
- **Scores** : Util 3 · Audience 4 · Complément 4 · Diff 2 · Effort 4 · Risque 4 → **Global : MOYEN**.
- **Verdict : GARDER** + opportunité d'y loger des **analytics de collection** très bon marché (orphelins, jamais joués — cf. C-F, SHOULD).

### F10 — Settings + i18n FR/EN
`SettingsView.vue`, `i18n/index.ts:21-63`.
- **Redondance** : n/a (infra). **Audience 5.**
- **Scores** : Util 3 · Audience 5 · Complément n/a · Diff 1 · Effort 4 · Risque 4 → **Global : MOYEN** (mais nécessaire).
- **Verdict : GARDER** (i18n D13). **Généralisation obligatoire** : retirer les chemins codés en dur (`config.py:15-19`, D1), valider tous les chemins (F15).

### F11 — Features mortes / vestigiales (déjà actées)
| Feature | Emplacement | Score | Verdict |
|---|---|---|---|
| **Live Import M3U8** | `live_import.py`, `EventsView.vue:66-125` | Audience 1 · Complément 2 | **RETIRER** (D10) — contourne la garde RB, source de B12 |
| **`tag_rules` (table legacy)** | `repositories/tags.py`, `library.ts:23` | superseded | **RETIRER** (D9) — cause de B4 (seed qui réverte les éditions) |
| **Script CLI `cleanup_rekordbox.py`** | `service/scripts/` | redondant | **RETIRER** (D8) — couvert par Duplicates + Untagged |
| **Auto-update electron-updater** | dormant, `DISTRIBUTION.md:119-126` | — | **RETIRER** (D24, cohérent mémoire `no-auto-build-release`) |
| **`event_playlists`, `ProposalType.*_to_spotify`, tons StatusBadge** | divers | morts | **RETIRER** (D25) après confirmation d'absence de consommateur |

### 3.bis — Classement des features existantes (de la plus à la moins justifiée)

1. **F8 Sûreté/Backup** (TRÈS ÉLEVÉ) — invariant + joyau + adresse la peur n°1, gratuit là où le concurrent est payant.
2. **F2 Match ISRC+fuzzy** (TRÈS ÉLEVÉ) — moteur transversal, edge ISRC unique.
3. **F5 Duplicates** (ÉLEVÉ) — douleur n°1 du marché.
4. **F1 Spotify sync** (ÉLEVÉ) — la lacune que le natif ne comblera jamais.
5. **F6 Missing Files** (ÉLEVÉ) — douleur majeure, edge scoring vs natif filename-only.
6. **F7 Untagged** (ÉLEVÉ) — diagnostic unique, à dépersonnaliser.
7. **F4 Events** (MOYEN-ÉLEVÉ) — niche P1, à simplifier.
8. **F3 Acquisition** (MITIGÉ) — forte valeur, fort risque → optionnel/streamrip/légal.
9. **F9 Doctor** (MOYEN) — utile, peu différenciant.
10. **F10 Settings/i18n** (MOYEN) — nécessaire, à généraliser.
11. **F11 morts** — RETIRER.

---

## 4. Carte de redondance vs Rekordbox natif (et concurrents)

> `complément` = comble une lacune · `partiel` = recouvre en partie · `total` = doublon d'une fonction native gratuite (⇒ ne pas refaire). Sources : [rekordbox.com/feature](https://rekordbox.com/en/feature/overview/), [/plan](https://rekordbox.com/en/plan/), [/cloud](https://rekordbox.com/en/feature/cloud/), DJ press.

| Capacité native | Gratuit ? | Qualité native | Feature Syncbox concernée | Verdict redondance |
|---|---|---|---|---|
| **My Tag** (4 groupes fixes) | ✅ free | Complet mais **manuel**, pas d'auto-tag depuis source | F1/F4/F7 (écrit *dans* My Tag) | **complément** (auto-application) |
| **Smart/Intelligent Playlists** | ✅ free | Très complet, auto-régénéré | F4 (émet un smart playlist natif) | **complément** (on émet, on ne refait pas) |
| **Analyse BPM/key/beatgrid/cues** | ✅ free | Le moteur natif possède le terrain | (aucune — on ne fait PAS d'analyse) | **total — ne pas construire** |
| **Auto hot/memory cues** | ✅ free | IA native | (auto-cues écartés) | **total — ne pas construire** |
| **Recherche de doublons** | ✅ free | **Rudimentaire** (titre-string, manuel, pas d'empreinte) | F5 Duplicates | **complément fort** |
| **Relocate / Auto Relocate** | ✅ free | **Filename-only**, abandonne sur homonymes | F6 Missing Files | **complément partiel** |
| **Backup Library** | ✅ free | **Manuel, grossier, restore destructif** | F8 Sûreté/Backup | **complément fort** |
| **Cloud Library Sync / CloudDirectPlay** | ❌ **payant** (Pro/cloud ; Core/Creative nouvelles souscriptions **suspendues** depuis mars 2025 — [correction recherche](https://www.digitaldjtips.com/rekordbox-subs-return-but-youll-pay-more-for-now-at-least/)) | Réplication multi-device cloud | (aucune — Syncbox est local-first) | **n/a** (on ne concurrence pas le cloud) |
| **Collection Auto Upload / Device Library Backup** | ❌ payant (Professional) | Backup cloud | F8 (mais local) | **n/a / complément local** |
| **Spotify intégré (sept. 2025)** | ❌ Premium | **Streaming-only** : pas de download/offline/USB/import | F1 Spotify sync | **complément** (le cœur du positionnement) |
| **Beatport streaming natif** | ❌ payant | Play-only, **pas d'export USB**, cache chiffré | F3 (chemin légal) | boundary légal |
| **Traffic Light / Related Tracks / Radar** | free/freemium | Aides perf/découverte | (hors périmètre) | n/a |

**Anchor de positionnement** : tout ce que Syncbox fait est soit **complément d'une fonction native gratuite mais rudimentaire** (dedup, relocate, backup), soit **comblement d'une lacune native totale** (Spotify→fichier possédé, match ISRC, untagged), soit **équivalent gratuit/local d'une fonction native payante** (backup versionné). Aucun doublon total d'une fonction native gratuite **complète**.

**Vs concurrents (synthèse) :**

| Concurrent | Modèle | Chevauchement | Edge de Syncbox |
|---|---|---|---|
| **Lexicon DJ** ([pricing](https://www.lexicondj.com/pricing)) | Free conversion ; Essential **$199 à vie / $9.99 mo** ; Ultimate **$399 / $19.99 mo** | dedup, missing, smart fixes, Track Matcher, backup — **payants** | Gratuit/OSS, local-first, **ISRC+download**, pas de cloud lock-in |
| **Music Library Doctor** ([site](https://musiclibrarydoctor.com/)) | freemium | import Spotify, dup, missing, scoring qualité FFT | OSS, dedup empreinte + sourcing intégré |
| **RCT (Rekordbox Collection Tool)** ([sellfy](https://atgr-production-team.sellfy.store/p/rct/)) | payant macOS | dedup empreinte + relocate + fix cloud path — **même plateforme RB 6/7** | gratuit, multi-OS, sync Spotify intégrée |
| **koraysels/rekordbox-library-fixer** ([repo](https://github.com/koraysels/rekordbox-library-fixer)) | OSS (XML, master.db en roadmap) | dedup empreinte + relink + keeper quality | écriture master.db directe + sourcing |
| **Choon** ([choon.app](https://choon.app/)) | freemium | auto-tag IA → MyTags (achats Bandcamp/Beatport) | sourcing Spotify + hygiène, déterministe |
| **MIK 11 / Pro** ([shop](https://shop.mixedinkey.com/)) | **$58 / $99** one-time | key + energy + 8 cues | n/a (Syncbox **ne fait pas** d'analyse — lit MIK/RB) |
| **SetFlow / DJ.Studio / Mixgraph** | abos cheap → perpétuel | set-prep harmonique | **hors périmètre** (écarté §8) |

---

## 5. Catalogue des features candidates (recherche web/GitHub approfondie)

> Issu des 8 clusters de recherche. Chaque candidate : description, qui la fait déjà (URL), personas, pertinence Syncbox. Le scoring/priorisation est en §6. ⚠️ signale un fait de faisabilité critique.

### A. Hygiène de bibliothèque avancée
- **A1 — Smart Fixes / nettoyage métadonnées en masse.** Extraire artiste/remixer du titre, corriger la casse, retirer caractères/URL parasites, fixer l'encodage. Fait par **Lexicon Smart Fixes** ([features](https://www.lexicondj.com/features)). **Améliore aussi la précision du matching fuzzy de Syncbox.** Personas P3/P6/P1. Effort faible.
- **A2 — Dedup par empreinte audio (Chromaprint/AcoustID).** Attrape les doublons que ISRC+fuzzy rate (ré-encodages, rips différents, ISRC absent/pourri). Fait par Lexicon, RCT, koraysels ; brique OSS = **Chromaprint/pyacoustid** ([repo](https://github.com/acoustid/chromaprint)), comme dans **beets** ([repo](https://github.com/beetbox/beets)) et Mixxx. Personas P3/P5. Comparaison locale sans réseau (vérifié). ⚠️ **CORRECTION (2026-06-16, recherche [_research/11](_research/11_Chromaprint-empreinte.md), repli SPEC-UNIFIED)** : l'affirmation initiale « KissFFT garde Chromaprint permissif » est **fausse pour les binaires `fpcalc` officiels** — ils embarquent FFmpeg statique (décodage audio) → **LGPL 2.1**, pas permissif ([LICENSE.md](https://github.com/acoustid/chromaprint/blob/master/LICENSE.md) : « as a whole … LGPL 2.1 »). KissFFT ne rend permissif qu'un build maison **sans** FFmpeg, qui perd alors le décodeur. **Décision Gate 2 : A2 différée en v2** (résiduel étroit + binaire LGPL à notariser).
- **A3 — Détection faux-320 / faux-FLAC.** Analyse de coupure spectrale (FFT) pour repérer les bitrates mentis. Fait par **Music Library Doctor** ([site](https://musiclibrarydoctor.com/)). Hygiène qualité des fichiers téléchargés (renforce F3). Personas P2/P3.
- **A4 — Keeper « merge » sur dedup.** Fusionner métadonnées + hot cues du perdant dans le keeper avant suppression, plutôt que jeter. Fait par RekordboxFix ([repo](https://github.com/TisTatig/RekordboxFix)). Améliore F5.
- **A5 — Enrichissement ISRC via AcoustID→MusicBrainz** pour les tracks sans ISRC fiable (renforce match + dedup). Brique : pyacoustid + musicbrainzngs (pattern de Picard — [repo](https://github.com/metabrainz/picard)). Note : ⚠️ B6 actuel utilise à tort le tag `barcode` comme ISRC (D20).

### B. Sourcing / acquisition
- **B1 — Backend streamrip** (multi-services Qobuz/Tidal/Deezer/SoundCloud, dedup d'historique) en remplacement de deemix ([repo](https://github.com/nathom/streamrip)). ⚠️ **deemix se meurt** (Deezer API/ARL + DMCA — [TorrentFreak](https://torrentfreak.com/deezer-targets-pirate-apps-maliciously-retrieving-publishing-encryption-keys-210212/)).
- **B2 — Track Matcher légal + panier d'achat ISRC.** Lister les manquants d'une playlist et générer des **liens d'achat lossless** (Beatport API v4 read-only, ToS-clean — [docs](https://api.beatport.com/v4/docs/) ; Bandcamp/Juno). Pattern « legalize » de DJ.Studio ([help](https://help.dj.studio/en/articles/12332505-beatport-beatsource-streaming-vs-shop-in-dj-studio)).
- **B3 — Fallback YouTube (yt-dlp)** quand ISRC/Deezer échoue. spotDL/freyr le font ([spotDL](https://github.com/spotDL/spotify-downloader)). ⚠️ **lossy + gris** — dernier recours seulement.
- **B4 — Sources SoundCloud/Bandcamp** (edits/bootlegs/prods absents des catalogues) pour P6. scdl ([repo](https://github.com/scdl-org/scdl)), Bandcamp via Choon-like.

### C. Préparation de set & mixage harmonique *(globalement ÉCARTÉ §8)*
- **C1 — Ordonnancement harmonique/énergie** d'une playlist (Camelot+BPM+arc). SetFlow ([site](https://www.setflow.app/)), DJ.Studio Harmonize ([transitions](https://dj.studio/transitions)).
- **C2 — Score de transition multi-dimensions** (harmonique/BPM/énergie/groove/mood/**vocal-fit**). Mixgraph ([how-it-works](https://www.mixgraph.io/how-it-works)).
- **C3 — Tag de transitions** (« ces deux-là mixent bien »). Quasi inexistant ailleurs ; round-trippable en MyTags. Différenciateur niche.
- **C4 — Crates par rôle/énergie** (warm-up/peak) + « jamais joué ». Taxonomie [DJ TechTools](https://djtechtools.com/2022/11/25/controlling-the-dancefloor-a-guide-on-organizing-playlists-by-energy/). ⚠️ Le natif a déjà les smart playlists par règles ([vibesdj](https://vibesdj.io/learn/techniques/smart-playlist-creation)).

### D. Métadonnées / analyse *(ÉCARTÉ §8 — pas d'analyse locale)*
- **D1 — Analyse locale energy/key/has-vocals → MyTags.** Essentia ([repo](https://github.com/MTG/essentia)), libkeyfinder ([repo](https://github.com/mixxxdj/libkeyfinder)). Équivalent gratuit de MIK/Choon. ⚠️ **C'est désormais le seul chemin** : l'API `audio-features` de Spotify est **morte depuis le 27 nov. 2024** ([blog Spotify](https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api)) — on ne peut plus tirer energy/key de Spotify. Coût : embarquer des modèles ~centaines de Mo.
- **D2 — ReplayGain / normalisation loudness** (tags non destructifs, rsgain — [repo](https://github.com/complexlogic/rsgain) / ffmpeg loudnorm). Lacune que Rekordbox n'expose pas en portable.
- **D3 — Auto-cues écrits dans Rekordbox.** Génération (CUE-DETR [repo](https://github.com/ETH-DISCO/cue-detr), all-in-one, structure) + écriture. Preuves OSS : djcues ([repo](https://github.com/mcroydon/djcues)), CueGen ([repo](https://github.com/mganss/CueGen)). ⚠️ **Risque** : pyrekordbox **n'écrit pas l'ANLZ** ; cues dans master.db **ET** ANLZ ; **support RB7 non confirmé** (CueGen issue #25). `rbox` (Rust, même auteur que pyrekordbox) revendique l'écriture ANLZ — piste future ([docs.rs](https://docs.rs/rbox)).

### E. Portabilité / export *(hors périmètre cross-app, §8)*
- **E1 — Export setlist/playlist** M3U8/CSV/HTML/PDF. Lexicon ([share](https://www.lexicondj.com/manual/share)), quickCUE ([repo](https://github.com/globalnomad/quickCUE)). Bon marché, complète Events.
- **E2 — Validation export CDJ/USB** : signaler les fichiers injouables (32-bit float, hi-res, formats non supportés) avant export, conversion optionnelle AIFF 16-bit. rekordbox-proof-audio-conversion ([repo](https://github.com/tammohesselink/rekordbox-proof-audio-conversion)). Sert l'invariant « jouable sur CDJ ». *(Décliné v1, §8.)*
- **E3 — Vérification d'un export USB** (parser PDB/ANLZ) pour confirmer que cues/grids ont survécu. rekordcrate ([repo](https://github.com/Holzhaus/rekordcrate)), crate-digger, [Deep Symmetry](https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/exports.html).
- **E4 — Conversion cross-app** RB↔Serato↔Engine↔Traktor. Lexicon (gratuit), DJCU (€24.50), DJ Cue Bridge (gratuit navigateur — [site](https://djcuebridge.com/)). **Hors périmètre Rekordbox-only.**

### F. Analytics de collection (Doctor)
- **F1 — Tracks orphelins** (dans aucune playlist), **jamais joués** (`DJPlayCount=0`), **occurrence de playlist**, fichiers non référencés. Requêtes DB bon marché. Briques : rekordbox-mcp ([repo](https://github.com/davehenke/rekordbox-mcp), `get_unplayed_tracks`), rekordfix ([repo](https://github.com/rzuppur/rekordfix)), PRACT ([repo](https://github.com/LePopal/PRACT)).
- **F2 — Fusion de l'historique de jeu USB** (Device Library Plus) pour un « jamais joué » fiable. pyrekordbox **lit** `exportLibrary.db` ⚠️ mais **n'écrit pas** ce format ([README](https://github.com/dylanljones/pyrekordbox)) — donc analytics en lecture seule.

### G. Angles inattendus (recherche)
- **G1 — Identification de set enregistré → tracklist** (Shazam-like). Setlist.ID ([site](https://setlist.id/)), TrackRadar ([site](https://trackradar.ai/tools/dj-set-analyzer)). ⚠️ Dépend d'un service d'empreinte externe (ACRCloud/AudD) — mauvais fit local-first ; **intégrer plutôt que construire**.
- **G2 — Playlists depuis logique de tags** (algèbre booléenne → smart playlist). DJ-Tools ([repo](https://github.com/a-rich/DJ-Tools)). Complète le système MyTag.
- **G3 — Génération de smart playlists par config** (Situation→Texture→Genre). tseitz/rekordbox-smart-playlist ([repo](https://github.com/tseitz/rekordbox-smart-playlist)) — **même stack** (pyrekordbox + backup-before-write).

---

## 6. Scoring & priorisation des candidates

> Barème §2.2. Priorité tenant compte des décisions §8.

### MUST-ADD (v1)
| # | Candidate | Util · Aud · Compl · Diff · Effort · Risque | Justification |
|---|---|---|---|---|
| **A2** | Dedup empreinte audio (Chromaprint) | 5·5·5·4·3·4 | Comble le gap de différenciation de F5 ; la feature que Lexicon/RCT **font payer**. Validé §8. |
| **A1** | Smart Fixes (nettoyage métadonnées) | 4·5·4·4·4·4 | Effort faible, **améliore le matching fuzzy** de Syncbox en bonus. Validé §8. |
| **A3** | Détection faux-320/faux-FLAC | 4·4·5·4·3·4 | Hygiène qualité unique côté OSS RB ; renforce la confiance dans F3. Validé §8. |
| **B1** | Backend streamrip | 4·3·5·3·3·2 | deemix mourant ; robustesse + multi-sources. Validé §8. |
| **B2** | Track Matcher légal + liens d'achat ISRC | 4·4·5·3·3·5 | Chemin **propre ToS**, élargit l'audience pro (P2/P5), désamorce le risque légal. Validé §8. |
| **(D7)** | Règles untagged structurelles + configurables | 4·4·5·4·3·3 | Déjà acté ; transforme F7 mono-utilisateur en produit multi-DJ. |

### SHOULD-ADD (v2, sous réserve)
| # | Candidate | Score | Justification |
|---|---|---|---|
| **F1** | Analytics Doctor (orphelins / jamais joués / occurrence) | 4·4·4·2·4·4 | Requêtes DB bon marché, hygiène-adjacent (pas du set-prep). N'a pas été soumis au proprio → **à valider**. |
| **E1** | Export setlist M3U8/CSV | 3·3·3·2·5·5 | Trivial, complète Events. **À valider.** |
| **A4** | Keeper « merge » (cues/métadonnées du perdant) | 3·3·4·3·3·3 | Améliore F5 sans nouvelle surface. |
| **A5** | Enrichissement ISRC AcoustID→MusicBrainz | 3·4·4·3·2·3 | Renforce match+dedup ; coût modéré (réseau MusicBrainz). |

### NICE-TO-HAVE (plus tard)
- **E1bis** export HTML/PDF setlist · **F2** lecture historique USB (Device Library Plus) · **G2** playlists par logique de tags · **G3** smart playlists par config · **B4** sources SoundCloud/Bandcamp pour P6.

### ÉCARTER (avec raison)
| Candidate | Raison |
|---|---|
| **D1** Analyse locale energy/key/vocal | **Décision proprio §8** (« pas d'analyse locale »). Objectivement : effort + poids sidecar (~centaines de Mo) ; *seul* chemin depuis la mort de l'API Spotify audio-features, mais arbitré contre. |
| **C1/C2** Ordonnancement harmonique / score transition | **Décision proprio §8.** Terrain SetFlow/DJ.Studio/Mixgraph déjà dense ; le natif a Traffic Light/Radar. |
| **D2** ReplayGain | **Décliné §8** (réversible : effort faible, valeur réelle — noté pour mémoire). |
| **D3** Auto-cues | **Décliné §8** + objectivement risqué (ANLZ non writable, RB7 non confirmé). |
| **C3** Tag de transitions | **Décliné §8** ; niche/personnel (57 % des tags sont uniques par DJ — [reallychrism](https://reallychrism.substack.com/p/the-library-changes-im-betting-on)). |
| **E2** Validation export CDJ/USB | **Décliné §8** (réversible ; sert pourtant l'invariant — noté). |
| **E4** Conversion cross-app | **Hors périmètre Rekordbox-only §8** ; Lexicon/DJCU couvrent bien. |
| **G1** ID de set enregistré | Dépend d'un service d'empreinte externe → anti local-first. **Intégrer si jamais, pas construire.** |
| Mobile / cloud sync | Hors périmètre local-first ; contrainte TCC desktop. |
| Édition de beatgrid | **Invariant : préserver, pas éditer** ; DSP lourd ([reallychrism](https://reallychrism.substack.com/p/how-to-grid-impossible-tracks)). |
| Streaming jouable in-app (Spotify/Beatport) | **Bloqué par les licences labels** (réservé aux partenaires RB/Serato/djay). Irréaliste pour une app tierce. |

---

## 7. Overhaul cible (le périmètre retenu)

### 7.1 Positionnement
> **Syncbox — le compagnon Rekordbox gratuit et local-first qui transforme tes playlists Spotify en vrais fichiers possédés et jouables sur CDJ, et garde ta collection propre et sauvegardée — sans abonnement, sans cloud, sans MIK.**

Deux promesses, deux preuves de complémentarité non-redondante : (1) le **sourcing** que le Spotify natif ne fera jamais (streaming-only), (2) l'**hygiène + sûreté** que le natif fait mal et que les concurrents font payer.

### 7.2 Vagues

**v1 — « Cœur solide » (sync + hygiène + sûreté)**
- GARDER : F1 Spotify sync (PKCE), F2 Match ISRC+fuzzy, F4 Events (simplifié), F5 Duplicates, F6 Missing Files, F7 Untagged, F8 Sûreté/Backup, F9 Doctor, F10 Settings/i18n.
- CORRIGER (D14–D23) : redownload seuillé, garde delete event, tags add/remove par delta, restore unignore, apply-avec-warnings, etc.
- AJOUTER : **A2** dedup empreinte · **A1** Smart Fixes · **A3** faux-320/FLAC · **B1** streamrip · **B2** Track Matcher légal · **D7** règles untagged universelles+configurables.
- RETIRER : F11 (Live Import, tag_rules, CLI cleanup, auto-update, champs morts).

**v2 — « Affinage hygiène » (pas de différenciation analyse)**
- **F1** analytics Doctor (orphelins/jamais joués/occurrence) · **E1** export setlist · **A4** keeper merge · **A5** enrichissement ISRC. *(Tous à valider — §8 a écarté la couche analyse, pas l'hygiène.)*

**Plus tard / expérimental**
- F2 historique USB · G2/G3 playlists par tags/config · B4 SoundCloud/Bandcamp · export HTML/PDF.

### 7.3 Exclusions explicites (et pourquoi)
Analyse locale energy/key/vocal · set-prep harmonique · ReplayGain · auto-cues · transition-tagging · conversion cross-app · validation export CDJ · mobile/cloud · édition beatgrid · streaming jouable. *(Justifs : §6 ÉCARTER. La plupart relèvent d'une décision de goût §8 ; les autres de l'impossible — licences — ou de l'anti-invariant.)*

### 7.4 Généralisations nécessaires (mono-utilisateur → produit multi-DJ)
1. **Retirer tous les chemins codés en dur** (`config.py:15-19`, `settings.ts:14-17`, `.env.example`) → tout configurable (D1). *Bloquant pour « utile à tous ».*
2. **Règles untagged structurelles + configurables** au lieu des motifs perso/français (D7).
3. **Cross-OS macOS + Windows** : détection process Rekordbox, chemins système, corbeille, opérations fichiers (D2).
4. **Hygiène secrets** : pas de credential en clair dans un repo open-source ; tokens chiffrés/keychain ([SPEC-UNIFIED §6.7](SPEC-UNIFIED.md)).
5. **Onboarding générique** (connecter Spotify → chemins → Doctor vert) au lieu d'un setup implicite Dropbox.

---

## 8. Journal des décisions interactives

**Lot 1 — Positionnement (avant recherche) :**
| Question | Réponse retenue |
|---|---|
| Portée au-delà de Rekordbox | **Companion Rekordbox-only** (profondeur + sourcing comme angle). |
| Place du téléchargement (zone grise) | **Module optionnel OFF par défaut + chemin d'achat légal ISRC** mis en avant. |
| Offrir gratuitement des équivalents Pro | **Oui**, là où c'est faisable/légal (backup versionné réversible). |
| Appétit différenciation coûteuse/risquée | **Hygiène + sync d'abord (v1), différenciation en v2.** |

**Lot 2 — Arbitrages candidates (après recherche) :**
| Question | Réponse retenue |
|---|---|
| Différenciateurs v2 (analyse/ordering/ReplayGain/auto-cues) | **Aucun de ceux-là.** → la différenciation vient du cœur fait mieux/gratuit. |
| Backend d'acquisition (deemix mourant) | **Basculer sur streamrip** (multi-services), module optionnel OFF. |
| Poids de l'analyse locale | **Pas d'analyse locale** — lire seulement RB/MIK. |
| Hygiène v1 à ajouter | **Dedup empreinte (Chromaprint) + Smart Fixes + détection faux-320/FLAC.** (Validation export CDJ **non** retenue.) |

---

## 9. Questions ouvertes & briques réutilisables (Phase 2)

### 9.1 Questions ouvertes de périmètre (à reprendre par le prompt d'architecture)
1. **Complétude du backup vs cues ANLZ.** Correction de fait : les cues vivent dans **master.db `djmdCue` ET les ANLZ** ([pyrekordbox](https://pyrekordbox.readthedocs.io/en/latest/tutorial/anlz.html)). [SPEC-01 §3.1](SPEC-01-syncbox.md) affirme l'inverse. **Le backup F8 couvre-t-il les ANLZ ?** Sinon, un restore peut perdre des cues écrits côté ANLZ. À trancher en Phase 2.
2. **Track Matcher légal — sources d'achat** : ✅ **RÉSOLU** ([_research/13](_research/13_Achat-legal-ISRC.md), [SPEC-UNIFIED §5.13](SPEC-UNIFIED.md)) — Beatport API v4 = portail **de facto fermé** (partner-only) ; reco = **URL de recherche construites côté app vers Beatport + Bandcamp** (stdlib, zéro réseau). **Juno Download a fermé le 2026-06-01** (retiré).
3. **streamrip — modèle d'embarquement** : ✅ **RÉSOLU** ([_research/14](_research/14_streamrip-embedding-Deezer-SoundCloud.md), [SPEC-UNIFIED §5.5/§6.5](SPEC-UNIFIED.md)) — **lib importée = défaut** (API `PendingSingle.resolve()→track.download_path`, D18 réel), **CLI sous-process écartée** (pas de sortie machine-lisible) ; **Deezer-only v1** (SoundCloud→v2, ffmpeg) ; ARL en mémoire jamais en clair ; **deemix-fork = fallback documenté**.
4. **Validation des candidates SHOULD** (analytics Doctor, export setlist) non encore soumises au proprio.
5. **Dépendance Spotify** : durcissement Web API (fév. 2026) — confirmer que seuls les scopes `playlist-read-*` sont utilisés et qu'aucun endpoint déprécié (audio-features, recommendations) n'est requis.
6. **Risque légal acquisition** à documenter (ToS Deezer, DMCA, licence GPL streamrip) — cohérent avec « module optionnel ».

### 9.2 Briques réutilisables repérées (sans choix d'archi)
| Brique | URL | Usage Syncbox |
|---|---|---|
| **pyrekordbox** | [github](https://github.com/dylanljones/pyrekordbox) | Cœur DB (déjà utilisé). Écrit master.db ; **pas** l'ANLZ. Lit désormais `exportLibrary.db` (USB). |
| **Chromaprint / pyacoustid** | [github](https://github.com/acoustid/chromaprint) | Empreinte audio pour A2 (dedup) et A5 (enrichissement). |
| **beets** | [github](https://github.com/beetbox/beets) | Référence AcoustID + MusicBrainz (ISRC canonique) pour A5. |
| **streamrip** | [github](https://github.com/nathom/streamrip) | Backend acquisition B1 (Qobuz/Tidal/Deezer/SC + dedup historique). |
| **Music Library Doctor (concept FFT)** | [site](https://musiclibrarydoctor.com/) | Algorithme de coupure spectrale pour A3 (faux-320/FLAC) — reproductible. |
| **koraysels/rekordbox-library-fixer** | [github](https://github.com/koraysels/rekordbox-library-fixer) | Échelle de qualité keeper (format/bitrate, cas BitRate=0) pour D6. |
| **rekordbox-bulk-edit (jviall, v0.6.0)** | [github](https://github.com/jviall/rekordbox-bulk-edit) | Pattern filter→dry-run→confirm→mutate sur pyrekordbox (Smart Fixes A1). |
| **tseitz/rekordbox-smart-playlist** | [github](https://github.com/tseitz/rekordbox-smart-playlist) | Création smart playlist + backup-before-write (mirror de la stack Syncbox). |
| **davehenke/rekordbox-mcp** | [github](https://github.com/davehenke/rekordbox-mcp) | Requêtes prêtes : `get_unplayed_tracks` (jamais joué), key compatible (analytics F1). |
| **rekordbox-repair (edkennard)** | [github](https://github.com/edkennard/rekordbox-repair) | Règle « refuser le relink sur match multiple » (F6). |
| **rekordcrate / crate-digger / Deep Symmetry** | [djl-analysis](https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/exports.html) | Specs PDB/ANLZ pour vérifier un export USB (E3, et la question backup-ANLZ). |
| **rbox (Rust, même auteur que pyrekordbox)** | [docs.rs](https://docs.rs/rbox) | Piste future si écriture ANLZ requise (cues/beatgrids) depuis un sidecar Rust/Tauri. |

---

*Fin du rapport. Toutes les affirmations de valeur, redondance et faisabilité sont sourcées (`fichier:ligne`, URL, ou fonction native). Incertitudes signalées : prix exacts Lexicon/MIK (pages JS, sources secondaires) ; statut RB7 des écritures de cues ; stabilité réelle de streamrip vs evolutions Deezer/Qobuz. La recherche complète (158 items vérifiés) est archivée dans le journal de la run.*
