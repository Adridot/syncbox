# Syncbox — SPEC-DESIGN

> **Objet.** Intrant UI de [PROMPT-03-build.md](../PROMPT-03-build.md). Fige les décisions **COMMENT** que SPEC-UNIFIED §9 délègue (§10.9 navigation/structure + §10.10 matching configurable), plus la carte des écrans, le modèle de navigation, l'inventaire de composants et les tokens visuels.
>
> **Autorité.** Ce document ne tranche que le **COMMENT** des écrans. Le **QUOI** (comportement, invariants §5, gardes §3) reste régi par [SPEC-UNIFIED.md](../SPEC-UNIFIED.md) — non re-débattu ici. En cas de conflit, SPEC-UNIFIED gagne.
>
> **Mockup de référence.** [`Syncbox.dc.html`](../Syncbox.dc.html) — prototype cliquable haute-fidélité, tous domaines + tous états. Le bouton « Démo états » (bas-droite) bascule RB-ouvert / backend-down / vide / chargement pour inspecter les états de sûreté.

---

## 1. Direction retenue (résumé)

| Sujet | Décision |
|---|---|
| Esthétique | **Studio sombre / cabine DJ** — fonds quasi-noirs froids, surfaces ardoise-bleu, accent azur, sémantique froide. Dark only en v1. |
| Plateforme | **macOS d'abord** ; chrome neutre transposable Windows (le design n'utilise aucun élément mac-only). |
| Navigation | **Router réel** (deep-link + back + écran persisté) ; IA **regroupée par tâche** : 6 destinations + onboarding. |
| Santé système | **Widget dashboard + pile sidebar permanente, source unique** — pas d'écran dédié. |
| Matching configurable | **Exposé en Réglages › Avancé** (replié, garde-fous) ; invariants verrouillés affichés ; re-match manuel par track = outil de 1re intention. |
| Acquisition (manquants) | **Deux voies visibles côte à côte** : achat légal (Beatport/Bandcamp) **en avant** + module download Deezer (opt-in, OFF). **SoundCloud** ajouté (demande propriétaire) **uniquement** en ajout manuel de titre à un event — voir note build §10 (ffmpeg). |

---

## 2. Carte des écrans

L'existant (9 écrans, nav par état) est **remplacé** par **6 destinations** regroupées par tâche (Piste B de SPEC-01 §8.2) + 1 flux guidé (Piste C).

```
Onboarding (1er lancement / “Revoir” depuis Réglages)
  └─ flux linéaire 4 étapes : Spotify → Dossiers → Module download (opt-in) → Collection prête

Coque persistante (sidebar gauche + zone principale)
├─ ◎ Vue d'ensemble (Dashboard)
│     hero sûreté RB · 4 tuiles santé · activité récente · connexions
├─ ≡ Bibliothèque
│     cartes sources Spotify · table de revue (filtres par statut, tags delta, re-match)
├─ ◆ Events
│     cartes events (statuts) · workspace staging · apply → smart playlist · delete avec aperçu
│     ajout manuel par lien **Spotify / Deezer / SoundCloud** (SoundCloud = ce seul point d'entrée)
├─ ✛ Santé de collection (hub Doctor, sous-onglets)
│     ├─ Doublons         (groupes + keeper explicable, confirmation par groupe)
│     ├─ Fichiers manquants (racheter/relier/retirer)
│     ├─ Untagged          (4 catégories triées junk<dup<alt<review)
│     ├─ Smart Fixes       (catalogue fixe → dry-run → confirm → mutate)
│     └─ Backups & logs    (liste/restore/rotation N + journal)
├─ ↓ Acquisition (centre unifié, scopes event/library/collection)
│     chemin légal (achat) EN AVANT · module download Deezer (opt-in, OFF) · jobs SSE réels
└─ ⚙ Réglages
      Spotify · 4 dossiers (validés) · module download + ARL masquée · rétention · langue
      └─ Avancé (replié) : seuils de matching + invariants verrouillés
```

