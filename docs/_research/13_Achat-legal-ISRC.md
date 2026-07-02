## Chemin d'achat légal par ISRC — lister les manquants d'une playlist + générer des liens d'achat lossless (Beatport API v4 vs alternatives) — état 2026-06-16

> **Cadre déjà tranché (Gate 1/2, non rediscuté ici)** : Rekordbox-only, hygiène d'abord, pas d'analyse audio locale ; module d'acquisition par téléchargement = **Fork D, optionnel et OFF par défaut** (streamrip, ARL/credentials utilisateur). La **brique B2 traitée ici est distincte** : un chemin d'achat **légal** qui transforme `artist+title(+ISRC)` d'un morceau manquant en **lien cliquable vers une boutique**, alternative ToS-propre au téléchargement. B2 est en **lecture pure** (affichage), n'écrit jamais dans `master.db` et ne déplace aucun fichier.

> **STATUT GLOBAL DU TOPIC : holds, avec une correction factuelle dure.** Le choix de fond (Option B — URL de recherche construites côté app, stdlib `urllib.parse.quote`, zéro API/clé/réseau côté app) **tient** et a passé le sceptique non-négociables/budget. **Mais** le sceptique SOURCES a réfuté un pilier factuel de la reco d'origine : **Juno Download a fermé le 1er juin 2026**, soit 15 jours avant cette recherche. La liste de boutiques recommandée passe donc de « Beatport + Bandcamp + Juno » à **« Beatport + Bandcamp »**. La conclusion sur le fond est **inchangée et renforcée** : une URL de recherche survit mieux à la volatilité du secteur que n'importe quelle API.

---

### Reco ponytail (en tête)

**Choix : Option B — construire des URL de recherche profondes côté app vers Beatport et Bandcamp, par pur templating de chaîne avec `urllib.parse.quote` (stdlib).** Afficher 1 à 3 boutons « Acheter sur … » par morceau manquant. **Aucune API, aucune clé, aucune approbation, aucun credential, aucun appel réseau depuis l'app** — c'est le navigateur de l'utilisateur qui ouvre l'URL.

- **Pourquoi c'est le barreau le plus paresseux qui tient** : (1) la brique B2 doit exister en v1 (valeur P2/P5 pour un public DJ pro). (2) La stdlib SUFFIT : `urllib.parse.quote` + des templates = ~5 lignes, aucun barreau plus haut nécessaire. La valeur réelle de B2 (« donne-moi un lien pour acheter ce morceau manquant ») est livrée à ~95 % par un bouton qui ouvre une recherche pré-remplie dans le navigateur. La résolution exacte au produit (prix, fiche track) est un luxe qui ne justifie ni une API approuvée de facto fermée (A), ni un format non-lossless (C/D).
- **Tient tout le §3 sans effort** : c'est le navigateur de l'utilisateur qui émet la requête, donc **§3.5 (réseau sortant → `certifi`) n'est même pas sollicité par l'app**, et **§3.6 (secrets) non plus** (zéro credential). **Aucun contact** avec `master.db` (§3.1), résolution de chemins volume-relatifs (§3.2) ou déplacement de fichier (§3.3). **Seul §3.8 s'applique** : les libellés des boutons « Acheter sur Beatport/Bandcamp » doivent être ajoutés en parallèle dans `en.ts` ET `fr.ts`.
- **Coût sidecar : zéro.** Aucun octet, aucune dépendance, aucune surface réseau ajoutée. Le sidecar reste dominé par numpy + sqlcipher3 (~95-120 Mo). Respecte strictement la priorité §2(2) empreinte légère. `urllib.parse.quote` est stdlib (sidecar `requires-python >=3.12`).

---

### Constat (faits sourcés)

> **Fait / Inférence / Opinion** : les claims sont marqués. Les sources réfutées ou périmées par le sceptique SOURCES ont été **retirées ou remplacées** (voir « Vérification adversariale »).

