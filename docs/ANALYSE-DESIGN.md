# Analyse design Syncbox — alignement mockup ↔ specs & cohérence interne

> Rapport d'analyse de conformité du mockup `Syncbox.dc.html` vis-à-vis des specifications amont (le QUOI) et de la décision de design figée (`SPEC-DESIGN.md`), assorti d'une évaluation de la cohérence interne du design system.

---

## 1. Résumé exécutif

Deux verdicts indépendants sont rendus :

- **Alignement design ↔ spec** : **fort**. Les 6 destinations + l'onboarding sont tous présents et câblés ; la quasi-totalité des gardes de sûreté sont à une surface UI réelle ; les 7 corrections d'incohérences SPEC-01 §8 sont structurellement présentes ; les deux décisions déléguées (§10.9 / §10.10) sont tranchées et largement implémentées.
- **Cohérence interne du design system** : **moyenne**. Source de santé unique, typographie disciplinée et helpers de badges bien factorisés ; mais sprawl chromatique (~63 hex), i18n non câblée (texte tout-FR en dur), thème accent paramétrable entrant en collision sémantique avec la palette figée, et quelques composants promis non rendus.

### Tableau de scores par axe

| Axe | Domaine | Score /5 |
|-----|---------|----------|
| A | Couverture fonctionnelle par domaine | 5 |
| B | Gardes de sûreté à surface UI | 4 |
| C | États requis par écran | 4 |
| D | Décisions déléguées (§10.9 / §10.10) | 3 |
| E | Incohérences SPEC-01 §8 corrigées | 5 |
| F | Ajouts / dérives hors-spec (neutre) | 3 |
| G | Manques | 3 |
| H | Cohérence interne du design system | 3 |

### Points saillants

1. **Couverture exemplaire** : chaque domaine spec a son écran/composant dédié, statuts complets (`statusMeta` l.1553-1563), keeper explicable par échelle ordonnée (l.570), chemin légal en avant + Deezer gated (l.762).
2. **Le routeur réel décidé en §3.1 n'est pas implémenté** : navigation purement par `setState({screen})` (l.1836), aucun deep-link/history/persistance (grep = 0 occurrence). Écart attendu au stade mockup mais c'est la décision-phare de §10.9.
3. **Trois gardes « froides » manquent ou sont seulement implicites** : la garde de fraîcheur du snapshot avant `_mutate` (absente), la sémantique D22 « restore restaure le statut antérieur » (absente), et l'exclusion `removed_from_source` des liens d'achat B2 (invisible).
4. **L'état Erreur réseau actionnable est absent** (404 playlist privée → « connectez votre compte »), alors qu'il figure dans les états requis.
5. **Dérives hors-spec concentrées sur le Dashboard** : set-prep harmonique (clé Camelot / mix harmonique), analytics de collection (jamais joués), seuil binaire « < 256 kbps » rouge contraire à la garde qualité 3-niveaux.

---

## 2. Méthode & corpus

### Fichiers analysés (font foi)

| Rôle | Fichier | Volume |
|------|---------|--------|
| Design (FAIT FOI) | `/Users/adriendidot/Documents/Dev/syncbox/syncbox-ui-ux-design/project/Syncbox.dc.html` | 2347 lignes |
| Décision de design (tokens, navigation, gardes) | `/Users/adriendidot/Documents/Dev/syncbox/syncbox-ui-ux-design/project/docs/SPEC-DESIGN.md` | ~234 lignes |
| Spec amont (le QUOI) | `/Users/adriendidot/Documents/Dev/syncbox/docs/SPEC-UNIFIED.md` | — |
| Brief design amont | `/Users/adriendidot/Documents/Dev/syncbox/docs/PROMPT-DESIGN.md` | — |
| Spec d'origine + bugs | `/Users/adriendidot/Documents/Dev/syncbox/docs/SPEC-01-syncbox.md` | — |

### Règles de lecture

- **SPEC-UNIFIED = le QUOI** : périmètre, gardes, états attendus.
- **Mockup = le design** : il fait foi pour l'esthétique et la structure visuelle ; SPEC-DESIGN fige les tokens et les décisions déléguées.
- Toutes les citations `fichier:ligne` ont été ouvertes et vérifiées une à une (Read/grep). Les rares citations infirmées en vérification ont été corrigées ou écartées (voir liste en fin de réponse).

### Limites

