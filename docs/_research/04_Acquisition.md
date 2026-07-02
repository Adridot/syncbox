I have all the data I need. Note pleezer is a *player* (streaming/Connect), not a downloader, and uses a non-OSI "Sustainable Use License" — important distinction. Let me compile the deliverable.

## Acquisition de morceaux Deezer — embarquer une lib vs downloader externe (D4)

### Constat (faits sourcés)

**deemix (lib Python originale, RemixDev)**
- La lib `deemix` se décrit explicitement comme **"a barebone deezer downloader library"**, utilisable comme CLI standalone OU intégrée dans une UI via son API — c'est donc bien une **librairie embarquable**, pas qu'une app · [pypi.org/project/deemix](https://pypi.org/project/deemix/).
- **Langage Python ≥3.7. Licence GPL-3.0.** Dernière version PyPI **3.6.6 du 11 janvier 2022** → PyPI **non mis à jour depuis ~4 ans** · [libraries.io/pypi/deemix](https://libraries.io/pypi/deemix), [pypi.org/project/deemix](https://pypi.org/project/deemix/).
- **Dépendances minces et standard (5)** : `click`, `pycryptodomex`, `mutagen`, `requests`, `deezer-py>=1.3.0` · [setup.py RemixDev/deemix-py](https://gitlab.com/RemixDev/deemix-py/-/raw/main/setup.py). Aucune dépendance lourde type numpy/ML → bon pour la légèreté du bundle.
- La lib `deemix` **dépend de `deezer-py`** (= `deezer-py`/`deezer-gw`, aussi de RemixDev), qui gère l'auth ARL et l'API GW de Deezer · setup.py ci-dessus. Le repo source original (`RemixDev/deemix-py`, GitLab) totalise ~675-678 commits ; **le dépôt note lui-même "Fix whatever is broken"** dans le TODO, signe de maintenance incomplète · [gitlab.com/RemixDev/deemix-py](https://gitlab.com/RemixDev/deemix-py).
- **Dépendance ARL impérative** : authentification par token ARL (cookie de session Deezer, chaîne ~192 caractères) ; il faut un compte Deezer valide · [pypi/CLI docs deemix](https://pypi.org/project/deemix/), [github.com/youegraillot/lidarr-on-steroids#106](https://github.com/youegraillot/lidarr-on-steroids/issues/106).

**deemix (l'app / le projet "revived")**
- `bambanah/deemix` est le **monorepo de la revival** (JS/TS/Vue, **GPL-3.0**), explicitement "the monorepo for the revived Deemix project, originally created by … RemixDev" (RemixDev n'est plus actif). **~1 000 stars**, **activité récente** (releases jusqu'à `deezer-sdk@1.10.2` en avril 2026). C'est l'app GUI/webui Electron + Express qui expose le **port 6595** que vous pilotez actuellement · [github.com/bambanah/deemix](https://github.com/bambanah/deemix).
- Cette revival est en **JS/TS** (deezer-sdk, deemix-core, webui, gui Electron) — donc **distincte de la lib Python**. Embarquer "la revival" = embarquer du Node, pas du Python.
- **deemix-remastered (`DRAZY/deemix-remastered`)** = **app desktop réécrite from scratch** (Electron + Vue 3 + TS), "spiritual successor … no shared code", dernière release **v1.6.5 le 15 mai 2026**. C'est une **app, pas une lib embarquable** · [github.com/DRAZY/deemix-remastered/releases](https://github.com/DRAZY/deemix-remastered/releases).
- **Forks de fix Python** existent à cause des changements d'API Deezer : `DeeplyDrumming/DeemixFix` (GitLab, créé ~22 juil. 2024), `vietsman/deemix-py` (fork peu adopté, 1 star) · [gitlab.com/deeplydrumming/DeemixFix](https://gitlab.com/deeplydrumming/DeemixFix), [github.com/vietsman/deemix-py](https://github.com/vietsman/deemix-py). Signal : **la lib Python casse périodiquement et survit par forks communautaires**.

**streamrip**
- **App CLI Python (100% Python), GPL-3.0**, **~4.7k stars**, **maintenue activement** (release v2.2.0 mars 2026) ; supporte Qobuz/Tidal/Deezer/SoundCloud · [github.com/nathom/streamrip](https://github.com/nathom/streamrip), [formulae.brew.sh/formula/streamrip](https://formulae.brew.sh/formula/streamrip).
- pip-installable mais **conçue comme CLI/config-file**, pas comme API d'embarquement propre ; usage Deezer via ARL confirmé par les issues (changements de format d'URL Deezer en juin 2025) · [issue #865](https://github.com/nathom/streamrip/issues/865).

**OrpheusDL + module Deezer**
- `OrpheusDL` (OrfiTeam) = framework modulaire ; `orpheusdl-deezer` (uhwot) = module Deezer. **Aucune licence déclarée** sur le module Deezer, pas de release récente (>6 mois), support faible · [kandi/orpheusdl-deezer](https://kandi.openweaver.com/python/uhwot/orpheusdl-deezer), [github.com/uhwot/orpheusdl-deezer](https://github.com/uhwot/orpheusdl-deezer). Embarquement = framework + module, plus lourd à intégrer proprement.

**Alternatives hors Python**
- **Node/JS** : la revival deemix elle-même (`deezer-sdk` en TS) ; `deezer-js` (npm, dernière publi ~3 ans), `kmille/deezer-downloader` · [npmjs.com/package/deezer-js](https://www.npmjs.com/package/deezer-js), [github.com/kmille/deezer-downloader](https://github.com/kmille/deezer-downloader).
- **Rust** : `Rusteer` (lib+CLI, ARL), `deezer_downloader`/`zggff` (crate de download+décryptage), `lm-deezer-bf-dec` (accélère le décryptage Blowfish) · [github.com/xScherpschutter/Rusteer](https://github.com/xScherpschutter/Rusteer), [crates.io/crates/deezer_downloader](https://crates.io/crates/deezer_downloader). **`pleezer` (roderickvd)** est un **player Deezer Connect headless, PAS un downloader**, et sous **"Sustainable Use License" (non-OSI, non-commercial seulement)** — à ne pas confondre · [github.com/roderickvd/pleezer](https://github.com/roderickvd/pleezer), [crates.io/crates/pleezer](https://crates.io/crates/pleezer/0.11.0).
- **Go** : `joshbarrass/deezerdl`, `89z/deezer` (fonctions `getBlowfishKey`, `Decrypt`, `GetDownloadURL`) · [pkg.go.dev/…/deezerdl/pkg/deezer](https://pkg.go.dev/github.com/joshbarrass/deezerdl/pkg/deezer).
- Constante technique : tous reposent sur **ARL + décryptage Blowfish** des fichiers Deezer ; le savoir-faire est documenté et reproduit dans plusieurs langages.

**Dimension légale / licence (factuel)**
- **GPL-3.0 = copyleft fort.** Embarquer `deemix`/`streamrip` (GPL-3.0) **dans le service Python** crée vraisemblablement une œuvre dérivée/combinée → l'ensemble distribué devrait être sous GPL-3.0 (code source ouvert, mêmes droits transmis). C'est un fait de licence, pas un avis juridique. Syncbox étant déjà open-source, l'impact diffère d'un produit propriétaire mais **contamine tout le binaire distribué** · licences GPL-3.0 listées ci-dessus.
- **Télécharger via ARL viole les CGU/DRM de Deezer** : Deezer a déposé une **plainte DMCA le 10 février 2021** (Deezer SA) visant `deezloader`, **`deemix-gui`**, DeezLoader-Reborn/Remix, etc., motif : usage de **"private encryption keys retrieved maliciously to bypass Deezer's security measures to unlawfully download its music catalogue"** (contournement de mesures techniques) · [github/dmca 2021-02-10-deezer.md](https://github.com/github/dmca/blob/master/2021/02/2021-02-10-deezer.md).
- Historique de **retraits GitHub** d'outils Deezer (Deezloader, DeezerDownload, Deeze et forks) suite aux DMCA Deezer · [torrentfreak](https://torrentfreak.com/deezer-targets-pirate-apps-maliciously-retrieving-publishing-encryption-keys-210212/), [digitalmusicnews 2017](https://www.digitalmusicnews.com/2017/12/26/deezer-deezloader-dmca/). Risque concret de **takedown du repo qui distribue/embarque l'outil**.

### Tableau comparatif

| Option | Langage | Lib embarquable ? | Deezer via ARL | Maturité / dernière MAJ | Licence | Dépendances / poids | Notes |
|---|---|---|---|---|---|---|---|
| **deemix (lib Python, RemixDev)** | Python | **Oui** (API conçue pour ça) | Oui (deezer-py) | PyPI figé v3.6.6 (jan 2022) ; survit par forks | **GPL-3.0** | 5 deps légères (click, pycryptodomex, mutagen, requests, deezer-py) | Le plus naturel pour embarquer dans VOTRE service Python ; casse périodiquement |
| **deemix revival (bambanah)** | JS/TS/Vue | App (sdk TS réutilisable) | Oui | **Active** (2026, ~1k★) | GPL-3.0 | Stack Node + Electron | C'est l'app port 6595 actuelle ; pas du Python |
| **deemix-remastered (DRAZY)** | Electron/Vue/TS | Non (app) | Oui | Active (v1.6.5 mai 2026) | (à confirmer) | App complète | Concurrent direct de Syncbox, pas une lib |
| **streamrip** | Python | Partiel (CLI/config-first) | Oui | **Très active** (v2.2.0 mars 2026, 4.7k★) | GPL-3.0 | Python only | Multi-source ; API d'embarquement non idiomatique |
| **OrpheusDL + module Deezer** | Python | Framework+module | Oui | Module peu actif (>6 mois) | OrpheusDL: ? / module Deezer: **aucune licence** | Framework | Licence module floue → risque |
| **Rust (Rusteer, deezer_downloader)** | Rust | Oui (crates) | Oui | Variable | (par crate) | Binaire natif léger | Réécriture nécessaire ; gain légèreté |
| **Go (deezerdl, 89z/deezer)** | Go | Oui | Oui | Variable | (par repo) | Binaire natif léger | Idem |
| **pleezer** | Rust | Lib/app | Oui | Active | **Sustainable Use (non-OSI, non-commercial)** | — | **PLAYER, pas downloader** — hors sujet |

### Verdict (orienté robustesse + légèreté + performance, macOS+Windows, UI web)

- **Pour "tout au même endroit", la voie la moins coûteuse est d'embarquer `deemix` comme librairie dans votre service Python existant** (vous avez déjà un service Python pour `master.db`). Ses 5 dépendances sont légères et standard (pas de numpy) → **excellent pour l'empreinte** vs lancer un second process Node/Electron sur :6595. C'est la plus grosse simplification d'archi et de RAM disponible.
- **Mais la robustesse de l'acquisition est faible et instable** : PyPI figé depuis 2022, casses récurrentes liées aux changements d'API Deezer (DeemixFix 2024, issues streamrip 2025). Si vous embarquez, **vinglez une version/fork précis, isolez-le derrière une interface mince, et prévoyez un chemin de mise à jour rapide** — ne le mettez jamais sur le chemin critique de l'écriture de `master.db`.
- **`streamrip` est le projet le mieux maintenu et le plus solide** (4.7k★, releases 2026, Python pur) ; si la maintenance prime sur l'élégance d'API, c'est le pari le plus sûr — au prix d'une intégration moins "lib-friendly" (orienté CLI/config).
- **Couper le process externe :6595 est un gain net de légèreté et de démarrage** (un binaire Python au lieu de Python + app Node/Electron). C'est le levier #2 le plus aligné sur vos priorités après l'unification du langage.
- **Coût licence GPL-3.0, à assumer consciemment** : embarquer deemix/streamrip pousse tout le binaire distribué de Syncbox sous **GPL-3.0**. Acceptable pour un projet open-source, **rédhibitoire** si vous envisagiez un jour du proprio/closed-source. Une **réécriture Rust/Go** (crates avec licences plus permissives) éviterait à la fois GPL et le second runtime — mais demande de réimplémenter ARL + Blowfish, donc charge de maintenance face aux changements Deezer.
- **Risque DMCA/distribution réel et documenté** (plainte Deezer 2021 ciblant `deemix-gui` ; retraits GitHub historiques) : **embarquer le downloader dans le binaire distribué augmente la surface de takedown** du dépôt/des releases Syncbox. Mitigation possible : **garder l'acquisition comme module optionnel/plugin séparé** (l'utilisateur fournit ARL + installe le composant), plutôt que bundlé par défaut — compromis entre "tout au même endroit" et exposition juridique.

### Incertitudes / à confirmer
- **État exact de maintenance de la lib `deemix` Python en 2025-2026** : PyPI est figé à 2022, mais quel fork (DeemixFix ? autre ?) fonctionne réellement aujourd'hui avec l'API Deezer actuelle ? À tester en conditions réelles avec un ARL valide. Confiance : moyenne.
- **API d'embarquement de `streamrip`** : pip-installable confirmé, mais la stabilité de son API Python interne pour un usage programmatique (vs CLI) n'est pas documentée — à vérifier dans le code.
- **Licence d'OrpheusDL (framework)** et du module Deezer (déclaré "no license") — à confirmer avant tout usage ; l'absence de licence = pas de droits d'usage accordés par défaut.
- **Licence exacte de `deemix-remastered`** (DRAZY) non vérifiée ici.
- **Compatibilité Windows + macOS** des forks Python deemix avec décryptage Blowfish (pycryptodomex) : standard, mais le packaging PyInstaller (vous avez déjà le souci numpy/pyrekordbox) doit être validé pour `pycryptodomex`/`mutagen`.
- **Qualification juridique précise** "œuvre dérivée GPL" pour un service Python qui importe deemix : c'est l'interprétation standard du copyleft, mais une confirmation par un juriste est requise pour toute décision de distribution — je ne donne pas d'avis juridique définitif.