**Aucune voie ISRC → produit lossless gratuite et sans approbation.** *(Fait)* La résolution exacte ISRC→produit n'est offerte par aucune API gratuite, sans clé ni approbation. La valeur du chemin B2 est atteinte à ~95 % par de simples URL de recherche, sans dépendance ni surface réseau.

**(A) Beatport API v4 — de facto fermée.** *(Fait, bien sourcé)*
- Le portail d'approbation renvoie « No Access — You don't have permission to view this portal » ; des demandes d'accès v4 restent **sans réponse depuis plus d'un an** ; conseil communautaire de chercher d'autres sources de données — accès de facto **partner-only** · [groups.google.com/g/beatport-api (thread No Access)](https://groups.google.com/g/beatport-api/c/3qR1Uj1HnUk), consulté 2026-06-16 ; processus de demande de clé confirmé mais lent/incomplet · [groups.google.com/g/beatport-api (annonce API key)](https://groups.google.com/g/beatport-api/c/sU8TCHEOpuY), consulté 2026-06-16.
- La doc `beets-beatport4` **v1.1.1 (publiée 2026-06-08)** écrit qu'il **n'est actuellement plus possible de demander un accès API de la manière normale** (client credentials ou token généré par Beatport) ; le plugin contourne via le **`client_id` public de la doc + login user/pass** ou extraction de token depuis le trafic navigateur — **approche grise vis-à-vis du ToS** · [pypi.org/project/beets-beatport4](https://pypi.org/project/beets-beatport4/), v1.1.1, publié 2026-06-08, consulté 2026-06-16 (citation **vérifiée exacte** par le sceptique).
- Auth = OAuth 2.0 PKCE ou login session ; le catalogue expose un objet `price` mais — **claim NON VÉRIFIÉ** — aucune URL produit/achat documentée et aucun endpoint de recherche par ISRC documenté (seulement recherche texte `q=`). *(Inférence)* La page de doc est un Swagger rendu en JS, **non inspectable par fetch** ; ces deux points sont **plausibles mais invérifiables ici** · [api.beatport.com/v4/docs/](https://api.beatport.com/v4/docs/), consulté 2026-06-16 (Swagger JS, non vérifiable automatiquement — **à confirmer manuellement si l'accès s'ouvre un jour**).

**(B) URL de recherche profondes construites côté app — ponytail.** *(Fait, sources vivantes)*
- **Beatport** : `https://www.beatport.com/search?q=<artist+title urlencodé>`. *(Fait)* La page de recherche renvoie **403 aux bots** (vérifié) — **sans impact** sur l'ouverture par un navigateur humain (cas d'usage réel), mais proscrit toute idée future de scraping côté app (ToS).
- **Bandcamp** : `https://bandcamp.com/search?q=<…>` · format de recherche publique confirmé · [bandcamp.com/search](https://bandcamp.com/search?q=test), consulté 2026-06-16. *(Fait)* Argument renforcé : le message d'adieu de Juno renvoie lui-même vers Bandcamp et le direct-to-fan.
- **Juno Download** : **RETIRÉ.** *(Fait, correction adversariale)* Juno Download a **fermé le 1er juin 2026**, avec effet immédiat et sans préavis — confirmé par plusieurs sources concordantes et indépendantes : [DJ Mag](https://djmag.com/news/juno-download-closes), [Resident Advisor](https://ra.co/news), [Digital DJ Tips](https://www.digitaldjtips.com/), [iMusician](https://imusician.pro/en/blog), consultés 2026-06-16. Le template `q[all][0]=` cité dans la recherche d'origine était **doublement caduc** : (a) la boutique est morte ; (b) le format réel est `q[all][]` (crochets vides), pas `q[all][0]=`. **Juno n'est plus une boutique cible** et est retiré du reco.

**(C) iTunes Search API — lien + prix, sans clé, mais pas lossless ni ISRC.** *(Fait)*
- `GET https://itunes.apple.com/search?term=<artist+title>&entity=song&country=FR` : **sans clé**, rate limit **~20 req/min**, renvoie `trackViewUrl` (lien boutique cliquable) ET `trackPrice` ; lookup par **UPC documenté (pas ISRC)** ; termes promotionnels stricts · [performance-partners.apple.com/search-api](https://performance-partners.apple.com/search-api), consulté 2026-06-16.
- *(Fait)* L'**ISRC n'est PAS un paramètre supporté** : la recherche par ISRC exige l'**Apple Music API** (`GET /v1/catalog/{storefront}/songs?filter[isrc]=…`) qui réclame un **developer token JWT (ES256, Apple Developer Program payant ~99-100 USD/an)** — distinct et plus lourd · [developer.apple.com — get-multiple-catalog-songs-by-isrc](https://developer.apple.com/documentation/applemusicapi/get-multiple-catalog-songs-by-isrc), consulté 2026-06-16.
- *(Fait)* iTunes/Apple Music = **AAC 256k, PAS lossless** → en tension avec la cible lossless du brief pour le public pro.

**(D) Odesli/Songlink — agrégateur multi-boutiques.** *(Fait, source remplacée)*
- `GET /v1-alpha.1/links?url=<URL_streaming>` : **sans clé limité à 10 req/min** (plus avec clé sur demande) ; **entrée = URL streaming ou platform+id, PAS un ISRC brut** ; réponse `entitiesByUniqueId` + `linksByPlatform` ; l'algorithme matche par ISRC + métadonnées et renvoie des liens par service incluant des **stores d'achat (itunes, amazonStore)** en plus du streaming · [help.song.link — API documentation v1-alpha.1](https://help.song.link/en/articles/3037922-api-documentation-v1-alpha-1), consulté 2026-06-16 ; recoupé par [publicapi.dev — Songlink/Odesli](https://publicapi.dev/songlink-odesli-api), consulté 2026-06-16.
  > **Source corrigée** : la recherche d'origine citait `github.com/songlink/docs/blob/master/api-v1-alpha.1.md`, qui n'est plus qu'un **stub redirigeant vers Notion** et ne soutient plus le claim. Remplacée ici par `help.song.link` (source vivante). *(Fait — correction adversariale)*
- *(Fait)* Liens d'achat = surtout iTunes/Amazon (**AAC/MP3, pas lossless dance**) ; Beatport/Bandcamp absents. Dépendance à un service tiers → contre §2(1) robustesse.

**(MusicBrainz) — non recommandé.** *(Inférence)* MusicBrainz possède bien un type de relation **« Purchase for download »**, mais la couverture des liens d'achat sur l'électro de niche est **éparse/incohérente** → peu fiable comme résolveur ISRC→boutique en pratique · [musicbrainz.org — relation Purchase for download](https://musicbrainz.org/relationship/98e08c20-8402-4163-8970-53504bb6a1e4), consulté 2026-06-16.

### Tableau comparatif

| Critère | **B — URL de recherche (ponytail)** | A — Beatport API v4 | C — iTunes Search API | D — Odesli/Songlink |
|---|---|---|---|---|
| Clé / approbation | **Aucune** | **Approbation de facto fermée** (No Access, partner-only) | Aucune | Aucune (clé optionnelle) |
| Réseau sortant côté app | **Zéro** (navigateur de l'utilisateur) | Oui (OAuth + appels) | Oui (HTTPS) | Oui (HTTPS) |
| `certifi` sollicité (§3.5) | **Non** | **Oui** | Oui | Oui |
| Secret au repos (§3.6) | **Non** | **Oui** (client_secret/token) | Non | Non |
| Résolution exacte au produit | Non (page de résultats) | Oui (en théorie ; URL produit **non vérifiée**) | Oui (`trackViewUrl` + prix) | Oui (liens multi-stores) |
| Entrée ISRC | Inutilisée (texte) | Non documentée | Non supporté (UPC seult) | Non (URL/ID streaming) |
| Format des stores ciblés | **Lossless** (Beatport/Bandcamp) | Lossless (WAV/AIFF/FLAC) | **AAC 256k** | AAC/MP3 surtout |
| Dépendance / robustesse | **Zéro dép. ; survit aux API** | API instable, fragile | stdlib `urllib` | service tiers (peut tomber) |
| Coût sidecar | **0 octet** | +client OAuth, surface code | ~0 (stdlib) | ~0 (stdlib/httpx) |

### Verdict (reco ponytail) — détail

**Option B (Beatport + Bandcamp).** Templating pur de chaîne, `urllib.parse.quote`, zéro réseau côté app. Couvre exactement le besoin DJ pro (Beatport = lossless dance ; Bandcamp = direct-to-fan/lossless). ToS-clean : une URL de recherche publique est l'usage prévu. Robuste par construction : aucune API à casser — **précisément parce qu'elle survit mieux que toute API à la volatilité du secteur** (Juno fermé, deemix mourant, audio-features Spotify tuée, portail Beatport fermé).

**Garde-fous d'implémentation (exigés par les deux sceptiques) :**
1. **Concaténation + urlencode PURE.** Interdire explicitement tout fetch/scraping/résolution d'URL côté sidecar. Une « amélioration » qui pré-vérifierait l'URL réactiverait §3.5 (`certifi`) **et** se heurterait au 403 anti-bot Beatport. C'est le navigateur de l'utilisateur qui ouvre l'URL, point.
2. **Templates configurables (données, pas code en dur compilé).** Un redesign — ou une **fermeture** de boutique (cf. Juno) — doit être un changement de config, pas un rebuild. Prévoir un **fallback dégradé** : cacher le bouton si le template est marqué invalide.
3. **Réutiliser la pipeline de normalisation UNIQUE (D19 / §5.3 : NFKD→ASCII, minuscule, parenthèses retirées)** pour construire le terme `artist+title`, au lieu d'une normalisation ad-hoc — sinon on réintroduit une divergence que D19 vient justement de tuer.
4. **i18n (§3.8)** : ajouter les libellés des boutons en parallèle dans `src/renderer/i18n/locales/en.ts` ET `fr.ts` (arbres de clés parallèles).
5. **Lecture pure** : B2 consomme la liste des manquants déjà calculée (statut `missing`/`acquisition_failed` du modèle de domaine §4), n'écrit rien — aucune txn `_mutate`, aucun backup `master.db` requis.

**Ce que ça écarte** : (A) une API approuvée de facto fermée + un secret OAuth à protéger ; (C/D) un format **non-lossless** (AAC/MP3) hors cible pour le public pro ; MusicBrainz comme résolveur ISRC→boutique (couverture trop éparse).

**Chemin d'upgrade (`addWhen`)** : si la résolution exacte (prix + fiche produit) devient un jour indispensable, ajouter l'**iTunes Search API (option C) en complément STRICTEMENT OPTIONNEL** — sans clé, un seul appel HTTPS routé via le `certifi` **déjà embarqué** (aucun ajout sidecar) — pour afficher prix+lien exact **explicitement marqué « AAC 256k, non-lossless » dans l'UI**, en GARDANT les boutons de recherche Beatport/Bandcamp pour le lossless dance. **Ne tirer Beatport API v4 (option A) QUE** si un partenariat officiel ouvre l'accès approuvé ; tant que le portail est fermé/partner-only, ne **jamais** s'y engager.

### Vérification adversariale

> Les deux verdicts sceptiques sont recopiés fidèlement — issues, corrections de sources et risque non-négociable — sans lissage.

**Sceptique 1 — lens SOURCES** (réalité, fraîcheur 2024-2026, soutien réel des claims par recoupement WebSearch/WebFetch) · **verdict : réfuté (correction factuelle dure)**

- **RÉFUTATION CENTRALE** : **Juno Download a FERMÉ le 1er juin 2026**, avec effet immédiat et sans préavis (DJ Mag, Resident Advisor, The Quietus, Digital DJ Tips, Electronic Groove, iMusician, Gearnews — concordants, indépendants), soit **15 jours avant la date de la recherche (2026-06-16)**. Or Juno était l'un des 3 piliers de l'option B recommandée. Le template d'URL Juno mène désormais à une page d'adieu/login, pas à une boutique. La source `junodownload.com/search/` (datée « consulté 2026-06-16 ») **décrivait un service mort comme s'il était opérationnel** : claim NON soutenu.
- **ERREUR DE FORMAT D'URL Juno** : la recherche réelle utilisait `q[all][]` (crochets vides), PAS `q[all][0]=`. Mineure, mais elle invalidait le template tel qu'écrit. **Caduque de toute façon vu la fermeture.**
- **Source Songlink GitHub PÉRIMÉE** : `github.com/songlink/docs/blob/master/api-v1-alpha.1.md` existe mais est devenu un **stub redirigeant vers Notion** ; il ne soutient plus le claim détaillé. Les faits restent corrects via `help.song.link`/`publicapi.dev` — la citation telle quelle était trompeuse.
- **Beatport API v4 docs** : page Swagger rendue en JS, **non vérifiable par fetch**. Les claims « objet `price` mais AUCUNE URL produit » et « AUCUN endpoint ISRC documenté » restent **NON VÉRIFIÉS** (plausibles mais invérifiables ici) → à marquer comme non confirmés, pas comme faits établis.
- **Cohérence interne** : l'open-risk « redesign de boutique peut casser un template (impact faible) » **sous-estimait le risque réel** — une boutique peut **purement disparaître** (Juno), pas seulement être redessinée.
- **Sources VÉRIFIÉES OK** : beets-beatport4 v1.1.1 (2026-06-08), citation exacte ; portail Beatport « No Access » + tickets >1 an (corroboré, plusieurs threads) ; iTunes Search sans clé ~20 req/min, `trackViewUrl`+`trackPrice`, lookup UPC, aucun paramètre ISRC ; Apple Music `filter[isrc]` exige JWT + Apple Developer Program payant ; Odesli sans clé 10 req/min, entrée URL/platform+id, stores itunes/amazonStore (via `help.song.link`) ; Bandcamp `/search?q=` ; Beatport `/search?q=` renvoie 403 aux bots. **Aucune URL inventée détectée.**
- **Conclusion sur le fond INCHANGÉE et renforcée** : l'option B reste la plus paresseuse et la plus robuste — précisément parce qu'elle survit mieux que toute API à la volatilité du secteur. **Mais la liste de boutiques doit refléter le marché de juin 2026 : Bandcamp + Beatport, pas Juno.** → **corrections appliquées dans ce document.**

**Sceptique 2 — lens NON-NÉGOCIABLES & BUDGET** (reco B contre SPEC-UNIFIED §3, §2(2) légèreté, test ponytail) · **verdict : NON RÉFUTÉ (garde-fous à border)**

- **§3.5 / certifi NON sollicité** — VÉRIFIÉ et exact : la requête est faite par le navigateur de l'utilisateur, pas par le sidecar Python. Aucun appel HTTPS sortant côté app dans l'option B. `certifi` est de toute façon **déjà embarqué** (`service/dist/syncbox-service/_internal/certifi/cacert.pem`, chargé par httpx/httpcore). B n'ajoute **aucune** surface réseau.
- **RISQUE DE DÉRIVE à border** : si quelqu'un « améliore » B pour pré-vérifier/récupérer un titre de page côté sidecar, cela rajouterait un appel sortant → réactiverait §3.5 ET tomberait sur le 403 anti-bot Beatport. La spec doit interdire explicitement tout fetch/scraping côté app. → **garde-fou n°1 inscrit dans la reco.**
- **Aucun binaire lourd caché** — VÉRIFIÉ : le seul `libffmpeg.dylib` du repo appartient à la **coque Electron**, pas au sidecar. Le `_internal` du sidecar ne contient que libssl/libcrypto/libsqlite3/liblzma/libzstd/libmpdec. Option B n'introduit ni ffmpeg ni pycryptodomex ni streamrip (ceux-là = module acquisition Fork D, OFF par défaut, hors B2).
- **Zéro dépendance nouvelle** — VÉRIFIÉ : `urllib.parse.quote` est stdlib (sidecar `requires-python >=3.12`). Les 7 deps déclarées (fastapi/httpx/mutagen/pydantic/pyrekordbox/rapidfuzz/uvicorn) ne sont pas requises pour B. Aucun barreau ponytail plus haut nécessaire.
- **§3.6 secrets NON sollicité** — exact : option B a zéro credential (à l'inverse de l'option A OAuth qui exigerait keyring/store chiffré).
- **§3.1 master.db / §3.2 chemins / §3.3 déplacement** — AUCUN contact : B2 est en lecture/affichage pure. Les 3 non-négociables Rekordbox les plus dangereux ne sont pas même approchés.
- **§3.8 i18n** — VÉRIFIÉ que l'infra existe (`en.ts` + `fr.ts`). **Seul non-négociable réellement activé par B** : libellés des boutons en parallèle dans les deux fichiers.
- **Test ponytail PASSÉ** : B est le barreau le plus paresseux qui tient ; A/C/D sont des sur-barreaux pour une valeur livrée à ~95 % par B. Upgrade-path (C iTunes optionnel, via certifi déjà présent) correctement gardé et non-engageant.
- **Budget sidecar : impact RÉEL = 0 octet, 0 dépendance, 0 surface réseau.** Respecte strictement §2(2).
- **Risque non-négociable** : **AUCUN non-négociable §3 cassé.** Le seul activé est §3.8 (i18n), correctement identifié.

### Risques ouverts

- **[CORRIGÉ — était le risque maximal] Disparition de boutique, pas seulement redesign.** Juno a fermé le 2026-06-01. Une boutique cible peut **purement disparaître**. Mitigation : templates configurables (données) + fallback dégradé (cacher le bouton si invalide). À re-tester au build.
- **Stabilité des formats d'URL de recherche.** Beatport `/search?q=` et Bandcamp `/search?q=` sont déduits de l'usage observé, non d'une doc officielle versionnée. Impact faible (un bouton atterrit au pire sur la home/recherche, **jamais** une corruption de données — feature en lecture pure). À re-tester au build, idéalement rendre les templates configurables.
- **Beatport `/search` renvoie 403 aux bots** (vérifié). N'affecte PAS l'ouverture par un navigateur humain (cas d'usage réel), mais proscrit toute idée future de scraping côté app — **à proscrire de toute façon (ToS).**
- **[NON VÉRIFIÉ] Beatport API v4** : aucune URL produit/achat documentée dans la réponse track (seulement un objet `price`) et aucun endpoint ISRC documenté — **claims invérifiables** (doc Swagger JS). Même avec accès, générer le lien produit pourrait nécessiter une reconstruction d'URL non garantie. À confirmer si l'accès s'ouvre.
- **iTunes Search API : ISRC non supporté.** Seul l'UPC est documenté ; les rapports communautaires d'un `isrc=` fonctionnel ne sont pas fiables. La recherche par ISRC exige l'Apple Music API payante (JWT). La voie gratuite avec lien+prix reste basée sur la recherche texte `artist+title`.
- **Tension lossless.** iTunes/Apple Music et Odesli pointent surtout vers de l'AAC/MP3 (non-lossless), hors cible pour le public DJ pro. Les boutiques lossless (Beatport/Bandcamp) ne sont atteignables que par URL de recherche, pas par API gratuite.
- **MusicBrainz** : relation « Purchase for download » existe mais couverture trop éparse sur l'électro de niche → **non recommandé en v1** comme résolveur ISRC→boutique.

### POC à faire

1. **Tester les 2 templates d'URL de recherche (Beatport, Bandcamp)** à la main dans un navigateur avec 5-10 morceaux réels (`artist+title` encodés) et mesurer le taux où le 1er résultat est le bon morceau — valide que la valeur « lien cliquable » est suffisante sans résolution exacte.
2. **Vérifier l'iTunes Search API sur un échantillon dance/électro** : taux de présence de `trackViewUrl` + `trackPrice`, et confirmer empiriquement qu'un paramètre `isrc=` ne renvoie rien (probable) — pour décider si l'upgrade C vaut le coup.
3. **Valider le fallback « boutique disparue »** : forcer un template invalide/404 et confirmer que le bouton se cache proprement (leçon Juno).
