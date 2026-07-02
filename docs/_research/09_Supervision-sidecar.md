## Supervision, redémarrage et health-reporting du sidecar Python sous Tauri v2 (SPEC-01 §10.8)

> Cadre déjà tranché (Gate 1/2, non rediscuté ici) : réécriture from scratch ; coque **Tauri v2** ; transport **HTTP+SSE** loopback gardé (pas de JSON-RPC) ; acquisition = module optionnel ; signature macOS décidée plus tard ; suppression fichier cloud/exFAT = corbeille OS sinon suppression définitive + avertissement.
>
> Bugs à corriger : **F13** (service tué SIGTERM-only sans relance) et **F14** (migration invisible si le service est down).

### Constat (faits sourcés)

**Mécanisme de spawn et de détection de mort (Tauri v2)**
- `app.shell().sidecar("syncbox-service").spawn()` rend un tuple `(rx, child)` : un récepteur d'events + un handle de process · [Tauri v2 — Embedding External Binaries / Sidecar](https://v2.tauri.app/develop/sidecar/).
- L'enum `CommandEvent` (`#[non_exhaustive]`) porte les variantes `Stdout`, `Stderr`, `Error`, `Terminated` · [docs.rs — tauri_plugin_shell::process::CommandEvent](https://docs.rs/tauri-plugin-shell/latest/tauri_plugin_shell/process/enum.CommandEvent.html). Le payload de fin `TerminatedPayload` expose `code: Option<i32>` et `signal: Option<i32>` · [docs.rs — TerminatedPayload](https://docs.rs/tauri-plugin-shell/latest/tauri_plugin_shell/process/struct.TerminatedPayload.html).
- Dans Tauri v2 il faut lancer la boucle async avec `tauri::async_runtime::spawn` et **non** `tokio::spawn` (sinon panic « no reactor running ») · [docs.rs — tauri::async_runtime](https://docs.rs/tauri/latest/tauri/async_runtime/index.html), [Bug Tauri v2 #10289 — tokio::spawn provoque un panic](https://github.com/tauri-apps/tauri/issues/10289).

**Tree-kill du worker PyInstaller (chemin critique, non adjacent)**
- En mode one-file, `child.kill()` côté Tauri ne tue que le bootstrap PyInstaller (PID parent) et **laisse orphelin le worker Python enfant** qui tient le port `8765` · confirmé indépendamment par [Tauri issue #11686](https://github.com/tauri-apps/tauri/issues/11686) (fermée *not-planned*). Sans `taskkill /T` (Windows) ou kill du *process group* (macOS), le port reste pris au shutdown — **c'est exactement F13**.

**Superviseur lifecycle clé en main**
- Le plugin `tauri-plugin-sidecar-lifecycle` (auto_restart, max_restart_attempts, backoff, health checks, port-conflict resolution) n'est qu'une **proposition ouverte** : [Feature: Sidecar Lifecycle Management Plugin — issue #3062](https://github.com/tauri-apps/plugins-workspace/issues/3062) (ouverte 2025-10-23, aucun crate/plugin publié, aucune réponse mainteneur tranchant « core vs plugin »). **Rien à installer au 2026-06.**

**Repli / échappatoire utilisateur**
- Le plugin Process expose `exit()` / `relaunch()` (JS) et `app.restart()` (Rust) · [Tauri v2 — Process plugin](https://v2.tauri.app/plugin/process/). `relaunch()` redémarre **toute** l'app (fenêtre + état UI), re-spawnant le sidecar par le chemin de boot normal · [Tauri v2 — Sidecar](https://v2.tauri.app/develop/sidecar/).

**Single-instance**
- `tauri-plugin-single-instance` est officiel, supporte macOS + Windows, mais doit être **enregistré EN PREMIER** ; la doc ne détaille pas le mécanisme sous-jacent (Windows = named mutex, macOS = socket de domaine UNIX d'après l'implémentation).

### Tableau comparatif

| Option | Dépendance ajoutée | Couvre F13 (relance auto) | Couvre F14 (UI sait que c'est down) | Robustesse crash en boucle | Verdict non-négociables |
|---|---|---|---|---|---|
| **A — Supervision maison** : boucle `async_runtime::spawn` sur `rx`, relance bornée à N (~3) + backoff 1/2/4s sur `CommandEvent::Terminated`, puis event `backend-down` | **Aucune** (réutilise `tauri-plugin-shell` + `tauri::async_runtime`, déjà requis) | Oui (auto, bornée) | Oui (épuisement du compteur = signal) | Bornée à N → pas d'emballement | Oui, sous conditions (reset compteur + chaîner le tree-kill) |
| **B — Pas de superviseur** : l'UI poll `/health`, après K échecs propose un bouton « Relancer » → `relaunch()`/`app.restart()` | Aucune (`/health` déjà prévu + 1 ligne `relaunch()`) | **Non** (humain requis même pour crash transitoire) | Oui (bannière explicite) | Très robuste (pas de respawn auto) | Sous conditions : ne tient PAS « robustesse > légèreté » seul |
| **C — `tauri-plugin-sidecar-lifecycle`** : supervision déclarative (restart+backoff+health+port conflict) | Plugin tiers… **inexistant** (#3062 = proposition ouverte) | (si livré) | (si livré) | (si livré) | **Non** (rien à installer aujourd'hui ; viole « pas de superviseur lourd ») |

### Verdict (reco ponytail)

**Option A — supervision maison minimale dans le process Tauri**, plus le bouton « Relancer » de l'option B en échappatoire de dernier recours.

- Boucle `tauri::async_runtime::spawn` sur le `rx` du sidecar ; sur `CommandEvent::Terminated`, relance **bornée à N (~3)** avec **backoff 1/2/4s** ; au-delà de N, émission d'un event Tauri `backend-down` vers l'UI, on arrête de relancer.
- En complément, après épuisement des N tentatives, un bouton « Relancer » via `relaunch()` (plugin Process) comme échappatoire utilisateur.
- Anti-double-instance : adopter `tauri-plugin-single-instance` (officiel, macOS+Windows, **enregistré EN PREMIER**) — 1 dépendance officielle d'1 ligne, plus paresseux que tout mutex/lockfile maison.

**Pourquoi** : c'est l'option la plus paresseuse qui tient TOUS les non-négociables et les décisions Gate 1, **sans ajouter aucune dépendance** — `tauri-plugin-shell` est déjà requis pour livrer le sidecar et `tauri::async_runtime` est déjà dans tauri (~40 lignes de Rust). `CommandEvent::Terminated{code,signal}` donne la détection de mort, et l'épuisement du compteur **EST** le signal « backend indisponible » poussé à l'UI (F14). Le plugin lifecycle #3062 qui ferait tout en déclaratif n'est qu'une proposition ouverte — impossible à adopter, et de toute façon « superviseur lourd » proscrit. Le poll `/health` côté UI sert de **filet secondaire** (process vivant mais figé), pas de mécanisme primaire — c'est précisément ce poll qui avait échoué en silence dans l'ancien Electron (F14).

**Ce qu'on écarte délibérément** : (1) tout superviseur/plugin lifecycle externe (#3062 non livré) ; (2) la relance automatique **infinie** — on borne à N pour ne pas boucler sur un crash déterministe ; (3) la résolution automatique de conflit de port (le tree-kill au shutdown libère le port 8765, donc le besoin disparaît) ; (4) le redémarrage de toute l'app par défaut (`relaunch()` réservé au bouton manuel de dernier recours).

### Vérification adversariale

Topic **needs-revision** : un sceptique valide les sources, l'autre exige deux corrections **dures** avant actionnabilité. Les deux verdicts sont recopiés fidèlement.

**Sceptique #1 — SOURCES (réalité, accessibilité, fraîcheur juin 2026) : verdict `holds`.**
> « Tentative de réfutation menée à terme : aucune source ne s'effondre. Les 7 URL distinctes sont toutes réelles, accessibles, et corroborées par fetch direct. Détails relevés mais NON disqualifiants : (1) La source #4 (docs.rs/tauri/async_runtime) est citée comme portant l'argument "utiliser async_runtime::spawn et NON tokio::spawn (sinon panic no reactor running)" — or la page docs.rs elle-même ne contient PAS cet avertissement ; ce sont les sources #5 (issue #10289) et la doc sidecar qui le portent. La citation #4 reste exacte sur ce qu'elle prouve (spawn existe) mais son titre lui prête un contenu qu'elle n'a pas ; l'argument tient quand même grâce à #5. (2) La doc sidecar #1 ne montre dans son exemple QUE CommandEvent::Stdout, jamais le cas Terminated — ce qui CONFIRME plutôt qu'il infirme la reco : le superviseur Terminated est bien du code maison à écrire (~40 lignes), pas un pattern copié-collé. (3) Le pivot "CommandEvent::Terminated distingue gratuitement crash vs kill volontaire" n'est PAS garanti par les sources : aucune source ne prouve que child.kill() de shutdown produit un payload code/signal identifiable et distinct d'un crash — la reco le reconnaît honnêtement comme openItem "à confirmer par POC", donc pas de sur-affirmation. (4) La doc single-instance ne détaille PAS le mécanisme macOS/Windows (mutex/socket) ; la reco l'admet aussi comme openItem. Bonus de corroboration : la recherche fait remonter l'issue #11686 confirmant indépendamment le bug PyInstaller deux-process / kill incomplet, qui valide le non-négociable "kill d'arbre". Conclusion : les faiblesses sont des nuances de citation et des incertitudes déjà déclarées, pas des sources fausses ou périmées. Le verdict Option A est réellement soutenu. »
>
> **Sources douteuses** : « Aucune source inventée, périmée ou inaccessible. Réserve mineure (non disqualifiante) sur la source #4 "docs.rs/tauri/async_runtime" : la page est réelle et confirme que `async_runtime::spawn` existe, mais son TITRE dans le JSON lui attribue l'avertissement "NON tokio::spawn sinon panic no reactor running" — or cet avertissement ne figure PAS sur cette page docs.rs ; il provient de la source #5 (issue github #10289), qui elle le porte bien. La citation surévalue le contenu de #4 mais l'argument reste correctement sourcé par #5. »
>
> **Risque non-négociable** : « Aucun non-négociable menacé par les sources elles-mêmes. La reco Option A respecte Gate 1 (Tauri v2, HTTP+SSE loopback, sidecar Python) et SPEC-01 §9. Seule vigilance non tranchée par les sources (et reconnue par la reco) : la distinction crash vs arrêt-volontaire via CommandEvent::Terminated n'est PAS prouvée par les sources et DOIT être validée par POC avant de s'y fier, sinon risque de relancer le sidecar pendant un before-quit intentionnel. Le kill d'arbre PyInstaller deux-process (non-négociable) reste à câbler séparément — confirmé nécessaire par l'issue #11686. »

**Sceptique #2 — NON-NÉGOCIABLES SPEC-01 §9 & DÉCISIONS Gate 1 : verdict `needs-revision`.**
> « La reco Option A respecte tous les non-negociables et decisions Gate 1, mais holds est premature. Le tree-kill est sur le chemin critique, pas adjacent. Tauri issue 11686 ferme not-planned prouve que child.kill ne tue que le bootstrap PyInstaller et laisse le worker qui tient le port 8765 orphelin. Au shutdown le port reste pris, ce qui est exactement F13. En auto-restart un re-spawn se heurte au port encore tenu par le worker zombie, echoue, et tombe en backend-down permanent. La feature anti-F13 recree F13 si le tree-kill, soit taskkill T sous Windows soit kill du process group sous macOS, n'est pas integre DANS le superviseur. La reco le relegue en con secondaire deja source, ce qui sous-evalue un couplage qui invalide l'effet vise. Second defaut : distinguer crash et arret volontaire doit reposer sur un flag d'intention interne pose avant le kill, pas sur code ou signal de TerminatedPayload dont les valeurs ne sont pas garanties cross-OS sur un kill. Troisieme point, correctness obligatoire : ne pas consommer le rx crashe le sidecar selon issue 2152, donc la boucle async_runtime spawn est un invariant et pas un confort. Point favorable verifie : aucun casse-EventSource trouve, la reconnexion SSE automatique environ 3 secondes apres re-spawn sur le meme port loopback tient, donc garder HTTP et SSE loopback est sain a condition que le port soit reellement libere. Single-instance officiel macOS et Windows, et le piege du callback qui ne doit pas re-spawn un second sidecar est bien identifie. Conclusion needs-revision : integrer le tree-kill dans le superviseur avec attente de liberation du port avant re-spawn, et baser la distinction crash et shutdown sur un flag interne plutot que sur code ou signal. »
>
> **Sources douteuses** : « aucune source perimee inventee ou non verifiable detectee, les cinq URL citees dans la reco ont ete confirmees reelles et accessibles ».
>
> **Risque non-négociable** : « Aucun non-negociable SPEC-01 section 9 ni decision Gate 1 n'est casse. Le risque est le non-tenu partiel de la priorite robustesse de Gate 1. La feature anti-F13 ne corrige reellement F13 que si le tree-kill PyInstaller est integre dans le superviseur, car child.kill laisse le worker orphelin et le port 8765 bloque selon Tauri issue 11686. Sinon l'auto-restart se heurte au port tenu par le worker zombie et retombe en backend-down, reproduisant le bug vise. Risque co-egal : la distinction crash et arret volontaire doit reposer sur un flag d'intention interne et non sur code ou signal de TerminatedPayload, non garanti cross-OS sur un kill. »

**Conditions dures à tenir (pourquoi `needs-revision`, pas `holds`) :**
1. **Le tree-kill doit être INTÉGRÉ DANS le superviseur**, pas relégué en « con déjà sourcé ». Sans `taskkill /T` (Windows) / kill du *process group* (macOS), le worker PyInstaller reste orphelin et tient le port 8765 ; l'auto-restart se heurte alors au port pris par le zombie et **retombe en `backend-down` permanent — la feature anti-F13 recrée F13**. Le re-spawn doit **attendre la libération effective du port** avant de relancer.
2. **La distinction crash vs arrêt-volontaire doit reposer sur un flag d'intention interne posé AVANT le kill**, pas sur `code`/`signal` de `TerminatedPayload` dont les valeurs ne sont **pas garanties cross-OS** sur un kill.
3. **Invariant de correctness** : ne pas consommer le `rx` crashe le sidecar (issue #2152) — la boucle `async_runtime::spawn` est un **invariant**, pas un confort.

### Incertitudes / POC à faire

- **Valeurs N et backoff à fixer empiriquement** : 3 tentatives + 1/2/4s sont des valeurs de départ raisonnables, à régler selon le cold-start réel du sidecar PyInstaller (déjà sourcé comme lent avec FastAPI/uvicorn) — un backoff trop court relancerait avant que le port précédent soit libéré.
- **Reset du compteur d'échecs** : décider du critère « sidecar sain à nouveau » (ex. uptime > 30s, ou 1er `/health` 200 après spawn) pour remettre N à zéro, sinon des crashes espacés finiraient par épuiser le quota à tort. À concevoir et tester.
- **Distinguer arrêt volontaire vs crash** : confirmer par POC que le `child.kill()` de shutdown produit un event identifiable (et surtout que le **flag d'intention interne** est posé avant) pour ne pas déclencher de relance pendant le before-quit, sur macOS process-group vs Windows `taskkill /T`.
- **Mécanisme exact du single-instance sur macOS/Windows** : la doc officielle confirme le support mais ne détaille pas le mécanisme (Windows = named mutex, macOS = socket de domaine UNIX d'après l'implémentation) ; à dé-risquer par POC, surtout que le plugin doit être **enregistré EN PREMIER**.
- **Interaction single-instance ↔ sidecar** : sur lancement d'une 2e instance, le callback single-instance ne doit PAS re-spawner un 2e sidecar (sinon 2 process sur le port 8765) — il doit seulement re-focus la fenêtre existante. À câbler explicitement.
- **Liveness vs readiness** : `/health` détecte un process vivant-mais-figé que `CommandEvent::Terminated` ne verra jamais. Décider si on veut une sonde active qui tue+relance sur `/health` KO répété, ou si on s'en tient à la détection de mort + bouton manuel — choix non tranché, dépend de la fréquence observée des hangs.
