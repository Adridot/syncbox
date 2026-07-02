I have comprehensive, sourced data. Here is the deliverable.

## Coques desktop légères gardant une UI web (vs Electron) pour macOS + Windows — pilotant un sidecar Python

### Constat (faits sourcés)

**Empreinte — Tauri v2**
- Tauri v2 produit des binaires « souvent < 10 MB », descendant à 2.5–3 MB grâce au webview natif + backend Rust ; Electron embarque Chromium + Node.js et dépasse typiquement 100–150 MB · [pkgpulse / raftlabs / applicationize](https://www.pkgpulse.com/guides/electron-vs-tauri-2026).
- RAM au repos : Tauri ~30–40 MB (jusqu'à 50–100 MB), Electron 200–300 MB · [dev.to/raftlabs](https://dev.to/raftlabs/tauri-vs-electron-23d1), [applicationize](https://applicationize.me/tauri-vs-electron-2025-which-desktop-app-framework-wins-on-speed-security-and-features/). Résumé courant : « Tauri ~10× plus petit, ~5× moins de RAM ».
- Architecture webview natif : WebView2 (Chromium) sur Windows, WKWebView (WebKit/Safari) sur macOS · [v2.tauri.app/reference/webview-versions](https://v2.tauri.app/reference/webview-versions/).

**Maturité — Tauri v2**
- v2 **stable le 2 octobre 2024**, sous **MIT + Apache 2.0**, audit de sécurité externe public avant la release · [Tauri 2.0 Stable](https://v2.tauri.app/blog/tauri-20/), [Wikipedia](https://en.wikipedia.org/wiki/Tauri_(software_framework)). Version courante ~2.10.x (début 2026). Maturité production confirmée.

**Sidecar Python — Tauri v2 (point clé pour Syncbox)**
- `externalBin` dans `tauri.conf.json` embarque un binaire externe ; cas d'usage explicitement cités : **serveur API Python bundlé via PyInstaller** · [v2.tauri.app/develop/sidecar](https://v2.tauri.app/develop/sidecar/).
- Chaque binaire doit exister avec **suffixe target-triple** : `-aarch64-apple-darwin` / `-x86_64-apple-darwin` (macOS), `-x86_64-pc-windows-msvc.exe` (Windows) · même source. Implique de produire 1 build PyInstaller par arch/OS.
- Spawn via le **plugin Shell** (`app.shell().sidecar("name").spawn()`), IPC **stdin/stdout** par défaut (pas de HTTP imposé). Permissions à déclarer dans `capabilities/` (`shell:allow-execute`/`spawn`, args avec validateurs regex) · même source.
- Caveat PyInstaller : `process.kill()` ne tue que le bootloader PyInstaller (PID parent), pas le process Python enfant en mode one-file · [discussion #2759](https://github.com/orgs/tauri-apps/discussions/2759).
- **PIÈGE MAJEUR macOS** : avec `externalBin`, la **notarisation Apple échoue** (« The signature of the binary is invalid ») ; OK dès qu'on retire `externalBin`. Affecté v2.1.1, ouvert depuis déc. 2024, non résolu côté framework · [issue #11992](https://github.com/tauri-apps/tauri/issues/11992). Workaround : **signer manuellement chaque binaire sidecar** (`codesign --deep`, hardened runtime, entitlements adaptés) · [discussion #12803](https://github.com/tauri-apps/tauri/discussions/12803).

**Webview hétérogène (impact UI Vue)**
- WebView2/WKWebView/WebKitGTK n'implémentent pas les standards à l'identique : différences possibles sur CSS Grid, flexbox `gap`, fonctionnalités CSS récentes ; nécessité de tester sur chaque OS et d'ajouter préfixes/polyfills `-webkit-` · [dev.to/shrsv](https://dev.to/shrsv/exploring-system-webviews-in-tauri-native-rendering-for-efficient-cross-platform-apps-9hl). Figma a renoncé à Tauri pour des features non couvertes par les 3 webviews.
- WKWebView est lié à la version de macOS : un user sur vieux macOS peut avoir un WebKit ancien · même source.
- **SSE/EventSource** : `EventSource` est supporté dans Safari/WKWebView (depuis Safari 5 macOS) — **fonctionne via HTTP localhost** · [Wikipedia SSE](https://en.wikipedia.org/wiki/Server-sent_events), [testmuai](https://www.testmuai.com/learning-hub/eventsource-browser-support/). WKWebView peut charger `http://localhost`/`127.0.0.1` et y faire du SSE · [Apple forums #104901](https://developer.apple.com/forums/thread/104901). En revanche, faire du SSE **via le custom-protocol Tauri** (`tauri://`) n'est PAS un transport SSE natif — Tauri n'a pas de SSE intégré et recommande WebSocket plugin · [discussion #14552](https://github.com/orgs/tauri-apps/discussions/14552). Limite Safari connexe : l'itération async `for await` sur `ReadableStream` n'est pas supportée (utiliser `getReader()`) · [web-developpeur](https://www.web-developpeur.com/en/blog/sse-fetch-readable-stream-api-key).

**Wails (Go)**
- Wails **v2 stable** (MIT), Windows binaire < 10 MB (≈3 MB compressé UPX) ; webview natif WebView2 (Win) / WKWebView (macOS) · [wails.io](https://wails.io/), [johal.in](https://johal.in/wails-python-go-web-tech-desktop-applications-2026/). Sur Windows, **dépendance au runtime WebView2** (embed bootstrapper +~150 kB, ou download, ou bundle fixed-version) · [wails.io/docs/guides/windows](https://wails.io/docs/guides/windows/).
- **Wails v3 = ALPHA** (API « raisonnablement stable », apps en prod), MIT ; releases actives (v3.0.0-alpha.73, fév. 2026) · [v3.wails.io](https://github.com/wailsapp/wails), [pkg.go.dev/wails/v3](https://pkg.go.dev/github.com/wailsapp/wails/v3). Pas de mécanisme « sidecar » officiel documenté ; spawn d'un process externe = code Go standard (`os/exec`), pas d'embedding/signing automatisé.

**Neutralino.js**
- Très léger (~2.7 MB vs 134 MB NW.js), webview système par OS · [neutralino.js.org](https://neutralino.js.org/). « Extensions » = process séparés dans n'importe quel langage, **IPC via WebSocket**, credentials passés en stdin · [extensions-overview](https://neutralino.js.org/docs/how-to/extensions-overview/). Réserve : stabilité de l'API WebSocket pointée du doigt (perte de chargement HTML/JS/CSS) en 2025 · même source. Maturité < Tauri.

**Localhost + navigateur système (baseline)**
- Tauri propose un `tauri-plugin-localhost` exposant les assets via un serveur localhost au lieu du custom-protocol, mais **risques de sécurité notables** ; recommandation officielle = garder le custom-protocol par défaut · [v2.tauri.app/plugin/localhost](https://v2.tauri.app/plugin/localhost/).

**Contexte Syncbox (lu dans le repo)**
- `electron/main.ts` spawn déjà le service Python et parle en **HTTP `http://127.0.0.1:${port}`** (REST). Le backend est **FastAPI/uvicorn** (`service/app/main.py`).
- Le frontend consomme du **SSE réel** : `useAcquisitionStream.ts` ouvre `new EventSource(url)` contre l'endpoint FastAPI `StreamingResponse media_type="text/event-stream"` (`/...stream_acquisition_jobs`). Le refresh manager, lui, est en **polling `setInterval` + REST** (pas de SSE). → La SSE existe et est load-bearing pour la file d'acquisition.

### Tableau comparatif

| Option | Langage shell | Webview | Sidecar Python embarqué + spawn (mac+Win) | IPC sidecar | Empreinte (binaire / RAM) | Maturité / dernière MAJ | Licence | Notes critiques |
|---|---|---|---|---|---|---|---|---|
| **Tauri v2** | Rust | WKWebView (mac) / WebView2 (Win) | Oui via `externalBin` (suffixe target-triple par arch) ; spawn via plugin Shell | stdin/stdout natif **OU** HTTP localhost (libre) | ~3–10 MB / ~30–100 MB | Stable 10/2024, v2.10.x 2026 | MIT + Apache-2.0 | **Bug notarisation macOS avec externalBin (#11992)** → signature manuelle des binaires obligatoire. Webview hétérogène. |
| **Wails v2** | Go | WKWebView / WebView2 | Pas de mécanisme sidecar dédié ; `os/exec` manuel | À toi (HTTP/stdio) | <10 MB (≈3 MB UPX) / faible | Stable, MIT | MIT | Dépendance runtime WebView2 sur Windows (embed/download/bundle). Pas d'embed-binary auto. |
| **Wails v3** | Go | WKWebView / WebView2 | idem, manuel | À toi | similaire | **ALPHA** (alpha.73, 02/2026) | MIT | Trop tôt pour une app à zéro-corruption en prod. |
| **Neutralino** | C++ (runtime) | Webview système | « Extensions » = process externe quelconque | **WebSocket** (credentials via stdin) | ~2.7 MB / faible | Moins mature ; stabilité WS signalée | MIT | IPC WS imposé ; risques stabilité. |
| **Electron (baseline)** | Node.js | Chromium bundlé | `child_process.spawn` (déjà en place) | HTTP localhost (déjà en place) | ~100–150 MB / 200–300 MB | Très mature | MIT | Rendu Chromium **homogène mac/Win** ; lourd. |
| **Localhost + navigateur système / PWA** | — (serveur Python seul) | Navigateur user | Tu ne « spawns » rien : Python EST le serveur | HTTP/SSE direct | ~0 (pas de shell) | — | — | Pas d'app native packagée ; UX/onboarding/notarisation différents. |

### Verdict (orienté robustesse + légèreté + performance, mac+Win, UI web)

- **Tauri v2 est le meilleur candidat « coque légère + UI web »** sur les 3 priorités : empreinte ~10× sous Electron, RAM ~5× moindre, stable et audité, licence permissive. C'est le seul à offrir un **mécanisme sidecar de première classe** (embedding + spawn + permissions déclaratives) aligné sur votre besoin PyInstaller.
- **Découplez le shell de la SSE** : votre archi actuelle (UI → `http://127.0.0.1` FastAPI, REST + SSE `EventSource`) est *idéale* pour Tauri. Gardez exactement ce modèle — webview qui charge l'UrlVue et parle au sidecar **en HTTP localhost**, pas en commandes Tauri. WKWebView gère `EventSource` sur HTTP localhost ; vous évitez ainsi le trou « SSE sur custom-protocol » de Tauri. Ne migrez pas la SSE vers les events Tauri.
- **Le vrai risque Tauri pour vous est la signature macOS, pas le rendu** : le bug `externalBin` + notarisation (#11992) est concret et touche directement une app qui embarque un sidecar Python. Budgétez une étape CI de **signature manuelle deep + hardened runtime + entitlements** de chaque binaire PyInstaller avant notarisation. C'est faisable mais c'est le point de friction n°1 — à prototyper en premier.
- **Webview hétérogène = risque maîtrisable** ici : votre UI est déjà du Vue « classique » consommant une API ; testez sur WKWebView réel (CSS `gap`, Grid, polyfills `-webkit-`) tôt, mais ce n'est pas un blocage de l'ampleur de Figma. Surveillez l'itération `for await` sur `ReadableStream` (non supportée Safari) — votre SSE passe par `EventSource`, donc non concerné, mais évitez `for await (chunk of stream)` ailleurs.
- **Wails (Go) : écartez pour l'instant.** v2 n'a pas d'embedding-binary auto (vous réimplémentez le packaging/signature du sidecar à la main) et ajoute la dépendance runtime WebView2 à gérer ; v3 est en alpha — incompatible avec la priorité « zéro corruption ». **Neutralino** : trop immature et IPC WebSocket imposé. **PWA/localhost pur** : abandonne l'app native packagée (onboarding, mises à jour, intégration OS) — ne répond pas au besoin d'une coque desktop.
- **Pondération finale** : Tauri v2 maximise légèreté+perf sans sacrifier l'UI web, à condition d'investir sur la chaîne signature/notarisation du sidecar. Si ce coût de signature s'avère bloquant en POC, le repli pragmatique est **rester sur Electron** (rendu homogène, sidecar déjà spawné, zéro surprise webview) — au prix de l'empreinte.

### Incertitudes / à confirmer

- **Statut courant de #11992** (juin 2026) : vérifier manuellement si Tauri a livré un fix natif de signature des `externalBin` sur macOS, ou si la signature manuelle reste requise. Source consultée datée déc. 2024.
- **PyInstaller one-dir vs one-file sous Tauri** : le caveat kill-PID et la signature sont plus simples en mode one-dir ; à tester. `externalBin` attend un binaire unique par target-triple — valider la stratégie de packaging (one-file signé) vs un dossier.
- **Démarrage à froid réel du sidecar PyInstaller** (priorité « démarrage rapide ») : non mesuré ici ; PyInstaller one-file a un coût d'extraction au lancement — à benchmarker mac+Win.
- **Comportement exact d'`EventSource` dans WKWebView contre votre endpoint FastAPI** (keepalive `: keepalive`, reconnexion, `readyState===CLOSED`) : à valider sur device macOS réel, pas seulement en build Chromium/Electron.
- **Taille réelle du bundle Tauri une fois le sidecar Python+numpy/pyrekordbox inclus** : le « 3–10 MB » concerne la coque seule ; le sidecar PyInstaller (numpy obligatoire d'après votre mémoire projet) dominera la taille finale — à mesurer.