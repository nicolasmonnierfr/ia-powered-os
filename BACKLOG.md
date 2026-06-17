# Backlog — IA-Powered-OS

Évolutions identifiées, **à traiter**. Chaque item est décrit avec assez de
contexte pour être repris sans rediscussion.

> **Cycle de vie** : ce fichier ne contient QUE ce qui reste à faire. Quand un
> item est réalisé, il est décrit dans [`CHANGELOG.md`](CHANGELOG.md) (sous la
> version concernée, avec son numéro d'origine) **et retiré d'ici**. Les numéros
> sont des identifiants stables — ne pas les renuméroter.

---

## Tagueur (`tools/transcription/tagger.html`)

### 5. Couper le 1er segment doit retirer tout le début de l'audio
**Besoin** : quand les premiers segments sont coupés, le plan de coupe conserve
quand même l'audio AVANT la 1re parole gardée (silence/bruit d'intro entre 0.0 et
le `start` du 1er segment, qui n'est pas dans un intervalle coupé). Idem en fin.

**Comportement à trancher** (description initiale contradictoire — à clarifier) :
- soit **rogner** : le 1er `keep_interval` commence au 1er segment CONSERVÉ et le
  dernier finit au dernier segment conservé (l'intro/outro hors parole gardée est
  retirée) ;
- soit **garder** l'intro/outro bruts (1er keep à 0.0, dernier keep à la durée
  totale).

**À cadrer avant de coder** : symétrie début/fin ; cohérence avec les timecodes
du `.srt`/`.txt` exportés ; ne touche que la génération des `keep_intervals`
(`buildCompactTimeline` dans tagger.html), pas `couper_audio.py`.

**Sévérité** : mineure, non bloquante. Identifié le 14/06/2026.

---

## Anonymisation — éditeur d'alias / détection

> Les timecodes par occurrence sont désormais propagés dans le `.etat.json`
> (v1.3.0). #10 et #9 peuvent s'appuyer dessus.

### 9. Détecteur de similarité / alerte homonymes
**Besoin** : signaler le risque d'homonymie — ex. « Marc Durand » et « Marc
Dupont », ou un « Marc » seul qui peut désigner l'un ou l'autre. L'outil ne peut
pas trancher (le bon référent dépend du contexte), mais il doit **lever une
alerte à traiter à la main**.

**Piste** : après détection, comparer les candidats `PERSONNE` entre eux —
partage d'un même token (prénom commun), ou proximité (distance de Levenshtein
faible) — et marquer les groupes concernés. Affichage de l'alerte dans
l'éditeur. Ajout local à `detecter.py`, sans dépendance lourde.

**Limite assumée** : un prénom seul réellement ambigu ne peut être que signalé,
pas résolu automatiquement. La désambiguïsation effective se fait en amont dans
le tagueur (rendre le texte distinct : « Marc Durand » vs « Marc Lefèvre »).

**Sévérité** : importante pour la qualité d'anonymisation. Identifié le
14/06/2026.

### 10. Lister toutes les occurrences d'un terme (vue liste)
**Besoin** : quand une ambiguïté est levée (item #9), pouvoir voir **toutes** les
occurrences du mot dans leur contexte, et y accéder rapidement.

**État** : les timecodes/positions sont désormais capturés par `detecter.py`
(jusqu'à 60 par candidat) et le bouton **▶** de l'éditeur cycle déjà sur les
occurrences (réécoute). **Reste** : une **vue liste** déroulant toutes les
occurrences (texte + ▶ + ✎) au lieu du seul cyclage sur un bouton.

**Sévérité** : confort, mais utile pour traiter les alertes de #9.

### 11. Surligner le terme en cours dans l'extrait d'illustration (quick win)
**Besoin** : dans l'éditeur d'alias, l'extrait de contexte affiché peut contenir
plusieurs noms ; on ne voit pas immédiatement lequel on est en train de
catégoriser. Mettre le terme **en gras / autre couleur** dans l'extrait.

**Piste** : côté éditeur uniquement — au rendu de l'extrait, encadrer les
occurrences du texte de la variante par `<mark>`/`<strong>`. Insensible à la
casse, sur toutes les correspondances de l'extrait.

**Avantage** : ne touche PAS `detecter.py` ni le format `.etat.json` — réalisable
immédiatement, indépendamment des autres items. Identifié le 14/06/2026.

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
