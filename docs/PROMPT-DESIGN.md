# PROMPT-DESIGN — Design UI/UX de Syncbox (phase design, avant le build)

> **Comment l'utiliser.** Coller ce prompt dans une session **Claude Design** (mockups cliquables). Il **précède** [PROMPT-03-build.md](PROMPT-03-build.md) : on conçoit d'abord les écrans/parcours, on code ensuite. La spec qui fait foi sur le **QUOI** (comportement, sûreté, données) est [SPEC-UNIFIED.md](SPEC-UNIFIED.md) — **ne pas la re-débattre**. La phase design tranche le **COMMENT** des écrans : c'est exactement ce que SPEC-UNIFIED §9 (§10.9 UI/UX + §10.10 matching configurable) **délègue ici**.
>
> **Livrables attendus** (deux, l'un nourrit le build) :
> 1. **Mockups cliquables** haute-fidélité (desktop, macOS + Windows), parcours navigables, états réels (vide / chargement / erreur / succès / avertissement).
> 2. **`docs/SPEC-DESIGN.md`** — doc concise qui fige : carte des écrans, modèle de navigation, inventaire de composants, tokens visuels (couleurs/typo/espacements/densité), et **les décisions §10.9 + §10.10 tranchées**. C'est l'intrant UI de PROMPT-03.

---

## Mission

Concevoir l'**UI/UX complète** de **Syncbox** — app desktop **macOS + Windows**, open-source, qui maintient la collection **Rekordbox** d'un DJ : synchronise des **playlists Spotify** (lecture seule), **entretient la collection** (doublons, fichiers manquants, tags, **Smart Fixes** de nettoyage de métadonnées en masse, **détection faux-320/FLAC**), et propose deux voies pour les morceaux manquants : un **chemin d'achat légal mis en avant** (liens Beatport/Bandcamp) et un **module de téléchargement optionnel, OFF par défaut** (Deezer).

**But du design** : des parcours **clairs, sûrs et explicables**, fidèles à la promesse produit (« je tague ma bibliothèque et mes events, sans jamais risquer ma collection Rekordbox »). Le design est **libre sur l'esthétique et la structure des écrans**, mais **lié par les gardes de sûreté UI** ci-dessous — elles ont une surface écran non négociable.

## Intrants (hiérarchie d'autorité)

1. **[SPEC-UNIFIED.md](SPEC-UNIFIED.md)** — fait foi sur le comportement : modèle de domaine (§4), invariants (§5), non-négociables (§3). Le design **habille** ces invariants, ne les contredit jamais.
2. **[SPEC-01-syncbox.md](SPEC-01-syncbox.md) §8** — **état des lieux UI existant + pistes ouvertes** (9 écrans, navigation par état Pinia, composants partagés, incohérences relevées). C'est le **point de départ à challenger**, pas une contrainte.
3. Le reste de SPEC-01 / `_research` : seulement si une question de design touche une constante ou une mécanique précise.

## Le design est libre sur… / lié par…

**Libre** : direction visuelle, structure et nombre d'écrans, modèle de navigation (routeur/deep-link ou état), regroupements, densité, onboarding, micro-interactions. Rien de l'existant n'est figé.

**Lié (gardes de sûreté à surface UI — non négociables, repris de §3/§5)** :
- **Garde « Rekordbox ouvert »** : toute action de mutation est **bloquée** si Rekordbox/rekordboxAgent tourne, avec un message **amical** (pas de PID, pas de chemin `/Applications/`, pas de flag technique). Cet état doit être **visible et compréhensible**, pas une erreur sèche.
- **Cycle `dry-run → confirm → mutate`** (Smart Fixes, deletes, dedup, events) : l'utilisateur **prévisualise** l'effet exact (par track : champ, avant → après) **avant** d'écrire. Le texte de confirmation reflète **exactement** le payload exécuté (jamais l'inverse de l'action — corrige B10).
- **`protected` exclus par défaut** des écritures Smart Fixes : inclure une piste protégée exige un **opt-in nommé, jamais coché par défaut, jamais mémorisé** entre runs ; le dry-run **liste nommément** les pistes protégées touchées.
- **Suppression irréversible (fichier sur volume cloud/exFAT)** : **avertissement + consentement explicite AVANT** l'action (« l'audio sera perdu définitivement sur ce volume »). Jamais de notification après coup. La DB reste toujours réversible (soft-delete + backup).
- **Keeper de doublons explicable** : la suggestion de keeper affiche **la raison** (échelle de priorité ordonnée : protégé > fichier présent > qualité/bitrate > départage), pas un score opaque. Confirmation **par groupe** (pas de bulk auto-resolve 1-clic).
- **Verdict qualité faux-320/FLAC** : signal en **3 niveaux** (`ok` / `lossy probable` / `incertain`), jamais binaire ; `incertain` est une nuance prudente, pas une accusation.
- **Progression réelle** : toute barre/compteur de job dérive du flux SSE réel — **pas de barre factice** (corrige le faux progress existant). Compteurs santé (Spotify/Rekordbox/téléchargements) **dérivés d'une source unique** (corrige les compteurs divergents sidebar↔dashboard).
- **État « backend indisponible »** : après épuisement des redémarrages, un état clair + bouton « Relancer ». À designer comme un vrai état, pas un freeze.
- **Module de téléchargement OFF par défaut** : activation **explicite** par l'utilisateur (+ saisie de son ARL). Le **chemin légal (liens d'achat) est mis en avant** comme voie par défaut des morceaux manquants ; le téléchargement est l'option opt-in, jamais imposée ni pré-activée.
- **i18n FR/EN** : tout libellé user-facing doit exister en parallèle FR/EN (le design prévoit des chaînes traduisibles, pas de texte en dur dans l'image).
- **Secrets** : les champs ARL / tokens ne s'affichent jamais en clair une fois saisis (champ masqué + état « configuré »).

## Écrans & domaines à couvrir (intrant, à réorganiser librement)

L'existant = **9 écrans, navigation par état** (pas de routeur). Domaines fonctionnels à servir, quel que soit le découpage retenu :
- **Bibliothèque** — playlists Spotify suivies en permanence ; tracks avec statuts (`new → matched|conflict|ready|imported`, + `missing`, `removed_from_source`, `ignored`) ; tags par défaut ; table de revue (filtres, ignore/restore, édition de tags en masse en **delta add/remove**).
- **Events** — imports temporaires (mariage, soirée) depuis playlist / vide / lien ; staging ; apply qui crée un smart playlist sous « Event Imports ».
- **Santé de collection (Doctor)** — **Doublons** (groupes + keeper explicable), **Fichiers manquants** (re-download / re-link / remove), **Untagged** (4 catégories : junk < dup < alt < review), **Smart Fixes** (nettoyage métadonnées dry-run→confirm→mutate), **gestion des backups** (liste / restore / rotation N) + **logs**.
- **Acquisition** — morceaux manquants : **liens d'achat (par défaut)** + **module download Deezer (opt-in)** ; jobs unifiés (event/library/collection) avec progression SSE.
- **Réglages** — credentials Spotify (OAuth PKCE), ARL Deezer (opt-in), 4 chemins, rétention backups, langue, activation du module download.
- **Onboarding** — premier lancement : connecter Spotify → choisir les chemins → (option) module download → collection prête.

## Questions de design à TRANCHER (et justifier dans SPEC-DESIGN.md)

Ce sont les décisions que SPEC-UNIFIED §9 délègue explicitement :

1. **§10.9 — Navigation & structure.** Routeur (deep-link/back) ou navigation par état ? Persistance de l'écran courant entre lancements ? Conserver 9 écrans (piste A) ou **regrouper par tâche** (piste B : un **centre d'acquisition unifié** ; un **hub « Santé de collection »** pour Doublons/Manquants/Untagged/Smart Fixes/Doctor) ? Des **flux guidés** (piste C : onboarding linéaire, parcours « sync source » / « créer un event ») plutôt que des écrans-tiroirs ? Le Download Center et le contexte event se chevauchent-ils ? La santé système mérite-t-elle un écran dédié ou un indicateur ?
2. **§10.10 — Matching configurable.** Exposer ou non à l'utilisateur les seuils (confidence **82**, marge d'ambiguïté **6**, pondérations title/artist/duration) et la politique de collision ISRC ? Si oui : où, sous quelle forme (avancé/caché ?), avec quels garde-fous ? Les **invariants d'algorithme (§5.3) et la normalisation unique (D19) restent intouchés** — seule l'**exposition** est en jeu. Recommandation attendue, pas un catalogue d'options.

