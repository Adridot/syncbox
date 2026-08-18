# Design — fix-stale-ready-spotify-hover

## Context

Voir proposal.md (Why). État actuel du code :

- [sync.py:24](../../sidecar/src/syncbox/sync.py) : `CARRIED_AS_IS = {"ignored", "ready"}` — un `ready` est reconduit tel quel, sans vérifier son fichier.
- [library_service.py:247](../../sidecar/src/syncbox/library_service.py) : le précontrôle d'import accepte tout `ready` avec `staging_file_path` non vide (existence non vérifiée).
- [rb_write.py:531](../../sidecar/src/syncbox/rb_write.py) : `add_content()` fait le vrai `stat()` — trop tard, à l'intérieur du `mutate()` (rollback complet).
- [events_service.py:383](../../sidecar/src/syncbox/events_service.py) : même motif côté Événements (`ready` + `staging_file_path` → `add_content`), aucune prévalidation.
- [missing_service.py:33](../../sidecar/src/syncbox/missing_service.py) : `MISSING_STATUSES` inclut `missing` — aucune modification nécessaire, le reclassement suffit à rendre le titre actionnable.
- [SpotifyAttributionLink.vue:82](../../ui/src/components/SpotifyAttributionLink.vue) : dévoilement par `:global(.hover-reveal:hover .spotify-attribution)` — WKWebView laisse des états `:hover` fantômes quand les lignes bougent sous un pointeur immobile pendant le défilement.

Contraintes : macOS/WKWebView (le bug WebKit est la cause racine côté UI) ; le repo n'a pas de lint UI (test + typecheck seulement) ; listes virtualisées (TanStack) — les lignes sont recyclées pendant le scroll.

## Goals / Non-Goals

**Goals :**
- Aucun titre `ready` ne peut rester bloqué non-actionnable quand son fichier stagé disparaît.
- Aucune écriture Rekordbox tentée pour un fichier stagé absent (plus de `FileNotFoundError` + rollback).
- Zéro flèche Spotify fantôme après défilement, sur les 8 sites, avec un correctif dans le seul composant.

**Non-Goals :**
- Pas de réparation des jobs d'acquisition anciens (`downloaded`) — ils restent comme historique, décision d'Adrien.
- Pas de migration DB : les deux titres réels bloqués sont des lignes bibliothèque, la prochaine synchronisation les reclasse via le nouveau contrôle au carry.
- Pas de changement du comportement « flèche permanente » (Historique, ReMatchModal).
- Pas de refonte du composant d'attribution au-delà du mécanisme de dévoilement.

## Decisions

### 1. Reclassement au carry de sync, pas en tâche de fond

Le contrôle d'existence se fait dans `diff_tracks()` (ou juste autour du carry `CARRIED_AS_IS`) : un `ready` dont `staging_file_path` n'est pas un fichier régulier devient `missing` avec chemin vidé. Alternative écartée : un scan périodique dédié — plus de code, et la sync tourne déjà au bon moment. Attention : `sync.py` est documenté « pure, no I/O » ; le contrôle fichier se fera donc dans l'appelant (le service qui prépare `previous` avant `diff_tracks`, ou un post-passage), pour préserver la pureté du module — à trancher à l'implémentation selon le point d'insertion le plus court, la spec ne contraint que le résultat.

### 2. Précontrôle d'import partagé, exclusion plutôt qu'échec global

Un helper commun (sidecar) valide `Path(staging_file_path)` régulier pour chaque `ready` sélectionné, AVANT `mutate()`. Les lignes invalides : reclassées `missing` + chemin vidé + remontées dans la réponse ; les lignes valides s'importent normalement. Alternative écartée : refuser tout l'import (`ConflictError`) — punit les lignes saines et re-crée une impasse utilisateur. Événements : même helper avant la boucle d'apply.

### 3. UI : état explicite dans `SpotifyAttributionLink.vue` seul

**Amendé deux fois à l'implémentation (05/08, vérifs app réelle) :**

*Amendement 1 — état, pas d'événements de frontière.* La version `pointerenter`/`pointerleave` par conteneur laissait des fantômes : les événements de frontière reposent sur la même comptabilité hover périmée que `:hover` pendant un scroll WKWebView. Mécanisme retenu (`ui/src/lib/hover-reveal.ts`, partagé module-level, refcounté) : UN état `activeHoverReveal` piloté par `pointermove` en capture window (hit-test frais à chaque événement, `event.target.closest('.hover-reveal')`), remis à null par `scroll` ET `wheel` en capture (le wheel est l'entrée trackpad elle-même, il ne peut pas être raté) et à la sortie de fenêtre (`pointerout` sans relatedTarget). Chaque instance calcule `revealed = activeHoverReveal === son conteneur` → au plus une flèche stylée visible.

*Amendement 2 — masquage structurel, pas d'opacité.* Le test en app réelle montrait ENCORE des fantômes : plusieurs flèches, pas sous le curseur, insensibles aux mouvements — donc pas un problème d'état mais de **pixels orphelins** : la `transition: opacity 120ms` donne à chaque flèche sa propre couche de compositing, que WKWebView orpheline quand les lignes virtualisées bougent/se démontent en cours d'animation (seules les flèches ghostent, jamais le texte des lignes — signature de la couche d'animation). Correctif final : plus AUCUNE règle d'opacité ni transition d'opacité ; l'icône est retirée du DOM (`v-if="shown"`) quand elle est cachée — une icône absente du DOM ne peut pas laisser de pixels. Le bouton 22px reste toujours en layout (zéro layout shift, cible focusable). `:focus-within` CSS remplacé par un suivi `focusin`/`focusout` JS sur le conteneur (l'accessibilité clavier révèle toujours). Le hover vert du bouton est gated `[data-shown]` (un ghost `:hover` sur bouton vide ne peint rien). Alternatives écartées : modifier les 8 conteneurs ; flèches toujours visibles (refusé par Adrien) ; hack de re-layout au scroll ; `visibility: hidden` (invalidation discrète mais toujours dépendante du repaint d'une couche existante — le retrait DOM est le seul niveau garanti).

## Risks / Trade-offs

- [Écouteur scroll capture global par instance de composant → beaucoup d'instances dans les listes virtualisées] → écouteur `passive`, travail nul quand l'état est déjà faux ; si profilage nécessaire, mutualiser en un seul écouteur module-level partagé.
- [Fenêtre de course : le fichier disparaît entre le précontrôle et `add_content()`] → le `stat()` de `rb_write` reste le filet de sécurité ; le rollback existant couvre ce cas résiduel, désormais rarissime.
- [`pointerenter` non redéclenché par WKWebView après recyclage de ligne virtualisée] → à vérifier au test manuel ; au pire la flèche n'apparaît qu'au prochain mouvement du pointeur, comportement acceptable (jamais de fantôme).
- [Reclassement silencieux `ready` → `missing` pendant la sync] → l'utilisateur retrouve le titre dans Manquants, comportement conforme à l'ancien invariant SPEC-01 ; les jobs conservés gardent la trace.

## Migration Plan

Rien à migrer : la prochaine synchronisation reclasse les deux titres réels (`NUEVAYoL`, `La lettre`) ; les jobs `downloaded` restent en historique. Rollback = revert du commit, aucun état persistant nouveau.
