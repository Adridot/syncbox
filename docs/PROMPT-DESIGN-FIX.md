# PROMPT-DESIGN-FIX — Correctifs du mockup Syncbox (itération, pas refonte)

> **Comment l'utiliser.** Coller dans la session **Claude Design** existante (projet `Syncbox UI/UX Design`, fichier `Syncbox.dc.html`, 2702 lignes au 2026-07-02). C'est une **liste de correctifs fermée** : ne rien redessiner d'autre, ne pas toucher à la direction visuelle ni aux écrans existants au-delà des points listés. Les numéros de ligne réfèrent à la version courante du mockup.
>
> **Contexte d'autorité.** Le QUOI est régi par SPEC-UNIFIED (dont le nouveau §11 qui entérine tes ajouts de juillet : ré-application d'events, ajout par lien, onboarding 11 étapes, readouts dashboard). Ces correctifs alignent le mockup sur les gardes §3/§5 qui manquent encore, et corrigent 3 données de démo. Chaque correctif **réutilise un pattern déjà présent dans le fichier** — aucun nouveau langage visuel.

---

## A. Gardes de sûreté manquantes (prioritaire)

1. **Consentement-checkbox sur la suppression irréversible** (modale `l.1630-1646`). Le bouton « Supprimer définitivement » commit sans case bloquante. Reprendre **le pattern ANLZ déjà exemplaire dans le même fichier** (`anlzConsent`, checkbox qui active le CTA, ré-armée après usage, `l.1655-1656` / `l.2653-2657`) : case nommée « Je comprends que l'audio sera définitivement perdu sur ce volume », CTA grisé tant que non cochée.
2. **Delete event : re-garde au commit** (modale `l.1534-1552`). Le CTA « Supprimer l'event » de la modale doit refléter la garde RB au moment du commit (grisé « Rekordbox ouvert — bloqué ») comme le fait déjà le CTA d'ouverture (`openDeleteEvent`, `l.2448`) — pas seulement à l'ouverture.
3. **Garde de fraîcheur du dry-run Smart Fixes** (modale `l.1582-1623`). Ajouter un état d'erreur *dans la modale existante* (pas de nouvel écran) : « ⚠ La collection a changé depuis cet aperçu — relance le dry-run », CTA « Confirmer & écrire » remplacé par « Relancer l'aperçu ». Ajouter ce cas à la barre « Démo états ».
4. **État d'erreur réseau actionnable.** Aucune surface aujourd'hui (grep 404 = 0). Réutiliser le pattern empty-state pointillé existant, avec message + CTA : cas canonique « Playlist privée ou inaccessible (404) → Connecter mon compte Spotify » + bouton « Réessayer ». L'ajouter à la barre « Démo états ».
5. **États d'échec OAuth Spotify.** Le flux n'existe qu'en succès (`l.250/833/835`, onboarding `l.1925-1928`). Ajouter : échec de connexion (erreur + « Réessayer ») et session expirée (badge ambre « reconnexion requise » sur la ligne Connexions + Réglages).

## B. Sémantique spec non respectée

6. **D22 — « Restaurer » un track ignoré** (`l.2319-2323`) : l'action ouvre aujourd'hui la modale re-match. Elle doit **restaurer le statut antérieur** (matched/ready/new…) directement — feedback inline suffisant (badge qui reprend son état), pas de modale.
7. **Liens d'achat : exclure `removed_from_source`** (`acqMissing()` `l.1996-2007`). Ajouter le champ `st` aux items et filtrer la voie d'achat (`l.748`, `l.759-761`) sur `missing`/`acquisition_failed` uniquement — une donnée, pas une mécanique.
8. **Dashboard « basse qualité (< 256 kbps) » rouge** (`l.195`, mock `lowQuality` `l.1864`) : **rejeté par SPEC-UNIFIED §11.3** (verdict qualité = 3 niveaux, jamais binaire ni rouge). Remplacer par le vocabulaire de `QualityBadge` déjà défini : « N lossy probable » (ambre) + « M incertains » (violet `#9b8cce`). Jamais de rouge sur un verdict qualité.
9. **« Prêt pour le set »** (`l.202-205`) : garder les métriques (entérinées §11.3) mais **retirer le libellé « mix harmonique »** — écrire « clés analysées » (readout passif ; le set-prep harmonique n'est pas une feature v1).

## C. Données de démo & design system

10. **Sources mock `provider:'deezer'`** (`l.1885`, `l.1897`) → `'spotify'` (les sources de bibliothèque sont Spotify-only). La pastille provider sur SourceCard est **abandonnée** ; la pastille provider ne vit que sur l'ajout par lien d'un event (déjà fait, `l.2634`).
11. **Thèmes accent `data-props`** (`l.1722`, valeurs `l.1754-1757`) : retirer les accents violet/emeraude/ambre qui collisionnent avec la sémantique figée (incertain `#9b8cce`, ready `#2dd4bf`, warning `#f5b544`). Garder cobalt (défaut) + magenta au plus. Ne pas porter l'éditeur de thème au build.
12. **Toggle dupliqué** : fusionner `dlToggleTrack/dlToggleKnob` (`l.2547-2548`) et `settingsDlTrack/settingsDlKnob` (`l.2558-2559`) — valeurs identiques, un seul helper.
13. **Tokenisation des couleurs** : consolider les hex répétés (~63 distincts) en variables CSS — en priorité les 3 violets proches et les textes-warning hors-token (`#b8a572`, `#d8c08a`). Consolidation, pas refonte.

## Hors périmètre de ce fix

- **i18n** : reste côté build (`en.ts`/`fr.ts`) — le mockup reste FR, ne pas câbler de locale.
- **Router/deep-link** : préoccupation build (couche mince `screen ↔ location.hash`), pas mockup.
- Tout le reste du mockup (écrans, flux ré-application, onboarding 11 étapes, arbitrage ambiguïté, master-list) est **validé tel quel** — n'y touche pas.
