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

### 13. BUG — le type des entités est perdu à l'export (tout devient PRODUIT)
**Symptôme** : dans `table_correspondance.json`, des entités identifiées comme
PERSONNE (badge correct dans l'éditeur) ressortent typées `PRODUIT`.

**Cause identifiée** (code lu le 14/06/2026) :
- L'éditeur **n'écrit jamais le type** dans le YAML. Sous `forcer:`, il n'écrit
  que le pseudo comme clé (`PERSONNE_1:`) ; l'attribut interne `g.type` (le badge
  bleu à l'écran) n'est pas exporté.
- `appliquer.py` **déduit** le type du **préfixe du pseudo** via
  `type_from_pseudo()` : `p.split("_")[0]`, et si ce préfixe n'est pas dans
  `TYPES = [PERSONNE, LIEU, ORG, PRODUIT, EMAIL, TEL]`, il renvoie `PRODUIT` par
  défaut.
- Donc un pseudo parlant (`CONSULTANT_1`, `SOCIETE_1`) → préfixe inconnu →
  typé `PRODUIT`, quel que soit le badge affiché dans l'éditeur.

**Lien avec #8** : même racine (le pseudo porte seul l'information). Tant que le
préfixe n'est pas un type reconnu, le type est faux.

**Impact réel** : le **remplacement reste correct** (le type ne sert qu'à
l'affichage/regroupement, pas au remplacement). Seule la métadonnée `type` de la
table est erronée. Mais cette métadonnée compte pour la lisibilité, le tri, et
un éventuel traitement par type.

**Correctif possible** (à trancher avec #8 et #14) :
- soit l'éditeur **écrit explicitement le type** dans le YAML (changement de
  format de l'`alias.yaml`),
- soit on impose que le préfixe du pseudo SOIT un type de `TYPES` (mais cela
  interdit les pseudos parlants comme `CONSULTANT_1`).

**Sévérité** : métadonnée erronée, non bloquante pour l'anonymisation.
Identifié le 14/06/2026.

---

## Architecture (structurant — à cadrer avant tout code)

### 14. ★ PRIORITAIRE — Refondre le modèle de persistance (alias.yaml + table.json)
**Problème** : deux fichiers se recoupent partiellement et créent des frictions
et des pertes d'information.

- `alias.yaml` : configuration **éditée à la main** (entrée). Contient les
  forçages (`forcer:`), les faux positifs (`ignorer:`), les locuteurs génériques,
  les réglages.
- `table_correspondance.json` : artefact **généré** par `appliquer.py` (sortie).
  Contient pseudo + `canonique` + `variantes` + `type` + `compteurs` + `client`.
  Sur-ensemble de ce qui a été remplacé (détection auto **+** forçages).

**Frictions constatées (14/06/2026)** :
1. **Redondance gênante** : la correspondance pseudo↔variantes existe dans les
   deux ; éditer l'un ne met pas l'autre à jour → divergence possible.
2. **« Ne pas éditer le JSON » est intenable en pratique** : quand le JSON
   contient des erreurs (cf. types faux, #13), regénérer coûte une passe
   complète (detecter → éditeur → appliquer) ET, tant que les bugs ne sont pas
   corrigés, rejoue les mêmes erreurs. Éditer le JSON à la main est alors plus
   simple. → La table doit être **éditable** sans tabou.
3. **Perte d'information inter-séances (le point le plus fort)** : les
   `ignorer:` (faux positifs : « Ancienneté », politesses, lieux communs) sont
   **réutilisables d'une séance à l'autre**, mais ils vivent dans le YAML, **ne
   sont pas** dans la table JSON (rien n'a été remplacé), et `--table` ne
   réinjecte que le JSON. → On re-trie les mêmes faux positifs à chaque
   transcript. La mémoire inter-séances est donc bancale : les pseudos se
   réutilisent, mais pas les décisions de tri.

**Pistes à évaluer (décision d'archi, non tranchée)** :
- **Piste A — Mémoire client unique** : un seul artefact réutilisable par client
  (pseudos + canoniques + faux positifs + génériques + types), éditable et
  versionnable. Le YAML par transcript ne porte que les forçages spécifiques et
  alimente cette mémoire.
- **Piste B — Deux fichiers mais cohérents** : la table JSON mémorise AUSSI les
  `ignorer:`/`generiques:` (même sans remplacement), et `--table` les réinjecte.
  On garde la séparation entrée/sortie sans perte d'info.
- **Piste C — Tout dans le YAML** : le YAML porte toute la mémoire (forçages +
  ignorer + génériques + table apprise) ; le JSON devient un export jetable.

**Impacts** : touche `detecter.py`, `appliquer.py`, `editeur_alias.html`,
`reconcilier.py`, le `SCHEMA.md`, ET la dé-anonymisation (#12). C'est le **format
d'échange central** du pipeline.

**Dépendances** : à arbitrer AVANT ou EN MÊME TEMPS que #8 et #13 (le sort du
« type » et des pseudos parlants dépend du format retenu). Conditionne aussi #12
(quelle source pour le canonique du retour).

**Décision actée le 14/06/2026** : la table JSON **peut** être éditée à la main
pour des corrections ponctuelles (types, canonique), en attendant cette refonte.
Ce n'est pas un fichier sacré — la précaution est de ne pas l'écraser par un
re-run involontaire.

---

## Fait

### 14 + 8 + 13 + 7 + 12 + 17. Refonte du modèle de persistance (16/06/2026)
Format de persistance unifié (**piste A2**) : un **artefact unique par client**
`memoire_client.json` (remplace `alias.yaml` + `table_correspondance.json`) +
un `config/ignorer_global.json` partagé (faux positifs universels). Format
**JSON**. Logique centralisée dans le nouveau module `tools/anonymisation/memoire.py`.

Résolu d'un bloc :
- **#14** (refonte persistance) : un seul fichier, éditable, mémorisant pseudos
  + canoniques + variantes + types + faux positifs (client ET global) +
  génériques. Les `ignorer`/`generiques` survivent désormais entre séances
  (friction #14.3 levée).
- **#8** (corruption pseudos non numérotés) : l'éditeur n'impose plus `_<chiffre>`
  ; pseudos parlants (`SOCIETE`, `CONSULTANT_1`) pleinement valides. Export via
  `JSON.stringify` (plus de générateur YAML bricolé).
- **#13** (type perdu → PRODUIT) : `type` est un **champ explicite** par entrée,
  écrit par l'éditeur, lu tel quel par `appliquer.py`.
- **#7** (génériques non exportés) : UI dédiée dans l'éditeur (bouton
  « + Locuteur générique » + section), inclus à l'export.
- **#17** (fusion alias existant + nouvelles détections) : l'éditeur charge la
  mémoire du périmètre PUIS fusionne les nouvelles détections (`mergeFromState`),
  sans écraser les regroupements existants.
- **#12** (dé-anonymisation) : nouveau script `desanonymiser.py` (mapping inverse
  pseudo → canonique, pseudos longs d'abord, formats .txt/.md/.srt/.docx).

Outils touchés : `memoire.py` (nouveau), `migrer.py` (nouveau, conversion
ancien→nouveau), `desanonymiser.py` (nouveau), `detecter.py`, `appliquer.py`,
`reconcilier.py`, `editeur_alias.html`, `serveur_editeur.py`, `anonymiser.ps1`,
`_commun.ps1`, `SCHEMA.md`. Rétrocompatibilité : `--alias`/`--table` encore
acceptés (migration à la volée) ; `migrer.py` convertit définitivement.

> ⚠️ Reste à valider sous Windows : les `.ps1` (syntaxe non vérifiable hors
> PowerShell) et l'éditeur en mode serveur (Chrome + serveur_editeur.py).


### 4. Scripts wrapper + commande `ia` (15/06/2026)
Industrialisation du pipeline réalisée. Commande unique `ia` (dispatcher +
fonction de profil PowerShell), wrappers `transcrire` / `taguer` / `couper` /
`anonymiser` dans `scripts/`. Arborescence constante par entretien
(`1_transcription/`, `2_coupe/`, `3_anonymisation/`). alias + table partagés au
niveau d'un « périmètre » trouvé par **recherche ascendante**. Les wrappers
ciblent le `python.exe` du venv en absolu (plus besoin d'activer le venv ;
`ia setenv` le fait à la demande). Voir `scripts/GUIDE-USAGE.md`.

Évolutions de fond apportées au passage :
- `transcribe_robuste.py` : option `--outdir` (rétrocompatible).
- `tagger.html` : mode serveur (chargement auto audio + srt, export groupé
  cohérent vers `2_coupe/`, heartbeat) + repli File System Access API / fichier.
- `editeur_alias.html` : mode serveur (chargement auto etat/alias, écriture de
  l'alias au périmètre, heartbeat) + repli fichier.
- Nouveaux : `serveur_tagueur.py`, `serveur_editeur.py` (serveurs locaux
  127.0.0.1, arrêt par heartbeat à la fermeture de l'onglet).

---

## Industrialisation / automatisation (suite)

### 15. `entretien.json` — fichier d'état par entretien
**Besoin** : un petit JSON à la racine de chaque entretien décrivant l'état
d'avancement (audio, étapes faites/à faire, dates), lu et mis à jour par chaque
outil. Sert de mémoire de progression et de socle à une future orchestration
(Claude Code). Discuté le 15/06/2026, reporté au backlog pour un chantier dédié.

**À cadrer** : schéma (comme `SCHEMA.md`), qui écrit quoi et quand, intégration
dans chaque wrapper + les deux serveurs, affichage de l'état dans les éditeurs.

### 16. Serveur tagueur — support des Range requests (lecture audio)
**Besoin** : `serveur_tagueur.py` sert l'audio en bloc (`Accept-Ranges: none`).
Sur de gros fichiers, le *seek* dans `<audio controls>` peut être limité.
**Piste** : implémenter les requêtes HTTP `Range` (206 Partial Content) dans le
serveur. À valider d'abord sur un vrai entretien : peut-être inutile selon le
format. Identifié le 15/06/2026.

### 17. Éditeur d'alias — fusion alias existant + nouvelles détections
**Constat** : en mode serveur, si un `alias.yaml` existe déjà au périmètre, on
le charge **sans** y fusionner les entités nouvellement détectées dans le
nouvel entretien (l'éditeur ne sait pas fusionner ; il charge l'un OU l'autre).
**Conséquence** : pour un nouvel entretien sur un périmètre existant, les
nouvelles entités ne remontent pas automatiquement dans l'éditeur.
**Piste** : fusionner `loadFromYaml` (alias existant) et `loadFromState`
(nouvelles détections) sans doublon. Lié à l'item #14 (modèle de persistance).
Identifié le 15/06/2026.

---


