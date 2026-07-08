# PROMPT-04 — Ré-unification specs Syncbox : périmètre overhaul × architecture (ultracode + ponytail)

> **Comment l'utiliser.** Coller ce prompt dans une session Claude Code à la racine du dépôt. Le mot **`ultracode`** active l'orchestration multi-agents (Workflow). Le module **ponytail** doit rester actif (`/ponytail full`). Tout choix structurant **passe par moi** via `AskUserQuestion` — ne rien trancher seul.

---

ultracode — `/ponytail full`

## Mission

Les décisions de périmètre produit de **`docs/OVERHAUL-01-valeur-features.md`** (16/06, les plus récentes) ont été prises **après** **`docs/SPEC-UNIFIED.md`** et **ne sont pas redescendues** dans la spec d'architecture ni dans le prompt de build. Les deux sources de vérité ont divergé.

**Replier OVERHAUL-01 dans SPEC-UNIFIED**, résoudre les contradictions que l'overhaul introduit, **compléter `docs/_research/`** pour les briques nouvelles, puis **régénérer `docs/PROMPT-03-build.md`** — pour obtenir **une seule spec cohérente, sans contradiction, qui porte le périmètre v1 réel** (sync + hygiène + sûreté + les 5 ajouts), prête à construire.

**Principe de single-source-of-truth maintenu** : la sortie **met à jour `SPEC-UNIFIED.md` en place** (pas un 3e doc). OVERHAUL-01 reste la **trace** des décisions de valeur ; SPEC-UNIFIED reste la **source de vérité** archi+produit consolidée.

## Intrants (hiérarchie d'autorité)

1. **`docs/OVERHAUL-01-valeur-features.md`** — décisions de **périmètre/valeur** les plus récentes (§7 périmètre cible, §8 journal interactif, §9 questions ouvertes + briques réutilisables). **Fait foi sur le QUOI/le périmètre.**
2. **`docs/SPEC-UNIFIED.md`** — **fait foi sur l'architecture** (forks A–D §7.1, réponses §10 en §7.2, D1–D25 §7.3, non-négociables §3, modèle de domaine §4, invariants §5, archi §6, dé-risquage §8). À **mettre à jour**, pas à re-débattre.
3. **`docs/SPEC-01-syncbox.md`** — source canonique des **constantes** (seuils, pondérations, buckets) + comportement observable.
4. **`docs/_research/00–10`** — état de l'art sourcé existant (à **compléter**, pas refaire l'acquis).
5. **`docs/_analysis/00–15`** — preuves `fichier:ligne` du comportement existant.

En cas de conflit **de périmètre** : OVERHAUL-01 > SPEC-UNIFIED. En cas de conflit **d'architecture/invariant** : SPEC-UNIFIED > SPEC-01 > research > analysis.

## Principes non négociables (chaque phase)

1. **Lens ponytail sur CHAQUE feature ajoutée.** Pour chacune des 5 nouvelles (Chromaprint, Smart Fixes, faux-320, Track Matcher légal, streamrip) remonter l'échelle : (1) doit-elle exister en v1 ? (2) stdlib ? (3) feature native OS/Rekordbox ? (4) dépendance déjà bundlée (numpy/pyrekordbox/mutagen sont **déjà là**) ? (5) une ligne ? (6) le minimum. Toute brique nouvelle pèse sur le sidecar (mesure POC #3) et doit le justifier.
2. **Préserver TOUS les non-négociables SPEC-UNIFIED §3** : sûreté Rekordbox (garde RB fermé, `_mutate`, backup-avant-mutation, soft-delete, entiers 256/258 load-bearing), résolution de chemins volume-relatif/absolu, « ne jamais déplacer les fichiers » + quirk TCC, secrets jamais en clair, local-first, cross-OS, i18n FR/EN. **Toute nouvelle feature qui écrit `master.db` (ex. Smart Fixes) passe par `_mutate` — pas d'échappatoire.**
3. **Aucun choix sans état de l'art sourcé.** Les 5 nouvelles briques n'ont **aucun fichier `_research/`**. Toute reco s'appuie sur des sources réelles, datées, vérifiées (web), pas sur la mémoire.
4. **Tout passe par moi.** Forks/choix structurants ou de périmètre via `AskUserQuestion` (reco ponytail **en premier**, alternatives sourcées, trade-offs vs priorités *robustesse > légèreté > perf* + maintenabilité).
5. **Faithful reporting.** Question sans réponse fiable après recherche → le dire.

