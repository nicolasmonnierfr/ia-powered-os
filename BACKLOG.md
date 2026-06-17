# Backlog — IA-Powered-OS

Évolutions identifiées, **à traiter**. Chaque item est décrit avec assez de
contexte pour être repris sans rediscussion.

> **Cycle de vie** : ce fichier ne contient QUE ce qui reste à faire. Quand un
> item est réalisé, il est décrit dans [`CHANGELOG.md`](CHANGELOG.md) (sous la
> version concernée, avec son numéro d'origine) **et retiré d'ici**. Les numéros
> sont des identifiants stables — ne pas les renuméroter.

---

## Tagueur (`tools/transcription/tagger.html`)

### 1. Scinder un segment (diarisation ratée)
**Besoin** : la diarisation regroupe parfois plusieurs interlocuteurs dans un
seul segment (elle signale un seul locuteur à tort). Pouvoir **scinder** un
segment en deux pour ensuite taguer chaque moitié à un locuteur différent.

**À cadrer avant de coder** :
- Où s'effectue la scission ? (position de lecture audio courante ? clic dans
  le texte ? saisie d'un timecode ?)
- Comment répartir le texte entre les deux moitiés (le texte n'a pas de
  timecode par mot dans un .srt simple).
- Recalcule des `start`/`end` des deux nouveaux segments.

> Attention au vocabulaire : ici « scinder » (diviser en deux), à ne PAS
> confondre avec « couper » (touche C = marquer pour suppression à l'export).

### 3. Saut au changement de locuteur
**Besoin** : quand 20 segments consécutifs sont du même locuteur, pouvoir sauter
directement au **prochain segment où le locuteur change** (la « réponse »),
sans parcourir manuellement. Idéalement boutons précédent/suivant changement.

**Piste** : bouton(s) dans la barre de contrôle audio ; raccourci clavier
possible. Logique simple (chercher le prochain `i` où `speaker` diffère du
courant).

### 5. Couper le 1er segment doit retirer tout le début de l'audio
**Besoin** : quand on coupe le premier segment conservé, le plan de coupe
génère actuellement un `keep_interval` qui démarre au `start` de ce segment —
or ce `start` n'est pas forcément 0.0 (silence/bruit avant la 1re parole).
Résultat : le tout début de l'audio (avant le 1er segment) est conservé alors
qu'on voulait le supprimer.

**Comportement attendu** : si le 1er segment **conservé** est coupé/retiré, ou
plus généralement, le **tout premier `keep_interval`** devrait démarrer à 0.0
(englober le début de l'audio jusqu'au 1er segment réellement gardé) — ou
inversement, couper le 1er segment doit faire disparaître tout l'audio
antérieur à la 1re parole conservée.

**À cadrer avant de coder** :
- Symétrie en fin d'audio : si le **dernier** segment est coupé, faut-il aussi
  étendre le dernier `keep_interval` jusqu'à la fin réelle du fichier (queue
  d'audio après la dernière parole) ? Probablement oui, par cohérence.
- Définir la règle : le 1er `keep` commence à `0.0`, le dernier `keep` finit à
  la durée totale de l'audio — plutôt qu'aux bornes `start`/`end` des segments.
- Vérifier que ça reste cohérent avec le `.srt`/`.txt` exporté (les timecodes
  des sous-titres sont relatifs au montage : un début à 0.0 ne décale rien tant
  que les deux exports utilisent la même logique).

**Sévérité** : mineure, non bloquante. Identifié au test du 14/06/2026.

> Vocabulaire : ne concerne que la logique de génération des `keep_intervals`
> à l'export du plan de coupe (pas le réencodage de `couper_audio.py`, qui se
> contente d'appliquer fidèlement les intervalles reçus).

---

## Anonymisation — éditeur d'alias / détection

> Chantier cohérent à traiter ensemble : **#6 + #9 + #10** reposent sur la même
> évolution du format `.etat.json` (propagation des timecodes par occurrence).

### 2. Naviguer entre plusieurs extraits d'un même locuteur
**Besoin** : lors de l'identification d'un locuteur, l'extrait proposé est
parfois inaudible. Pouvoir écouter d'**autres** passages du même locuteur via
deux triangles ◄ ► (extrait précédent / suivant) pour l'identifier sûrement.

**À clarifier** : cela concerne-t-il
- le **tagueur** (écouter d'autres segments d'un même speaker pendant le
  tagging), ou
- la **réconciliation d'anonymisation** (éditeur d'alias / reconcilier.py,
  pour confirmer une identité avant pseudonymisation) ?
La formulation initiale dit « tagueur » mais parle de « réconciliation
post-fusion », d'où l'ambiguïté.

### 6. Propager les timecodes jusqu'à l'éditeur d'alias (réécoute + correction)
**Besoin** : pendant la validation des entités (éditeur d'alias), deux frictions
identifiées comme également pénalisantes :
1. **Réécouter** une occurrence dans son contexte audio (lever un doute sur une
   entité).
2. **Retrouver** vite un passage où le texte du transcript est fautif, pour le
   corriger.

**Constat d'architecture** (discuté le 14/06/2026) :
- La correction du **texte** reste dans le tagueur, qui est la **source de
  vérité unique** du transcript. L'éditeur d'alias ne doit PAS éditer le texte
  (sinon divergence entre le .srt et la version bricolée → perte de cohérence).
- La détection NER (Presidio/spaCy) tourne forcément en Python → fusionner
  tagueur + éditeur en un seul HTML ne supprimerait pas l'étape `detecter.py`.
  Décision : **garder les outils séparés**, ne pas fusionner.
- Les deux besoins se ramènent à **un seul chaînon manquant** : le `.etat.json`
  ne transporte pas les **timecodes** (`start`/`end`) de chaque occurrence. Or
  ils existent déjà dans le `.srt`. Une fois propagés, on peut : jouer l'audio
  (besoin 1) ET pointer « à corriger à HH:MM:SS dans le tagueur » (besoin 2).

**Sous-tâches** :
- `detecter.py` : ajouter, pour chaque occurrence de chaque candidat, son
  timecode (`start`/`end`) dans le `.etat.json`. Vérifier l'impact sur le
  schéma (SCHEMA.md) et sur l'éditeur (qui parse `exemples`).
- `editeur_alias.html` : charger l'audio + le `.srt`, afficher le timecode par
  occurrence, bouton ▶ (mini-lecteur) pour réécouter, et un repère de position
  pour retrouver le passage dans le tagueur.

**À cadrer avant de coder** :
- Format/portée des timecodes dans le `.etat.json` (par occurrence ? une par
  variante ? l'occurrence représentative ?).
- Comment l'éditeur accède à l'audio (chargement manuel du fichier vs chemin).
- Confirmer qu'on ne fait PAS d'édition de texte dans l'éditeur (juste un renvoi
  vers le tagueur), ou rediscuter si vraiment souhaité.

**Sévérité** : confort, non bloquant. Mais fort impact sur la vitesse de
validation. Identifié le 14/06/2026.

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
pas résolu automatiquement (cohérent avec « alerte à traiter à la main »). La
désambiguïsation effective se fait en amont dans le tagueur (rendre le texte
distinct : « Marc Durand » vs « Marc Lefèvre »).

**Sévérité** : importante pour la qualité d'anonymisation. Identifié le
14/06/2026.

### 10. Lister toutes les occurrences d'un terme + y accéder
**Besoin** : quand une ambiguïté est levée (item #9), pouvoir voir **toutes** les
occurrences du mot incriminé dans leur contexte, et y accéder rapidement.

**Constat** : aujourd'hui `detecter.py` ne conserve que **2 exemples max** par
candidat (ligne ~213 : `if (len(c["exemples"]) < 2)`), **sans timecode**.

**Sous-tâches** :
- `detecter.py` : lever la limite de 2 exemples (ou la rendre configurable) et
  attacher le **timecode** à chaque occurrence.
- Éditeur : afficher la liste complète des occurrences ; combiné aux timecodes
  (item #6), permettre la réécoute / le renvoi vers le tagueur.

**Dépendance** : repose sur la **même évolution du format `.etat.json`** que
l'item #6 (propagation des timecodes). **À traiter dans le même chantier que #6
et #9** (« enrichir la chaîne détection → éditeur »).

**Sévérité** : confort, mais clé pour traiter les alertes de l'item #9.
Identifié le 14/06/2026.

### 11. Surligner le terme en cours dans l'extrait d'illustration (quick win)
**Besoin** : dans l'éditeur d'alias, l'extrait de contexte affiché peut contenir
plusieurs noms ; on ne voit pas immédiatement lequel on est en train de
catégoriser. Mettre le terme **en gras / autre couleur** dans l'extrait.

**Piste** : côté éditeur uniquement — au rendu de l'extrait (`ex.textContent`),
encadrer les occurrences du texte de la variante par `<mark>`/`<strong>`.
Surlignage **insensible à la casse** et sur **toutes** les correspondances de
l'extrait.

**Avantage** : ne touche PAS `detecter.py` ni le format `.etat.json` — réalisable
immédiatement, indépendamment des autres items. Identifié le 14/06/2026.

---

## Industrialisation / automatisation

### 16. Serveur tagueur — support des Range requests (lecture audio)
**Besoin** : `serveur_tagueur.py` sert l'audio en bloc (`Accept-Ranges: none`).
Sur de gros fichiers, le *seek* dans `<audio controls>` peut être limité.
**Piste** : implémenter les requêtes HTTP `Range` (206 Partial Content) dans le
serveur. À valider d'abord sur un vrai entretien : peut-être inutile selon le
format. Identifié le 15/06/2026.
