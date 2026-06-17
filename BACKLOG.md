# Backlog — IA-Powered-OS

Évolutions identifiées, **à traiter**. Chaque item est décrit avec assez de
contexte pour être repris sans rediscussion.

> **Cycle de vie** : ce fichier ne contient QUE ce qui reste à faire. Quand un
> item est réalisé, il est décrit dans [`CHANGELOG.md`](CHANGELOG.md) (sous la
> version concernée, avec son numéro d'origine) **et retiré d'ici**. Les numéros
> sont des identifiants stables — ne pas les renuméroter.

---

## Anonymisation — éditeur d'alias / détection

> Les timecodes par occurrence sont propagés dans le `.etat.json` (v1.3.0) ;
> #10 peut s'appuyer dessus.

### 10. Lister toutes les occurrences d'un terme (vue liste)
**Besoin** : quand une ambiguïté est levée (item #9), pouvoir voir **toutes** les
occurrences du mot dans leur contexte, et y accéder rapidement.

**État** : les timecodes/positions sont désormais capturés par `detecter.py`
(jusqu'à 60 par candidat) et le bouton **▶** de l'éditeur cycle déjà sur les
occurrences (réécoute). **Reste** : une **vue liste** déroulant toutes les
occurrences (texte + ▶ + ✎) au lieu du seul cyclage sur un bouton.

**Sévérité** : confort, mais utile pour traiter les alertes d'homonymie.

---

## Industrialisation / automatisation

### 16. Serveur tagueur — support des Range requests (lecture audio)
**Besoin** : `serveur_tagueur.py` sert l'audio en bloc (`Accept-Ranges: none`).
Sur de gros fichiers, le *seek* dans `<audio>` peut être limité. (Le serveur de
l'éditeur, lui, gère déjà le Range depuis la v1.3.0 — reste à le porter au
tagueur.)

**Piste** : implémenter les requêtes HTTP `Range` (206 Partial Content) dans
`serveur_tagueur.py` (réutiliser la logique de `serveur_editeur.py`). À valider
sur un vrai entretien : peut-être inutile selon le format. Identifié le 15/06/2026.