**Regroupements qui fusionnent l'existant :**
- « Download & Match » + « Missing » + acquisition de Library/Events → **un seul centre d'Acquisition** (les jobs sont déjà unifiés côté données). Les écrans Library/Events **lient vers** l'Acquisition avec scope pré-filtré, au lieu de dupliquer l'UI de download → résout le chevauchement Download Center ↔ contexte event.
- Duplicates + Untagged + Missing + Smart Fixes + Backups → **hub « Santé de collection »** (Doctor).
- La santé système n'a **pas** d'écran : un widget sur le dashboard + une **pile permanente** dans la sidebar, **dérivés d'un sélecteur canonique unique**.

---

## 3. §10.9 — Navigation & structure (décision justifiée)

### 3.1 Router réel, pas navigation par état
**Décidé : router avec deep-link, back/forward et persistance de l'écran courant.** L'existant (`ui.activeView` Pinia, pas de routeur, pas de back, pas de persistance, Settings en `v-else` fourre-tout) est abandonné.
- *Justification.* Un outil pro est rouvert des dizaines de fois ; retrouver l'écran/onglet quitté est un gain réel et bon marché. Le deep-link permet aussi de pointer un sous-onglet (`#health/smartfixes`) depuis une notification de job ou un lien d'aide.
- *Garde-fou contre la régression existante.* Une route inconnue tombe sur un **défaut explicite** (Dashboard), jamais sur Settings silencieusement.

### 3.2 Regroupement par tâche (Piste B), pas 9 écrans-tiroirs
**Décidé : 6 destinations.** Le critère ponytail : le plus petit ensemble qui sert les parcours réels.
- *Acquisition unifiée* — les 3 scopes partagent déjà le modèle `GlobalAcquisitionJob` ; trois entrées de download séparées étaient une dette d'UI, pas une réalité métier.
- *Hub Santé* — Doublons/Manquants/Untagged/Smart Fixes/Backups sont tous « entretien de collection, en aperçu avant écriture » ; ils partagent le même cadre mental (et la même garde RB).

### 3.3 Onboarding = flux guidé linéaire (Piste C), le reste = destinations
Seul le **premier lancement** justifie un flux imposé (Spotify → dossiers → module → prêt). Les tâches récurrentes (sync, event, diagnostic) restent des destinations libres — un assistant linéaire pour elles ajouterait de la friction sans valeur. Re-jouable depuis Réglages.

### 3.4 Santé système : indicateur, pas écran
**Décidé : pile permanente sidebar + tuiles dashboard, source unique.** Corrige directement les incohérences relevées (compteurs téléchargements divergents sidebar↔dashboard ; condition « download prêt » différente). **Tous** les compteurs santé dérivent d'**un seul sélecteur** (`health`) ; il n'existe plus qu'une définition de « connecté », « prêt », « actifs ».
- *Pourquoi pas d'écran dédié.* La santé est une info d'ambiance (toujours visible) + des détails de réparation qui vivent déjà dans le hub Santé (Backups & logs). Un écran « système » à part serait un tiroir vide la plupart du temps.

### 3.5 Friction assumée (faithful reporting)
- La garde **RB-ouvert** bloque les mutations partout. Plutôt que de griser silencieusement des boutons, le design la rend **lisible** : bandeau amical en haut + hero dashboard qui passe en « écritures en pause » + boutons d'action qui affichent **« Rekordbox ouvert — bloqué »** au lieu de paraître cliquables. Friction nécessaire, rendue compréhensible.
- Le cycle **dry-run → confirm** ajoute une étape à chaque écriture en masse. C'est le cœur de la promesse de sûreté ; on l'**habille** (aperçu exact, lisible, scrollable) plutôt que de le raccourcir.

---

## 4. §10.10 — Matching configurable (décision justifiée)

