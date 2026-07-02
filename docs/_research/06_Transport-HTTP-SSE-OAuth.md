## Transport HTTP+SSE du sidecar Python & callback OAuth Spotify (PKCE loopback) — Syncbox

> **Cadre déjà tranché (Gate 1/2, non rediscuté ici)** : réécriture from scratch ; coque Tauri v2 ; **transport HTTP+SSE conservé** (pas de JSON-RPC) ; acquisition = module optionnel (lib laissée au build après POC) ; signature macOS décidée plus tard (2 chemins) ; suppression fichier cloud/exFAT = corbeille OS sinon suppression définitive + avertissement.
>
> Ce document persiste la recherche Phase 2 sur **deux briques d'infra** : (1) le serveur HTTP+SSE minimal du sidecar Python ; (2) le callback OAuth PKCE de Spotify sur port loopback fixe.

---

# Section 1 — Serveur HTTP+SSE minimal Python (Starlette + sse-starlette + uvicorn 1 worker)

**Sujet** : serveur HTTP+SSE le plus léger et robuste pour le sidecar Python de Syncbox (REST loopback + 1 flux SSE), consommé par une UI Vue dans WKWebView (macOS) / WebView2 (Windows).

### Constat (faits sourcés)

**La cause du « FastAPI lent » est mal attribuée — c'est Pydantic v2, pas Starlette/uvicorn**
- Le cold-start lent vient de l'init des `TypeAdapters` de Pydantic v2 (rapporté « 2-4× », chiffre à considérer comme indicatif/non mesuré), pas du serveur ASGI nu · [FastAPI Cold Starts Explained — Medium hadiyolworld007](https://medium.com/@hadiyolworld007/fastapi-cold-starts-explained-why-your-containers-feel-slow-and-the-optimization-order-that-dcac906ffe2b) (2025, **paywallé** — chiffrage non vérifiable indépendamment).
- Source **primaire** confirmant l'attribution : démarrage passant de ~5 s à >20 s après migration V2, dû à l'init des TypeAdapters · [Very slow FastAPI startup after V2 due to TypeAdapter init — pydantic #6768](https://github.com/pydantic/pydantic/issues/6768) (2023).

**Couche applicative — Starlette nu + sse-starlette**
- Deps runtime de sse-starlette : `starlette>=0.49.1`, `anyio>=4.7.0` requis ; `uvicorn`/`granian`/`daphne` en **extras optionnels** · [sse-starlette pyproject.toml](https://github.com/sysid/sse-starlette/blob/main/pyproject.toml) (2026-05-12).
- Starlette : seule dépendance requise = `anyio` ; httpx/jinja2/etc. optionnels · [Starlette — Introduction](https://www.starlette.io/) (2025-11-01).
- Projet maintenu (encode/Kludex), 0.49.x oct.-nov. 2025 avec fix sécu Range header dans FileResponse · [Starlette release notes](https://github.com/encode/starlette/blob/master/docs/release-notes.md) (2025-11-01).

**Serveur — uvicorn embarqué programmatiquement, 1 worker**
- On peut passer un **objet app** directement à `uvicorn.Config(app=...)` puis `await Server.serve()` (pas de chaîne `module:app`) ; 1 worker par défaut · [Uvicorn — settings](https://www.uvicorn.org/settings/) (2026-02-03). Nuance officielle : ce style ne marche **que** sans multiprocessing/reload — donc valide précisément parce qu'on impose **1 worker**.

**Alternatives écartées (faits)**
- **Granian** (ASGI Rust) : listé/testé par sse-starlette, mais embarquer un objet app pose un échec de pickling multiprocessing, usage canonique = CLI `module:app` · [Granian issue #35](https://github.com/emmett-framework/granian/issues/35). Extension Rust = classe d'erreur PyInstaller connue (`DLL load failed while importing _rust`) · [PyInstaller #6390](https://github.com/pyinstaller/pyinstaller/issues/6390) (2023). Perf supérieure annoncée mais non pertinente en loopback · [Stop Using Uvicorn — thenerdnook](https://www.thenerdnook.io/p/stop-using-uvicorn) (2025, **paywallé**).
- **aiohttp + aiohttp-sse** : serveur HTTP intégré (pas d'ASGI), mature (3.13.5 mars 2026) mais surface de deps plus large (multidict/yarl/frozenlist/aiosignal + extensions C) et API plus bas niveau · [aiohttp-sse README](https://github.com/aio-libs/aiohttp-sse/blob/master/README.rst) (2025), [aiohttp releases](https://github.com/aio-libs/aiohttp/releases) (2026-03-31), [aiohttp vs Starlette — stackshare](https://stackshare.io/aiohttp/vs/starlette) (2025).
- **stdlib http.server + SSE maison** : zéro dépendance, mais réinvente keepalive/reconnexion/déconnexions · [SSE en stdlib — devtut](https://devtut.github.io/python/python-server-sent-events.html) (2024), [Server-Sent Events — Wikipedia](https://en.wikipedia.org/wiki/Server-sent_events) (2025).

**Quirk SSE connu** : sse-starlette ne fonctionne PAS avec `GZipMiddleware` sur la route SSE — ne pas gzip le flux `text/event-stream`.

### Tableau comparatif

| Option | Serveur | Deps runtime | Empaquetage PyInstaller | Robustesse SSE | Embarquement programmatique | Tient non-négociables |
|---|---|---|---|---|---|---|
| **Starlette nu + sse-starlette + uvicorn (1 worker)** ⭐ | uvicorn (ASGI, pur-Python) | starlette + anyio + sse-starlette + uvicorn | Propre, documenté (pur-Python, hiddenimports uvicorn) | Fournie (keepalive, send_timeout, déconnexions) | `Config(app=obj)` + `await Server.serve()` (OK car 1 worker) | **Oui** |
| Starlette + sse-starlette sur **Granian** | Granian (ASGI Rust) | + extension Rust | **Risque** non dé-risqué (erreur `_rust`/.so) | Idem (SSE testé) | Bancal (pickling multiprocessing, orienté CLI) | Sous conditions |
| **aiohttp** + aiohttp-sse | intégré (pas d'ASGI) | + multidict/yarl/frozenlist/aiosignal (+C) | Plus de hooks potentiels | Établie (StreamResponse) | AppRunner programmatique | Oui (mais écosystème distinct) |
| **stdlib http.server** + SSE maison | ThreadingHTTPServer | aucune (stdlib) | Trivial | **À coder soi-même** | Threads à marier avec asyncio | Sous conditions |

### Verdict (reco ponytail)

**Starlette nu + sse-starlette, servi par uvicorn en 1 worker lancé programmatiquement** (`uvicorn.Config(app=<objet Starlette>)` + `await Server.serve()`). **Supprimer FastAPI/Pydantic v2.**

Rationale : c'est l'option la plus paresseuse qui tient TOUTES les décisions tranchées. Le grief « FastAPI/uvicorn lourd » est mal attribué : le cold-start lent vient de FastAPI+Pydantic v2 (init TypeAdapters), PAS de Starlette/uvicorn nus (pydantic #6768). En retirant juste FastAPI, on supprime la cause sans changer de paradigme : on reste sur le couple HTTP+SSE+ASGI déjà connu (maintenabilité préservée). Les deps tombent à `starlette+anyio+sse-starlette+uvicorn`, tout **pur-Python** (pas d'extension Rust comme Granian → empaquetage PyInstaller propre). uvicorn s'embarque proprement avec un objet app en 1 worker (contourne le bug multi-workers déjà sourcé). sse-starlette livre la robustesse SSE (keepalive, send_timeout, déconnexions) gratuitement — ce que « robustesse > légèreté » exige de ne PAS recoder. Le lens ponytail penche pour la stdlib, mais ici l'échelon « dépendance mûre qui fait exactement le job » gagne : un SSE-maison réintroduit du risque pour un gain de poids marginal (starlette+anyio sont déjà minuscules).

**Ce que ça écarte** : FastAPI/Pydantic v2 (la taxe de cold-start) ; Granian (extension Rust = risque PyInstaller + embarquement bancal) ; le SSE-maison sur http.server (réinvente la robustesse) ; aiohttp (écosystème distinct, surface de deps plus large). Aucun middleware non nécessaire (pas de GZip sur la route SSE).

**Quand ajouter** : Granian seulement si un POC d'empaquetage prouve que l'extension Rust + l'embarquement programmatique passent sur macOS ET Windows ET qu'une mesure montre un besoin de throughput réel (improbable en loopback 1 client). FastAPI/Pydantic uniquement si la validation de payloads complexes devient un besoin fort (alors lazy-import + mesure cold-start). http.server-maison seulement si le besoin SSE devient trivial et figé.

**Confidence : medium** (les 2 POC ci-dessous sont les vrais juges).

### Vérification adversariale

**Sceptique n°1 — SOURCES (authenticité, fraîcheur, adéquation source↔affirmation) → `holds`**

La réfutation échoue : aucune source ne s'effondre, les sources qui PORTENT vraiment la reco (sse-starlette pyproject, deps Starlette, pydantic #6768, Granian #35, uvicorn settings) sont toutes réelles, accessibles, à jour et soutiennent l'option recommandée. Trois fissures à intégrer, **sans lisser** :
- Le chiffrage « 2-4× » de la taxe Pydantic repose sur deux billets **paywallés** (Medium hadiyolworld007, thenerdnook) — contenu quantitatif **non vérifiable**. La THÈSE tient quand même sur source **primaire** (pydantic #6768, ~5 s → >20 s). → **Dégrader « 2-4× » en estimation non mesurée.**
- La doc uvicorn sur-vend l'embarquement programmatique : passer un objet app marche, mais uvicorn lui-même précise que ce style ne marche PAS avec multiprocessing/reload et **recommande** la chaîne d'import. Comme la reco impose 1 worker, l'objet app fonctionne — nuance, pas erreur. → **Reformuler pour refléter la mise en garde officielle.**
- Glissements de dates mineurs non-inventés : Granian #35 daté « 2024 » alors qu'ouverte le 16 janv. 2023 ; Starlette en 1.3.x et aiohttp en 3.14.x en juin 2026 (les versions précises citées 0.49.1 oct. 2025 / 3.13.5 mars 2026 sont exactes — drift normal).

**`badSources`** : aucune source inventée. Réserves — (1) Medium hadiyolworld007 : RÉEL mais **paywallé**, « Pydantic 2-4× » non vérifiable ; (2) thenerdnook : RÉEL mais **paywallé**, « throughput supérieur » non étayé par données visibles ; (3) Granian #35 daté 2024 mais ouvert 2023 (authentique, pertinent) ; (4) Starlette/aiohttp « latest » légèrement périmés (drift normal, non disqualifiant).

**`nonNegotiableRisk`** : aucun. HTTP+SSE localhost conservé, JSON-RPC rejeté, pur-Python cross-OS, 1 worker (contourne le bug uvicorn multi-workers), local-first intact. Seule vigilance non bloquante (déjà en openItem) : valider le mode de lancement (asyncio in-process vs sous-process) pour que la garde « Rekordbox fermé » et le kill d'arbre restent fiables.

**Sceptique n°2 — NON-NÉGOCIABLES SPEC-01 §9 & DÉCISIONS Gate 1 → `holds`** (sous réserve d'une **précision non-négociable** à intégrer)

La réfutation la plus forte cherche le cas limite où l'embarquement uvicorn trahit l'arrêt propre du sidecar (touche les non-négociables « garde Rekordbox fermé » + arrêt fiable). Découverte **vérifiée sur le code source** : sse-starlette détecte le shutdown UNIQUEMENT via les signal handlers d'uvicorn — il monkeypatche `Server.handle_exit` (`AppStatus.should_exit`) ET introspecte `signal.getsignal(SIGTERM).__self__` pour retrouver le Server (`sse_starlette/sse.py`). Or les signal handlers uvicorn ne s'installent QUE dans le **thread principal** ([uvicorn #506](https://github.com/encode/uvicorn/issues/506) : « set_wakeup_fd only works in main thread »), et une connexion SSE long-lived **bloque le graceful shutdown** ([uvicorn discussion #1103](https://github.com/encode/uvicorn/discussions/1103)). Le contournement « uvicorn-en-thread » (`install_signal_handlers: pass`) CASSERAIT les deux voies de détection → générateurs SSE annulés brutalement à l'arrêt.

MAIS la reco ne prescrit PAS le thread — elle prescrit explicitement `uvicorn.Config(app=objet)` + `await Server.serve()` **dans la boucle asyncio principale**, où les signal handlers s'installent normalement. La réfutation échoue donc à casser la reco TELLE QU'ÉCRITE ; elle impose une **PRÉCISION non-négociable** à **figer dans la spec** :
- **(a) uvicorn lancé via `await Server.serve()` DANS la boucle asyncio principale, JAMAIS dans un thread avec `install_signal_handlers` désactivé** — sinon les générateurs SSE sont coupés brutalement.
- **(b) configurer un `timeout-graceful-shutdown` court + `force_exit` de secours** pour que l'arrêt reste BORNÉ (sinon le sidecar peut hanger sur le flux SSE, empêcher l'arrêt/relance et rendre l'état process incertain — ce qui fragiliserait indirectement la garde « Rekordbox fermé avant mutation »).

Le reste tient : aucun non-négociable §9 touché par le transport (mutations/backup/soft-delete/statuts/résolution chemins/pyrekordbox+sqlcipher3+mutagen+rapidfuzz/PKCE/local-first vivent dans les handlers, indépendants de Starlette-vs-FastAPI). Rejet de Granian (extension Rust + pickling) BIEN fondé ; rejet du SSE-maison BIEN fondé. **Risque orthogonal à retenir** : le **kill d'ARBRE** du sidecar côté Tauri reste obligatoire (les enfants du 2e process PyInstaller deviennent orphelins si non propagé — tauri-apps discussions #3273/#5504 ; cohérent avec `taskkill /T` Win + process group macOS).

**`badSources`** : (1) Medium hadiyolworld007 « FastAPI Cold Starts » non vérifiable (fetch tronqué) — atténué par la source primaire pydantic #6768. (2) Contournement WKWebView par « padding de lignes de commentaire `:` » : le phénomène est attesté (curl reçoit immédiatement, navigateur bufferise — uvicorn #689, API Gateway streaming #13177) mais NI le seuil de flush WebKit NI l'efficacité du padding ne sont documentés → honnêtement marqué « à vérifier empiriquement », **ne pas le présenter comme acquis**. (3) URL `uvicorn.org/settings` non re-confirmée bit à bit (pattern validé indirectement par #1103 + #506).

**`nonNegotiableRisk`** : aucun non-négociable cassé. Risque RÉSIDUEL (précision, pas blocage) sur l'arrêt propre du sidecar : figer (a) `Server.serve()` dans la boucle principale, (b) `timeout-graceful-shutdown` court + `force_exit`, et garder le kill d'arbre côté Tauri.

### Incertitudes / POC à faire

- **POC BLOQUANT n°1 — cold-start réel** : mesurer empiriquement le temps de démarrage de Starlette+sse-starlette+uvicorn 1 worker **DANS le binaire PyInstaller**, sur macOS (WKWebView) ET Windows (WebView2). Les sources expliquent la cause de la lenteur FastAPI mais ne chiffrent pas Starlette nu sous PyInstaller.
- **POC BLOQUANT n°2 — buffering SSE côté WebKit/WKWebView** : curl reçoit immédiatement mais le navigateur bufferise initialement (problème côté navigateur). Le contournement attesté est le padding par lignes de commentaire SSE `:` — **à vérifier empiriquement** dans WKWebView/WebView2 (seuil de flush WebKit non formellement documenté).
- Bug iOS18 EventSource (error non firé au retour de veille, `readyState` reste OPEN) — peu probable en WKWebView desktop, à garder en tête si reconnexion sur veille.
- Confirmer que sse-starlette sans `GZipMiddleware` sur la route SSE n'entre pas en conflit avec une compression globale souhaitée sur les routes REST (middleware par route ou app distincte).
- Valider le kill d'arbre de process (PyInstaller crée 2 process) avec uvicorn embarqué en coroutine vs process séparé — choisir le mode de lancement pour que la garde « Rekordbox fermé » et l'arrêt propre restent fiables.

---

# Section 2 — Callback OAuth Spotify PKCE, port loopback fixe 127.0.0.1:8765

**Sujet** : mécanisme de callback OAuth Spotify (Authorization Code + PKCE, lecture seule) pour Syncbox desktop, et résolution de SPEC-01 §10.7 : port fixe `:8765` vs port dynamique enregistré, sur le serveur HTTP loopback du sidecar Python.

### Constat (faits sourcés)

**Politique Spotify avril 2025 (durcissement des redirect URIs)**
- HTTP toléré UNIQUEMENT pour les **IP loopback littérales** (`127.0.0.1` / `[::1]`) ; **`localhost` interdit** ; **match exact** de l'URI enregistrée requis · [Spotify — Redirect URIs](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri) (consultée 2026-06-15).
- Annonce officielle du durcissement · [Increasing the security requirements for integrating with Spotify](https://developer.spotify.com/blog/2025-02-12-increasing-the-security-requirements-for-integrating-with-spotify) (2025-02-12).
- Rappel migration OAuth 27 nov. 2025 · [Reminder: OAuth Migration 27 November 2025](https://developer.spotify.com/blog/2025-10-14-reminder-oauth-migration-27-nov-2025) (2025-10-14).
- Exemples terrain de migration `localhost`→`127.0.0.1` · [spotipy issue #1186](https://github.com/spotipy-dev/spotipy/issues/1186) (2025).

**Port dynamique « pur » RFC 8252 — supporté en théorie, fragile en pratique**
- Spotify documente l'enregistrement du loopback **sans port** + injection du port dynamique dans la requête d'autorisation, « only supported for loopback IP literals » · même doc redirect_uri + [Migrate away from Insecure Redirect URIs](https://developer.spotify.com/documentation/web-api/tutorials/migration-insecure-redirect-uri) (« We do support dynamic ports for loopback interfaces »).
- Norme : « the authorization server MUST allow any port to be specified at the time of the request for loopback IP redirect URIs » · [RFC 8252 §7.3](https://www.rfc-editor.org/rfc/rfc8252) (2017, en vigueur).
- **Fragilité de validation dashboard documentée** : des devs rapportent que `http://127.0.0.1` enregistré SANS port est refusé « This redirect URI is not secure », alors qu'avec un port explicite ça passe.

### Tableau comparatif

| Option | URI enregistrée | Robustesse validation dashboard | Réutilise le serveur loopback déjà décidé | Complexité | Tient non-négociables |
|---|---|---|---|---|---|
| **Port FIXE pré-enregistré** ⭐ `http://127.0.0.1:8765/callback` | figée | **Fiable** (port explicite = cas standard) | Oui (1 route GET `/callback` en plus) | Minimale | **Oui** |
| Port DYNAMIQUE (port-less RFC 8252) `http://127.0.0.1` sans port | dynamique au handshake | **Fragile** (refus « not secure » rapporté) | Non (pousse vers listener éphémère séparé) | Bind `:0` + ré-injection port | Sous conditions |
| Listener éphémère dédié (http.server jetable) | fixe ou dynamique | identique à l'option 1 | Non (2e serveur jetable = double travail) | Cycle de vie socket à gérer | Oui mais redondant |

### Verdict (reco ponytail)

**Port FIXE pré-enregistré** : enregistrer `http://127.0.0.1:8765/callback` dans le dashboard Spotify, et ajouter une **route GET `/callback`** au serveur HTTP loopback que le sidecar Python sert DÉJÀ. Authorization Code + **PKCE (S256)**, **aucun client secret**. → **Trancher SPEC-01 §10.7 en faveur du PORT FIXE `:8765`.**

Rationale : option la plus paresseuse tenant TOUS les non-négociables et décisions Gate 1. (1) Le composant existe déjà : le sidecar sert un serveur HTTP loopback + SSE par décision tranchée → le callback n'est qu'une route en plus, pas un nouveau process, pas une nouvelle dépendance (lens ponytail niveaux 1 et 4). (2) Conformité Spotify avril 2025 garantie SANS angle mort : HTTP toléré seulement pour `127.0.0.1` littéral (localhost banni), match exact trivialement respecté car l'URI est figée. Un port explicite comme `:8765` passe la validation du dashboard de façon fiable (cas standard). (3) Priorité robustesse > légèreté > perf : pas de port à ré-injecter dynamiquement, pas de mismatch possible enregistré-vs-envoyé. Le port dynamique RFC 8252 « pur » est plus propre sur le papier mais sa validation dashboard est rapportée fragile (refus de `127.0.0.1` sans port), risque opérationnel net pour une app DJ mono-utilisateur sans besoin de ports multiples.

**Ce que ça écarte** : (a) le port dynamique / port-less RFC 8252 malgré sa conformité « à la lettre » (fragilité dashboard + complexité injustifiée) ; (b) le listener éphémère dédié (redondant avec le serveur loopback déjà décidé) ; (c) tout usage de `localhost` (interdit depuis avril 2025) ; (d) HTTPS sur la boucle locale (inutile, exemption loopback HTTP, la requête ne quitte jamais la machine).

**Quand ajouter** : basculer vers le port dynamique UNIQUEMENT si (1) `:8765` s'avère régulièrement occupé chez les users, OU (2) on doit supporter plusieurs instances Syncbox simultanées, ET (3) un POC confirme que le dashboard accepte aujourd'hui `127.0.0.1` sans port. Solution intermédiaire bon marché : enregistrer 2-3 ports de secours fixes (8765/8766/8767) et essayer le premier libre — garde le match exact tout en réglant les collisions.

**Confidence : high.**

### Vérification adversariale

**Sceptique n°1 — SOURCES (réalité, accessibilité, fraîcheur, adéquation source↔affirmation) → `holds`**

La réfutation échoue sur trois axes. (1) Sources inventées : **aucune** — les 6 sources de la reco centrale sont réelles et accessibles ; les trois piliers Spotify (doc redirect_uri, tutoriel migration, blog 2025-02-12) et RFC 8252 §7.3 vérifiés mot pour mot (verbatim « localhost is not allowed », « We do support dynamic ports for loopback interfaces », « MUST allow any port… ephemeral port », exception port-less loopback correspondent au texte fetché). Blog 2025-10-14 et spotipy #1186 confirmés. (2) Sources mal interprétées pour gonfler la reco : non — au contraire, le point pivot (port fixe préféré au port-less à cause de la fragilité de validation) est CONFIRMÉ empiriquement par le fil communauté Spotify #6968154 (`127.0.0.1` sans port rejeté « not secure », port explicite accepté). La preuve terrain **renforce** la reco. (3) Fait périmé trouvé — mais dans les openItems, pas dans la reco centrale, **à dire sans lisser** :

> **Fait périmé** : l'openItem « Spotify rejette les tirets dans le path du loopback (n8n #25805, 2026-02-15) » est **obsolète**. L'issue existe bien mais les sources (Spotify Community #6929053 « Solved ») indiquent que Spotify a **corrigé** ce bug de validation des tirets, et la date « 2026-02-15 » n'est pas vérifiable. Conséquence pratique nulle (le conseil « `/callback` sans tiret = sûr » reste prudent), mais le fait sous-jacent ne tient plus tel quel.

**`badSources`** : openItems #3 — n8n issue #25805 RÉELLE mais le fait est PÉRIMÉ (Spotify a corrigé le bug des tirets ; date « 2026-02-15 » non vérifiable). Impact sur la reco centrale : nul.

**`nonNegotiableRisk`** : aucun.

**Sceptique n°2 — NON-NÉGOCIABLES SPEC-01 §9 & DÉCISIONS Gate 1 → `holds`** (sous réserve d'une **exigence de spec** à promouvoir d'openItem en règle dure)

La réfutation la plus forte = le **quirk navigateur `127.0.0.1`→`localhost`**. Risque RÉEL et documenté : un navigateur peut livrer le callback à `http://localhost:PORT/callback` au lieu de `127.0.0.1`, et Spotify renvoie alors « Invalid redirect URI » (spotify-mcp #44 du 2025-10-08 ; thread Spotify Community « 127.0.0.1 being changed to localhost » ; cas NextAuth/Spotify ; claude-code #42765 du 2026-04-02). **Crucialement, ce quirk frappe MÊME avec un port fixe `:8765`** — le port fixe n'immunise PAS contre lui. À première vue, ça casse le non-négociable « le login Spotify doit marcher cross-OS » et défait le pro « match exact = zéro ambiguïté ».

**MAIS la réfutation ne tient PAS comme defeater**, après vérification du mécanisme de validation. Spotify valide le match exact sur le **string `redirect_uri` que l'APP envoie**, à deux endroits : (1) la requête d'autorisation, (2) l'échange code→token (où le `redirect_uri` sert uniquement à la validation, pas de redirection réelle, et doit correspondre exactement à celui de l'autorisation — doc Spotify PKCE confirmée). Ces deux strings sont contrôlés par le sidecar Syncbox, PAS lus depuis le navigateur. Le navigateur n'a qu'à LIVRER le callback au serveur loopback ; comme `localhost` résout vers `127.0.0.1`, le serveur reçoit la requête et capture le `code` quelle que soit la réécriture de la barre d'adresse (à condition de répondre indépendamment du header `Host`). Les échecs NextAuth/claude-code viennent d'apps qui **DÉRIVENT le `redirect_uri` du host de la requête entrante** — pas du cas Syncbox qui code en dur la chaîne. **Le quirk est un piège d'IMPLÉMENTATION, pas un défaut du choix port-fixe.**

> **CONDITION DE VALIDITÉ NON-NÉGOCIABLE (la reco la sous-estime — à intégrer dans la spec, pas juste en openItem)** : le sidecar DOIT
> **(a)** coder en dur `"http://127.0.0.1:8765/callback"` comme `redirect_uri` dans les **DEUX** appels (authorize + token), ne JAMAIS le reconstruire à partir du host / header `Host` de la requête entrante ;
> **(b)** binder le serveur sur `127.0.0.1` et répondre au `/callback` **quel que soit le `Host`**.
> Si cette règle est respectée, le quirk navigateur est inoffensif. La reco liste l'openItem « valider que le navigateur redirige bien vers 127.0.0.1 » mais **formule mal le remède** : le vrai garde-fou n'est pas de contrôler le navigateur (incontrôlable), c'est de **NE JAMAIS dériver le `redirect_uri` de la requête**.

Le reste résiste : port explicite `:8765` confirmé accepté par le dashboard (doc Spotify donne l'exemple valide `http://127.0.0.1:8000/callback`) ; localhost banni + IP loopback littérale + match exact (seule exception = port dynamique) confirmés ; fragilité de l'enregistrement port-less confirmée par plusieurs rapports « This redirect URI is not secure » → rejeter l'option 2 par défaut est justifié ; `/callback` sans tiret reste le bon choix. Aucun non-négociable §9 cassé (local-first, PKCE sans secret en clair, cross-OS) ; aucune décision Gate 1 violée (réutilise le serveur HTTP loopback déjà décidé, pas de JSON-RPC, PKCE lecture seule, Tauri-agnostique).

**`badSources`** : aucune.

**`nonNegotiableRisk`** : aucun non-négociable cassé. Seule réserve d'implémentation (**à promouvoir d'openItem en exigence de spec**) : le quirk `127.0.0.1`→`localhost` casserait le login Spotify (non-négociable cross-OS) SI le sidecar dérivait le `redirect_uri` du host de la requête entrante. Remède obligatoire : coder en dur `"http://127.0.0.1:8765/callback"` dans les deux appels, binder sur `127.0.0.1`, répondre au `/callback` indépendamment du `Host`. Risques secondaires bien gérés : path sans tiret (`/callback` OK), collision `:8765` (fallback ports de secours).

### Incertitudes / POC à faire

- **Gestion de collision de port `:8765`** : décider entre (a) message d'erreur clair invitant à libérer le port, ou (b) liste de 2-3 ports de secours fixes pré-enregistrés (8765/8766/8767) essayés en cascade. Recommandation = **(b)**, bon marché et conserve le match exact.
- **POC à faire si un jour on envisage le port dynamique** : vérifier EMPIRIQUEMENT, dans le dashboard Spotify de mi-2026, si l'enregistrement de `http://127.0.0.1` SANS port est accepté ou refusé « not secure » — la doc dit oui, des rapports terrain disent non. Ne PAS s'engager sur le dynamique sans cette confirmation.
- **Path du callback sans tiret** : `/callback` est sûr ; éviter un path type `/oauth-callback` (un rapport n8n #25805 montrait un rejet des tirets — désormais corrigé selon le sceptique SOURCES, mais rester prudent).
- **IPv4 (`127.0.0.1`) vs IPv6 (`[::1]`)** : `127.0.0.1` recommandé par défaut (compatibilité cross-OS la plus large) ; valider que le navigateur système redirige bien vers `127.0.0.1` et non `localhost` — voir la **règle dure** « redirect_uri codé en dur, jamais dérivé de la requête » qui neutralise ce quirk.
