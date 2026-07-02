I have all the data I need for a solid, sourced deliverable.

## Empaqueter et piloter un service/binaire Python en sidecar d'une app desktop légère (perf + taille + démarrage)

### Constat (faits sourcés)

**Packagers Python — tailles et démarrage**
- Benchmark indépendant déc. 2025 (Python 3.12.2, Ubuntu 24.04 + Win 11) : PyInstaller ~95 MB / 250 ms démarrage ; Nuitka ~60 MB / 180 ms ; cx_Freeze ~80 MB / 220 ms · [x321.org](https://x321.org/empirical-pyinstaller-vs-nuitka-vs-cx_freeze/). ⚠ Le banc n'isole pas onefile vs onedir ni le poids exact de numpy ; ce sont des moyennes agrégées sur 3 workloads.
- Nuitka produit généralement les plus petits binaires (linking statique, compilation) et tourne 2–4× plus vite que CPython au runtime, mais build le plus lent ; PyInstaller build le plus vite · [coderslegacy](https://coderslegacy.com/nuitka-vs-pyinstaller/).
- PyInstaller `--onefile` ≈ 3× plus petit que `--onedir` MAIS au lancement il **décompresse dans un dossier temp** puis lance Python → démarrage à froid lent ; la doc officielle recommande de **ne pas utiliser onefile** si le temps d'extraction gêne · [PyInstaller docs](https://pyinstaller.org/en/stable/usage.html). Banc cité : workload PyTorch/ML en onefile ≈ 180 MB, ~3,2 s de démarrage.
- Réduction de taille : utiliser un **venv minimal** (PyInstaller exclut alors les deps optionnelles non installées) + flags `--exclude`, est la voie recommandée ; lister les exclusions à la main est peu praticable · [PyInstaller issue #3111](https://github.com/pyinstaller/pyinstaller/issues/3111).

**PyOxidizer — à écarter**
- **Non maintenu** : pas de release depuis janv. 2023, l'auteur indique qu'il ne reprendra probablement pas le projet (statut mars 2024) · [PyOxidizer discussion #737](https://github.com/indygreg/PyOxidizer/discussions/737), [Anki issue #3081](https://github.com/ankitects/anki/issues/3081) (ouverte 19 mars 2024). Anki note que PyOxidizer était « considérablement plus agréable que PyInstaller » mais doit le remplacer pour cause de bit-rot / montées de version Python.

**Runtime Python embarqué (sans packager)**
- **Windows embeddable** : ZIP officiel ~7 MB téléchargé, ~12 MB extrait ; stdlib pré-compilée en .pyc, pas de pip/tcl-tk. Conçu pour être embarqué dans une app. **Windows uniquement** · [docs.python.org/using/windows](https://docs.python.org/3/using/windows.html).
- **python-build-standalone** (maintenu par **Astral**, moteur de `uv`) : builds Python autonomes et portables, stdlib + pip incluses, dispo **macOS arm64 (aarch64) ET Windows x86_64**. C'est l'équivalent cross-platform de l'embeddable. Note : binaires Windows dépendent du VC++ Redistributable (vcruntime140.dll), non inclus · [astral.sh blog](https://astral.sh/blog/python-build-standalone), [repo](https://github.com/astral-sh/python-build-standalone).

**pyrekordbox — contrainte de dépendances (confirmé)**
- Deps runtime exactes (pyproject master) : `bidict>=0.21.0`, `construct>=2.10.0`, **`numpy>=1.19.0`**, `packaging`, `psutil>=5.9.0`, `sqlalchemy>=2.0.0`, **`sqlcipher3-wheels`**, `python-dateutil`. Python `>=3.8` jusqu'à 3.12 · [pyproject.toml](https://github.com/dylanljones/pyrekordbox/blob/master/pyproject.toml).
- **numpy est importé de façon eager → non excludable** : confirmé indirectement (dépendance dure du package). À chiffrer : numpy seul ajoute typiquement ~30–50 MB au bundle.
- `sqlcipher3-wheels` = fork de sqlcipher3 fournissant des **wheels Windows/macOS/Linux** avec **SQLCipher 4** embarqué ; c'est ce qui permet d'ouvrir le master.db Rekordbox 6 · [sqlcipher3-wheels PyPI](https://pypi.org/project/sqlcipher3-wheels/), [pyrekordbox README](https://github.com/dylanljones/pyrekordbox). Pour Rekordbox 6.6.5+, si l'extraction de clé échoue, on écrit la clé manuellement dans un cache · [pyrekordbox](https://github.com/dylanljones/pyrekordbox).

**Pont UI ↔ service**
- **stdin/stdout JSON-RPC** : qualifié de « comparativement léger » vs HTTP, cross-platform ; piège : ne jamais écrire de non-JSON sur stdout (logs → stderr) · [Mark Jordan / Electron blog](https://medium.com/ingeniouslysimple/building-an-electron-app-from-scratch-part-4-5d0906897bf1).
- **HTTP local** : language-agnostique mais « héberger un serveur web complet pour de l'IPC rapide est overkill » et ouvre un endpoint local à sécuriser · même source. FastAPI/uvicorn : **démarrage à froid lent** (jusqu'à 20 s dans des cas extrêmes ; Pydantic v2 peut 2–4× le startup) à cause des imports/construction de modèles au boot · [FastAPI cold starts](https://medium.com/@hadiyolworld007/fastapi-cold-starts-explained-why-your-containers-feel-slow-and-the-optimization-order-that-dcac906ffe2b), [aws-lambda-web-adapter #620](https://github.com/aws/aws-lambda-web-adapter/discussions/620).
- uvicorn + PyInstaller : bug connu de **workers qui ne démarrent pas** (~50% du temps) avec multi-workers · [uvicorn discussion #1820](https://github.com/Kludex/uvicorn/discussions/1820).

**Cycle de vie du process (robustesse)**
- **Bug majeur orphan-process** : un binaire PyInstaller crée **2 process (parent-enfant)** ; `child.kill()` ne tue que l'enfant → le parent reste orphelin. Reporté sur Tauri (Windows), **fermé en "not planned"** · [Tauri #11686](https://github.com/tauri-apps/tauri/issues/11686). Vaut pour Electron aussi : tu dois tuer l'arbre de process, pas juste le PID retourné.
- Règle générale : « tu es responsable de tuer le process enfant à la fermeture, sinon tu pollues la machine avec des orphelins » ; les sidecars spawnent leurs propres enfants · [Tauri sidecar docs](https://v2.tauri.app/develop/sidecar/).

**Patterns sidecar**
- Tauri v2 : `externalBin` dans tauri.conf.json, binaire suffixé par **target triple** (`-aarch64-apple-darwin`, `-x86_64-pc-windows-msvc`), spawn via `tauri_plugin_shell`, perms `shell:allow-execute` · [Tauri sidecar docs](https://v2.tauri.app/develop/sidecar/).
- Electron : `child_process` — préférer **toujours la variante async/non-bloquante** · [Node child_process](https://nodejs.org/api/child_process.html), [Electron perf](https://www.electronjs.org/docs/latest/tutorial/performance).

### Tableau comparatif

| Option d'embarquement | Lang/runtime | Taille typique | Démarrage à froid | numpy/sqlcipher3 OK ? | macOS arm64 + Win | Maturité / MAJ | Notes |
|---|---|---|---|---|---|---|---|
| **PyInstaller onedir** | CPython embarqué | ~95 MB+ (gonflé par numpy) | rapide (pas d'extraction) | Oui (hooks numpy mûrs) | Oui | Très actif, std du marché | **2 process → kill d'arbre obligatoire**. Build rapide. |
| **PyInstaller onefile** | idem | ~3× plus petit sur disque | **lent** (extraction temp à chaque run) | Oui | Oui | idem | À éviter ici (priorité démarrage). |
| **Nuitka --standalone** | C compilé | ~60 MB, plus petit | meilleur (~180 ms simple) | Oui mais **compile tout numpy** → build très lent, soucis arm64 cross-build | Oui (arm64 avec ccache/brew) | Actif | Runtime + rapide, mais friction build/numpy. |
| **PyOxidizer** | Rust+CPython | petit | rapide | théorique | partiel | **Abandonné (2023)** | À écarter. |
| **Windows embeddable** | CPython minimal | ~12 MB + deps | rapide | deps à vendoriser à la main | **Windows seul** | Officiel Python | Pas de solution macOS. |
| **python-build-standalone (uv/Astral)** | CPython portable | ~30–60 MB selon strip | rapide | Oui (installe wheels via pip/uv) | **Oui les deux** | Maintenu par Astral, très actif | Tu gères toi-même le venv + lifecycle ; pas de "onefile". |

### Verdict (orienté robustesse + légèreté + perf, macOS+Win, UI web)

- **Process Python minimal piloté en JSON-RPC sur stdin/stdout, PAS de FastAPI/uvicorn.** Tu n'as pas besoin d'un serveur web : un boot FastAPI ajoute des secondes de cold-start et un bug multi-worker connu sous PyInstaller. Un worker Python « nu » qui lit des requêtes JSON ligne-par-ligne sur stdin démarre quasi instantanément, est plus léger, et supprime toute surface réseau loopback à sécuriser. C'est le choix le plus robuste ET le plus réactif. Si tu tiens à HTTP, lie-le strictement à 127.0.0.1 avec un port éphémère + token, mais c'est du poids et du risque en plus pour zéro bénéfice ici.
- **Pour la robustesse (priorité #1), le risque n'est pas le packager mais le cycle de vie du process.** Le piège documenté : PyInstaller spawne 2 process et un `kill()` naïf laisse un orphelin qui **garde le master.db / la transaction SQLCipher ouverts** → risque de corruption. Impératif : tuer l'**arbre de process** (taskkill /T sur Windows, process group/`SIGTERM`→`SIGKILL` sur macOS), handshake d'arrêt propre (envoyer une commande "shutdown" RPC, attendre la fermeture de la connexion DB, puis kill de secours), et garde-fou anti-double-instance.
- **Pour la légèreté + le cross-platform, vise un sidecar single-process et préfère `python-build-standalone` (Astral) ou Nuitka onedir à PyInstaller onefile.** onefile est disqualifié (extraction à chaque démarrage). numpy étant non-excludable (importé eager par pyrekordbox), accepte le plancher de ~30–50 MB et concentre tes gains ailleurs : strip des .pyc inutiles, exclusion de matplotlib/scipy/pandas/tests, venv minimal.
- **PyInstaller onedir reste le pari le plus sûr/rapide-à-livrer ; Nuitka est l'upgrade taille/perf si tu acceptes la friction de build** (compile tout numpy, soucis cross-build arm64 → builder nativement sur chaque OS en CI/local, pas de cross-compile).
- **Côté shell desktop, Electron comme Tauri savent piloter un sidecar**, mais aucun ne résout magiquement le kill d'arbre : c'est à ta charge dans les deux cas. Tauri donne un binaire final plus léger ; Electron, un écosystème JS plus simple si l'UI existe déjà en web. Le bridge stdin/stdout fonctionne identiquement des deux côtés.
- **SQLCipher : pas de blocage.** `sqlcipher3-wheels` embarque SQLCipher 4 et fournit des wheels macOS+Windows, ce qui couvre l'ouverture du master.db 6.6.5+. Vendoriser ces wheels dans le bundle te dispense de toolchain C chez l'utilisateur.

### Incertitudes / à confirmer

- **Poids réel de numpy + sqlcipher3 dans TON bundle** : non chiffré par les sources. À mesurer empiriquement (PyInstaller onedir vs Nuitka) avec ton venv exact — c'est le levier de taille #1.
- **Démarrage à froid d'un worker Python "nu" important pyrekordbox+numpy+sqlcipher3** : non benchmarké publiquement. À chronométrer toi-même (import de numpy seul = quelques centaines de ms ; à valider).
- **Compatibilité de pyrekordbox avec Python 3.13+** : pyproject ne classe que jusqu'à 3.12 → vérifier avant de figer le runtime embarqué (impacte le choix de version python-build-standalone).
- **Kill d'arbre fiable sur macOS via Electron/Tauri** : le bug #11686 est documenté Windows ; le comportement macOS (process group) est à tester explicitement, surtout pour garantir la fermeture propre de la connexion SQLCipher avant kill.
- **VC++ Redistributable** requis par les builds Windows de python-build-standalone : vérifier sa présence/embarquement pour éviter un échec de lancement chez l'utilisateur.
- **Variance des chiffres x321.org** (pas d'IC, pas de séparation onefile/onedir) : à traiter comme ordres de grandeur, pas comme vérités absolues.