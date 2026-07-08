# PROMPT — Analyse de valeur des features & overhaul produit objectif
### Phase 1.5/2 : utilité, redondance vs Rekordbox, et features à ajouter

> **Mode d'emploi.** À lancer **après** la Phase 1 (analyse fonctionnelle & technique, voir `PROMPT-01-analyse-fonctionnelle-technique.md`). Soit dans la même session (« tu as déjà la big picture »), soit dans une session fraîche — dans ce cas, lis d'abord le document de spec produit par la Phase 1. Le livrable est un **rapport d'overhaul produit** : il statue sur la valeur de chaque feature et propose un périmètre cible. Il ne décide pas l'architecture (Phase 2).

---

## ── DÉBUT DU PROMPT ──

### Contexte

Maintenant que tu as une vue d'ensemble de **Syncbox** (app companion Rekordbox : sync de playlists Spotify, téléchargement Deemix/Deezer, nettoyage de collection — doublons / fichiers manquants / non-taggés, préparation d'events/sets DJ), je veux que tu fasses une **analyse de valeur approfondie et objective** de toutes ses fonctionnalités, puis que tu proposes un **overhaul** du périmètre produit.

Trois questions guident l'analyse, pour **chaque** feature existante :
1. **Utilité propre** — à quoi elle sert vraiment, pour qui, à quelle fréquence.
2. **Redondance** — fait-elle double emploi avec une fonction **native de Rekordbox** (ou d'un concurrent évident) ? Si oui, à quel degré, et est-ce gratuit ou payant côté natif ?
3. **Intérêt / différenciation** — apporte-t-elle une valeur que le natif ne couvre pas (ou mal) ?

Puis : **qu'est-ce qu'on pourrait ajouter ?** Il y a sûrement des features très intéressantes que je voudrais intégrer. Pour les trouver, **explore le web en profondeur**, et **particulièrement tous les projets GitHub** qui touchent à Rekordbox et au DJing en général. Ramène-moi tout ce qui s'y rapporte.

Objectif final : un **overhaul très objectif**, pour aboutir à une application **utile pour tous les DJs**, pas seulement pour mon usage personnel actuel.

### Ton rôle et ta posture

Tu es un **stratège produit** doublé d'un **analyste du domaine DJ**. Tu es objectif et fondé sur des preuves : chaque jugement de valeur s'appuie sur un fait vérifiable (un usage réel, une source web, une redondance constatée dans le code ou dans Rekordbox), jamais sur une opinion gratuite. Tu représentes **l'ensemble des DJs**, pas le propriétaire actuel de l'app.

### Règles d'or — NON NÉGOCIABLES

1. **Objectivité tracée.** Toute affirmation de valeur, de redondance ou de manque doit citer sa preuve : `fichier:ligne` du code, URL d'une source, ou fonction native Rekordbox identifiée. Pas de « ce serait bien » sans justification. Sépare clairement *fait* / *inférence* / *opinion*.

2. **« Utile pour tous » = raisonner par personas, pas par mon setup.** L'app actuelle est taillée pour un seul utilisateur (ex. chemins de stockage Dropbox codés en dur, workflow Spotify→Deemix très personnel). Pour chaque feature et chaque ajout, demande-toi : *quels profils de DJ en bénéficient, et combien ?* Définis 4-6 personas (voir Phase A) et évalue la largeur d'audience de chaque feature.

3. **Redondance vs natif : à vérifier systématiquement.** Pour chaque feature, confronte-la explicitement aux capacités **natives de Rekordbox** (utilise l'Appendice A comme base, mais vérifie/actualise — Rekordbox évolue vite, ex. réintégration Spotify en sept. 2025). Conclus par : `complément` / `doublon partiel` / `doublon total`, en notant si le natif est gratuit ou payant (le payant change la donne : dupliquer une feature Pro de Rekordbox peut avoir de la valeur si on l'offre gratuitement).

4. **Recherche web & GitHub OBLIGATOIRE et approfondie.** Les appendices B/C/D sont un **point de départ daté (juin 2026), pas une limite**. Étends-les : cherche de nouveaux projets GitHub (Rekordbox, Serato, Traktor, Engine DJ, outils de tagging/analyse, downloaders), de nouveaux concurrents, et les douleurs récurrentes des DJs (forums, Reddit, presse spécialisée). Pour chaque piste : URL, ce qu'elle fait, et ce qu'on pourrait en réutiliser ou s'en inspirer.

5. **Au moindre doute sur garder / ajouter / retirer → DEMANDE.** Dès qu'un arbitrage dépend de mes goûts, de mon modèle d'usage ou de mes priorités — et que tu ne peux pas trancher objectivement — pose-moi la question (`AskUserQuestion`, en lots thématiques). Surtout pour : les features à fort potentiel mais effort élevé, les redondances ambiguës, et les ajouts « différenciants mais risqués ». En cas d'hésitation : demande.

6. **Tu ne décides PAS l'architecture ni la stack.** Ici on parle **périmètre produit et valeur**, pas implémentation. Tu peux noter l'effort relatif et les briques réutilisables (Appendice B), mais les choix techniques restent pour la Phase 2. Si tu écris « il faudrait coder X en Y », transforme-le en note d'effort ou en question ouverte.

7. **Honnêteté sur la faisabilité légale et technique.** Distingue franchement ce qui est faisable, gris, ou bloqué : le **téléchargement de streaming** (Deemix/yt-dlp) est en zone légale grise ; le **streaming jouable** (Spotify/Beatport en lecture directe) est verrouillé par les licences labels et réservé à des partenaires (Rekordbox/Serato/djay) — irréaliste pour une app tierce. Ne propose pas de l'impossible sans le signaler.

8. **Lecture seule, pas de code.** Le seul artefact est le rapport d'overhaul (+ les questions posées).

### Méthode (phases d'analyse)

**Phase A — Cadre d'évaluation.**
Avant de juger quoi que ce soit, pose le cadre :
- **Définis 4-6 personas DJ** (ex. DJ mobile/mariage open-format · DJ club électronique/mixage harmonique · collectionneur multi-genres · DJ débutant · DJ pro multi-appareils/multi-logiciels · producteur-DJ). Pour chacun : son workflow, ce qui lui fait mal, ce qu'il valorise.
- **Définis le barème de scoring** (voir plus bas) et les **verdicts** possibles.
- Identifie les **invariants du domaine** qui doivent rester vrais quel que soit le périmètre (sûreté Rekordbox, fichiers locaux jouables sur CDJ, préservation cues/beatgrids/My Tags lors des écritures).

**Phase B — Audit de valeur des features EXISTANTES.**
Pour **chaque** feature recensée en Phase 1, produis une fiche :
- description courte + emplacement (`fichier:ligne`) ;
- utilité & personas concernés ;
- **redondance vs Rekordbox natif** (complément / doublon partiel / doublon total ; gratuit ou payant) et vs concurrents (Lexicon, MIK, DJ.Studio, Mixxx…) ;
- intérêt/différenciation ;
- **score** (barème ci-dessous) ;
- **verdict** : `GARDER` / `FUSIONNER` (avec quelle autre) / `SIMPLIFIER` / `RETIRER` / `À-DÉCIDER` (question posée).
Termine par un classement des features de la plus à la moins justifiée.

**Phase C — Découverte d'opportunités (recherche en profondeur).**
Pars de l'existant + des appendices B/C/D, puis **creuse le web et GitHub**. Constitue un **catalogue de features candidates**, chacune avec : description, qui la fait déjà (URL/projet), personas servis, et ce qui la rend pertinente pour Syncbox. Couvre au moins : hygiène de bibliothèque avancée, sourcing/acquisition, préparation de set & mixage harmonique, sauvegarde/portabilité, métadonnées/analyse, et tout angle inattendu que la recherche fait émerger.

**Phase D — Scoring des candidates & priorisation.**
Applique le même barème aux candidates. Classe-les en : `MUST-ADD` / `SHOULD-ADD` / `NICE-TO-HAVE` / `ÉCARTER` (avec raison : redondant, illégal/bloqué, hors périmètre, effort disproportionné). Pour les arbitrages incertains → **demande-moi**.

**Phase E — Overhaul objectif (la cible).**
Synthétise une **vision de périmètre cible** pour « une app utile à tous » :
- ce qu'on **garde / fusionne / simplifie / retire** de l'existant ;
- ce qu'on **ajoute** (par vague : v1 essentielle, v2, plus tard) ;
- ce qu'on **exclut explicitement** et pourquoi ;
- le **positionnement** résultant (en quoi l'app est utile et différente du natif Rekordbox + des concurrents) ;
- les **généralisations nécessaires** pour passer d'un outil mono-utilisateur à un produit multi-DJ (config des chemins, hypothèses à retirer, etc.).

**Phase F — Passerelle vers la Phase 2.**
Liste les **questions ouvertes de périmètre** non tranchées (à reprendre par le prompt d'architecture), et les **briques réutilisables** repérées (Appendice B + trouvailles) sans en faire un choix d'archi.

### Barème de scoring (à appliquer en B et D)

Note chaque critère 0-5, puis donne un score global pondéré et explique-le (pas de moyenne aveugle) :
- **Utilité** — valeur réelle pour le DJ ciblé.
- **Largeur d'audience** — combien de personas en profitent (0 = un seul, 5 = tous).
- **Complémentarité au natif** — 5 = comble une vraie lacune Rekordbox ; 0 = doublon total d'une fonction native gratuite. *(C'est l'inverse de la redondance.)*
- **Différenciation** — par rapport aux concurrents (Lexicon, MIK, DJ.Studio, Mixxx…).
- **Effort** (indicatif, sans décider la techno) — 5 = faible, 0 = très lourd.
- **Risque** — légal / technique / maintenance — 5 = négligeable, 0 = bloquant.

### Protocole d'interaction

- Groupe tes questions par thème, `AskUserQuestion`, max 4 par appel ; propose toujours une recommandation par défaut **et** demande validation.
- **Demande** quand l'arbitrage dépend de mes goûts/priorités ou quand une feature est « forte mais coûteuse/risquée ». **Ne demande pas** ce que la recherche tranche objectivement, ni les détails d'implémentation.
- Chaque réponse alimente le verdict correspondant et est consignée.

### Livrable attendu

Un seul document Markdown structuré — le **Rapport d'overhaul produit de Syncbox** — comprenant :
1. Résumé exécutif (le verdict en 10 lignes : ce qu'on garde, ce qu'on ajoute, le positionnement).
2. Personas & cadre d'évaluation (barème, invariants du domaine).
3. Audit de valeur des features existantes (fiches + scores + verdicts + classement).
4. Carte de redondance vs Rekordbox natif (et concurrents).
5. Catalogue des features candidates (issu de la recherche web/GitHub approfondie, avec URLs).
6. Scoring & priorisation des candidates (MUST / SHOULD / NICE / ÉCARTER).
7. **Overhaul cible** : périmètre v1/v2/futur, exclusions, généralisations multi-DJ, positionnement.
8. Journal des décisions interactives (mes réponses).
9. Questions ouvertes & briques réutilisables pour la Phase 2.

Reste factuel et cite tes sources. Signale toute incertitude (ex. statut gratuit/payant d'une feature Rekordbox, fiabilité d'une source). Le rapport doit pouvoir convaincre objectivement un tiers du périmètre retenu.

---

## Appendice A — Rekordbox natif : base pour l'analyse de redondance
*(daté juin 2026 — à vérifier/actualiser ; sources : rekordbox.com, support AlphaTheta, Digital DJ Tips, DJ TechTools, DeeJay Plaza)*

**Couvert nativement et plutôt complet (⇒ risque de redondance élevé) :**
- **My Tag** (tags personnalisés, 4 groupes), commentaires, ratings, couleurs, genre — gestion/classement complets. *Stratégie : écrire DANS My Tag plutôt que le remplacer.*
- **Intelligent / Smart Playlists** par règles (BPM, key, genre, My Tag, ratings, dates, play count…) auto-régénérées — **très complètes**. *Forte redondance si Syncbox refait des playlists à règles.*
- Analyse **BPM / key / beatgrid / waveform / phrase**, **détection vocale & STEMS** (désormais présentés comme accessibles en Free, à reconfirmer), **hot/memory cues, loops, active loops**.
- **Related Tracks / Track Match / Traffic Light** (suggestions harmoniques), **Collection/Streaming Radar**.

**Couvert mais faible/rudimentaire (⇒ vraie valeur ajoutée tierce possible) :**
- **Doublons** : pas d'effaceur auto ; seulement une « Duplicate Search » manuelle par titre, sans empreinte audio. → marché tiers établi.
- **Relocate / Relocate All** (fichiers manquants) : existe mais rudimentaire et risqué (premier match, mauvaise gestion des homonymes/renommages).
- **Backup** de la collection : non automatique par défaut, restauration peu granulaire (les cues vivent dans `DjmdCues` de master.db, pas dans les ANLZ).

**Payant / gated (⇒ dupliquer gratuitement peut avoir de la valeur) :**
- **Cloud Library Sync / CloudDirectPlay** (Free = 10 pistes max), **Collection Auto Upload** & **Device Library Backup** (Professional), **playlists collaboratives**. *NB : nouvelles souscriptions Core/Creative suspendues depuis mars 2025 → choix réel Free vs Professional.*

**Spotify natif (réintégré 24 sept. 2025) — POINT CLÉ :** **streaming live uniquement**, **pas de download / pas d'offline / pas d'export USB-CDJ**, cues/stems limités, pas d'import dans la collection, Premium requis, 51 marchés, 3 logiciels (RB/Serato/djay). → **Ne duplique PAS** un flux « Spotify → fichier local jouable » ; c'est complémentaire.
*Sources : rekordbox.com/feature/overview · rekordbox.com/plan · rekordbox.com/en/2025/09/…spotify-support · djtechtools.com (24/09/2025) · deejayplaza.com (My Tag, Intelligent Playlist, Related Tracks, Track Match, Backup).*

## Appendice B — Écosystème GitHub / open-source (briques à réutiliser ou dont s'inspirer)
*(à étendre par la recherche)*
- **pyrekordbox** — https://github.com/dylanljones/pyrekordbox — Python, lit/écrit master.db (SQLCipher) + XML + ANLZ ; **fondation déjà utilisée** par Syncbox.
- **OneTagger** — https://github.com/Marekkon5/onetagger — Rust/Vue, auto-tagging multi-sources (Beatport/Discogs/MusicBrainz/Spotify), **matching ISRC**, **écriture des My Tags Rekordbox**, détection BPM/KEY. *Le plus pertinent pour la couche métadonnées.*
- **CueGen** — https://github.com/mganss/CueGen — .NET, **écrit hot cues + My Tags + active loops** dans Rekordbox (depuis données Mixed In Key). Preuve de faisabilité d'auto-cues.
- **libKeyFinder** (Mixxx) — https://github.com/mixxxdj/libkeyfinder — C++, détection de tonalité open-source (alt. à Mixed In Key) ; + Essentia pour BPM/key.
- **rekordbox-library-fixer** — https://github.com/koraysels/rekordbox-library-fixer — déduplication (métadonnées + audio), relocalisation, backups.
- **rekordcrate** (Rust, https://github.com/Holzhaus/rekordcrate) / **crate-digger** (Java, https://github.com/Deep-Symmetry/crate-digger) + **doc Deep Symmetry** (https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/) — formats d'export USB/PDB/ANLZ (lecture).
- Concurrents directs OSS Spotify↔DJ : **PySync-DJ**, **DJ-Tools** (a-rich), **Trackmatch**, **rekordbox-spotify-downloader** (Dixter999) — patterns playlist→download→analyse→tags→playlist Rekordbox.
- Conversion inter-apps : **dj-data-converter** (Traktor/RB/Serato), **libdjinterop** (Engine DJ), **traktor-nml-utils**, **serato-tools**.
- Downloaders : **spotDL**, **deemix** (forks bambanah / deemix-gui), **beatportdl**, **scdl**, **beets** (tagging MusicBrainz).
*⚠️ La plupart des downloaders passent par YouTube (bitrate limité) ou des sources en zone grise ; l'écriture dans master.db exige Rekordbox fermé + backup.*

## Appendice C — Concurrents & features remarquables (opportunités)
*(à étendre)*
- **Lexicon DJ** (https://www.lexicondj.com) — LE concurrent de référence. Sync/conversion entre RB/Serato/Traktor/Engine/VirtualDJ/djay (préserve cues/loops/grids/tags). **Track Matcher** (matche une playlist Spotify/Tidal/Apple/SoundCloud/YT/Beatport contre la bibliothèque locale, exporte les manquants), **Smart Fixes** (nettoyage métadonnées en masse), doublons par signature audio, relocate robuste, **Energy/Danceability/Popularity/Happiness**, auto-cues, achat Beatport qui **remplace auto** la version streaming, cloud backup, watch folder, export CSV/M3U8/HTML/PDF, occurrence des playlists.
- **Mixed In Key** (https://mixedinkey.com) — key/Camelot, **Energy 1-10**, **8 auto-cues**, **Mashup Studio** (suggère des morceaux compatibles key+energy+BPM).
- **DJ.Studio** (https://dj.studio) — prépa de set sur timeline, **AutoMix/Solver** (ordonnancement harmonique + BPM), stems IA, export RB avec hotcues, export tracklist/vidéo.
- **MIXO** (https://www.mixo.dj) — bibliothèque cloud-first, **édition mobile** (cues/ratings/commentaires depuis le téléphone), sync via Drive/OneDrive/Dropbox.
- **Mixxx** (https://mixxx.org) — OSS : crates + smart crates, **MusicBrainz fingerprinting**, **ReplayGain** (normalisation loudness), Auto DJ.
- **Engine DJ / DJUCED** — Smart Crates, **assistant de suggestion** (IMA), Energy, Auto-Gain.
- Cratedigging web : **Tunebat**, **Mixgraph** (score de transition multi-dimensions dont **vocal fit**), **Chosic**.

**Liste consolidée d'opportunités (à scorer en Phase D) :** déduplication par empreinte audio · Track Matcher multi-sources · nettoyage/normalisation de métadonnées en masse · relocate robuste + fichiers orphelins · roue de Camelot / suggestions harmoniques · Energy levels + champs d'analyse enrichis · auto-cues écrits dans Rekordbox · vocal-fit · ReplayGain · backup cloud versionné · conversion vers autres logiciels DJ · édition mobile · achat Beatport avec remplacement auto · AutoMix/Solver de setlist · export/partage tracklist · occurrence/« jamais joués ».

## Appendice D — Douleurs & wishlist DJ (demande validée par le marché)
*(à étendre ; preuve = nombre d'outils payants par douleur)*
1. **Hygiène de bibliothèque** (doublons acoustiques, fichiers manquants après déplacement de disque, tags/genres incohérents, métadonnées absentes) — **la douleur n°1**, tout un marché payant dessus (Lexicon, Music Library Doctor, DJ Duplicate Cleaner, RCT).
2. **Peur de la base corrompue** → besoin de backup auto **versionné** avec restauration granulaire (les cues sont dans master.db, pas récupérables depuis les ANLZ).
3. **Portabilité cross-app/device** sans perte (RB↔Serato↔Engine↔Traktor) — cœur de Lexicon ; OneLibrary (AlphaTheta+NI+Algoriddim) est partiel/critiqué.
4. **Sourcing streaming→bibliothèque jouable** : la réintégration Spotify 2025 ne couvre ni offline, ni édition, ni USB → besoin de « vrais fichiers » intact. Piste peu exploitée : **matching ISRC** vers l'achat lossless équivalent (Beatport/Beatsource/Juno).
5. **Prépa de set** : crates intelligents (non-joués, warm-up/peak, paliers d'énergie), planification de l'arc énergétique/harmonique ; filtre fiable « **morceaux jamais joués** ».
6. **Tagger les transitions** (paires de morceaux qui marchent ensemble) — quasi inexistant ailleurs, différenciateur potentiel mais niche.
7. **Précision key/BPM/beatgrid** sur tempos complexes — défiance envers l'analyse native (d'où l'usage massif de MIK).
8. Friction **export USB / Device Library (Plus)**, gestion des historiques.
*Sources : forums.pioneerdj.com · cflo/reallychrism (substack) · digitaldjtips.com · djtechtools.com · cdm.link · lexicondj.com · musiclibrarydoctor.com · github.com/edkennard/rekordbox-repair. (Reddit non citable directement — bloqué ; la preuve la plus forte reste le nombre d'outils tiers payants par douleur.)*

## ── FIN DU PROMPT ──
