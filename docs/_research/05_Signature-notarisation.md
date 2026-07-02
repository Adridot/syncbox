## Signature & notarisation du sidecar `externalBin` (Tauri v2, macOS) — issue #11992 et chemin de signature pour un sidecar PyInstaller

> Cadre déjà tranché (Gate 1/2, non rediscuté ici) : réécriture from scratch ; coque **Tauri v2** ; transport **HTTP+SSE** gardé (pas de JSON-RPC) ; acquisition = module optionnel (lib laissée au build après POC) ; **signature macOS décidée plus tard** (2 chemins possibles) ; suppression fichier cloud/exFAT = corbeille OS sinon suppression définitive + avertissement.
> Ce topic est le **dé-risquage n°1 du Fork B**.

> ⚠️ **Statut global du topic : `needs-revision`.** La conclusion de fond (signature manuelle du sidecar = seule voie qui passe Apple tant que #11992 n'est pas corrigée) **tient et est vérifiée à la source**, mais deux sceptiques imposent des **corrections dures avant que la reco soit actionnable** : (1) une métadonnée de date fausse, (2) le **mécanisme exact** de la reco (le hook nommé est le mauvais — voir Vérification adversariale). Ne pas lisser : la reco telle qu'écrite désigne `beforeBundleCommand`, ce qui est réfuté ; le bon point d'accroche est une **étape POST-bundle**.

### Constat (faits sourcés)

**L'issue #11992 est toujours OUVERTE (juin 2026)**
- `[bug] MacOS - Codesigning and notarization issue when using ExternalBin` · Issue #11992 — état **OPEN** vérifié via API GitHub : `closedAt=null`, labels exactement `type: bug` + `status: needs triage`, **1 seul commentaire** (23/12/2024, GillesPlatteeuw), aucun PR de correctif mergé · [github.com/tauri-apps/tauri/issues/11992](https://github.com/tauri-apps/tauri/issues/11992) · 2024-12-17 (ouverte) / état OPEN confirmé 2026-06-15.
- Symptôme racine cité mot pour mot dans l'issue : **« nested code is modified or invalid / file modified: …/test_binary »** — la signature du binaire nesté est cassée au moment du scellement du `.app`.

**Aucun fix natif livré entre déc. 2024 et juin 2026**
- La doc officielle Tauri v2 **macOS Code Signing** ne mentionne PAS les sidecars / `externalBin` / nested code · [v2.tauri.app/distribute/sign/macos](https://v2.tauri.app/distribute/sign/macos/) · consultée 2026-06-15.
- La doc **Embedding External Binaries** exige le suffixe `-$TARGET_TRIPLE` et ne parle ni de signature ni de notarisation · [v2.tauri.app/develop/sidecar](https://v2.tauri.app/develop/sidecar/) · consultée 2026-06-15.
- La **config reference** Tauri v2 expose bien les clés `bundle.macOS` (`signingIdentity`, `hardenedRuntime`, `entitlements`, `providerShortName`) et les hooks de build · [v2.tauri.app/reference/config](https://v2.tauri.app/reference/config/) · consultée 2026-06-15.

**Le problème persiste et s'étend aux libs Python embarquées**
- `Trouble signing Mac bundle with sidecar and extra libs` · Discussion #12803 — **non résolue**, contient littéralement **« code object is not signed at all »** sur `Contents/Frameworks/librosa/__init__.pyi` · [github.com/tauri-apps/tauri/discussions/12803](https://github.com/tauri-apps/tauri/discussions/12803) · 2025-02-24. → soutient le risque sur les libs Python lourdes (numpy via pyrekordbox).
- `Code sign embedded binaries` · Discussion #12001 — **non résolue**, contient le workaround « frameworks macOS auto-signés », avec l'aveu explicite de l'auteur (raphaelmenges) qu'il doit **séparer macOS et Windows** · [github.com/orgs/tauri-apps/discussions/12001](https://github.com/orgs/tauri-apps/discussions/12001) · ⚠️ **date corrigée par les sceptiques : createdAt = 2024-12-18** (la reco citait à tort 2025-03-06). → soutient le « macOS-only » de l'option C.

**Contrainte de packaging PyInstaller (onefile vs onedir)**
- `externalBin` référence **un fichier exécutable unique** par target-triple : **onedir** (un dossier) n'est **pas** spawnable comme sidecar ; il faut **onefile**. ⚠️ Cette distinction est une **déduction de la doc**, pas une citation : la doc sidecar ne formule pas explicitement « onefile obligatoire » (correction sceptique).
- En **onefile**, les `.so` numpy sont rangés DANS le Mach-O (extraction temp au runtime), ce qui **esquive** le piège `Contents/Frameworks/…` du cas librosa/#12803 — argument load-bearing en faveur de onefile pour pyrekordbox.

### Tableau comparatif

| Option | Mécanisme | Couvre le binaire PyInstaller exécuté ? | Cross-OS | Tient les non-négociables ? | Verdict |
|---|---|---|---|---|---|
| **A — Signature manuelle du sidecar** (re-codesign hardened runtime + entitlements, AVANT scellement du `.app`, puis notarytool) | Hook Tauri + `codesign`/`notarytool` natifs OS | **Oui** | macOS (Windows = chemin distinct signtool/EV) | **Oui** (pur build/distribution) | ✅ **Retenue** — seule voie qui passe Apple, sous réserve de corriger le hook (voir adversarial) |
| **B — Attendre / forcer le fix natif Tauri** | Compter sur le bundler pour signer correctement les sidecars | n/a | n/a | **Non** | ❌ Pari sans échéance : 0 PR de fix, l'app reste non-notarisable aujourd'hui |
| **C — Éviter `externalBin`** (embarquer Python en `resource`/framework auto-signé) | Signature auto Tauri des `.dylib`/frameworks | **Non** (ne signe pas l'exécutable PyInstaller spawné) | **macOS-only** (casse cross-OS) | **Sous conditions, défavorable** | ❌ Ne couvre pas le cœur du problème, diverge de l'archi sidecar HTTP loopback |

### Verdict (reco ponytail)

**Option A — Signer manuellement le sidecar PyInstaller** (onefile, suffixe `aarch64-apple-darwin`) avec **hardened runtime + entitlements minimales**, **AVANT le scellement du `.app`**, puis laisser Tauri signer le bundle et **notariser via `notarytool`**. Sidecar = **onefile obligatoire** (`externalBin` n'accepte qu'un binaire self-contained unique ; onedir = dossier, incompatible).

**Rationale.** C'est l'option la plus paresseuse qui tient les faits vérifiés : #11992 est confirmée OUVERTE en juin 2026 (status `needs triage`, zéro PR de fix), la doc officielle ne couvre toujours pas les sidecars, et #12803/#12001 montrent le bug persistant. Donc la **signature manuelle N'EST PAS optionnelle** : c'est la seule voie qui passe Apple. On remonte le lens : `codesign` + `notarytool` sont des **features OS natives** (pas de dépendance), le hook est **déjà fourni par Tauri** (pas de pipeline CI maison), et le périmètre reste **pur build/distribution** — aucun non-négociable SPEC-01 ni décision Gate 1 n'est touché. Cause racine à respecter : **signer le binaire nesté AVANT que Tauri scelle le `.app`**, sinon « nested code is modified or invalid ».

**Ce que ça écarte.** Attendre un fix amont (option B : pari sans échéance, non actionnable). Le détour « frameworks/resources auto-signés » (option C : macOS-only, ne signe pas l'exécutable Python, casse le cross-OS). Le mode **onedir** pour PyInstaller (`externalBin` veut un binaire unique). On ne met PAS en place de pipeline CI maison au-delà du hook natif.

**À rajouter seulement si le POC le révèle.** (a) Si le hook de pré-bundle ne suffit pas pour l'ordre de signature, basculer sur un **re-codesign + re-scellement explicite** du sidecar dans `Contents/MacOS` **post-bundle** avant `notarytool`. (b) Si des `.dylib`/frameworks Python (numpy via pyrekordbox) déclenchent « code object is not signed at all » comme dans #12803, **étendre le script aux feuilles** (signer feuilles d'abord, bundle ensuite). (c) Re-tester un retrait du script dès que #11992 reçoit un PR mergé.

**Confiance : `high`.**

### Vérification adversariale

> Recopie fidèle des deux verdicts sceptiques. Les deux concluent `needs-revision` : la conclusion de fond HOLDS, mais des corrections dures sont exigées avant actionnabilité.

#### Sceptique 1 — SOURCES (réalité, accessibilité, fraîcheur juin 2026 ; API GitHub + WebFetch/WebSearch) → **`needs-revision`**

**Réfutation.** Le constat de FOND tient à la vérification :
1. Issue **#11992 confirmée OPEN** via API GitHub (created 2024-12-17, `closedAt=null`, 1 commentaire 2024-12-23 de GillesPlatteeuw, labels EXACTEMENT `type: bug` + `status: needs triage`) ; **aucun PR de fix mergé** (recherche PR vide, timeline = cross-refs non-correctifs).
2. Discussion **#12803 réelle**, titre exact « Trouble signing Mac bundle with sidecar and extra libs », date 2025-02-24 exacte, non résolue, contient littéralement « code object is not signed at all » sur `Contents/Frameworks/librosa/__init__.pyi` → soutient l'open-item libs Python/numpy.
3. Discussion **#12001 réelle**, non résolue, contient bien le workaround « frameworks auto-signés » avec l'aveu explicite de l'auteur (raphaelmenges) qu'il doit séparer macOS/Windows → soutient le con macOS-only de l'option C.
4. Doc signature macOS Tauri v2 NE mentionne PAS sidecars/`externalBin`/nested (vérifié) ; doc sidecar exige le suffixe `-$TARGET_TRIPLE` et ne parle ni de signature ni de notarisation (vérifié).
5. `beforeBundleCommand` existe bien (BuildConfig) et `hardenedRuntime` confirmé sous `bundle.macOS`. La recherche web juin 2026 ne révèle AUCUN fix natif.

**Conclusion.** Option A (signature manuelle du sidecar avant scellement) reste la seule voie soutenue par les faits ; B (attendre) et C (frameworks macOS-only) restent réfutées par les sources. **La reco de fond HOLDS.** MAIS verdict `needs-revision` pour **DEUX corrections de métadonnées** :
- **(a) Date de #12001 FAUSSE** — la reco la date « 2025-03-06 » alors que l'API donne `createdAt 2024-12-18` ; **corriger**.
- **(b) « onefile obligatoire / onedir incompatible » présenté comme tiré de la doc**, alors que la doc sidecar ne formule pas cette distinction — **la reformuler en déduction** (`externalBin` référence un fichier exécutable unique) et non citation.

*Réserve mineure :* `signingIdentity`/`entitlements`/`providerShortName` non rendus dans le fetch de la config reference (seul `hardenedRuntime` visible) — probable limite de fetch sur page schéma volumineuse ; ces clés existent réellement, pas une invention.

**Mauvaises sources signalées :**
- **Discussion #12001** ([…/discussions/12001](https://github.com/orgs/tauri-apps/discussions/12001)) : la **DATE citée « 2025-03-06 » est inexacte** — l'API GitHub donne `createdAt 2024-12-18` (`answerChosenAt=null`, non résolue). La discussion est RÉELLE et soutient bien l'affirmation, mais la métadonnée de date ne tient pas et doit être corrigée.
- **Article DEV community « Shipping a Production macOS App with Tauri 2.0 »** : l'URL renvoyée par la recherche (`dev.to/massi_24/...-o10`) renvoie **HTTP 404** ; la bonne URL est `dev.to/0xmassi/...-mc3`. NB : cette source n'est PAS citée par la reco (non disqualifiant). Après lecture elle ne corrobore PAS le chemin de signature manuelle avant scellement (elle traite surtout du naming convention) — ce qui **conforte l'open-item honnête** : aucune source publique ne donne LE script codesign canonique end-to-end.

**Risque non-négociable :** **Aucun.** La reco reste pur build/distribution et ne touche aucun non-négociable SPEC-01 §9 ni décision Gate 1. Les corrections demandées sont purement documentaires (date d'une source, formulation onefile) et n'affectent ni l'archi ni la conclusion.

#### Sceptique 2 — NON-NÉGOCIABLES SPEC-01 §9 & DÉCISIONS Gate 1 (réfutation par défaut) → **`needs-revision`**

**Réfutation.** Le CHOIX (signer manuellement le sidecar PyInstaller onefile, hardened runtime + entitlements minimales, puis notarytool) **ne casse AUCUN non-négociable** SPEC-01 ni décision Gate 1 : pur build/distribution, conforme Tauri v2, ne touche ni la sûreté RB, ni les secrets, ni le local-first, ni le transport HTTP+SSE. Les faits sur #11992 sont **EXACTS et vérifiés à la source** (state=open, created 2024-12-17, updated 2024-12-23, `closedAt=null`, comments=1, labels exactement `["type: bug","status: needs triage"]` ; l'unique commentaire de GillesPlatteeuw du 23/12/2024 confirme mot pour mot « nested code is modified or invalid / file modified: …/test_binary »). Aucun PR de correctif trouvé. Le **mandat ONEFILE est correct et load-bearing** : `externalBin` n'accepte qu'un binaire self-contained unique (onedir = dossier non spawnable, confirmé), ET onefile range les `.so` numpy DANS le Mach-O (extraction temp au runtime), ce qui **esquive précisément** le piège librosa/#12803 (« code object is not signed at all » sur fichiers nestés dans `Contents/Frameworks/`) — piège quasi-certain pour pyrekordbox qui tire numpy eager. Donc le choix tient et la réfutation FRONTALE échoue.

**MAIS trois corrections obligatoires avant actionnabilité (d'où `needs-revision`, pas holds) :**

1. **MÉCANISME FAUX — le hook nommé est le mauvais.** La doc config Tauri dit que `beforeBundleCommand` « runs before the bundling phase », donc **AVANT que le `.app` et `Contents/MacOS/` existent** : on ne peut pas y « signer le sidecar dans `Contents/MacOS` AVANT scellement », le binaire n'y est pas encore copié.

2. **FRAMING FAUX — depuis Tauri 1.5 le bundler signe DÉJÀ automatiquement tous les exécutables, y compris les sidecars** (l'env var `TAURI_SKIP_SIDECAR_SIGNATURE_CHECK` le confirme). #11992 n'est donc PAS « le bundler ne signe pas les sidecars » mais **« l'auto-signature du bundler casse la signature nestée »** — exactement le « nested code is modified » : Tauri **re-touche le binaire APRÈS** qu'on l'a signé. La vraie voie qui marche est le **FALLBACK que la reco classe en openItem (b)** : re-codesign de `Contents/MacOS/<sidecar>` en feuille PUIS re-scellement du `.app`, PUIS `notarytool` — via une **étape POST-bundle** (+ éventuellement `TAURI_SKIP_SIDECAR_SIGNATURE_CHECK` pour éviter le double-sign), **PAS `beforeBundleCommand`**. C'est aussi potentiellement plus PARESSEUX au sens ponytail : commencer par tenter la **config seule** (`signingIdentity` + `hardenedRuntime` + `TAURI_SKIP_SIDECAR_SIGNATURE_CHECK`) avant d'écrire un script de hook.

3. **« Tient TOUS les non-négociables » est surdit pour le cross-OS** : l'option A est **macOS-only** et ne LIVRE pas le non-négociable cross-OS à elle seule (Windows = signtool/EV, chemin distinct) — elle ne le casse pas mais elle est **nécessaire-non-suffisante** ; la reco doit l'énoncer ainsi.

**Risque adjacent hors périmètre signature :** la recherche a fait remonter des preuves réelles (Tauri discussion #14552 ; opencode issue #13655 « SSE event stream silently drops ») que **EventSource sur HTTP localhost peut être SILENCIEUSEMENT coupé** dans les WebViews Tauri (WebView2 confirmé ; WKWebView ~60s timeout nécessitant heartbeat). Cela ne rend pas la reco signature fausse mais **touche la décision tranchée HTTP+SSE** — à dé-risquer dans la recherche transport, **pas ici**.

**Risque non-négociable :** Aucun non-négociable n'est CASSÉ par le choix. Réserve cross-OS : l'option A est macOS-only et ne livre pas seule le cross-OS (Windows signtool/EV = chemin distinct, correctement renvoyé en openItem) — nécessaire-non-suffisante, à reformuler. Risque adjacent à surveiller pour la décision HTTP+SSE : EventSource peut être silencieusement coupé en WKWebView/WebView2 (Tauri #14552, opencode #13655) — non lié à la signature.

### Incertitudes / POC à faire

> Ce topic est le **POC de dé-risquage n°1**. Condition dure issue de l'adversarial : **valider le bon mécanisme = étape POST-bundle** (re-codesign feuille + re-scellement + notarytool), PAS `beforeBundleCommand` ; tenter d'abord la **config seule** (`signingIdentity` + `hardenedRuntime` + `TAURI_SKIP_SIDECAR_SIGNATURE_CHECK`) avant d'écrire un hook.

- **Script codesign canonique manquant** : aucune source publique ne fournit LE script `codesign` validé end-to-end pour un sidecar PyInstaller onefile + `notarytool` sous Tauri v2 → **POC empirique requis** (signer le binaire, vérifier `codesign -vvv --deep`, soumettre à `notarytool`, lire le log de notarisation).
- **Entitlements exactes** pour un binaire PyInstaller : `allow-jit` / `allow-unsigned-executable-memory` sont cités pour des sidecars Swift ; à confirmer pour CPython gelé (bootloader PyInstaller) par POC — **ne pas sur-spécifier d'avance**.
- **Ordre précis vs hook** : vérifier empiriquement que l'étape POST-bundle signe au bon moment (la cause racine « nested code modified » dépend de l'ordre) ; tester `TAURI_SKIP_SIDECAR_SIGNATURE_CHECK` pour éviter le double-sign.
- **Impact des libs lourdes** (numpy tiré par pyrekordbox) embarquées par PyInstaller : risque « code object is not signed at all » sur fichiers internes (cf. #12803 librosa) → à éprouver ; peut imposer de **signer des feuilles avant le bundle**. Hypothèse à valider : onefile (numpy dans le Mach-O) esquive le piège.
- **Volet Windows non couvert** par cette recherche (`signtool` / certificat EV) — **chemin de signature distinct**, à dé-risquer séparément. L'option A est macOS-only : nécessaire-non-suffisante pour le non-négociable cross-OS.
- **Surveiller #11992** : un correctif natif rendrait le hook de signature supprimable (réduction de dette).
- **Hors périmètre signature mais à ne pas perdre** : EventSource potentiellement coupé silencieusement en WKWebView/WebView2 (Tauri #14552, opencode #13655) → à traiter dans la recherche **transport HTTP+SSE**.
