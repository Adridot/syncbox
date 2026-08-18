# fix-stale-ready-spotify-hover

## Why

Deux titres réels (`NUEVAYoL`, `La lettre`) sont bloqués dans un état sans issue : ils sont `ready` mais leur fichier stagé a disparu (`staging_file_path` pointe dans le vide, `content_id` vide). L'import échoue en `FileNotFoundError` au moment de l'écriture Rekordbox, le rollback conserve `ready`, et le centre Manquants exclut `ready` — aucune action utilisateur n'est possible. C'est une régression d'un invariant documenté (SPEC-01 §: un fichier téléchargé disparu doit rendre le titre à nouveau actionnable). Le même risque existe côté Événements.

Par ailleurs, les flèches d'attribution Spotify (dévoilées au survol via `.hover-reveal:hover`) restent affichées de façon persistante après un défilement — bug WebKit/WKWebView connu quand des éléments se déplacent sous un pointeur immobile. Reproduit dans l'app ; 8 emplacements concernés.

## What Changes

- Un titre `ready` (bibliothèque ou événement) dont le fichier stagé n'est plus un fichier régulier est automatiquement reclassé `missing` : `staging_file_path` vidé, ancien job d'acquisition conservé comme historique. Le titre redevient actionnable dans le centre Manquants.
- Le même précontrôle d'existence du fichier stagé s'exécute avant tout import Bibliothèque ou Événements (aujourd'hui seul le chemin non-vide est vérifié, [library_service.py:247](../../sidecar/src/syncbox/library_service.py) ; le contrôle réel n'arrive qu'à l'écriture Rekordbox, [rb_write.py:531](../../sidecar/src/syncbox/rb_write.py)).
- Les flèches Spotify conservent l'apparition au survol, mais le `:hover` CSS est remplacé par un état explicite central dans `SpotifyAttributionLink.vue`, réinitialisé à chaque défilement. Correction unique pour les 8 emplacements hover-reveal (Bibliothèque ×3, Événements ×2, AddSourceModal ×2, Manquants ×1). Historique et ReMatchModal affichent déjà la flèche en permanence — non concernés.

## Capabilities

### New Capabilities

- `staged-file-integrity` : un fichier stagé disparu ne laisse jamais un titre dans un état non actionnable — reclassement automatique en `missing` et précontrôle d'existence avant import (Bibliothèque et Événements).
- `spotify-attribution-reveal` : le dévoilement au survol des liens d'attribution Spotify est piloté par un état explicite (pas de `:hover` CSS), réinitialisé au défilement, pour ne jamais laisser de flèches fantômes persistantes.

### Modified Capabilities

_(aucune — `reconcile-stale-library-matches` couvre les liens `matched`/`imported` vers du contenu Rekordbox, pas les fichiers stagés ; aucune spec existante ne couvre l'attribution Spotify UI)_

## Impact

- **Sidecar** : `sync.py` (le carry-as-is de `ready` doit vérifier le fichier), `library_service.py` (précontrôle import), `events_service.py` (précontrôle import), `missing_service.py` (aucun changement attendu : `missing` y est déjà éligible), migration des deux titres réels bloqués en base.
- **UI** : `SpotifyAttributionLink.vue` (état explicite + reset au scroll) ; les 8 conteneurs `hover-reveal` dans `LibraryScreen.vue`, `EventsScreen.vue`, `AddSourceModal.vue`, `MissingEntryList.vue` — idéalement sans toucher chaque conteneur.
- **Tests** : sidecar (reclassement, précontrôle, idempotence) ; UI (disparition au défilement, non couverte aujourd'hui).
- Pas de changement d'API publique ni de dépendance nouvelle.
