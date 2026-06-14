# Backlog — IA-Powered-OS

Évolutions identifiées, à traiter plus tard. Chaque item est décrit avec assez
de contexte pour être repris sans rediscussion. Quand on en traite un, le
déplacer en « Fait » avec la date.

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

## Réconciliation — à clarifier : tagueur OU anonymisation ?

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

### 7. L'éditeur d'alias n'exporte pas `locuteurs_generiques`
**Besoin** : l'éditeur HTML lit la section `locuteurs_generiques` d'un
`alias.yaml` existant, mais son tableau interne `generiques` n'est jamais
alimenté par l'interface, et l'export réécrit donc toujours une liste vide
(`locuteurs_generiques: []`). Conséquence : les rôles génériques à conserver
(« Interviewer », « Candidat ») doivent être ajoutés à la main dans le YAML.

**Piste** : ajouter dans l'éditeur une zone pour déclarer/éditer les locuteurs
génériques, et les inclure à l'export. Vérifier la cohérence avec `appliquer.py`
(comment il traite cette liste).

**Sévérité** : mineure. Identifié le 14/06/2026.

### 8. BUG — l'export YAML corrompt silencieusement les pseudos non numérotés
**Symptôme** : certains pseudos s'affichent correctement dans l'éditeur mais ne
sont pas correctement exportés ; un avertissement signale des pseudos
« incomplets » (`_?`/`_X`) qu'on ne voit pas à l'écran.

**Cause identifiée** (code lu le 14/06/2026) :
- Validation (ligne ~427) : `groups.filter(g => !/_\d+$/.test(g.pseudo))` —
  un pseudo est jugé invalide s'il ne finit PAS par `_<chiffre>`.
- Écriture (ligne ~413) : `g.pseudo && /_\d+$/.test(g.pseudo) ? g.pseudo :
  ${g.type}_X` — si le pseudo ne finit pas par `_<chiffre>`, il est **réécrit
  silencieusement en `TYPE_X`**. Plusieurs pseudos non conformes s'écrasent
  alors sur le même `TYPE_X`.

**Pattern des cas perdus** : tout pseudo ne se terminant pas par `_<nombre>` —
ex. `SOCIETE`, `CONSULTANT`, `PRODUIT_A`, `PROJET_ALPHA`, `PERSONNE_1b`.

**Gravité** : SÉRIEUSE — perte silencieuse de configuration d'anonymisation,
sans indiquer quel pseudo est fautif. Contournement actuel : forcer un suffixe
`_<chiffre>` (ex. `SOCIETE_1`) même pour les singletons.

**Constat de conception associé** : la contrainte `_<chiffre>` est purement
artificielle, propre à l'éditeur. `appliquer.py` accepte n'importe quel pseudo
tel quel (la regex `([A-ZÉ]+)_(\d+)$` n'y sert qu'à incrémenter les compteurs,
pas à valider). Donc `SOCIETE` / `CONSULTANT` sans numéro fonctionneraient
parfaitement à l'application — c'est l'éditeur qui bloque à tort.

**Correctif** :
- Écriture : ne plus jamais réécrire en `TYPE_X` ; écrire le pseudo tel quel.
- Validation : remplacer `/_\d+$/` par un test « pseudo non vide / format
  raisonnable » et **lister nommément** les pseudos fautifs.
- Autoriser les pseudos sans suffixe numérique (singletons : `SOCIETE`,
  `CONSULTANT`). Noter que `type_from_pseudo` les typera `PRODUIT` par défaut
  (sans incidence sur le remplacement).

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

### 12. Dé-anonymisation / repersonnalisation des rapports
**Besoin** : les rapports d'analyse produits à partir du transcript anonymisé
contiennent les pseudos (`PERSONNE_1`…). Pour les livrer au dirigeant, il faut
faire le **chemin inverse** : réinjecter les vrais noms.

**Faisabilité** : simple et plus directe que l'anonymisation. La
`table_correspondance.json` contient déjà, par entrée : `pseudo`, `canonique`
(variante la plus longue, ex. « Jean Dupont ») et `variantes`. Le retour est un
mapping **`pseudo → canonique`** sans ambiguïté (chaque pseudo est unique → pas
de collision, contrairement à l'aller).

**Forme pressentie** : nouveau script symétrique d'`appliquer.py`, p. ex.
`desanonymiser.py` :
`python desanonymiser.py rapport_avec_alias.<ext> --table table_correspondance.json`
→ `rapport_REPERSONNALISE.<ext>`.

**À cadrer avant de coder** :
- **Cible du remplacement** : toujours le `canonique` (le plus long), ou rendre
  configurable (forme courte/formelle selon le rapport) ?
- **Robustesse du match** : remplacer en **mot entier** (insensible à la casse)
  pour éviter les faux positifs ; **trier par longueur décroissante** pour que
  `PERSONNE_10` ne soit pas cassé par `PERSONNE_1` (réflexe déjà présent dans
  `appliquer.py`).
- **Format de sortie** : `.txt`/`.md` (trivial) vs `.docx`/`.pdf` (traverser la
  mise en forme sans la casser — s'appuyer sur les skills docx/pdf). Déterminer
  le format réel des rapports avant de coder.

**Sévérité** : fonctionnalité manquante (complète le pipeline). Identifié le
14/06/2026.

> ⚠️ SÉCURITÉ : le fichier dé-anonymisé **contient à nouveau les vraies données**.
> Il ne doit JAMAIS être renvoyé vers une IA externe. Le script doit le rappeler
> et nommer la sortie de façon explicite (`_REPERSONNALISE`).

---

## Industrialisation / automatisation

### 4. Scripts wrapper pour éviter les longues lignes de commande
**Besoin** : aujourd'hui chaque étape demande une commande longue et précise
(chemins, `--alias`, `--table`, `--client`…). C'est source d'erreurs et pénible
à taper. Industrialiser le process avec des scripts qui enchaînent et
simplifient.

**Pistes à cadrer** :
- **Scripts d'entrée courts** (un par usage) dans `scripts/` (dossier déjà
  prévu, vide) ou `bootstrap/`. Sous Windows : `.ps1` ou `.bat`. Ex :
  - `transcrire.ps1 <audio>` → lance `transcribe.py` avec les bons réglages.
  - `couper.ps1 <plan>` → lance `couper_audio.py`.
  - `anonymiser.ps1 <transcript> <client>` → enchaîne `detecter.py` →
    (pause pour validation éditeur/CLI) → `appliquer.py`.
- **Pipeline anonymisation semi-automatique** : un seul script qui fait
  détection, ouvre l'éditeur HTML (ou lance la CLI), attend le `alias.yaml`,
  puis applique. Gérer le point d'arrêt « validation humaine » proprement.
- **Conventions de dossiers** : définir où vivent audios / transcripts / tables
  par client (ex. `data/<client>/`) pour que les scripts déduisent les chemins
  et réutilisent automatiquement la `table_correspondance.json` du client.
- **Découverte automatique** : un script qui détecte le dernier `.srt` / le
  `plan_de_coupe.json` dans le dossier courant pour éviter de taper les noms.

**À décider** : jusqu'où automatiser sans masquer ce qui se passe (garder des
messages clairs et des points de contrôle, surtout pour l'anonymisation où une
erreur = fuite de données).

---

## Fait
*(rien pour l'instant — y déplacer les items traités, avec la date)*