**Décidé : exposer en `Réglages › Avancé`, replié par défaut, avec garde-fous.** (≠ le slider de confiance visible en évidence de l'app actuelle.)

**Ce qui est exposé** (panneau Avancé) :
- Seuil de confiance (défaut **82**), marge d'ambiguïté (défaut **6**).
- Pondérations title/artist/duration (**0.52 / 0.36 / 0.12**), avec **contrainte somme = 1.00** validée.
- Politique de collision ISRC (défaut : rejet si `|Δdurée| > 15 s` ET titre < 82).
- **Reset aux valeurs par défaut** toujours à un clic.

**Garde-fous :**
- Section **repliée** par défaut, précédée d'un **bandeau d'avertissement** : valeurs recommandées/calibrées, préférer le re-match manuel.
- **Invariants verrouillés affichés et non éditables** (§5.3 / D19) : ISRC-first prioritaire, **pipeline de normalisation unique** matching+dedup, buckets de durée. Seule l'**exposition** des seuils est ouverte — l'algorithme ne change pas.

**Outil de 1re intention = re-match manuel par track** (dans la table de revue → modale « Re-matcher »), qui montre les candidats Rekordbox avec confiance/durée/bitrate. *Recommandation : 95 % des cas se règlent là ; toucher les seuils globaux est l'exception, d'où le repli.* On expose parce que l'utilisateur l'a demandé et que des garde-fous le rendent sûr — pas parce que le parcours l'exige.

---

## 5. Modèle de navigation (état)

| Élément | Comportement |
|---|---|
| Destination courante | persistée entre lancements ; deep-link `#<screen>` / `#health/<tab>` |
| Sous-onglets Santé | état propre persisté ; route `#health/smartfixes` adressable |
| Back/forward | natif (history) |
| Route inconnue | → Dashboard (défaut explicite, jamais Settings) |
| Pile santé sidebar | toujours visible, dérivée du sélecteur `health` unique |
| Garde RB-ouvert | bandeau global + reflet sur chaque CTA de mutation |
| Backend-down | overlay plein écran sur la zone principale (après épuisement des restarts) + « Relancer » |

---

## 6. Inventaire de composants réutilisables

| Composant | Rôle | États |
|---|---|---|
| **Sidebar + nav item** | navigation primaire, badge de compte | actif / inactif / badge neutre / badge warn |
| **Pile santé (HealthPill)** | Spotify / Rekordbox / Téléchargements — **source unique** | vert / amber (RB ouvert) / gris (idle) |
| **RB-guard banner** | bandeau amical mutation bloquée | visible si `rbOpen` (sans PID/chemin/flag) |
| **StatBadge / StatusBadge** | statuts track & event | new, matched, conflict/ambiguous, ready, imported, missing, removed_from_source, ignored, acquisition_failed |
| **QualityBadge** | verdict faux-320/FLAC, **3 niveaux** | ok (vert) / lossy probable (amber) / **incertain (violet-gris, prudent)** |
| **ScopeBadge** | scope d'acquisition | library / event / collection |
| **TrackReviewTable** | table de revue (Library + Events) | filtres par statut, **sélection + select-all**, skeleton de chargement, vide, lignes ; **méthode de matching masquée** (non pertinente pour l'utilisateur — seuls statut + confiance) ; titre sur 2 lignes en fenêtre étroite |
| **SourceCard** | playlist suivie | **pochette (cover) + pastille provider Spotify/Deezer**, statut, compteur, tags |
| **AddSourceModal** | ajout de source | coller un lien → aperçu résolu (cover/nom/tracks) + MyTags par défaut |
| **BulkTagBar + TagPicker** | édition tags **en delta add/remove** (jamais union) | un seul bouton « Éditer les tags » à la sélection ; modale avec **picker recherchable** (filtre live sur N MyTags, résultats scrollables + catégorie), **boutons +/− par ligne** (ajouter/retirer sans mode global), chips de sélection, résumé delta |
| **DuplicateGroupCard** | groupe + **keeper explicable (raison affichée)** | **layout comparatif côte à côte** : keeper vs copies, attributs justificatifs (bitrate, fichier présent, playlists, cues), keeper **re-sélectionnable** (radio), issue explicite « conserver X · supprimer N », confirmation par groupe, warn titres divergents |
| **ApplyEventModal / DeleteEventModal** | aperçu avant écriture event | apply et delete ont des aperçus **distincts** (smart playlist créé vs artefacts supprimés) ; **les deux CTA reflètent la garde RB** (« Rekordbox ouvert — bloqué », grisé) — pas seulement apply |
| **DryRunModal** | aperçu Smart Fixes champ par champ (avant → après) | + **opt-in protégé nommé non mémorisé** ; CTA reflète le payload exact, bloqué si RB ouvert |
| **IrreversibleDeleteModal** | suppression audio volume cloud/exFAT | avertissement + consentement explicite **avant** ; DB réversible rappelée |
| **AnlzReplaceModal** | consentement avant un re-download qui **remplace** un fichier | avertissement cues/beatgrid/waveform **hors backup** (ANLZ non écrits par pyrekordbox, §3.1/§5.5) + **case de consentement nommée** ; rappelle que la DB (tags/playlists) reste réversible ; CTA actif seulement après consentement |
| **ReMatchModal** | re-match manuel par track | candidats RB + confiance/durée/bitrate |
| **JobRow (SSE)** | job d'acquisition | progression **dérivée du flux SSE réel** (jamais factice) ; ready / downloading / ambiguous |
| **PurchaseLinks** | liens d'achat (Beatport/Bandcamp) | chemin légal **par défaut**, mis en avant ; quand le module download est ON, un bouton **↓ Deezer** s'ajoute à côté de l'achat (achat vs téléchargement — deux voies visibles côte à côte) |
| **PathField** | chemin avec validation | valide ✓ / introuvable ✕ |
| **SecretField** | ARL / tokens | masqué + état « configuré », jamais en clair |
| **Toggle (download module)** | activation opt-in | OFF par défaut |
| **Modal shell** | conteneur dialogues | overlay + slide-up |
| **Onboarding step** | flux 4 étapes | dots de progression, skip |
| **Empty / Loading / Error states** | par domaine | vide illustré, skeleton shimmer, erreur actionnable |

---

## 7. Tokens visuels

### 7.1 Couleurs (dark studio)
| Token | Hex | Usage |
|---|---|---|
| bg-base | `#0a0c10` | fond application |
| bg-sidebar | `#070910` | sidebar |
| surface | `#0c0f16` / `#0e1119` | panneaux, cartes conteneur |
| surface-raised | `#11141c` | tuiles, cartes internes |
| border | `#1c2230` / `#1f2532` | bordures cartes |
| border-subtle | `#141925` / `#1a1f2b` | séparateurs de lignes |
| text-primary | `#e7ebf2` | titres, valeurs |
| text-secondary | `#9aa4b4` / `#cdd5e1` | corps |
| text-muted | `#5f6b7d` / `#7a8699` | légendes, méta |
| **accent (azur)** | `#4da3ff` (hover `#7cc0ff`) | actions primaires, nav active, matched |
| **secondaire (teal)** | `#2dd4bf` | Smart Fixes, ready, chemin légal recommandé |
| success | `#34d399` | importé, OK, validations |
| warning | `#f5b544` (texte `#f5cd7a`) | conflit/ambigu, RB ouvert, applied-with-warnings |
| danger | `#f76e6e` (texte `#f59a9a`) | manquant, échec, suppression |
| **incertain** | `#9b8cce` | verdict qualité prudent — **jamais rouge** |

Tints de fond : `rgba(<accent>, .12–.14)` pour badges/états actifs ; bordures à `.25–.35`.

### 7.2 Typographie
- **Geist** (400/500/600/700) — UI, titres, corps.
- **Geist Mono** (400/500/600) — **valeurs techniques** : bitrate, confiance, IDs, chemins, timestamps, % de jobs. Renforce le côté « readout matériel ».
- Échelle : H1 24px/600 · H3 14–15px/600 · corps 13–14px · méta 11–12px · labels uppercase 10–11px letter-spacing .06–.08em.

### 7.3 Espacement / forme / densité
- Rayons : cartes conteneur **13–14px** · cartes internes **10–12px** · badges/boutons **6–9px** · modales **16px**.
- Padding écran : `28px 32px`, contenu centré `max-width: 760–1180px`.
- Densité **moyenne-dense** (outil pro) : lignes de table ~11px vertical, cible tactile boutons ≥ 28px de haut (desktop).
- Bordure 1px partout ; ombres réservées aux overlays (`0 8px 28px rgba(0,0,0,.5)`).

### 7.4 Mouvement
- Barre de job : `barflow` (rayures animées) **uniquement** en `downloading`, largeur = `pct` réel SSE.
- Modales : `slideup .18s`. Skeleton : `shimmer 1.3s`. Aucune animation purement décorative.

---

## 8. Couverture des gardes de sûreté (où elles vivent à l'écran)

| Garde (§3/§5) | Surface UI |
|---|---|
| RB-ouvert bloque les mutations | bandeau global + hero dashboard + CTA « bloqué » (sans PID/chemin/flag) |
| dry-run → confirm → mutate | DryRunModal ; CTA = libellé du payload exact (corrige B10) |
| protected exclus par défaut | opt-in nommé non coché/non mémorisé, protégés listés nommément dans l'aperçu |
| suppression irréversible (cloud/exFAT) | IrreversibleDeleteModal — consentement **avant**, jamais après |
| re-download qui remplace un fichier (cues ANLZ hors backup) | AnlzReplaceModal — avertissement + consentement nommé **avant** le remplacement (§5.5) |
| delete event gardé sur `mutationAllowed` (D11/D23) | CTA « Supprimer » grisé « Rekordbox ouvert — bloqué », **comme apply** (cohérence corrigée) |
| keeper explicable | DuplicateGroupCard — raison affichée, confirmation par groupe (pas de bulk auto) |
| verdict qualité 3 niveaux | QualityBadge — incertain en violet-gris prudent |
| progression réelle | JobRow dérivé du SSE ; compteurs santé d'un sélecteur unique |
| backend indisponible | overlay plein écran + « Relancer » |
| module download OFF par défaut | toggle opt-in + ARL masquée ; chemin légal mis en avant |
| i18n FR/EN | sélecteur de langue ; tout libellé est une chaîne traduisible |
| secrets au repos | SecretField masqué + « configuré » |

---

## 9. Incohérences existantes corrigées par ce design

| Réf. | Existant | Correction design |
|---|---|---|
| compteurs divergents | sidebar ≠ dashboard | sélecteur santé **unique** |
| « download prêt » | `available` vs `available && authenticated` | une seule définition d'état |
| tons statut event | carte ≠ workspace | StatusBadge partagé, vocabulaire unique |
| barre factice (F16) | largeur dérivée du ton | barre dérivée du **% SSE réel** |
| sélection cross-filtre (Untagged) | agit sur lignes cachées | sélection liée au filtre visible |
| B10 | confirmation inversée vs action | CTA reflète le payload exact |
| Settings `v-else` fourre-tout | route invalide y atterrit | route inconnue → Dashboard |
| vocabulaire conflict/ambiguous | divergent library/event | StatusBadge unifié (libellés distincts mais cohérents) |

---

## 10. Notes pour PROMPT-03 (build)

- Le mockup est **inline-styled** (Design Component) à des fins de prototypage ; le build Vue 3 doit reproduire le **comportement et la hiérarchie**, pas le CSS littéral.
- Tous les libellés du mockup sont en FR ; prévoir les clés `en.ts`/`fr.ts` parallèles (§3.8).
- Les données du mockup sont fictives ; les états (vide/chargement/erreur/RB-ouvert/backend-down/dry-run) sont les **contrats visuels** à câbler sur le SSE/REST réels.
- La pile santé et tous les compteurs **doivent** lire un unique sélecteur (corrige T4/T5 côté UI).

## 11. Écarts de périmètre vs SPEC-UNIFIED (décisions propriétaire post-design)

- **SoundCloud en v1 (ajout manuel d'event uniquement).** Le propriétaire a demandé d'ajouter SoundCloud comme source de titres, **bornée** au seul point d'entrée « ajout manuel d'un titre à un event temporaire » (edits/bootlegs introuvables en boutique) — **pas** un provider d'acquisition général (library/collection restent Deezer-only). L'UI le reflète (pastille provider, libellés de route, note Réglages).
  - **⚠ Implication build (faithful reporting).** SPEC-UNIFIED §6.5 diffère SoundCloud en v2/B4 car il sert du **HLS** et **exige ffmpeg** (+40–80 Mo/plateforme, packaging cross-OS §3.7). Restreindre l'usage à l'event ne change **pas** ce coût technique : le décodage ffmpeg reste requis dès qu'un seul lien SoundCloud est supporté. Cette décision **rouvre donc le critère « légèreté » (§2) et le packaging** — à arbitrer côté build (porter ffmpeg, ou livrer SoundCloud en plugin téléchargeable hors sidecar de base comme suggéré §6.5). Le design n'impose pas le « comment » ; il signale le coût.
- **Visibilité achat vs téléchargement.** Les deux voies des manquants sont rendues explicitement côte à côte (achat en avant ; ↓ Deezer quand le module est ON) plutôt que de masquer l'une au profit de l'autre.
