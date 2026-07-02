## Secrets au repos cross-OS — keyring (Keychain/Credential Locker) vs store chiffré maison

> **Cadre (décisions Gate 1/2 déjà prises, non rediscutées ici)** : réécriture from scratch ; coque Tauri v2 ; transport HTTP+SSE loopback gardé (pas de JSON-RPC) ; acquisition Deezer = module optionnel (ARL utilisateur) ; signature macOS tranchée plus tard (2 chemins possibles, dé-risquée par le POC #11992) ; suppression d'un fichier cloud/exFAT = corbeille OS sinon suppression définitive + avertissement.
>
> **Statut de ce topic : `needs-revision`.** Le CHOIX (keyring) est validé sur le fond, mais **deux conditions dures** doivent être intégrées avant actionnabilité (voir Vérification adversariale). Ce ne sont pas des détails : sans elles, le non-négociable §9.7 n'est PAS tenu de façon stable sur macOS.

Besoin : protéger au repos les secrets OAuth Spotify (refresh token) + ARL Deezer sur macOS ET Windows, lus depuis un sidecar Python. Non-négociable §9.7 : **aucun secret en clair dans un binaire open-source**.

### Constat (faits sourcés)

**Option (a) — lib Python `keyring` → Keychain macOS / Windows Credential Locker (DPAPI)**
- `keyring` délègue au coffre natif de l'OS : Keychain Services (macOS), Windows Credential Locker chiffré par DPAPI sous le capot (Windows). API ~3 lignes (`set_password`/`get_password`/`delete_password`), cross-OS, **aucune clé maître côté app** · [keyring · PyPI](https://pypi.org/project/keyring/) (2025-11-16).
- Activement maintenue ; backend macOS renommé `OS_X`→`macOS`, fallback UTF-8 Windows · [keyring History/changelog](https://keyring.readthedocs.io/en/latest/history.html) (2025-11-16).
- **Hook PyInstaller intégré et maintenu** depuis fin 2020 : `hook-keyring.py` top-level collecte les backends ET copie les metadata nécessaires à la découverte runtime, testé Linux/Windows/macOS → le packaging est un problème **résolu**, pas un risque ouvert · [PyInstaller PR #5245](https://github.com/pyinstaller/pyinstaller/pull/5245) (2020-12-21), [PyInstaller issue #4569](https://github.com/pyinstaller/pyinstaller/issues/4569) (2020-12-21), [keyring issue #399](https://github.com/jaraco/keyring/issues/399) (2019-09-11).
- Limite Windows Credential Manager de **1280 caractères** · [keyring issue #540](https://github.com/jaraco/keyring/issues/540) (datée 2023-01-01 dans la reco — date corrigée par le sceptique, cf. infra). **Non bloquant ici** : ARL Deezer ~192 hex et refresh token Spotify quelques centaines d'octets, très en dessous.
- macOS by-design : tout code lancé depuis le **même exécutable Python** relit le secret SANS prompt (effet voulu pour un sidecar auto-lancé : pas de pop-up bloquant) — mais ce n'est PAS un secret isolé par-app tant que l'app n'est pas signée Developer ID avec un Designated Requirement stable inscrit dans l'ACL Keychain.

**Option (b) — store chiffré maison (Fernet/`cryptography` ou `sqlcipher3`) à clé dérivée**
- `cryptography`/Fernet = AES-128-CBC + HMAC authentifié ; KDF Scrypt/Argon2id pour dériver une clé depuis un mot de passe · [Fernet](https://cryptography.io/en/latest/fernet/) (2025), [KDF Scrypt](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/) (2025).
- **Problème central : la clé.** La dériver d'une passphrase impose une saisie utilisateur à chaque démarrage (UX rédhibitoire pour un sidecar auto-lancé). Sans saisie, la clé (ou son matériel) finit forcément quelque part en clair → **viole §9.7**. Ne remonte PAS l'échelle ponytail : réimplémente une gestion de clé que l'OS fait déjà mieux et gratuitement.

**Option (c) — plugin Tauri Stronghold**
- Stronghold ne rend PAS la donnée lisible directement (accès uniquement via des « procedures » côté Rust) ; or notre transport impose que le secret soit LU côté **Python** · [Tauri v2 — Stronghold](https://v2.tauri.app/plugin/stronghold/) (2025).
- Faire transiter le secret Rust→Python (env/stdin) est un point ouvert non résolu et réintroduit le secret en clair sur un canal IPC · [tauri issue #12693](https://github.com/tauri-apps/tauri/issues/12693) (datée 2025-01-01 dans la reco ; statut corrigé par le sceptique, cf. infra). Stronghold protège par passphrase → même problème de clé maître que (b), juste déplacé côté Rust.

**Option (d) — DPAPI direct (pywin32) sur Windows + Keychain Services direct sur macOS**
- DPAPI `CryptProtectData`/`CryptUnprotectData` : la **clé de session est créée par la fonction** (jamais passée par l'app), liée au compte de logon, avec MAC d'intégrité → tient §9.7 nativement sur Windows · [Microsoft Learn — CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata) (2025-11-13), [CryptUnprotectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata) (2025), [DEV — pywin32 DPAPI](https://dev.to/samklingdev/use-windows-data-protection-api-with-python-for-handling-credentials-5d4j) (2021).
- Sécurité **strictement équivalente à (a)** — car `keyring` n'est QUE ce wrapper — mais on réécrit à la main deux chemins de code par-OS, à maintenir et packager séparément. Pas de gain de sécurité, moins paresseux.

### Tableau comparatif

| Option | Mécanisme | Clé maître à gérer ? | Cross-OS mac+Win | Lisible côté Python | Packaging PyInstaller | Tient §9.7 | Verdict |
|---|---|---|---|---|---|---|---|
| **(a) keyring** | Keychain (mac) / Credential Locker DPAPI (Win) | **Non** (clé dérivée par l'OS) | Oui, même code | Oui, direct | Hook intégré/maintenu (PR #5245) | **Oui par construction** | **Recommandé** |
| (b) store chiffré maison | Fernet/sqlcipher + KDF | Oui (passphrase ou clé en clair) | Oui (pur Python) | Oui | Trivial | **Non** (clé en clair ou UX cassée) | Écarté |
| (c) Stronghold Tauri | Coffre chiffré Rust/JS | Oui (passphrase) | Oui | **Non** (pas de lecture directe) | n/a | Non (pont Rust→Python fragile, #12693) | Écarté (incompatible archi) |
| (d) DPAPI/Keychain direct | API OS appelées à la main | Non | Oui, 2 chemins de code | Oui | pywin32 + ctypes Security.framework | Oui sur le fond | Repli de (a) seulement |

### Verdict (reco ponytail)

**Option (a) : lib Python `keyring`.** Un service-name unique par secret (ex. `syncbox.spotify.refresh_token`, `syncbox.deezer.arl`), ~3 lignes (`set_password`/`get_password`/`delete_password`).

- C'est l'option la plus haute sur l'échelle ponytail qui tient **tous** les non-négociables : feature native de l'OS (Keychain / DPAPI), **aucune clé maître stockée ni gérée côté app** → §9.7 satisfait par construction, rien en clair dans le binaire open-source ; accès direct depuis Python ; même code cross-OS.
- (b) et (d) reviennent à réimplémenter ce wrapper et/ou la gestion de clé que l'OS fait déjà — moins paresseux **à sécurité strictement égale** (keyring s'appuie sur les mêmes API). (c) est architecturalement disqualifiée (secret non lisible côté Python sans pont Rust→Python fragile).
- Le packaging keyring, souvent cité comme risque, est en réalité **résolu** (hook PyInstaller intégré, keyring activement maintenu).
- Le comportement macOS « lecture sans prompt depuis le même exécutable Python » est ici un **avantage** pour un sidecar auto-lancé — à condition de signer l'app pour que l'ACL Keychain reste stable.

**Ce qu'on écarte :** tout store chiffré maison (Fernet/sqlcipher) et toute clé dérivée par passphrase (pas de saisie au boot, pas de KDF/salt/rotation à maintenir) ; pas de Stronghold ni de pont Rust→Python ; pas d'appels DPAPI/Keychain écrits à la main par-OS ; on **ne chiffre PAS toute la DB**, seulement 2-3 secrets ciblés.

**Quand ajouter de la complexité :** basculer vers (d) DPAPI direct UNIQUEMENT si (1) le POC signature #11992 révèle que l'ACL Keychain macOS se casse de façon ingérable entre versions signées, ou (2) un secret dépasse un jour ~1280 car sur Windows (pas le cas). Garder un fallback `keyrings.alt` désactivé par défaut, **jamais en prod** (chiffrement faible).

### Vérification adversariale

Deux sceptiques ont attaqué la reco. **Verdict global : `needs-revision`** (le sceptique SOURCES valide ; le sceptique NON-NÉGOCIABLES impose des conditions dures).

#### Sceptique 1 — SOURCES : `holds`

Les 12 URLs citées ont toutes été ouvertes et vérifiées : aucune inventée, toutes accessibles et soutenant l'affirmation à laquelle elles sont rattachées. La réfutation échoue sur le fond.

- **Attaque la plus forte** — la reco affirme « le packaging keyring est un problème RÉSOLU ». La recherche de contrôle remonte des issues PyInstaller/keyring **toujours ouvertes** sur « No recommended backend » en mode frozen : #591 (NoKeyringError onefile, ouverte 29 août 2022) et #399. **Mais** #591 concerne CentOS 7 / Linux (KWallet manquant), **PAS macOS ni Windows** → ne contredit pas la reco, qui vise explicitement mac+Win. Le hook PR #5245 (mergée 21/12/2020, vérifiée) couvre le périmètre annoncé. La prudence de l'openItem (« tester `get_password()` dans le binaire gelé, pas seulement l'import ») est appropriée.
- **« Lecture sans prompt depuis le même exécutable Python »** repose sur issue #457 (ouverte 18 août 2020, vérifiée) : citation fidèle ; la reco reconnaît honnêtement la contrepartie d'isolation et la renvoie au POC #11992.
- **Disqualification de Stronghold via #12693** : exacte sur le fond (la fonctionnalité n'existe pas), mais **imprécise sur le statut** (l'issue est CLOSE comme duplicate de #12034, taguée « question », pas « ouverte/non résolue »). N'invalide pas la conclusion.
- Sources de fond toutes confirmées : DPAPI `CryptProtectData` crée elle-même la clé de session (non passée par l'app), lie au logon, ajoute un MAC ; Fernet = AES-128-CBC + HMAC-SHA256 ; Scrypt/Argon2id documentés.

**Corrections de forme exigées (`badSources`, non load-bearing) :**
- **keyring · PyPI** — la reco cite « v25.6.0, 16 nov 2025 ». INEXACT : la version du 16 nov 2025 est **v25.7.0** (v25.6.0 = 25 déc 2024). keyring est bien activement maintenu, donc non load-bearing.
- **keyring changelog** — « renommage macOS backend en v25.x ». INEXACT : le renommage `OS_X`→`macOS` est en **v22.0.0 (24 jan 2021)**.
- **keyring issue #540** — date citée « 2023-01-01 ». INEXACT : ouverte le **9 nov 2021**. Contenu (limite 1280 car) correct.
- **tauri issue #12693** — citée « non résolu », date « 2025-01-01 ». NUANCE : ouverte le **12 fév 2025**, **fermée comme duplicate de #12034**, taguée « question ».

**Risque non-négociable (selon ce sceptique) :** aucun menacé par la reco elle-même. §9.7 tenu par construction par keyring → Keychain/DPAPI. Seule inconnue : la robustesse de l'ACL Keychain macOS aux mises à jour de l'app signée — déjà identifiée en openItem, à valider au POC #11992.

#### Sceptique 2 — NON-NÉGOCIABLES SPEC-01 §9 + décisions tranchées : `needs-revision`

Le CHOIX (keyring) **survit à la pire menace trouvée** : la régression macOS Tahoe 26 qui casse les lectures Keychain ne casse que la **CLI `security`** (hang / exit 36) ; keyring passe par l'API C Security.framework (`SecItemCopyMatching`) via ctypes, jamais par la CLI → **immune** ([dev.to/euda1mon1a](https://dev.to/euda1mon1a), 2026-02-19 maj 2026-03-07 ; confirmé par recherche « keyring bypasses the broken CLI entirely »).

**MAIS la reco est sous-cotée sur trois cas limites touchant un non-négociable → `needs-revision`, pas `holds`. Ce sont des conditions DURES, pas des détails :**

1. **§9.7 EST DÉJÀ VIOLÉ aujourd'hui → keyring n'est pas optionnel, et une PURGE est obligatoire.** Vérifié dans le code : `service/app/spotify.py:181` et `:186` lisent/écrivent `spotify_user_refresh_token` via `database.get_setting/set_setting` ; `service/app/models.py:31` `spotify_client_secret`, `:37` `deemix_arl` — **tous en clair dans le SQLite local**. La reco DOIT inclure une **migration : lire l'ancienne valeur SQLite → écrire dans keyring → effacer la colonne SQLite**. Sans cette purge, le secret en clair **persiste sur disque** après l'adoption de keyring → §9.7 reste violé. La reco ne mentionne pas cette purge.

2. **errSecInteractionNotAllowed -25308 n'est PAS « keychain verrouillé, retry suffit » — c'est un problème de code-signing.** Sur macOS Tahoe 26, un binaire Python **non signé Apple** (Homebrew Python 3.12/3.14 — et par extension le binaire **PyInstaller gelé du sidecar**) reçoit `-25308` **APRÈS unlock**, keychain déverrouillé (cause = différence d'entitlement/codesigning entre binaire Apple-signé et binaire tiers ; confirmé 2 fois, même article). Le filet « retry gracieux » de la reco **ne couvre pas ce cas** : un retry ne résout rien. Conséquence : un secret illisible **bloque le refresh OAuth Spotify et l'ARL Deezer** (acquisition).

3. **L'ACL Keychain par-binaire dépend d'un Developer ID STABLE (le risque est CERTAIN, pas « théorique »).** Sans identité Developer ID stable, chaque release change le code hash → ACL invalidée → **re-prompt « veut utiliser vos infos confidentielles » à CHAQUE mise à jour**, même après « Toujours autoriser » ([eclecticlight.co](https://eclecticlight.co) 2026-01-17 ; openclaw/gogcli#569). Aggravé en **PyInstaller onefile** : extraction dans `_MEIxxxx` variable → le chemin exécutable peut bouger entre lancements, fragilisant l'ACL par-chemin. La reco qualifie ce risque de « théorique / à valider POC » — il est en réalité **certain sans signature stable** et touche directement l'UX d'un module non-négociable.

**Révision minimale exigée (garde le choix (a)) :**
- (i) **Signature Developer ID STABLE = pré-requis DUR du choix, pas un openItem optionnel** — verrouillé par le POC signature #11992. Sans elle, §9.7 n'est PAS tenu de façon stable sur macOS.
- (ii) **Migration + purge** de l'ancien secret SQLite en clair (cf. point 1).
- (iii) Traiter **-25308 comme erreur de signature/entitlement** (message clair + dégradation propre), pas comme « retry ».
- (iv) **Figer le chemin d'extraction** : onedir plutôt que onefile, ou `--runtime-tmpdir` stable, pour stabiliser l'ACL par-chemin.

Sous ces conditions, l'option (a) tient §9.7 + cross-OS + accès Python. **Côté Windows, DPAPI/Credential Locker via keyring ne présente aucun de ces écueils** (pas d'ACL par-signature) : OK tel quel.

**Risque non-négociable (selon ce sceptique) :** §9.7 sur macOS tenu **uniquement SOUS CONDITION** de signature Developer ID stable (classée à tort en openItem alors que c'est un pré-requis dur). Deux menaces concrètes non couvertes : (a) le secret en clair actuel dans SQLite doit être migré ET purgé ; (b) sur Tahoe 26, un binaire PyInstaller non signé Apple reçoit -25308 même keychain déverrouillé (cause code-signing), non résolu par le « retry gracieux » → blocage potentiel du refresh Spotify et de l'ARL Deezer. Décisions tranchées non menacées (Tauri v2, HTTP+SSE loopback, module optionnel+ARL, pas de JSON-RPC) : keyring est lu côté Python sans pont Rust.

### Incertitudes / POC à faire

- **POC signature Tauri #11992 (la seule vraie inconnue) :** vérifier empiriquement sur macOS signé Developer ID que l'ACL Keychain (Designated Requirement stable) **survit aux mises à jour SANS re-prompt** à chaque lancement/update. C'est le pré-requis dur du choix (a) sur macOS.
- **Hook keyring dans le bundle réel :** confirmer que le hook intégré collecte bien `keyring.backends.macOS` et `keyring.backends.Windows` + metadata ; sinon filet `collect_submodules('keyring.backends')` + `copy_metadata('keyring')`. Tester `get_password()` dans le **binaire gelé**, pas seulement l'import.
- **Chemin d'extraction stable :** trancher **onedir vs onefile** (ou `--runtime-tmpdir` stable) pour fixer l'ACL Keychain par-chemin sur macOS.
- **Gestion -25308 :** distinguer keychain verrouillé (retry légitime) vs erreur de code-signing (retry inutile) ; message d'erreur clair + dégradation propre côté sidecar.
- **Windows :** décider si on garde Credential Locker (keyring par défaut) ou un blob DPAPI dans un fichier app — à trancher seulement si besoin d'entropie additionnelle ou de dépasser 1280 car (a priori non).
- **Plan B :** vérifier si `cryptography`/`sqlcipher3` sont déjà dans l'arbre de deps (non utilisés dans la reco, utile à savoir pour un repli).
