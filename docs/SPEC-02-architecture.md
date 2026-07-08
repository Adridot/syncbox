# Syncbox — Remise en question architecturale & cible recommandée (Phase 2, V1)

> **Objet.** Challenger *chaque* choix d'architecture, de technologie et de « manière de faire » de l'app actuelle, et proposer **une cible recommandée** optimisée pour les 3 priorités validées : **(1) robustesse/sûreté** (zéro corruption Rekordbox), **(2) empreinte légère** (petit binaire, peu de RAM, démarrage rapide), **(3) performance/réactivité**. La maintenabilité a été *écartée* des priorités — j'assume donc une complexité accrue si elle sert ces trois axes.
>
> **Statut.** V1 = recommandation + **4 forks structurants soumis à validation** (§4). Les choix produits/features sont figés dans [SPEC-01-syncbox.md](SPEC-01-syncbox.md) (§7, journal D1–D25). Recherche factuelle sourcée dans `docs/_research/`.
>
> **Contraintes de cadrage** (réponses validées) : open-source/public · **macOS + Windows** (Linux exclu) · UI web conservée · Spotify OAuth PKCE only · acquisition Deezer « tout au même endroit » (à arbitrer, fork D).

---

## 1. Méthode & verdict en une phrase

J'ai vérifié par recherche web sourcée les 5 points qui déterminent l'archi : (a) librairies d'accès `master.db` par langage, (b) formats d'échange Rekordbox, (c) coques desktop légères, (d) packaging/transport d'un sidecar Python, (e) acquisition Deezer. **Verdict d'ensemble :** garder Python **uniquement** pour la couche Rekordbox (c'est le choix de robustesse, non négociable), **alléger radicalement tout le reste** (coque, transport, packaging, suppression du process externe Deemix), et trancher **une question de fond** — écrire `master.db` en place (fidélité totale) vs passer par les formats d'échange (sûreté maximale mais perte des MyTags/smart playlists).

---

## 2. Remise en question, couche par couche

Format : **Choix actuel** → *Verdict (sourcé)* → **Recommandation**.

### 2.1 — Le découpage en 3 process (Electron main + service Python + renderer)

**Choix actuel.** 3 process : Electron main (TS) qui spawn un service FastAPI/uvicorn (Python) et héberge un renderer Vue ; communication renderer↔service en HTTP `127.0.0.1` + SSE, renderer↔main en IPC, main↔service en spawn (`electron/main.ts`, `service/app/main.py`).

*Verdict.* Le découpage **UI / logique** est sain et porté par la nécessité (pyrekordbox est Python, l'UI est web). En revanche **le triple pont** (IPC + HTTP + SSE) et le **double store de réglages** (electron-store ↔ SQLite, réconciliation push/pull manuelle, cf. SPEC-01 §5 T5) sont de la complexité *subie*, pas *choisie*. Le service web complet (FastAPI/uvicorn) est surdimensionné pour un IPC local : **cold start lent** (jusqu'à plusieurs secondes ; Pydantic v2 multiplie le boot par 2–4×) et **bug connu uvicorn+PyInstaller** (workers qui ne démarrent pas ~50 % du temps) · [FastAPI cold starts](https://medium.com/@hadiyolworld007/fastapi-cold-starts-explained-why-your-containers-feel-slow-and-the-optimization-order-that-dcac906ffe2b), [uvicorn #1820](https://github.com/Kludex/uvicorn/discussions/1820).

**Recommandation.** Garder la séparation **UI web ↔ noyau Python**, mais : (a) **supprimer le double store de réglages** (une seule source de vérité, lue par l'UI) ; (b) **remplacer FastAPI/uvicorn par un worker Python minimal** (cf. §2.5) ; (c) réduire les ponts à **un seul** canal de commande + **un seul** canal d'événements (cf. fork C).

### 2.2 — La coque Electron

**Choix actuel.** Electron 42 (Chromium embarqué). Empreinte ~100–150 Mo binaire, 200–300 Mo RAM au repos · [pkgpulse 2026](https://www.pkgpulse.com/guides/electron-vs-tauri-2026), [raftlabs](https://dev.to/raftlabs/tauri-vs-electron-23d1).

*Verdict.* Frontalement opposé à la priorité **#2 (empreinte)**. **Tauri v2** (stable 02/10/2024, MIT+Apache, audité) produit des binaires **~3–10 Mo** et **~30–100 Mo RAM**, via webview natif (WKWebView macOS / WebView2 Windows), et offre un **mécanisme sidecar de première classe** (`externalBin` + plugin Shell) explicitement prévu pour **un serveur Python bundlé via PyInstaller** · [Tauri 2.0](https://v2.tauri.app/blog/tauri-20/), [Tauri sidecar](https://v2.tauri.app/develop/sidecar/). Deux risques concrets : (1) **bug de notarisation macOS avec `externalBin`** (#11992, ouvert depuis déc. 2024) → il faut **signer manuellement chaque binaire sidecar** ; (2) **webview hétérogène** (WKWebView ≠ WebView2 ≠ Chromium) → tests CSS/JS par OS · [Tauri #11992](https://github.com/tauri-apps/tauri/issues/11992), [webviews Tauri](https://dev.to/shrsv/exploring-system-webviews-in-tauri-native-rendering-for-efficient-cross-platform-apps-9hl). La SSE en `EventSource` **fonctionne** dans WKWebView sur HTTP localhost (à ne PAS faire passer par le custom-protocol Tauri) · [Apple forums #104901](https://developer.apple.com/forums/thread/104901).

**Recommandation.** **Tauri v2** (gain d'empreinte ~10×, RAM ~5×). **Electron en repli** uniquement si la chaîne de signature/notarisation du sidecar macOS s'avère bloquante en POC. ⚠️ **À dé-risquer en tout premier** (cf. §5). → **Fork B**.

### 2.3 — Le runtime service : Python + pyrekordbox

**Choix actuel.** Service Python, accès `master.db` via **pyrekordbox** (read/write SQLCipher).

*Verdict (analyse du paysage, demandée).* **La crypto n'est PAS un verrou** : la clé SQLCipher du `master.db` est une **constante publique connue**, identique sur toutes les installs (l'obfuscation de Rekordbox 6.6.5+ casse seulement l'*extraction automatique*, pas la clé) · [pyrekordbox #97](https://github.com/dylanljones/pyrekordbox/discussions/97), [liamcottle](https://github.com/liamcottle/pioneer-rekordbox-database-encryption). N'importe quel langage avec un binding SQLCipher (Rust `rusqlite`, Node `better-sqlite3-multiple-ciphers`, .NET, Go) peut donc ouvrir la base. **Le vrai verrou est la logique métier d'écriture cohérente** (FK, codes `rb_local_*`, smart playlists, MyTags) que **seul pyrekordbox encapsule de façon mûre** :

| Lib | Langage | Lit/écrit master.db | Maturité | Licence | OS | Note |
|---|---|---|---|---|---|---|
| **pyrekordbox** | Python | **Oui** (8 tables, testé RB 7.0.9) | **Mûre** (v0.4.4 2025, 415★) | **MIT** | Win+mac | Tire `numpy` (eager, non-excludable) → plancher ~30-50 Mo |
| rbox | Rust | Oui (ORM) | **Expérimental**, build cassé | GPL-3.0 | Win+mac | Trop risqué pour « zéro corruption » |
| RDBManager | Node | Oui (cues/BPM seulement) | Très petit projet | GPL-3.0 | **Windows seul** | Écriture trop partielle |
| rekordcrate / crate-digger | Rust / Java | **Non** (exports USB only) | Actifs | MPL / — | — | Hors sujet (device export) |
| Go / .NET / Swift / C++ | — | **Aucune lib métier** | — | — | — | Réécriture from scratch |

Sources : [pyrekordbox](https://github.com/dylanljones/pyrekordbox), [rbox crates.io](https://crates.io/crates/rbox), [RDBManager](https://github.com/l3x04/RDBManager), [rekordcrate](https://github.com/Holzhaus/rekordcrate).

**Recommandation.** **Garder Python + pyrekordbox** pour la couche Rekordbox — c'est l'arbitrage **robustesse (priorité #1) > légèreté (#2)**. Réimplémenter l'écriture en Rust/Node serait *le* risque de corruption, pour un gain de taille que l'on récupère autrement (coque + transport + acquisition). On **paie le plancher numpy (~30-50 Mo)** et on optimise le reste. *(L'option full-Rust via rbox reste un chemin futur si rbox mûrit ; non recommandée aujourd'hui.)*

### 2.4 — La stratégie d'écriture Rekordbox : `master.db` en place vs formats d'échange

**Choix actuel.** Écriture directe de `master.db` (apply library/event, dedup, relink, soft-delete), + un « Live Import » M3U8 secondaire (que SPEC-01 D10 retire).

*Verdict (le point le plus structurant).* Écrire `master.db` donne la **fidélité totale** : MyTags, **smart playlists** (le « Event Imports » + la bibliothèque taggée *sont* la valeur de Syncbox), mise à jour **en place**, sans action manuelle. Le coût : dépendance SQLCipher, **verrou « Rekordbox fermé »**, et risque de corruption (mitigé aujourd'hui par backup-avant-mutation + soft-delete). **La voie « formats d'échange » est plus sûre et plus légère** mais **ampute le cœur produit** :

| Voie | Corruption possible ? | Verrou RB fermé ? | MyTags | Smart playlists | En place ? | Action manuelle ? |
|---|---|---|---|---|---|---|
| **master.db (pyrekordbox)** | Oui (mitigée backup) | **Oui** | **Oui** | **Oui** | **Oui** | Non |
| **XML import** | **Non** | **Non** | **Non** | **Non** (aplaties) | Non (volet Bridge) | **Oui** (import RB manuel, additif/buggé) |
| **M3U8** | Non | Non | Non | Non | Non | Oui |

L'export XML a été **retiré de l'UI dès RB 6** (seul l'import subsiste), atterrit dans un volet « Bridge » séparé, et son upsert est **additif/buggé** sur les tracks existants · [spec XML PDF](https://cdn.rekordbox.com/files/20200410160904/xml_format_list.pdf), [Engine DJ thread](https://community.enginedj.com/t/no-more-xml-export-in-rekordbox-6-blocks-denon-prime-users/21170), [Mixo import bug](https://www.mixo.dj/guides/rekordbox-xml-import-bug). pyrekordbox sait **écrire le XML** (`rbxml.save()`, cues + beatgrid portés, MIT) mais **pas** les MyTags/smartlists (absents du format) · [pyrekordbox rbxml](https://raw.githubusercontent.com/dylanljones/pyrekordbox/master/pyrekordbox/rbxml.py).

**Recommandation.** **Garder l'écriture `master.db` comme chemin principal** (sans elle, Syncbox n'est qu'un downloader Deezer de plus), en s'appuyant sur la colonne vertébrale de sûreté déjà spécifiée (backup obligatoire, soft-delete, garde RB fermé, corbeille OS — SPEC-01 §3.1/D12). **Décision validée : A2 — écriture `master.db` *seule*, sans mode XML** (cœur produit intact, surface minimale, aucune échappatoire « zéro écriture »). → **Fork A** (cf. §4 décisions validées).

### 2.5 — Transport (HTTP + SSE + polling) & couche de données UI

**Choix actuel.** UI ↔ service en **HTTP REST + SSE** ; **deux moteurs de rafraîchissement** (vue-query partiel + `useRefreshManager` setInterval) ; SSE qui n'alimente **qu'un seul** des deux stores de jobs (SPEC-01 §5 F5/F6/T4). FastAPI/uvicorn côté service.

*Verdict.* (a) Côté UI, la **double couche de données est une migration inachevée** (git `phase-2a→2d`), pas un choix — à **converger sur une seule** (cf. mémoire projet « dual data layer kept » : statut à reconfirmer dans une réécriture ; ici on tranche pour la légèreté/perf → **convergence**). (b) Côté service, **FastAPI/uvicorn est surdimensionné** pour un IPC local : un **worker Python nu en JSON-RPC sur stdin/stdout** démarre quasi-instantanément, est plus léger, et **supprime la surface réseau loopback à sécuriser** · [JSON-RPC stdio vs HTTP](https://medium.com/ingeniouslysimple/building-an-electron-app-from-scratch-part-4-5d0906897bf1). (c) La **reconstruction manuelle du nom de fichier téléchargé** (SPEC-01 §5 F1/D18) doit disparaître au profit du **vrai chemin de sortie** lu depuis le downloader.

**Recommandation.** **Une seule couche de cache réactive côté UI** (style query-cache, intervalles de refetch unifiés, un flux d'événements canonique pour les jobs). Côté noyau, **worker Python minimal**, **piloté en JSON-RPC** ; la progression des jobs poussée à l'UI via **un seul canal d'événements**. Le choix exact du transport (stdin/stdout brokeré par Tauri **vs** HTTP+SSE localhost conservé) = **Fork C**.

### 2.6 — Packaging du sidecar Python

**Choix actuel.** PyInstaller `--onedir` (binaire autonome), embarqué en `extraResources` Electron.

*Verdict.* `--onedir` est le bon mode (le `--onefile` ré-extrait à chaque démarrage → lent, à proscrire vu la priorité démarrage) · [PyInstaller docs](https://pyinstaller.org/en/stable/usage.html). Alternatives : **Nuitka** (binaire plus petit ~60 Mo, runtime 2-4× plus rapide, mais build lent et compile tout numpy) ; **python-build-standalone (Astral)** (cross macOS arm64 + Windows, maintenu) · [x321 benchmark](https://x321.org/empirical-pyinstaller-vs-nuitka-vs-cx_freeze/), [astral.sh](https://astral.sh/blog/python-build-standalone). **PyOxidizer est abandonné** (à écarter) · [PyOxidizer #737](https://github.com/indygreg/PyOxidizer/discussions/737). **Le vrai risque robustesse n'est pas le packager mais le cycle de vie** : un binaire PyInstaller spawne **2 process** ; un `kill()` naïf laisse un **orphelin qui garde la transaction SQLCipher ouverte** → corruption · [Tauri #11686](https://github.com/tauri-apps/tauri/issues/11686). `sqlcipher3-wheels` (SQLCipher 4 embarqué) couvre l'ouverture du master.db sans toolchain C chez l'utilisateur · [sqlcipher3-wheels](https://pypi.org/project/sqlcipher3-wheels/).

**Recommandation.** **PyInstaller `--onedir`** (sûr, rapide à livrer) au départ ; **Nuitka** comme upgrade taille/perf si nécessaire. **Impératif robustesse** : arrêt propre = **handshake RPC « shutdown » → attendre fermeture DB → kill de l'arbre de process** (`taskkill /T` Windows, process-group macOS), + garde anti-double-instance. Mesurer empiriquement le poids numpy+sqlcipher3 et le cold start (leviers #1 de taille/démarrage).

### 2.7 — Acquisition Deezer/Deemix (process externe sur :6595)

**Choix actuel.** Pilotage d'une **app Deemix externe** (Electron/Node) via HTTP `127.0.0.1:6595`, ARL poussé par l'app (SPEC-01 §3.5). Un **second runtime** complet, fragile (parsing heuristique de la queue, globals process).

*Verdict.* La lib **`deemix` (Python, GPL-3.0)** est **embarquable** (API conçue pour ça), avec **5 dépendances légères** (`click, pycryptodomex, mutagen, requests, deezer-py`) — **pas de numpy** · [pypi deemix](https://pypi.org/project/deemix/), [setup.py](https://gitlab.com/RemixDev/deemix-py/-/raw/main/setup.py). L'embarquer **dans le sidecar Python existant supprime le process Node/Electron externe** → **gain net de légèreté/RAM/démarrage** (« tout au même endroit »). **Mais** : la lib est **figée sur PyPI depuis 2022**, casse périodiquement au gré des changements d'API Deezer (forks de fix : DeemixFix 2024), **`streamrip`** est mieux maintenu (4.7k★, 2026) mais orienté CLI · [streamrip](https://github.com/nathom/streamrip). Deux coûts à assumer : (1) **GPL-3.0 contamine tout le binaire distribué** (acceptable car open-source, rédhibitoire pour du proprio) ; (2) **risque DMCA/takedown** documenté (plainte Deezer 2021 visant `deemix-gui` ; retraits GitHub historiques) → embarquer le downloader **augmente la surface de takedown du dépôt** · [DMCA Deezer 2021](https://github.com/github/dmca/blob/master/2021/02/2021-02-10-deezer.md), [TorrentFreak](https://torrentfreak.com/deezer-targets-pirate-apps-maliciously-retrieving-publishing-encryption-keys-210212/).

**Recommandation.** **Embarquer une lib Python de download** (deemix ou streamrip) dans le sidecar, **isolée derrière une interface mince**, **version pinée**, **jamais sur le chemin critique d'écriture master.db**. Sérieusement considérer de la livrer comme **module/plugin optionnel** (l'utilisateur l'active + fournit son ARL) pour **limiter l'exposition juridique** du dépôt principal. → **Fork D**.

### 2.8 — Les « manières de faire » récurrentes (transversal)

| Pratique actuelle | Verdict | Cible |
|---|---|---|
| Reconstruction du nom de fichier téléchargé (`audio.py`) | Source chronique de bugs (SPEC-01 F1) | **Lire le vrai chemin** de sortie du downloader (D18) |
| Globals process (`_applied_arl`, caches mtime) | Races, fuites d'état (F3) | État porté par instance/requête ; pas de global mutable partagé |
| Navigation sans routeur (`ui.activeView`, Settings = `v-else`) | OK pour desktop mais pas de deep-link/persistance, fourre-tout dangereux | Garder l'état d'écran (léger) mais **défaut explicite** + persistance, ou un mini-routeur |
| Gestion d'erreur générique (`error.message` brut, parse null) | Fuite de texte backend, null silencieux (F7) | Mapping erreur→message i18n ; validation de schéma au bord |
| 2 normalisations matching/dedup | Jugements « identique » divergents (T3) | **Une** pipeline normalisation partagée (D19) |
| Migration SQLite ad-hoc + re-seed à chaque boot | Écrase les éditions utilisateur (B4) | **Migrations versionnées ordonnées** ; seed strictement 1er run |
| Tokens OAuth en clair dans SQLite | Inacceptable en open-source | **Keychain OS / DB chiffrée** |

---

## 3. Architecture cible recommandée (synthèse)

Optimisée **robustesse > légèreté > performance** ; UI web conservée ; macOS + Windows.

```
┌──────────────────────────────────────────────────────────────┐
│  Coque: TAURI v2 (Rust, ~3-10 Mo, webview natif WKWebView/    │
│  WebView2)                                                     │
│   • héberge l'UI web   • spawn + supervise le sidecar Python   │
│   • signe le binaire sidecar (chaîne macOS à dé-risquer)       │
└───────────────┬──────────────────────────────┬───────────────┘
                │ (1 canal commande +           │ (spawn + cycle de
                │  1 canal événements)           │  vie: shutdown
                ▼                                ▼  propre, kill arbre)
   ┌────────────────────────┐      ┌────────────────────────────────┐
   │ UI: Vue 3 (conservée)   │      │ NOYAU: sidecar Python minimal   │
   │  • UNE couche de cache  │      │  (PAS de FastAPI/uvicorn)       │
   │    réactive (convergée) │      │  • pyrekordbox (master.db, MIT) │
   │  • 1 flux d'événements   │      │  • acquisition Deezer (lib      │
   │    jobs canonique        │      │    embarquée, isolée, pinée)    │
   │  • i18n FR/EN            │      │  • SQLite app (état) + migrations│
   └────────────────────────┘      │    versionnées                  │
                                    │  • Spotify OAuth PKCE only       │
                                    └────────────────────────────────┘
   Sûreté (inchangée, non négociable): garde « RB fermé », backup
   avant chaque mutation, soft-delete, corbeille OS, résolution de
   chemins volume-relatif/absolu (SPEC-01 §3.1-3.2 / §9).
```

**Ce qui change vs aujourd'hui** : Electron→Tauri (−~140 Mo) ; FastAPI/uvicorn→worker Python minimal JSON-RPC stdin/stdout (cold start) ; process Deemix externe→lib embarquée **en module optionnel** (−1 runtime quand activé) ; double couche de données→une seule ; double store réglages→une seule source ; reconstruction de nom→vrai chemin ; migrations ad-hoc→versionnées ; tokens→chiffrés.
**Ce qui ne change pas** : Python+pyrekordbox pour Rekordbox ; UI Vue ; la colonne vertébrale de sûreté ; le modèle de domaine (SPEC-01 §6).

---

## 4. Les 4 forks majeurs à valider

> **⚠️ CLOS — tranché dans [SPEC-UNIFIED.md](SPEC-UNIFIED.md) §7.1.** Les 4 forks sont décidés : **A** = `master.db` en place **sans** mode XML (le double-sens du label « A2 » est abandonné) ; **B** = Tauri v2 (POC signature #11992) ; **C** = **garder HTTP+SSE localhost**, rejeter JSON-RPC ; **D** = lib embarquée en **module optionnel** + ARL (lib déléguée au POC). Cette section et la table « Décisions validées » ci-dessous sont conservées comme **historique** ; la décision faisant foi est dans SPEC-UNIFIED.

> Recommandation indiquée en premier ; ce sont les choix structurants où ta validation est requise.

**Fork A — Stratégie d'écriture Rekordbox.**
- **A1 (reco)** : `master.db` en place comme chemin principal (MyTags + smart playlists + en place), porté par la sûreté backup/soft-delete/corbeille. Optionnellement, ajouter un mode « export XML » sûr.
- A2 : Formats d'échange only (XML/M3U8) — zéro corruption, pas de verrou RB, mais **perte MyTags + smart playlists** + import manuel. Transforme Syncbox en downloader simple.
- *Pourquoi ça compte* : c'est l'identité du produit vs la sûreté absolue.

**Fork B — Coque desktop.**
- **B1 (reco)** : Tauri v2 (empreinte ~10×, RAM ~5×), Electron en repli si la signature sidecar macOS bloque.
- B2 : Rester sur Electron (rendu homogène, sidecar déjà en place, zéro surprise webview) au prix de l'empreinte.
- *Pourquoi ça compte* : priorité #2 vs risque/effort de la chaîne de signature Tauri.

**Fork C — Transport noyau ↔ UI.**
- **C1 (reco)** : worker Python minimal en **JSON-RPC stdin/stdout**, brokeré par Tauri, jobs poussés en **événements Tauri** (le plus léger/rapide, pas de surface réseau).
- C2 : conserver **HTTP + SSE localhost** (migration plus douce, SSE éprouvée en WKWebView) avec un Python minimal mais un mini-serveur.
- *Pourquoi ça compte* : pureté légèreté/perf vs effort de réécriture du transport.

**Fork D — Acquisition Deezer.**
- **D1 (reco)** : embarquer une lib Python (deemix/streamrip) dans le sidecar, isolée + pinée ; **la livrer en module/plugin optionnel** (l'utilisateur l'active + ARL) pour limiter l'exposition DMCA et le couplage GPL du cœur.
- D2 : garder un downloader **externe** piloté en HTTP (isolation robuste, mais 2e runtime, « pas au même endroit »).
- D3 : réécrire l'acquisition **nativement** (Rust/Go, ARL+Blowfish, licence permissive, pas de 2e runtime) — plus de maintenance face aux changements Deezer.
- *Pourquoi ça compte* : « tout au même endroit » vs robustesse/maintenance vs licence/légalité.

### Décisions validées (forks A–D)

| Fork | Décision | Effet sur la cible |
|---|---|---|
| **A — Écriture RB** | **A2 — `master.db` en place *seulement*** (pas de mode XML) | Cœur produit (MyTags + smart playlists + en place) intact ; surface minimale ; pas d'échappatoire « zéro écriture » — la sûreté repose **entièrement** sur la colonne vertébrale backup / soft-delete / corbeille OS / garde RB fermé. ⇒ rend les POC §5.2 (cycle de vie process) et §5.5 (non-régression schéma) d'autant plus critiques. |
| **B — Coque** | **B1 — Tauri v2** (repli Electron si la signature sidecar macOS bloque) | −~140 Mo binaire, RAM ~5× moindre. Dé-risquer la signature/notarisation macOS du sidecar (#11992) en **POC n°1**. |
| **C — Transport** | **C1 — worker Python minimal, JSON-RPC stdin/stdout** + jobs poussés en événements Tauri | Pas de FastAPI/uvicorn, pas de surface réseau loopback, cold start minimal. Le pont UI↔noyau passe par le broker Tauri ; transport à réécrire (pas de SSE/HTTP). |
| **D — Acquisition** | **D1 — lib Python embarquée, livrée en module/plugin *optionnel*** (l'utilisateur l'active + fournit son ARL) | Supprime le process externe **quand activé** ; isolée derrière une interface mince, version pinée, **jamais sur le chemin critique `master.db`** ; limite l'exposition DMCA et confine le copyleft GPL au module optionnel plutôt qu'au cœur. |

---

## 5. Risques & ordre de dé-risquage (POC avant tout engagement)

1. **Signature + notarisation du sidecar Python sous Tauri macOS** (#11992) — *le* point de friction n°1 ; à prototyper **en premier**. Si bloquant → repli Electron (Fork B).
2. **Cycle de vie du process** (kill d'arbre + fermeture propre de la connexion SQLCipher) — risque de corruption #1 côté packaging ; à valider mac **et** Windows.
3. **Taille réelle du bundle** (numpy + sqlcipher3 + lib download) et **cold start** du worker Python — mesurer empiriquement (lèvera/confirmera le gain de légèreté).
4. **`EventSource`/transport dans WKWebView réel** (si Fork C2) — tester sur device macOS, pas seulement en Chromium/Electron.
5. **Fidélité d'écriture pyrekordbox sur RB 7.x cible** (smart playlists/MyTags, bugs résiduels #110) — harnais de tests de non-régression sur le schéma `master.db` **avant** tout déploiement.
6. **Acquisition** : valider qu'un fork deemix/streamrip fonctionne avec l'API Deezer **actuelle** + packaging `pycryptodomex`.

---

## Annexe — Sources principales

Librairies RB : [pyrekordbox](https://github.com/dylanljones/pyrekordbox) · [clé SQLCipher #97](https://github.com/dylanljones/pyrekordbox/discussions/97) · [rbox](https://crates.io/crates/rbox) · [RDBManager](https://github.com/l3x04/RDBManager) · [rekordcrate](https://github.com/Holzhaus/rekordcrate).
Formats : [XML spec PDF](https://cdn.rekordbox.com/files/20200410160904/xml_format_list.pdf) · [pyrekordbox rbxml](https://pyrekordbox.readthedocs.io/en/latest/formats/xml.html) · [import bug](https://www.mixo.dj/guides/rekordbox-xml-import-bug).
Coques : [Tauri 2.0](https://v2.tauri.app/blog/tauri-20/) · [Tauri sidecar](https://v2.tauri.app/develop/sidecar/) · [notarisation #11992](https://github.com/tauri-apps/tauri/issues/11992) · [Wails](https://wails.io/).
Packaging : [PyInstaller](https://pyinstaller.org/en/stable/usage.html) · [Nuitka vs PyInstaller](https://x321.org/empirical-pyinstaller-vs-nuitka-vs-cx_freeze/) · [python-build-standalone](https://astral.sh/blog/python-build-standalone) · [orphan #11686](https://github.com/tauri-apps/tauri/issues/11686).
Acquisition : [deemix lib](https://pypi.org/project/deemix/) · [streamrip](https://github.com/nathom/streamrip) · [DMCA Deezer 2021](https://github.com/github/dmca/blob/master/2021/02/2021-02-10-deezer.md).

Recherche détaillée par axe : `docs/_research/00_RB.md` … `04_Acquisition.md`.