## Divergences déjà repérées (point de départ — compléter, pas présumer exhaustif)

1. **Acquisition lib — décision figée vs déléguée.** OVERHAUL §8 tranche **streamrip** ; SPEC-UNIFIED §6.5/§7.1 le laisse « streamrip vs deemix-fork délégué au POC ». **Aligner** : streamrip retenu ; le POC ne valide plus *le choix de lib* mais le **coût d'embarquement** + la **viabilité full-track**. Reconsidérer le cadrage « Deezer » → streamrip est **multi-service** (Qobuz/Tidal/Deezer/SoundCloud) : Fork D doit-il rester Deezer-only ou s'ouvrir ? (→ question).
2. **5 features v1 absentes de l'archi.** Chromaprint dedup (A2), Smart Fixes (A1), faux-320/FLAC (A3), Track Matcher légal (B2) — **rien** dans le modèle de domaine §4, les invariants §5, l'archi §6, ni les phases PROMPT-03. À **intégrer** : entités/statuts, invariants de comportement, dépendances, place dans l'archi, phase de build.
3. **Module acquisition OFF par défaut + chemin légal.** OVERHAUL insiste : OFF par défaut, Track Matcher légal (liens d'achat ISRC) mis en avant comme alternative. SPEC-UNIFIED §6.5 dit « optionnel » sans ces deux points. **Reformuler Fork D.**
4. **Correction de fait — cues ANLZ.** OVERHAUL §2.3-4/§9.1 : les cues vivent dans `master.db djmdCue` **ET** dans les ANLZ — contredit SPEC-01 §3.1. **Conséquence à trancher** : le backup §3.1/§5.1 (master.db seul) **perd-il des cues ANLZ** au restore ? Étendre le backup aux ANLZ, ou documenter la limite ? (→ question, cohérent mémoire `cues-in-masterdb-and-anlz`).
5. **Dépendance Spotify (fév. 2026).** OVERHAUL §9.5 : durcissement Web API. Confirmer que seuls `playlist-read-*` sont utilisés, aucun endpoint mort (audio-features, recommendations). Annoter §5.9.
6. **Recherche manquante.** Aucun `_research/` ne couvre : Chromaprint/pyacoustid (licence, packaging `fpcalc`, sans réseau) ; algo FFT faux-320/FLAC ; Beatport API v4 (portail d'approbation, ToS, alternatives Bandcamp/Juno par lien ISRC) ; streamrip embedding (sous-process CLI vs API, credentials par service) ; (optionnel) AcoustID→MusicBrainz pour enrichissement ISRC.

## Orchestration (Workflow)

**Phase 0 — Ingestion & matrice de divergence** *(agents parallèles, lecture seule)*
- Lecteur OVERHAUL-01 → extraire le **périmètre cible** (§7 : GARDER/AJOUTER/RETIRER/EXCLURE par vague v1/v2/futur), le journal §8, les questions §9, les briques réutilisables §9.2.
- Lecteur SPEC-UNIFIED → cartographier où chaque feature **devrait** vivre : modèle de domaine §4, invariants §5, archi §6, forks §7, dé-risquage §8.
- Lecteur SPEC-01 + `_analysis/` → constantes/comportements des features GARDÉES (ne pas perdre l'acquis en réintégrant).
- Lecteur `_research/00–10` → inventaire de l'acquis (éviter de re-chercher) + repérer le périmé.
- **Sortie** : matrice `{ feature → décision overhaul → emplacement cible SPEC-UNIFIED → présente ? → action (intégrer / réaligner / rechercher / trancher) }`.

**Phase 1 — Diff & contradictions** *(barrière : nécessite toute la phase 0)*
- Un agent de synthèse produit : (a) liste **complète** des divergences périmètre↔archi (seed ci-dessus + nouvelles) ; (b) features sans invariant/domaine ; (c) briques sans recherche ; (d) impacts sur les non-négociables §3 (ex. Smart Fixes × `_mutate`, Chromaprint × taille sidecar).

**Gate utilisateur 1** *(`AskUserQuestion`)* — me présenter la matrice + les divergences ; confirmer périmètre v1 réel, et trancher d'emblée : (i) Fork D Deezer-only vs streamrip multi-service ; (ii) backup ANLZ ou limite documentée ; (iii) ordre/priorité des 5 ajouts (tous v1 ou certains v2).

**Phase 2 — Recherche état-de-l'art des briques nouvelles** *(pipeline : un fil par brique ; verify dès qu'une recherche finit)*
- Par brique (Chromaprint, FFT faux-320, Beatport/légal, streamrip embedding, AcoustID si retenu) : agent style `deep-research` → **matrice d'options sourcée + datée** + **reco ponytail** (l'option la plus paresseuse qui tient les non-négociables et le budget sidecar).
- **Verify adversarial** par brique : un sceptique vérifie sources réelles/à jour + que la reco ne casse aucun non-négociable et ne fait pas exploser le sidecar (par défaut : réfuter). Majorité requise.
- **Sortie** : nouveaux fichiers `docs/_research/11_*` … (un par brique), même format daté/sourcé que 00–10.

**Gate utilisateur 2** *(`AskUserQuestion`, en lots)* — par brique : reco ponytail **en tête**, alternatives, trade-offs vs priorités + maintenabilité + poids sidecar, sources. Collecter mes décisions.

**Phase 3 — Intégration dans SPEC-UNIFIED** *(mise à jour en place)*
- Mettre à jour **`docs/SPEC-UNIFIED.md`** : ajouter les features retenues au **modèle de domaine §4** (entités/statuts : ex. groupe de doublons par empreinte, job Smart Fixes dry-run→confirm→mutate, verdict faux-320, manquants→liens d'achat), aux **invariants §5** (comportement + cas limites + `# ponytail:` pour chaque simplification), à l'**archi §6** (dépendances, place, isolation), aux **forks §7** (Fork D reformulé), au **dé-risquage §8** (nouveaux POC : empreinte sans réseau, full-track ARL réel déjà listé, packaging `fpcalc`). Réaligner §6.5 sur streamrip, §5.9 sur Spotify 2026, §3.1/§5.1 sur la correction ANLZ.
- Mettre à jour le **statut des décisions §0** et le **journal §7.3** (nouvelles lignes A1/A2/A3/B2 ; D-acquisition reformulé).
- Pointer OVERHAUL-01 et SPEC-UNIFIED l'un vers l'autre proprement (périmètre ↔ archi), sans double source de vérité.

**Phase 4 — Revue adversariale (boucle jusqu'à convergence)**
- *Completeness critic* : feature de §7 OVERHAUL non intégrée ? invariant manquant pour une feature qui écrit `master.db` ? brique sans recherche ? non-négociable §3 perdu ? contradiction résiduelle ?
- *Ponytail-review* : où la spec sur-conçoit-elle après ajout ? quelle brique v1 redescendre en v2 ? quoi fusionner ?
- Reboucler tant que : divergences ≠ 0, features non intégrées ≠ 0, briques non sourcées ≠ 0, ou findings ponytail non traités.

**Phase 5 — Régénérer le prompt de build**
- À partir de la `SPEC-UNIFIED.md` mise à jour, **régénérer `docs/PROMPT-03-build.md`** : intégrer les 5 features dans les phases (Phase 3 « logique métier » : dedup empreinte, Smart Fixes via `_mutate`, faux-320, Track Matcher ; Fork D = streamrip), ajouter les nouveaux POC au Phase 0, mettre à jour la définition du « terminé ». Garder la lens ponytail comme contrainte de réalisation.

## Livrables

1. **`docs/SPEC-UNIFIED.md` mise à jour** — périmètre v1 réel intégré, streamrip aligné, ANLZ/Spotify corrigés, **zéro contradiction**, chaque ajout avec invariant + `# ponytail:`.
2. **`docs/_research/11_*…`** — un fichier sourcé/daté par brique nouvelle.
3. **`docs/PROMPT-03-build.md` régénéré** — phases + POC + forks à jour.
4. Matrice de divergence + journal de décisions consolidé (traçable).

## Règles d'interaction

- **Tout choix de périmètre ou structurant → `AskUserQuestion`**, reco ponytail en tête. Ne pas passer en phase 3 sans mes décisions.
- Ponytail actif : livrable d'abord, explication courte ensuite ; la simplification se justifie par sa brièveté.
- Langue : **français** (cohérent avec les docs existantes).
