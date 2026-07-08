# PROMPT-02 — Unification & finalisation des specs Syncbox (ultracode + ponytail)

> **Comment l'utiliser.** Coller ce prompt dans une session Claude Code. Le mot **`ultracode`** active l'orchestration multi-agents (Workflow). Le module **ponytail** doit rester actif tout du long (`/ponytail full`). Tout choix structurant **passe par moi** via `AskUserQuestion` — ne rien trancher seul.

---

ultracode — `/ponytail full`

## Mission

Unifier **`docs/SPEC-01-syncbox.md`** (spec fonctionnelle/technique, focus sur ses **questions ouvertes Phase 2 §10**, le **journal de décisions §7 (D1–D25)**, les **non-négociables §9**, le **modèle de domaine §6**) et **`docs/SPEC-02-architecture.md`** (cible architecturale, **4 forks A–D**, ordre de dé-risquage §5) en **une seule spec cohérente, complète et sans contradiction**.

Le but final : une spec « parfaite et unifiée » qui résout **toutes** les questions en suspens — par **recherche état-de-l'art sourcée** quand il y a un choix, et par **ma validation** sur chaque arbitrage — pour servir d'intrant au **prompt idéal de construction de l'app** (livrable final).

## Principes non négociables (s'appliquent à chaque phase)

1. **Lens ponytail sur CHAQUE choix.** Remonter l'échelle : (1) ce composant/feature doit-il exister ? (2) la stdlib le fait ? (3) une feature native de la plateforme/OS le couvre ? (4) une dépendance déjà installée suffit ? (5) une ligne ? (6) sinon, le minimum qui marche. **Challenger explicitement SPEC-02** qui « écarte la maintenabilité » et « assume une complexité accrue » : pour chaque changement proposé (Tauri, JSON-RPC stdio, deemix embarqué, etc.), poser d'abord *« vs ce qui marche déjà aujourd'hui, ce changement doit-il avoir lieu ? »*. Réintégrer la maintenabilité comme garde-fou. Lancer `/ponytail-review` sur les choix d'architecture retenus et `/ponytail-audit` (mental) sur la surface de la spec finale.
2. **Aucun choix sans état de l'art sourcé.** Toute option et toute reco s'appuie sur des sources **réelles, datées, vérifiées** (web). Pas d'affirmation de mémoire sur un outil/lib/version.
3. **Tout passe par moi.** Les forks structurants et les choix produit/fonctionnels sont présentés via `AskUserQuestion` (reco ponytail **en premier**, alternatives sourcées, trade-offs vs les 3 priorités *robustesse > légèreté > perf* **et** impact maintenabilité). Ne rien figer sans ma réponse.
4. **Préserver les non-négociables SPEC-01 §9** : sûreté Rekordbox (gardes RB fermé, `_mutate`, backup-avant-mutation, soft-delete, entiers de statut load-bearing), résolution de chemins volume-relatif/absolu, « ne jamais déplacer les fichiers » + quirk TCC, et le **contrat de tests `service/tests/`** comme référence de comportement.
5. **Faithful reporting.** Si une question reste sans réponse fiable après recherche, le dire — ne pas inventer un consensus.

## Contradictions & lacunes déjà repérées (point de départ — à compléter, pas à présumer exhaustif)

- **Fork A — label incohérent dans SPEC-02.** §4 définit `A2 = formats d'échange only` ; §2.4 + table « décisions validées » emploient `A2 = master.db en place seulement, sans XML`. Deux sens pour un même label → trancher le libellé **et** confirmer la décision réelle.
- **« 4 forks à valider » vs « Décisions validées ».** SPEC-02 dit les deux. Clarifier le statut : ces forks sont-ils encore ouverts, ou déjà tranchés et à entériner ?
- **Fork C1 ⟂ OAuth.** C1 (JSON-RPC stdin/stdout, **pas de serveur HTTP**) casse le callback Spotify que SPEC-01 §3.9 épingle sur `http://127.0.0.1:8765/...`. Sans serveur HTTP, pas de redirect loopback → résoudre l'interaction (listener loopback éphémère dédié OAuth ? autre mécanisme ?).
- **Questions encore ouvertes après SPEC-02** (SPEC-01 §10) non tranchées par l'archi : §10.4 secrets au repos (keychain OS vs DB chiffrée), §10.5 outil de migration de schéma, §10.6 abstraction multi-OS (détection process RB Windows, corbeille OS, chemins système), §10.7 port service + callback OAuth, §10.9 structure UI/UX (§8.2 pistes A/B/C), §10.10 matching configurable (seuils 82 / marge 6 / pondérations ; politique unique de collision ISRC).
- **Tension ponytail vs SPEC-02** : chaque « complexité choisie » (coque Tauri, transport réécrit, downloader embarqué) doit survivre à la question « YAGNI / ce qui marche déjà suffit-il ? ».

## Orchestration (Workflow)

