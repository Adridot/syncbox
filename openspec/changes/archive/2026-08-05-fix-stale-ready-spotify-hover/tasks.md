# Tasks — fix-stale-ready-spotify-hover

## 1. Sidecar — intégrité des fichiers stagés

- [x] 1.1 Helper commun de validation : `staging_file_path` non vide ET fichier régulier ; les lignes `ready` invalides sont reclassées `missing` avec chemin vidé, jobs intacts (emplacement : module partagé par library/events, hors `sync.py` qui reste pur)
- [x] 1.2 Sync bibliothèque : au carry des `ready`, appliquer la validation — fichier disparu ou non régulier → carry en `missing` + chemin vidé (voir design, décision 1 pour le point d'insertion)
- [x] 1.3 Import bibliothèque ([library_service.py:247](../../sidecar/src/syncbox/library_service.py)) : remplacer le test « chemin non vide » par le helper AVANT `mutate()` ; lignes invalides reclassées + exclues + remontées dans la réponse, lignes valides importées normalement
- [x] 1.4 Apply événements ([events_service.py:383](../../sidecar/src/syncbox/events_service.py)) : même précontrôle avant la boucle d'apply, mêmes effets
- [x] 1.5 Tests sidecar : sync reclasse un `ready` au fichier disparu (et non régulier) en `missing` chemin vidé jobs intacts ; fichier présent → carry inchangé ; import bibliothèque mixte (valides importés, invalide reclassé/remonté, pas de rollback) ; apply événement idem ; `missing` reclassé visible dans le centre Manquants

## 2. UI — dévoilement des flèches Spotify

- [x] 2.1 `SpotifyAttributionLink.vue` : état explicite de visibilité — `closest('.hover-reveal')` à la pose, `pointerenter`/`pointerleave` sur le conteneur, écouteur `scroll` window capture+passive qui remet à faux ; nettoyage à l'unmount ; supprimer les règles CSS `:hover` d'opacité, conserver `:focus-within`
- [x] 2.2 Tests UI (spotify-attribution.spec.ts) : pointerenter révèle / pointerleave masque ; scroll masque une flèche révélée ; focus clavier révèle toujours ; sites permanents (Historique, ReMatchModal) inchangés
- [x] 2.3 Vérification manuelle dans l'app (WKWebView) : défilement des listes virtualisées Bibliothèque/Événements/Manquants + AddSourceModal → aucune flèche fantôme, re-hover après scroll OK

## 3. Validation finale

- [x] 3.1 `pnpm test` + typecheck UI, suite sidecar complète
- [x] 3.2 Vérifier en conditions réelles que `NUEVAYoL` et `La lettre` redeviennent actionnables dans Manquants après une sync (fichiers absents, jobs conservés)