- Le mockup tourne sur le runtime `claude.ai/design` (x-dc) ; `support.js` est **ignoré** (runtime, hors design).
- Conséquence directe : la navigation est par état et non par routeur réel ; l'i18n n'est pas câblée. Ces deux points sont des préoccupations *build-time* (PROMPT-03), pas des défauts de maquette — mais ils sont signalés car la décision design les revendiquait.
- La protection « blank » des secrets et la progression SSE temps réel ne sont pas observables en statique ; seul le câblage UI est évaluable.

---

## 3. Couverture fonctionnelle par domaine (axe A — score 5)

Les 6 destinations + l'onboarding sont présents et correctement câblés. La coque persistante (sidebar 5 nav + Réglages + pile « État système » source unique, l.34-91) regroupe par tâche (Piste B).

| Domaine | Surface UI | Statut | Preuve |
|---------|-----------|--------|--------|
| **Onboarding** (flux guidé linéaire) | Overlay 4 étapes + obStepsData | present | l.1029 (overlay z-index 120) ; l.1636-1644 (4 étapes : Spotify PKCE / dossiers / module OFF par défaut / collection prête) ; l.940 (« Revoir l'onboarding ») |
| **Bibliothèque** (sources Spotify suivies, statuts, tags delta) | `isLibrary` | present | l.269/274 ; empty l.280-287 ; master-list + filtres + bulk l.294-356 ; `libFilters` l.1946-1948 ; `statusMeta` 10 statuts l.1553-1563 ; table l.372-408 ; tags delta l.1054 |
| **Events** (playlist/vide/lien, staging, smart playlist) | `isEvents` | present | l.416/421 ; empty l.426-432 ; grille + workspace l.436-548 ; « catégorie Situation » l.464 ; modale Nouvel event l.1115-1173 |
| **Santé de collection** (hub Doctor 5 sous-vues) | `isHealth` | present | l.555 ; `healthTabs` l.2118-2123 ; Doublons keeper l.569-617 ; Manquants l.619-634 ; Untagged l.636-665 ; Smart Fixes l.667-685 ; Backups+logs l.687-719 |
| **Acquisition** (légal en avant, Deezer opt-in, jobs SSE) | `isAcquisition` | present | l.725/729 ; voie légale RECOMMANDÉ l.732-766 ; ↓ Deezer gated `m.dlOn` l.762 ; statut module l.768-782 ; jobs SSE l.784-816 |
| **Réglages** (Spotify PKCE, ARL masqué, chemins, langue, seuils) | `isSettings` | present | l.821 ; Spotify l.827-836 ; Dossiers l.839-856 ; module + ARL l.858-882 ; rétention + langue l.884-895 ; Avancé seuils l.897-937 |
| **Coque / regroupement par tâche** | sidebar + healthTabs | **partiel** | sidebar 5 nav + Réglages l.34-91 ; hub Santé l.2118-2123 (Piste B) ; **navigation par état** `nav('screen')→setState` l.1857-1861, pas de routeur réel |

**Synthèse** : couverture complète et homogène (même grammaire visuelle : en-tête + sous-titre, cartes `#0c0f16`/bordure `#1c2230`, empty-states pointillés, Geist Mono pour valeurs). La seule réserve (routeur par état) est traitée à l'axe D.

---

## 4. Gardes de sûreté à surface UI (axe B — score 4)

| Garde (§3/§5) | Présente ? | Preuve `fichier:ligne` | Conforme spec |
|---------------|-----------|------------------------|---------------|
| RB-ouvert bloque toute mutation | conforme | l.97-106 (bannière sans PID/chemin/flag) ; hero l.125-137 ; CTA grisés l.2101-2115, 2332-2333 | §3.1 l.52, §5.1 l.107 — message amical, CTA bloqués |
| Cycle dry-run → confirm → mutate | conforme | modale DRY-RUN l.1301-1346 ; « appliquera exactement ces changements » l.1307 ; CTA = payload l.2332 | §5.11 l.147, B10 — corrige l'inversion |
| **Fraîcheur du snapshot avant `_mutate`** | **absent** | l.705 (= restore backup) et l.712 (= log) sont sans rapport ; aucune surface ABORT/relancer-dry-run | §5.11 l.147 — invariant central **non rendu** |
| protected exclus par défaut (Smart Fixes) | conforme | opt-in nommé l.1327-1336 ; « non mémorisé — réarmer » l.1333 ; init false l.1454, reset l.2341 ; badge 🔒 PROTÉGÉ l.1314-1316 | §5.11/§5.4 l.115 — opt-in nommé, ré-armé |
| Suppression fichier irréversible → consentement AVANT | **partiel** | avertissement AVANT l.1349-1357 ; mais bouton commit = `closeModal` **sans checkbox bloquante** l.1360 (vs pattern ANLZ) | §6.9 l.261 — fond OK, consentement purement textuel |
| Keeper explicable + confirmation par groupe | conforme | échelle ordonnée l.570 ; raison par carte l.602, 2160-2161 ; « pas de masse » l.615 ; raisons discrètes l.1687-1697 | §5.4 D5/D6 — pas de score opaque |
| Verdict qualité 3 niveaux, jamais binaire | conforme | `qualityBadge` ok/lossy/incertain l.1677-1679 ; manquant = incertain violet l.1697 ; lossy rétrograde l.1691 | §5.12 l.149 — incertain `#9b8cce` jamais rouge |
| Progression réelle dérivée du SSE | conforme | « progression dérivée du flux SSE » l.788 ; `width:j.pct%` + barflow si downloading l.2191 ; source unique `get health()` l.1569 alimentant l.49/144 et l.60/153 | §5.5 l.126, F16 — pas de barre factice |
| Backend-down (état réel + Relancer) | conforme | overlay l.1006-1016 ; messages l.1011-1012 ; bouton « ↻ Relancer le moteur » l.1013 | §6.6 l.239 — vrai état, pas un freeze |
| Module download OFF, chemin légal en avant | conforme | bloc RECOMMANDÉ l.732-738 ; Deezer gated l.760-762 ; « Désactivé par défaut » l.863 ; onboarding l.1640 | §6.5 l.219-221 — OFF affirmé en 3 surfaces |
| i18n FR/EN — tout libellé traduisible | **partiel** | sélecteur l.893 ; `lang`/`setLang` l.2213-2217 — change seulement le surlignage, **aucun mécanisme de locale** | §3.8 l.74 — texte en dur FR, à câbler au build |
| Secrets jamais en clair | conforme | ARL masqué l.871 ; état « configuré » + « Modifier » l.872-873 ; « jamais en clair ni sur disque » l.875 ; Spotify l.833 | §3.6 l.69 — protection blank non observable en statique |
| Re-download (ANLZ hors backup) → consentement AVANT | conforme | modale ANLZ l.1366-1383 ; cues/beatgrid/waveform l.1372 ; checkbox bloquante l.1374-1376 ; verrou `anlzConsent` ré-armé l.2300-2302 | §5.5 l.120, §3.1 l.52 — **pattern exemplaire** |
| Delete event gardé sur `mutationAllowed` + aperçu | **partiel** | aperçu exact l.1253-1271 ; « Requiert Rekordbox fermé » l.1265 ; CTA d'ouverture gardé l.2101-2105 ; mais commit modale = `closeModal` **sans re-garde** l.1268 | §5.7 D11/D23 — corrige B11 ; garde non redondée au commit |

**Synthèse** : bloc cœur solide. Trois écarts d'homogénéité : (1) la garde de fraîcheur du snapshot est totalement absente ; (2) la suppression irréversible et le commit de delete event reposent sur un consentement **textuel** alors que la modale ANLZ démontre le bon pattern (verrou par checkbox) dans le même fichier ; (3) l'i18n est décorative.

---

## 5. États requis par écran (axe C — score 4)

Les 8 états requis sont tous matérialisés. Quatre sont pilotés par la barre « Démo états » (l.1019-1026) via des flags globaux (l.1446-1449).

| État | Présent ? | Preuve `fichier:ligne` |
|------|-----------|------------------------|
| **Vide** | present | toggle l.1024 ; flag l.1448 ; empty par domaine : `libEmpty` l.280-287, `eventsEmpty` l.426-432, `acqEmpty` l.790-792 ; empty-de-filtre l.402/546/1099 |
| **Chargement** | present | toggle l.1025 ; `loadingDashboard` l.947-980, `loadingOther` l.982-1001, `libLoading` l.360-370 ; shimmer 1.3s l.364-366 |
| **Erreur** | **partiel** | inline seulement : chemin introuvable l.853 ; arbitrage candidat ambigu l.1386-1433 ; job ambigu l.806-808 ; badge `acquisition_failed` l.1563/2188. **Aucun état REST global** (404 → « connectez votre compte », `status_code`) |
| **Succès** | present | chip « ✓ Appliqué » l.473 ; badges Matché/Prêt/Importé l.1555-1559 ; aperçu apply l.1219-1221 ; event applied l.2004 |
| **Avertissement (D17)** | present | « Appliqué · avertissements » ambre workspace l.1806 + carte l.2005 (literal l.2002) ; bannière « Modifié » l.493-498 ; module désactivé l.509-511 — jamais rouge |
| **RB-ouvert-bloqué** | present | toggle l.1022 ; bannière l.97-106 ; hero l.125-137 ; CTA grisés l.2101-2115, 2332-2335 ; « Requiert Rekordbox fermé » l.1265 |
| **Backend-down** | present | toggle l.1023 ; overlay l.1007-1016 ; texte rassurant l.1012 |
| **Dry-run → confirm** | present | modale l.1301-1346 ; diff par champ l.1318-1322 ; CTA = compte exact l.2332 ; aperçus apply/réapply/delete l.1211-1271 |

**Synthèse** : excellente homogénéité (même shimmer 1.3s, empty-states pointillés, tons sémantiques). L'**état Erreur** est le seul partiel : présent en inline et actionnable, mais aucun pattern d'erreur réseau unifié au sens §5.9 ; la barre Démo ne le simule pas. Le succès vit en état de statut stationnaire (pas de toast transitoire), nuance mineure.

---

## 6. Décisions déléguées (axe D — score 3)

Les deux décisions sont **tranchées et justifiées** dans SPEC-DESIGN (§3 l.60-83, §4 l.85-99). L'écart d'implémentation est net entre les deux.

### §10.9 — Navigation & structure

| Sous-décision | Statut | Preuve |
|---------------|--------|--------|
| 3.1 — **Router réel** (deep-link, back/forward, persistance) | **absent** | `nav=(scr)=>setState({screen:scr})` l.1836 ; état initial l.1444 ; setters l.1857-1858 ; grep `location.hash`/`history`/`pushState`/`localStorage`/`router` = 0 occurrence |
| 3.1 garde-fou — Route inconnue → Dashboard | **absent** | flags `s.screen==='x'` sans fallback l.1868-1873 ; pas de route à résoudre faute de routeur (régression Settings-fourre-tout évitée par construction) |
| 3.2 — Regroupement par tâche (Piste B) | conforme | 6 destinations l.1838 ; Acquisition unique l.58-60 ; hub Santé l.2118-2123 |
| 3.3 — Onboarding flux guidé re-jouable | conforme | flux linéaire 0→3 l.2224 ; « Revoir l'onboarding » l.940 ; `launchOnboarding` l.2218 |
| 3.4 — Santé = indicateur (pas écran) | conforme | pile « État système » sidebar l.66-86 ; aucune destination « système » l.1838 ; source unique `get health()` l.1569-1586, `healthBadgeTotal` l.1865 |

### §10.10 — Matching configurable

| Sous-décision | Statut | Preuve |
|---------------|--------|--------|
| Exposé en Réglages › Avancé, replié, avec bandeau | conforme | `advancedOpen:false` l.1452 ; section repliable l.898-903 ; bandeau ⚠ l.905 |
| Contenu : seuil 82, marge 6, pondérations 0.52/0.36/0.12 (somme 1.00), politique ISRC, reset | conforme | l.909-914 ; l.917-921 ; politique ISRC l.926 ; reset l.933 |
| Invariants verrouillés non éditables | conforme | « 🔒 Verrouillé — invariants d'algorithme » l.930-931 (lecture seule) |
| Outil de 1re intention = re-match manuel | conforme | bandeau renvoie au re-match l.905 ; modale Re-matcher l.1277 |

**Synthèse** : §10.10 est implémenté **à l'identique** de la décision. §10.9 est **partiel** : tout le regroupement par tâche, l'onboarding et « santé = indicateur » sont réalisés, mais la décision-phare « router réel » n'est pas démontrée (navigation par état). Acceptable au stade mockup x-dc — c'est un livrable build (note PROMPT-03), mais l'adressabilité revendiquée (`#health/smartfixes`) reste sur le papier.

---

## 7. Incohérences SPEC-01 §8 corrigées (axe E — score 5)

Les 7 corrections revendiquées par SPEC-DESIGN §9 sont **réelles** dans le HTML.

| Incohérence SPEC-01 | Correction | Statut | Preuve |
|---------------------|-----------|--------|--------|
| Compteurs divergents sidebar ↔ dashboard | sélecteur santé unique | conforme | `get health()` l.1569 alimente l.49/56/60 (sidebar), l.143-158 (tuiles), l.1865 (badge), l.2119 (hub) |
| « Download prêt » : `available` vs `available && authenticated` | définition unique | conforme | `downloadModuleOn → downloadsActive` l.1575 ; flag unique l.1453 ; dérivés l.1878-1879, 2199, 2186 |
| Tons de statut event carte ≠ workspace | `badge()` partagé | conforme | fabrique l.1545 ; carte l.2004-2005 (literal l.2002) ; workspace l.1805-1807 ; rendu via `this.badge()` l.2010/2026 |
| Barre factice (F16) | largeur = pct SSE réel | conforme | `width:j.pct%` + barflow si downloading l.2191 ; `pctText` l.2192 |
| Sélection cross-filtre (Untagged) | scopée à la liste visible | conforme | `untagAllChecked`/`untagToggleAll` l.2173-2174 ; `libAllChecked`/`libToggleAll` sur `libFiltered` l.1977-1978 |
| B10 : confirmation inversée vs action | texte = payload (même état) | conforme | `keepIdx` l.2137-2138 → `outcome` l.2146 ; `dryrunConfirmLabel` suit `protectedOptIn` l.2331-2332 ; « pas de masse » l.615 |
| Settings = v-else fourre-tout | égalité stricte, pas de `sc-else` | **partiel** | `isSettings: s.screen==='settings'` l.1873 ; aucun `sc-else` (grep) ; mais « route inconnue → Dashboard » non démontrable faute de routeur (Dashboard reste le défaut l.110/1444) |
| Vocabulaire conflict/ambiguous divergent | `statusMeta()` partagé | conforme | table unique l.1552 ; Conflit/Ambigu ambre l.1556-1557 ; Library `statusMeta(t.st)` l.1961 ; Events `statusMeta(resolving?'new':t.st)` l.2081 |

**Synthèse** : les 7 corrections sont structurellement présentes. La seule réserve (« route inconnue → Dashboard ») n'est pas littéralement démontrable car la navigation se fait par 6 setters fixes — la route arbitraire est inatteignable et la régression visée est absente par construction.

---

## 8. Ajouts / dérives hors-spec — signalés, ton neutre (axe F — score 3)

Le mockup introduit des concepts non prescrits, voire exclus, par les specs amont. **Aucune recommandation keep/remove ici** — constats factuels uniquement.

| Dérive | Preuve `fichier:ligne` | § spec divergente | Impact build |
|--------|------------------------|-------------------|--------------|
| Bloc « Prêt pour le set » : % clé Camelot + « mix harmonique » | l.202, 203, 205 ; mock l.1583 | §7.4 l.359 (set-prep harmonique exclu) | Implique un calcul harmonique hors v1 ; à dériver d'un champ RB existant ou à retirer |
| Compteur « jamais joués » (`neverPlayed`) | l.220 ; mock l.1584 | §5.10 l.137 + §7.4 l.359 (analytics Doctor différé v2) | Play-count non exposé en v1 ; à reporter v2 ou retirer |
| « ce mois-ci +57 » / activité collection | l.215, 216 ; mock l.1584 | §5.10 l.137 + §7.4 l.359 (aucune analyse de collection v1) | Agrégation « activité » non spécifiée ; à confirmer |
| Sources de bibliothèque `provider:'deezer'` | mock l.1603, 1615 | §4 l.86 (sources biblio = Spotify uniquement) | Deezer = acquisition seule ; champ non consommé par la SourceCard rendue |
| Catégorie MyTag « Energy » | l.1504 | §4 l.92 (catégories : Situation / Genre) | Faible — catalogue de tags de démo ; à documenter comme choix design |
| SoundCloud présent en v1 | l.505, 863, 877, 1731 | §6.5 l.229 + §7.4 l.359 (B4 différé v2) | **Dérive déjà tracée** SPEC-DESIGN §11 ; rouvre coût ffmpeg/HLS (+40-80 Mo/plateforme) |
| « basse qualité (< 256 kbps) » en rouge `#f76e6e` | l.195 ; mock l.1582 | §5.12 l.149 (verdict 3-niveaux, jamais binaire ni rouge dans le doute) | Réintroduit un seuil bitrate binaire rouge ; à aligner sur `quality_verdict` ou retirer |
| « sans cue points » (`noCue`) + colonne Cues dedup | l.194, 600 ; mock l.1582 | §4 l.91 (`cueCount` domaine) vs §3.1 l.52 (ANLZ non lus par pyrekordbox) | `cueCount` admissible ; vérifier qu'il provient de `master.db` et non d'une lecture ANLZ non supportée |

**Note** : les dérives sont concentrées sur le Dashboard (hero collection) et les données mock ; le reste des écrans reste fidèle au QUOI. La dérive SoundCloud est assumée et documentée en amont, pas un oubli.

---

## 9. Manques — exigences specs non servies (axe G — score 3)

| Manque | Statut | Preuve `fichier:ligne` | § spec |
|--------|--------|------------------------|--------|
| Garde de fraîcheur du snapshot avant `_mutate` (ABORT si DB changée) | **manque** | modale dry-run l.1301-1346 sans ré-assertion (mtime,size) ; l.712 = log seul ; grep `mtime`/`DB a changé` = 0 | §5.11 l.147 ; POC #9(e) §8 l.373 |
| D22 — restore restaure le statut antérieur (pas `new`) | **manque** | « Restaurer » (ignored) tombe dans la branche `modal:'rematch'` l.1972-1975 ; glyphe ↺ l.1973 ; grep `prevStatus` = 0 | §5.6 l.128, D22 l.139 ; B9 |
| Liens d'achat B2 exclus pour `removed_from_source` | **manque** | `acqMissing()` ne porte qu'un `scope`, aucun statut l.1650-1659 ; track removed l.1631 → action « Re-matcher » générique l.1972 ; voie d'achat sans filtre l.742/748/760-761 | §5.13 l.151 |
| État Erreur réseau actionnable (404 → « connectez votre compte ») | **manque** | grep `404`/`playlist privée`/`status_code`/`Réessayer` = 0 ; seul échec = chemin introuvable statique l.853 ; empty-state biblio = succès l.398-404 | §5.9 l.134 |
| Flux OAuth PKCE Spotify (callback, erreur de connexion, ré-auth) | **partiel** | CTA + sous-texte l.1638 ; badges « connecté · PKCE » l.250/833 (succès uniquement) ; bouton « Reconnecter » statique l.835 ; grep `callback`/`8765`/`refresh_token` = 0 ; aucun état d'échec | §5.9 l.134, §6.10 |

**Infirmations** (constats présumés manquants mais en réalité **servis**, à ne pas reporter comme manques) :

- Opt-in protégé non mémorisé : **présent** — l.1332-1333 (opt-in nommé « Café Del Mar », « réarmer au prochain run »), badge 🔒 l.1314-1316.
- État D17 « Appliqué · avertissements » ambre jamais rouge : **présent** — workspace l.1806, carte l.2005, donnée l.1738.

**Synthèse** : les gardes destructives sont bien couvertes, mais les garde-fous « froids » (fraîcheur DB, restauration de statut, état d'erreur réseau, exclusion d'achat par statut) sont systématiquement omis.

---

## 10. Cohérence interne du design system (axe H — score 3)

| Aspect | Statut | Preuve `fichier:ligne` |
|--------|--------|------------------------|
| Source de santé UNIQUE (corrige compteurs divergents) | conforme | `get health()` l.1569-1586 alimente sidebar l.49/56/60, tuiles l.143-158, badge l.1865 ; dots l.1878-1879 |
| Typographie homogène (Geist UI + Geist Mono valeurs) | conforme | `--font-ui` l.15 ; `var(--font-ui)` l.18 ; Geist Mono sur readouts l.39/73/78/167/171/1863 ; aucune police parasite en dur |
| Barres dérivées du réel, barflow réservé downloading | conforme | `barFill` l.2190-2191 ; barre event 3 segments l.2041-2043 ; keyframes l.26 |
| États gardés apply/delete : style + libellé unifiés | conforme | `deleteEventStyle`/`applyEventStyle` bloqués identiques l.2102-2111 ; libellé partagé l.2105/2115 |
| Helpers factorisés (badge/status/scope/quality) | partiel | `badge()` fabrique unique l.1545-1551 ; `statusMeta`/`scopeBadge`/`qualityBadge`/`untaggedCat` dérivent tous de `badge()` ; modal shell unique l.2234 ; **Toggle dupliqué** (valeurs identiques) l.2200-2201 vs 2211-2212 |
| **i18n FR/EN** | **non-conforme** | `lang`/`setLang` l.2214-2217 — 7 occurrences, toutes style/toggle, **aucun libellé conditionné** ; texte tout-FR en dur |
| **Sprawl chromatique** | partiel | ~63 hex distincts ; 3 violets proches (incertain `#9b8cce` l.1678, accent violet `#9b8cff` l.1472, Deezer `#c39bff` l.1730) ; textes-warning hors-token `#b8a572` l.102, `#d8c08a` l.496 ; gris `#8b97a9` l.130 |
| **Thème accent ↔ palette sémantique** | **non-conforme** | 5 accents `data-props` l.1470-1476 : violet `#9b8cff` ≈ incertain `#9b8cce`, emeraude `#2dd4a8` ≈ teal ready `#2dd4bf` (l.1558), ambre `#f5a524` ≈ warning `#f5b544` (l.1556) → collision sous accent non-azur |
| Pastille provider sur SourceCard | **manque** | carte source = cover + nom + reviewBadge, pas de pastille l.318-325 ; `libSourceList` ne consomme pas `provider` l.1902-1930 ; donnée présente mais morte l.1603/1615 (promesse SPEC-DESIGN §6 L129) |

**Synthèse** : l'essentiel est cohérent (sélecteur santé unique, typographie disciplinée, helpers de badges). Trois faiblesses réelles : i18n non câblée (dette dure pour PROMPT-03), sprawl chromatique non tokenisé, et le thème accent paramétrable qui menace l'invariant « incertain jamais confondu » sous un accent non-azur. La pastille provider promise est absente du master-list.

---

## 11. Recommandations d'homogénéité (lens ponytail — supprimer/aligner le moins de surface possible)

**Axe B (gardes)**
- Aligner la modale de suppression irréversible (l.1360) et le commit de delete event (l.1268) sur le **pattern ANLZ existant** (verrou par checkbox `anlzConsent`, l.2300-2302) plutôt que d'inventer un nouveau mécanisme — réutilisation, pas ajout.
- Réserver une surface UI pour la garde de fraîcheur du snapshot (ABORT + « relancer un dry-run ») : un simple état d'erreur dans la modale dry-run suffit, pas un nouvel écran.

**Axe C / G (états & manques)**
- Ajouter l'état Erreur réseau actionnable comme **réutilisation du pattern empty-state** (bordure + icône + message + CTA), pas une nouvelle famille de composants. Le câbler au moins sur le cas 404 Spotify.
- Servir D22 et l'exclusion `removed_from_source` en ajoutant un **champ `st`** à `acqMissing()` (l.1650-1659) — une donnée, pas une mécanique.

**Axe D (routeur)**
- Implémenter le routeur réel au build (PROMPT-03) comme une **couche mince** au-dessus de l'état `screen` existant (mapper `screen` ↔ `location.hash`), sans réécrire la navigation. Le garde-fou « route inconnue → Dashboard » devient un `default` du mapping.

**Axe F (dérives)**
- Décider en amont du sort des métriques harmoniques/analytics du Dashboard ; si conservées en démo, les marquer explicitement « v2 ». Aligner le compteur « < 256 kbps » sur `quality_verdict` (réutiliser `qualityBadge`) au lieu d'un seuil rouge en dur.

**Axe H (design system)**
- Tokeniser les ~63 hex en variables CSS (les violets et textes-warning surtout) — consolidation, pas refonte.
- Fusionner le Toggle dupliqué (l.2200-2201 / 2211-2212) en **un seul helper**.
- Retirer du mockup les accents `data-props` non-azur (l.1470-1476) qui entrent en collision sémantique, OU isoler l'accent de matched/ready/warning ; ne pas porter l'éditeur de thème tel quel au build.
- Câbler l'i18n sur `en.ts`/`fr.ts` au build ; le sélecteur UI existe déjà (l.893).
- Brancher la pastille provider sur la SourceCard (donnée `provider` déjà présente l.1603/1615) pour honorer SPEC-DESIGN §6.