**Phase 0 — Ingestion & cartographie** *(agents parallèles, lecture seule)*
- Lecteur SPEC-01 → extraire : D1–D25 (statut garder/changer/retirer), questions ouvertes §10, non-négociables §9, modèle de domaine §6, contrat de comportement §3.
- Lecteur SPEC-02 → extraire : verdicts par couche §2, forks A–D + statut, décisions validées, ordre de dé-risquage §5.
- Lecteur `docs/_research/` + `docs/_analysis/` → inventaire des sources déjà réunies (éviter de re-chercher l'acquis ; repérer le périmé/à-réactualiser).
- **Sortie** : une **matrice unifiée** `{ sujet → position SPEC-01 → position SPEC-02 → contradiction ? → statut (tranché / à-rechercher / à-valider) }`.

**Phase 1 — Diff, contradictions, lacunes** *(barrière : nécessite toute la phase 0)*
- Un agent de synthèse croise les deux specs et produit : (a) liste **complète** des contradictions (seed ci-dessus + nouvelles) ; (b) questions **encore ouvertes** ; (c) choix dont l'**état de l'art manque** ; (d) classement par priorité et par type d'action.

**Gate utilisateur 1** *(`AskUserQuestion`)* — me présenter la matrice + la liste contradictions/questions ; confirmer périmètre, priorités, et toute préférence forte **avant** la recherche lourde.

**Phase 2 — Recherche état-de-l'art** *(pipeline : un fil par question/fork ; verify dès qu'une recherche finit)*
- Par sujet : un agent recherche (style `deep-research`) fan-out WebSearch/WebFetch → **matrice d'options sourcée + datée** + **reco ponytail** (l'option la plus paresseuse qui tient les non-négociables).
- **Verify adversarial** par sujet : un sceptique vérifie que les sources sont réelles/à jour et que la « lazy option » ne casse aucun non-négociable (par défaut : réfuter). Majorité requise pour valider.
- **Sujets pré-identifiés** (compléter selon phase 1) : secrets au repos macOS+Windows ; outil de migration SQLite léger ; détection process Rekordbox sous Windows + corbeille OS cross-platform ; OAuth loopback **sans** serveur HTTP (impact Fork C1) ; état 2025–2026 signature/notarisation sidecar Tauri (#11992) ; deemix vs streamrip (maintenance + API Deezer actuelle + dimension légale GPL/DMCA) ; PyInstaller `--onedir` vs Nuitka (taille/cold-start mesurés) ; modèle de matching configurable (exposer ou non les seuils).

**Gate utilisateur 2** *(`AskUserQuestion`, en lots)* — pour chaque fork/choix : reco ponytail **en premier**, alternatives, trade-offs vs priorités + maintenabilité, sources. Collecter mes décisions.

**Phase 3 — Synthèse de la spec unifiée**
- Produire **`docs/SPEC-UNIFIED.md`** : une spec unique intégrant D1–D25, forks tranchés, réponses recherchées + validées, non-négociables, modèle de domaine, architecture cible. Forks réécrits avec **un seul libellé cohérent** et **statut clair (tranché)**. Chaque simplification ponytail porte un `ponytail:`-style rationale (ce qui est écarté, quand le rajouter). Mettre à jour/retirer SPEC-01 §10 et SPEC-02 §4 pour pointer vers la décision finale (pas de double source de vérité — appliquer le principe à la doc elle-même).
- Enrichir `docs/_research/` des nouvelles recherches sourcées.

**Phase 4 — Revue adversariale (boucle jusqu'à convergence)**
- *Completeness critic* : que manque-t-il ? contradiction résiduelle ? question §10 non répondue ? choix non sourcé ? non-négociable §9 perdu en route ?
- *Ponytail-review* : où la spec sur-conçoit-elle encore ? quoi supprimer/fusionner ?
- Reboucler tant que : contradictions ≠ 0, questions ouvertes ≠ 0, ou findings ponytail non traités.

**Phase 5 — Le prompt idéal de construction**
- À partir de `SPEC-UNIFIED.md` figée, générer **`docs/PROMPT-03-build.md`** : le prompt qui permet de construire l'app (objectif final), incluant stack tranchée, ordre de dé-risquage (POC d'abord), non-négociables, contrat de tests, et la lens ponytail comme contrainte de réalisation.

## Livrables

1. `docs/SPEC-UNIFIED.md` — spec unique, complète, sourcée, **zéro contradiction**, forks tranchés.
2. Journal de décisions consolidé (forks A–D entérinés + réponses aux 10 questions §10), traçable.
3. `docs/_research/` enrichi (nouvelles recherches datées/sourcées).
4. `docs/PROMPT-03-build.md` — le prompt de construction final.

## Règles d'interaction

- **Tout fork/choix structurant ou produit → `AskUserQuestion`**, reco ponytail en tête. Ne pas avancer en phase 3 sans mes décisions.
- Ponytail actif : livrable d'abord, explication courte ensuite. Pas de prose qui défend une simplification — la simplification se justifie par sa brièveté.
- Langue : **français** (cohérent avec les docs existantes).