> Lens ponytail (à appliquer au design aussi) : ne pas dessiner un écran/réglage « pour plus tard ». Un panneau de seuils de matching n'existe que si tu le recommandes vraiment. Le plus petit ensemble d'écrans qui sert les parcours réels gagne. Préférer une feature native (état système, champ standard) à un composant maison.

## Méthode

1. Lis SPEC-UNIFIED §3/§4/§5/§9 et SPEC-01 §8. Liste les **incohérences existantes** à corriger (compteurs divergents, condition « download prêt » incohérente, tons de statut event divergents, barre factice, sélection cross-filtre agissant sur lignes cachées).
2. Pose-moi (via question) **au plus 3 arbitrages** que tu ne peux pas trancher seul (ex. ambition visuelle, public, plateforme prioritaire).
3. Propose une **direction** (carte d'écrans + modèle de navigation + langage visuel) **avant** de produire tous les écrans — qu'on valide la structure d'abord.
4. Produis les **mockups cliquables** couvrant les domaines ci-dessus, **avec les états** (vide, chargement, erreur, succès, avertissement, RB-ouvert-bloqué, backend-down, dry-run/confirm).
5. Rédige **`docs/SPEC-DESIGN.md`** : carte des écrans, modèle de navigation tranché, inventaire de composants réutilisables, tokens visuels, et les réponses §10.9 + §10.10 justifiées. C'est ce que PROMPT-03 consommera.

**Faithful reporting** : si une garde de sûreté rend un parcours lourd, dis-le et propose le meilleur compromis — ne masque pas la friction, ne sacrifie pas la garde.
