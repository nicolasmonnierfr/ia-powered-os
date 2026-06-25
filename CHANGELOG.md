# Changelog — IA-Powered-OS

Évolutions notables du projet. Format inspiré de [Keep a Changelog](https://keepachangelog.com),
versionnage [SemVer](https://semver.org).

Ce qui reste **à faire** vit dans [`BACKLOG.md`](BACKLOG.md). Une fois un item
réalisé, il est décrit ici (avec son numéro de backlog d'origine entre
parenthèses) et retiré du backlog.

---

## [1.21.0] — 2026-06-25

### Ajouté
- **`ia synthese lancer` — synthèse multi-entretiens via l'API Claude.** Dernier
  maillon de l'outil `tools/synthese` : à partir du manifeste vérifié, appelle
  l'**API Claude** (`claude-opus-4-8` par défaut, thinking adaptatif, en
  streaming) sur le corpus anonymisé, puis écrit **deux versions** dans
  `4_synthese/` + un journal `synthese.run.json` (modèle, entrées, tokens) :
  - `synthese.md` — **anonyme** (pseudonymes), trace de ce qui a été envoyé ;
  - `<sortie>_REPERSONNALISE.md` — **le livrable** (vrais noms réinjectés),
    produit **automatiquement** (la repersonnalisation est intégrée à `lancer` —
    la version anonyme n'ayant pas d'usage propre, via `desanonymiser`). Option
    `-Court` pour les prénoms. **Toute la boucle d'analyse revient en interne**,
    plus de copier-coller dans un chat externe.
  - **Sortie au niveau de la mission, nommage configurable.** Les fichiers ne
    vont plus dans un sous-dossier `4_synthese/` (les `1_/2_/3_` n'avaient de sens
    qu'au niveau *entretien* ; ici on est au niveau *mission*) : ils sont écrits à
    côté du manifeste. Leur **nom de base** est le champ `sortie` du manifeste
    (défaut `synthese`), surchargé par `-Out` : `<sortie>.md`,
    `<sortie>_REPERSONNALISE.md`, `<sortie>.run.json`.
  - **`ia synthese creer` — créateur interactif de configuration.** Scanne le
    périmètre (récursif) et construit `synthese.manifeste.json` par questions
    (titre, nom de sortie, et par entretien : inclure / rôle / interviewé, en
    listant les pseudonymes connus de la mémoire). `ia synthese init` reste le
    modèle non interactif.
  - **Garde-fou rejoué en barrière.** `lancer` ré-exécute le filet anti-fuite
    (`garde_fou.verifier`) avant tout envoi : un vrai nom résiduel, une mémoire
    absente ou une source manquante **bloque** l'appel (code 2) — impossible à
    court-circuiter.
  - **`-DryRun`** assemble le prompt et l'écrit en local (`synthese.prompt.txt`)
    **sans** appeler l'API. Options `-Modele`, `-MaxTokens`, `-Gabarit`, `-Out`.
  - **Gabarit standard** « diagnostic transfo IA » (`gabarits/diagnostic_transfo_ia.md`,
    surchargeable) : résumé exécutif, constats transverses, douleurs, opportunités
    IA, maturité par dimension, divergences, recommandations.
  - **Clé API** : `ANTHROPIC_API_KEY` dans `config/.env` (ajoutée à `.env.example`) ;
    `anthropic` ajouté à `requirements.txt`.

## [1.20.0] — 2026-06-25

### Ajouté
- **Nouvel outil `tools/synthese` — synthèse multi-entretiens (incrément 1 :
  fondations, sans appel IA).** Objectif à terme : produire une synthèse croisée
  de plusieurs entretiens **anonymisés** via l'API Claude, livrable au client via
  `ia repersonnaliser`. Ce premier incrément pose les deux invariants de sûreté
  **avant** toute ligne d'appel API :
  - **Périmètre par manifeste (`ia synthese init`).** La synthèse porte sur une
    **sélection** explicite d'entretiens (pas un dossier entier), décrite dans
    `synthese.manifeste.json`. `init` le pré-génère en scannant le périmètre
    (récursif, moteur de l'orchestrateur réutilisé) ; on édite ensuite
    `inclure` / `role` / `interviewe`. Chaque entretien reçoit un **label neutre**
    (`E1`, `E2`…) — c'est lui qui part, **jamais le nom de fichier** (qui porte
    souvent un vrai nom).
  - **Garde-fou anti-fuite (`ia synthese verifier`).** Assemble le payload exact
    qui partirait (uniquement `id` / `role` / `interviewe` / **contenu
    anonymisé** — aucun chemin) et le confronte à la `memoire_client.json`
    (LOCALE) : il **rejoue le matcher de l'anonymiseur** (frontières `\b`, casse
    ignorée) sur le texte déjà anonymisé ; toute occurrence d'un vrai nom
    (`variantes`/`canonique`, nom du client) **bloque l'envoi** (code 2). Couvre
    à la fois les noms de fichiers (exclus par construction) et les **ratés de
    contenu**. Le rapport de fuite indique le **fichier source** concerné (et pas
    seulement le label `E1`/`E2`) — `lancer` aussi, pour ne pas rouvrir le
    manifeste. Option `-Dump` pour écrire le payload (ce qui partirait) en local.
  - Wrapper `scripts/synthese.ps1` + intégration au dispatcher (`ia synthese`).
    L'appel API (`ia synthese lancer`) viendra dans un incrément suivant.

## [1.19.0] — 2026-06-25

### Ajouté
- **Scan récursif des périmètres (entretiens imbriqués).** L'orchestrateur ne
  détectait les entretiens que dans les **sous-dossiers immédiats** d'un périmètre
  (`etat.py` / `sync.py`). Il les cherche désormais **récursivement**, jusqu'à
  `PROFONDEUR_MAX = 4` niveaux sous le périmètre inscrit (1 = enfants directs), ce
  qui permet d'organiser librement les entretiens en sous-dossiers de regroupement
  (par client, vague, thème…). Un dossier est un entretien **dès qu'il contient un
  audio** ; on **ne descend alors plus dedans** (garde-fou : sinon un
  `2_coupe\..._coupe.m4a` serait pris pour un nouvel entretien), et les dossiers
  techniques (pipeline, `.chunks`, `.git`, `__pycache__`, `.venv`…) sont ignorés.
  Les entretiens imbriqués s'affichent avec leur **chemin relatif** au périmètre
  (`GroupeA/ent_x`) pour lever toute ambiguïté de noms entre sous-arbres.
  `tableau`, `orchestrer` et `veille` en bénéficient (logique de scan partagée).

## [1.18.0] — 2026-06-25

### Ajouté
- **Registre de répertoires surveillés par la tâche planifiée (`ia veille`).**
  Jusqu'ici la tâche planifiée ciblait **un seul** périmètre, **gravé en dur**
  dans son action à l'installation (`-Perimetre`). Impossible d'en changer sans
  réinstaller, ni d'en surveiller plusieurs. Désormais les deux tâches
  (« Orchestrateur » et « Etat ») lisent à chaque tick un **registre local**,
  `config\perimetres.json` (gitignoré : chemins de missions), et orchestrent
  **chaque** répertoire inscrit. Trois nouvelles commandes :
  - `ia veille -Inscrire <dossier>` — ajoute un répertoire ;
  - `ia veille -Desinscrire <dossier>` — le retire ;
  - `ia veille -Lister` — affiche les répertoires inscrits (signale d'un `!` ceux
    devenus introuvables). `ia veille -Statut` les affiche aussi.
- **Activation / désactivation automatiques (la surveillance suit le registre).**
  Invariant : les tâches planifiées sont actives **ssi** au moins un répertoire est
  inscrit. Inscrire dans un registre **vide** **installe** les deux tâches ;
  désinscrire le **dernier** répertoire les **désinstalle**. Plus besoin de gérer
  `-Installer` / `-Desinstaller` à la main au quotidien (ils restent disponibles
  comme override).
- **Rétrocompatibilité / migration.** `ia veille -Installer [dossier]` réinstalle
  les tâches en **mode registre** (plus de chemin figé) et inscrit le dossier
  éventuellement passé en argument. Les lanceurs `_tache.ps1` / `_etat_tache.ps1`
  acceptent encore un `-Perimetre` explicite (override d'un run ad hoc) mais lisent
  le registre par défaut. Chaque tâche scanne les périmètres **l'un après
  l'autre**, le verrou de transcription garantissant une seule transcription à la
  fois tous périmètres confondus.

## [1.17.1] — 2026-06-25

### Corrigé (documentation)
- **Passe de cohérence doc ↔ code.** La documentation avait pris du retard sur le
  code. Corrigé :
  - **`DEMARRAGE-RAPIDE.md` — mauvaise licence pyannote.** La procédure faisait
    accepter `pyannote/speaker-diarization-3.1` ; or whisperx (3.8.x) utilise
    `pyannote/speaker-diarization-community-1` (cf. `whisperx/diarize.py`). Un
    nouvel utilisateur tombait sur une **erreur 403** à la diarisation. Aligné sur
    le modèle réellement utilisé.
  - **Étape `ia identifier` rétablie dans le pipeline documenté.** Le
    `GUIDE-USAGE.md` (§4 + aide-mémoire + arborescence) et le `README.md`
    présentaient `ia analyser` comme faisant la détection NER, alors que celle-ci
    est portée par **`ia identifier`** (étape distincte, automatisable) et que
    `ia analyser` (validation humaine) **exige** que `identifier` ait tourné. En
    flux manuel, suivre l'ancienne doc menait à une erreur. La séparation
    identifier/analyser est désormais documentée partout.
  - **`README.md` : commandes `ia` complétées** (`ia identifier`, `ia reconcilier`
    étaient absents de la liste).
  - **`tools/transcription/README.md` recadré sur le flux `ia`.** Le document
    décrivait l'ancien usage autonome comme primaire (sorties `data/transcriptions\`,
    double-clic sur `tagger.html`, « chargement manuel à chaque session »), ce qui
    contredit le flux projet (`ia transcrire`/`ia taguer` : auto-chargement, sorties
    `1_transcription\`/`2_coupe\`). Le flux `ia` est désormais primaire ; l'usage
    autonome est conservé en repli, explicitement étiqueté.
  - **`tools/anonymisation/README.md` : table de correspondance `ia` ↔ scripts**
    ajoutée, et **levée d'ambiguïté** sur `reconcilier` (deux scripts distincts :
    `ia reconcilier` = locuteurs/empreinte vocale, ≠ `anonymisation/reconcilier.py`).
  - **`config/.env.example` : `EMBEDDING_MODEL` documenté** (référencé par le README
    de transcription mais absent du modèle de config).

## [1.17.0] — 2026-06-18

### Ajouté
- **Éditeur d'alias : forme réelle (canonique) éditable par entrée.** La forme
  injectée à la **repersonnalisation** (le « vrai nom » qui remplace le pseudo)
  était systématiquement la **variante la plus longue** — souvent une mauvaise
  transcription (ex. `Societe_1` → « cliquite » au lieu de « ClikIt », ou un
  canonique placeholder/`Locuteur 2`). Chaque groupe a désormais un champ
  **« → réel »** : tu y saisis l'orthographe correcte, utilisée telle quelle à
  l'export de la mémoire puis par `ia repersonnaliser`. Vide = comportement par
  défaut (variante la plus longue, affichée en placeholder). Corrige aussi
  `buildMemoire` (qui figeait la plus longue) — sans toucher au reste de la mémoire.

## [1.16.0] — 2026-06-18

### Ajouté
- **`ia repersonnaliser -Memoire <chemin>` : cibler une mémoire explicite.**
  Jusqu'ici la mémoire (`memoire_client.json`) était toujours résolue par
  recherche **ascendante** depuis le répertoire courant — impossible de
  repersonnaliser un rapport situé **hors de l'arborescence du périmètre**.
  Le nouveau paramètre `-Memoire` court-circuite cette recherche et pointe une
  mémoire donnée (validée : erreur propre si le fichier n'existe pas) ; sans lui,
  le comportement reste inchangé. Le tube `desanonymiser.py` acceptait déjà
  `--memoire` : l'option n'est qu'exposée au niveau du wrapper (extension de #12).
- En complément, `repersonnaliser` ne crée plus de force le dossier
  `3_anonymisation\` dans le répertoire courant (il n'y écrit rien) — évite un
  dossier parasite quand on lance la commande hors d'un entretien.

## [1.15.0] — 2026-06-18

### Ajouté
- **Alerte « prénom partagé » basée sur la mémoire client.** Un même prénom peut
  désigner plusieurs personnes (ex. deux « Jean »), que la mémoire globale ne sait
  pas distinguer toute seule. `detecter.py` signale désormais tout candidat
  PERSONNE dont l'ensemble des tokens est inclus dans les variantes d'**au moins
  deux entrées distinctes** de la mémoire (« Jean » matche « Jean Dupont » ET
  « Jean Martin », mais « Jean Dupont » non) : champ `ambigu_memoire` dans le
  `.etat.json` + alerte console. L'éditeur d'alias affiche un badge **« ⚠ prénom
  partagé »** (avec les personnes possibles) sur la variante et un compteur dans
  les stats. La **résolution reste humaine** : préciser qui est visé en ajoutant
  une initiale (ex. « Jean R. ») — divergence assumée vs l'audio — via « ✎ corriger »
  (étiquette du locuteur et/ou mentions du corps), puis « 🔄 Relancer
  l'identification ». L'outil ne tranche pas (il ne peut pas deviner quel Jean).

## [1.14.2] — 2026-06-18

### Corrigé
- **`ia repersonnaliser` (desanonymiser.py) sortait en erreur** sur le `print`
  final « ⚠ » quand la console est en cp1252 (`UnicodeEncodeError`) — alors que le
  fichier `_REPERSONNALISE` était bel et bien produit : la commande le signalait
  comme un échec. stdout/stderr sont désormais forcés en UTF-8 (même correctif que
  `appliquer.py`).
- **Repersonnalisation : ne plus réinjecter d'étiquette technique.** Un locuteur
  jamais nommé pouvait avoir pour canonique « NON_AFFECTE » ou « Locuteur N » ;
  ces placeholders étaient réintroduits tels quels dans le livrable. `desanonymiser`
  (et le calcul du canonique dans `appliquer.py`) les ignorent désormais et
  reprennent une vraie variante ; à défaut, le **pseudo** est conservé (signal
  visible qu'un nom reste à compléter dans la mémoire, plutôt qu'un faux nom).

## [1.14.1] — 2026-06-18

### Modifié
- **Tagueur & éditeur d'alias : en-tête épurée en mode projet.** Comme on travaille
  désormais toujours par projet (lancement via `ia taguer` / `ia analyser`),
  l'en-tête ne garde que **le nom de l'audio** (`🎧 <audio>`). Sont masqués : le
  titre de l'outil, les boutons « Ouvrir / Changer le dossier », les champs de
  chargement manuel (audio + `.srt` / `.etat.json` / mémoire) et le statut de
  chargement verbeux. L'identité de l'outil passe dans le **titre de l'onglet**
  (`Tagueur — <audio>` / `Éditeur d'alias — <audio>`). Le titre reste affiché en
  repli si aucun audio n'est détecté (et en mode fichier autonome).

## [1.14.0] — 2026-06-18

### Modifié
- **Tableau d'avancement (`ia tableau` + `ETAT.md`) : « Identification » et
  « Analyse » dissociées en deux colonnes.** L'identification (détection NER,
  automatique — faite dès qu'un `.etat.json` existe) et l'analyse (validation
  humaine — faite quand la mémoire est exportée) étaient fondues dans une seule
  colonne « Analyse » (`~~` détecté / `OK` validé). Elles ont désormais leur
  propre colonne **Identif.** et **Analyse** (chacune `OK`/`--`), alignées sur la
  vue détaillée de `ia etat`. Le JSON expose deux nouveaux champs
  `identification` et `validation` (le champ `analyse` est conservé).

## [1.13.0] — 2026-06-18

### Ajouté
- **Anonymisation : sortie `.txt` lisible en plus du `.srt`** (`appliquer.py`). En
  plus de `<nom>_anonymise.srt`, la passe produit `<nom>_anonymise.txt` : le
  transcript **regroupé par locuteur, sans indices ni timecodes** — bien plus
  facile à analyser pour une IA. Dérivé du `.srt` anonymisé (mêmes contenu et
  remplacements). Produit quand l'entrée est un `.srt`.

### Corrigé / robustesse
- **`appliquer.py` : crash possible sur un `print` accentué/emoji** (« ⚠ ») quand
  la console est en cp1252 (`UnicodeEncodeError`) — purement cosmétique mais qui
  faisait sortir le script en erreur. stdout/stderr sont désormais forcés en UTF-8.

## [1.12.0] — 2026-06-18

### Ajouté
- **Éditeur d'alias (`ia analyser`) — bouton « 🔄 Relancer l'identification »** :
  après une correction de texte (via « ✎ corriger » → tagueur), l'éditeur ne
  reflétait pas la modification (extraits figés, nouvel alias non détecté).
  Nouveau bouton **manuel** (jamais automatique) : relance `detecter.py` sur le
  transcript corrigé (route serveur `POST /api/reidentifier`), réécrit le
  `.etat.json` et **recharge l'éditeur** (extraits à jour + tout nouvel alias).
  Réécrire l'état efface la validation → il faut ré-exporter la mémoire pour
  re-valider (cohérent : le transcript a changé).

### Corrigé / robustesse
- **Sessions d'édition tuées en arrière-plan** : le délai de grâce du heartbeat
  des serveurs locaux (tagueur + éditeur d'alias) passe de **15 s à 60 s**, et
  l'éditeur pingue dès que l'onglet redevient visible. Pendant une correction (le
  tagueur s'ouvre dans un autre onglet, l'éditeur passe en arrière-plan et le
  navigateur ralentit ses timers), le serveur de l'éditeur pouvait s'arrêter
  (« Aucun ping depuis 15 s ») → au retour, export/validation impossibles et
  travail perdu.

## [1.11.0] — 2026-06-18

### Ajouté
- **`edition.json` = LE document de travail (source de vérité unique)** : principe
  posé explicitement. Le tagueur édite toujours la timeline ORIGINALE (tous les
  segments, parties cachées, noms, texte) ; `plan_de_coupe.json`, `_coupe.srt`,
  `_coupe.txt` et l'audio coupé en sont des **sorties régénérées** à chaque export,
  jamais éditées à la main (la vue Finalisée reste en lecture seule).
- **Reconstruction automatique du document de travail (entretiens legacy)** :
  nouveau `tools/transcription/reconstruire_edition.py`. Les entretiens traités
  avant l'introduction de `edition.json` n'avaient que les sorties dérivées ;
  `serveur_tagueur.py` reconstitue désormais `2_coupe/<stem>.edition.json` au
  démarrage s'il manque, à partir du `.srt` brut (1_transcription), du
  `plan_de_coupe.json` et du `.srt` coupé : segments conservés **dé-recalés** vers
  la timeline originale (vrais noms + texte corrigé), segments cachés restaurés
  depuis le brut (`cut=true`). Idempotent, non bloquant.

### Corrigé
- **`ia analyser` → « ✎ corriger » : re-saisie des noms + perte du plan de coupe**.
  Depuis la vue Édition par défaut (v1.10.0), « corriger » rouvrait le tagueur sur
  le `.srt` brut (étiquettes locales) quand aucun `edition.json` n'existait → noms
  à re-saisir, et un ré-export aurait **écrasé tout le montage** (le brut n'a ni
  noms ni segments cachés). Avec la reconstruction ci-dessus, l'Édition reprend le
  document de travail complet (noms + parties cachées) — plus de re-saisie, plan
  réellement modifiable. (Rappel du flux : corriger → Édition → ré-exporter →
  `ia couper` régénère l'audio → `ia identifier` rafraîchit l'anonymisation.)

## [1.10.1] — 2026-06-18

### Corrigé
- **Éditeur d'alias (`ia analyser`) : toute la mémoire client s'affichait** au lieu
  des seules entités du transcript courant. `detecter.py` ré-expose les variantes
  d'alias de `memoire_client.json` en candidats (cohérence inter-entretiens), mais
  l'éditeur (`mergeFromState`) marquait « présent » **tout** candidat correspondant
  à une variante mémoire, sans vérifier l'occurrence — neutralisant le masquage
  prévu (`isHidden`) des entrées absentes. Résultat : les noms d'**autres**
  entretiens du même client (à 0 occurrence ici) apparaissaient. Désormais une
  variante mémoire n'est marquée présente (donc affichée) que si elle apparaît
  réellement dans **ce** transcript ; les groupes mixtes gardent l'indicateur
  « +N hors fichier ». En complément, `detecter.py` ne ré-expose plus en candidat
  une variante d'alias absente du transcript (0 occurrence) — état plus propre.
  Sans impact sur le livrable anonymisé (une entrée à 0 occurrence ne remplaçait
  rien). S'applique aux états déjà générés (pas besoin de relancer `ia identifier`).

## [1.10.0] — 2026-06-18

### Ajouté
- **Tagueur — deux versions à la réouverture (édition / finalisée)** : un bouton
  **✏️ Édition / 🎬 Finalisée** bascule, sans relancer, entre :
  - **Édition** (défaut) : audio **non coupé** + transcript **avec les parties
    cachées** (état d'édition complet) — pour reprendre le tagging, **dé-cacher**
    et réajuster le plan de coupe, **sans décalage** ;
  - **Finalisée** : audio **coupé** + `.srt` **recalé** — relecture du livrable
    (disponible une fois `ia couper` passé, l'audio coupé existant et à jour).
- **État d'édition persistant** : l'export du tagueur écrit désormais aussi
  `2_coupe/<stem>.edition.json` (tous les segments avec `cut`/`edited`/locuteur/
  texte et les noms, sur la timeline originale). La réouverture en mode Édition le
  recharge → le travail de tagging (y compris les parties cachées) survit à la
  fermeture, au lieu de repartir du transcript brut. (Distinct du `.etat.json`
  d'anonymisation, qui vit dans `3_anonymisation/`.)
- Serveur du tagueur (`serveur_tagueur.py`) : routes paramétrées par vue
  (`/api/manifest|audio|srt?vue=`) + nouvelle route `/api/etat`. Le manifest
  expose la vue courante et la disponibilité de chaque vue.

### Corrigé
- **Décalage SRT/audio à la réouverture du tagueur après un plan de coupe** : le
  serveur servait le `.srt` **coupé** (timecodes recalés) avec l'audio **non
  coupé** quand l'audio coupé manquait (export fait, `ia couper` pas encore lancé)
  ou était périmé — le tagueur calant la lecture sur les timecodes du `.srt`, tout
  était décalé. La sélection est désormais **appariée par timeline** : jamais un
  `.srt` coupé contre l'audio non coupé.

## [1.9.1] — 2026-06-18

### Corrigé
- **Tâches planifiées cassées après une mise à jour de PowerShell** : `veille.ps1`
  gravait le chemin **versionné** de pwsh (`...\WindowsApps\Microsoft.PowerShell_7.6.2.0_...\pwsh.exe`).
  Quand PowerShell se met à jour (Store/MSIX), ce dossier disparaît et `wscript`
  ne trouve plus l'exécutable → fenêtre d'erreur « chemin d'accès introuvable »
  (`0x80070003`) à chaque tick, transcription et état figés. `Get-PsExe` utilise
  désormais en priorité l'**alias d'exécution stable**
  `%LOCALAPPDATA%\Microsoft\WindowsApps\pwsh.exe` (indépendant de la version),
  avec repli sur `(Get-Command pwsh).Source` puis `powershell`. Réinstaller les
  tâches (`.\veille.ps1 <perimetre> -Installer`) pour appliquer le correctif.

## [1.9.0] — 2026-06-17

### Ajouté
- **Réconciliation automatique des locuteurs entre tronçons (empreinte vocale)** :
  nouveau `tools/transcription/reconcilier.py`. La diarisation tournant par
  tronçon produit des étiquettes locales sans lien (`T1-A` ≠ `T2-A`), ce qui
  imposait un recollage **100 % manuel** (1re étape du tagueur). Le script extrait
  une **empreinte vocale** par étiquette locale depuis les tronçons WAV
  (`data/.chunks/`), regroupe les voix identiques (clustering agglomératif sur
  distance cosinus, clusters ordonnés par 1re prise de parole) et écrit une
  suggestion `1_transcription/<nom>.reconcile.json` (mapping + **confiance** par
  étiquette). Modèle par défaut `speechbrain/spkrec-ecapa-voxceleb` (repli
  `pyannote/embedding`, surchargeable via `EMBEDDING_MODEL`).
- **Tagueur — panneau de réconciliation pré-rempli** : `serveur_tagueur.py`
  expose la suggestion dans `/api/manifest` (uniquement pour le transcript brut) ;
  `tagger.html` amorce le mapping, affiche un **bandeau récapitulatif** et un
  **badge de confiance** par étiquette (● sûr / moyen / incertain), et fixe le
  nombre de locuteurs suggéré. L'humain vérifie puis applique (philosophie
  identifier/analyser : pré-remplissage + validation).
- **Commande `ia reconcilier`** (`scripts/reconcilier.ps1`, option `-Speakers`).
  `ia taguer` la déclenche automatiquement si la suggestion manque ; `ia taguer
  -NoReconcile` pour l'éviter.

## [1.8.0] — 2026-06-17

### Ajouté
- **#10 — Éditeur d'alias : vue liste des occurrences** : un bouton **📃 N** par
  terme (dès 2 occurrences) ouvre la liste complète de ses occurrences localisées
  (extrait **surligné** + **▶** écouter + **✎** corriger dans le tagueur). Au-delà
  de la limite de capture (60), le surplus est signalé. Remplace le simple cyclage
  du bouton ▶.

### Modifié
- **#16 — `serveur_tagueur.py` : requêtes Range (206 Partial Content)** : l'audio
  du tagueur est servi par tronçons (`Accept-Ranges: bytes`) → *seek* fluide sur
  gros fichiers, comme le serveur de l'éditeur. (Auparavant `Accept-Ranges: none`.)

---

## [1.7.0] — 2026-06-17

Salve de retours de test : refonte UX du tagueur (scinder/fusionner, navigation,
lecture, libellés, minimap) et de l'éditeur d'alias (réécoute, fusion cliquable,
nouveaux labels, masquage hors-fichier), correctifs audio/export, et tâches
planifiées 100 % silencieuses.

### Corrigé
- **Tagueur — minimap décalée (marques ET rectangle de visualisation)** : les
  marques « non diarisé »/coupes étaient positionnées par la **durée audio** (≠
  liste par ligne), et le rectangle de visualisation + les marques étaient
  normalisés par `scrollHeight`, **gonflé par le padding bas de 40vh** → marques
  tassées et rectangle pouvant flotter dans le vide sous les segments. Désormais
  tout est calé sur les **positions DOM réelles des lignes** et normalisé par la
  **hauteur de contenu** (hors padding) ; le rectangle est borné à la zone de
  contenu. Alignement exact marques / rectangle / segments ; rafraîchi au tagage.
- **Éditeur d'alias — bouton ▶ sans effet** : `serveur_editeur` servait l'audio
  avec un type MIME deviné (souvent `octet-stream` pour `.m4a`) → le `<audio>` ne
  décodait pas. Table MIME explicite (comme le tagueur).
- **Tagueur ouvert depuis l'éditeur (✎) — export en *download*** au lieu d'écrire
  dans `2_coupe` : c'est désormais l'**éditeur** qui ouvre l'onglet du tagueur
  (`window.open` vers un port libre dédié), garantissant le mode serveur (export
  direct dans `2_coupe`/`1_transcription`). Avant, `serveur_tagueur` lancé en
  sous-processus ouvrait lui-même le navigateur (peu fiable en détaché).
- **Bouton « Renommer les locuteurs »** : ne faisait plus rien tant qu'aucun
  locuteur n'était assigné (régression Phase 2 — il ne traitait que les locuteurs
  déjà *utilisés*). Il renomme de nouveau **tous** les locuteurs (`nameAllSpeakers`).
- **Badge de prise de parole (« ▸ Nom ») non mis à jour après réaffectation** :
  on pouvait avoir un changement de locuteur sans badge. `turnStart` est désormais
  **recalculé** depuis la séquence des locuteurs après chaque édition (affecter,
  prise de parole, effacer, scinder, fusionner). `tagger.html`.
- **Réouverture du tagueur : reprise de la dernière version (plus de « branche
  orpheline »)**. À la réouverture (ex. depuis l'analyse via ✎), le tagueur
  chargeait toujours le transcript brut (`1_transcription`, étiquettes locales)
  → réconciliation + nommage à refaire, sans les coupes. Désormais :
  - `serveur_tagueur.py` sert la version la plus **avancée** : `2_coupe` (tagué +
    coupé) si présent, avec l'**audio coupé** correspondant (timecodes alignés),
    sinon `1_transcription` + audio brut.
  - `tagger.html` **conserve les noms** de locuteurs lus dans les étiquettes
    `[Nom]` (plus de re-nommage) ; `stemFromAudio` retire un `_coupe` superflu
    pour que la ré-export **écrase** `X_coupe.*` au lieu de créer `X_coupe_coupe.*`.
  → On peut rouvrir, corriger le texte et ré-exporter sans tout refaire.

### Ajouté
- **Tagueur — Fusionner** : bouton « Fusionner » (touche **F**) qui réunit les
  segments sélectionnés (plage Maj+clic / Maj+↑↓) en **un seul** — rattrape une
  sur-segmentation ou une scission erronée.
- **Tagueur — bouton ▶ par segment** : lit à partir de ce segment (entre le temps
  et le texte).
- **Éditeur d'alias — nouveaux labels distingués** : un label détecté dans CE
  fichier mais pas encore dans la mémoire client est affiché sur **fond vert**
  (≠ labels déjà connus de la mémoire). Aide à repérer ce qui reste à traiter.
- **Nom du fichier de référence affiché** (audio d'origine, « 🎧 X.m4a ») dans le
  tagueur ET l'éditeur d'alias — repère stable tout au long du workflow.
- **Éditeur d'alias — masquage des labels hors fichier** : les labels de la
  mémoire client **absents du fichier en cours** sont masqués de la vue principale
  (allègement). Ils restent **cibles de fusion** (liste « Fusionner vers… ») et
  **conservés à l'export** ; le groupe indique « +N hors fichier ».

### Modifié
- **Tagueur — boutons renommés** (plus distincts) : « Couper » (exclure du
  montage, touche **C**) devient **« Cacher » (🙈)** — ne se confond plus avec
  « Scinder » ; l'action « retirer l'affectation de locuteur » (touche **0**) garde
  le nom **« Effacer » (🧽)**.
- **Tagueur — sélection multiple plus contrastée** : fond bleuté + liseré, bien
  plus visible qu'avant (6 % de blanc).
- **Tagueur — 2ᵉ groupe de boutons = navigation** : le groupe « Prise de parole »
  (affectation jusqu'au prochain changement) est remplacé par « Aller à » —
  boutons (et **Maj+N**) qui sautent à la **prochaine intervention du locuteur N**
  (clics répétés = interventions suivantes, en boucle). On ne garde qu'**un seul**
  bouton d'affectation par locuteur (« Affecter au locuteur », touche N).
- **Éditeur d'alias — « Fusionner vers… » cliquable** : remplace le `prompt()`
  numéroté par une **liste cliquable** des groupes cibles (pseudo + type +
  variantes) ; un clic fusionne.
- **Panneau « Scinder » refondu** : lecture/pause de l'extrait, **curseur ▲
  positionnable** sous la timeline (glisser), bouton « ⟐ Couper au point lu »
  (place la coupe au point d'écoute + met en pause), et « ▶ Avant la coupe » /
  « ▶ Après la coupe » pour valider le point choisi.
- **Sélection dissociée de la lecture** : cliquer un segment ne démarre **plus**
  la lecture automatiquement (lecture via le ▶ du segment, Espace ou Entrée).
- **Nommage des locuteurs en TOUTE PREMIÈRE étape** à l'ouverture du tagueur :
  on nomme « Locuteur 1 / 2 » (noms réels, suggérés) **avant** la réconciliation,
  qui affiche alors directement ces noms (au lieu de « Loc 1/2 »). Nouvelle
  fonction `nameAllSpeakers` (nomme tous les locuteurs globaux, même pas encore
  assignés). `tagger.html`.
- **Nombre de locuteurs par défaut = celui de la diarisation** : déduit des
  étiquettes locales `T<tronçon>-<lettre>` (max de voix distinctes par tronçon),
  clampé à [2, 4]. Avant : toujours 2 par défaut. `tagger.html`.
- **Tâches planifiées 100 % silencieuses** (État *et* Orchestrateur) : plus
  aucune fenêtre de terminal qui s'ouvre (rafraîchissement toutes les 2 min,
  ticks d'orchestration toutes les 5 min). Lancement via `wscript.exe` + nouveau
  shim `scripts/_silent.vbs` (fenêtre masquée, aucune console allouée), sans
  droits admin (le logon S4U les aurait exigés). Le shim **attend** la fin de la
  commande (`sh.Run …,0,True`) → l'instance de tâche reste vivante pendant une
  transcription inline (pas de process détaché tué en fin de tick). `veille.ps1`
  installe les deux tâches avec `-Silencieux` ; les tâches en service ont été
  basculées. Le `-WindowStyle Hidden` seul laissait un bref flash à chaque tick.

---

## [1.6.1] — 2026-06-17

### Modifié
- **`ia etat`** affiche désormais l'avancement au niveau du **workflow complet**
  (transcrire · taguer · couper · **identifier** · **analyser** · anonymiser) +
  la prochaine action, au lieu des 3 étapes brutes de `entretien.json` (qui
  masquaient la distinction identifier/analyser). S'appuie sur `etat.py` (source
  de vérité unique, alignée sur `ia tableau`).
- `etat.py` : nouveau **mode entretien** — quand le chemin contient lui-même un
  audio, sortie détaillée d'un seul entretien (`--format table`/`json`).

Outils : `etat.py`, `ia.ps1`.

---

## [1.6.0] — 2026-06-17

### Ajouté — éditeur d'alias : surlignage + alerte homonymes
- **#11 — Surlignage du terme** : dans l'éditeur, le terme en cours de
  catégorisation est mis en évidence (`<mark>`) dans l'extrait de contexte
  (toutes occurrences, insensible à la casse). Côté éditeur uniquement.
- **#9 — Alerte homonymes** : `detecter.py` compare les candidats PERSONNE entre
  eux et signale les risques de confusion — **token partagé** (« Marc Durand » /
  « Marc Dupont » / « Marc ») ou **nom proche** (Levenshtein token à token :
  « Dupont » / « Dupond »). Chaque candidat concerné porte `homonymes` dans le
  `.etat.json` ; l'éditeur affiche un **⚠** (liste au survol) + un compteur dans
  les stats. L'outil n'arbitre pas : alerte à lever à la main.

Outils : `detecter.py`, `editeur_alias.html`.

---

## [1.5.1] — 2026-06-17

### Corrigé
- **#5** — Le montage de coupe **rogne le début et la fin** : l'audio coupé (et
  ses timecodes) commence au 1ᵉʳ segment **conservé** et finit au dernier
  (l'intro/outro hors parole gardée — silence, bruit, segments coupés en
  tête/queue — est supprimée). Avant, le tout début (avant la 1ʳᵉ parole gardée)
  restait dans le montage. `buildCompactTimeline` (tagger.html) ; timecodes
  recalés en conséquence. Vérifié sur 4 scénarios.

---

## [1.5.0] — 2026-06-17

### Ajouté — tagueur : scinder un segment + saut au changement de locuteur
- **#1 — Scinder un segment** (diarisation ayant fusionné deux voix) via une
  **fenêtre dédiée** : mini-timeline zoomée sur [segment précédent · segment ·
  suivant] pour écouter précisément (▶ Contexte / ▶ Segment) ; **clic** = point
  de coupe **audio**, **curseur dans le texte** = point de coupe **texte** →
  2 segments. La ré-affectation des locuteurs se fait ensuite dans la vue
  globale. Bouton « Scinder » + touche **S**.
- **#3 — Saut au changement de locuteur** : depuis le segment courant, saute le
  « run » du même locuteur et se pose sur la prochaine/précédente prise de parole
  d'un autre locuteur. Boutons « Locuteur ⏭ / ⏮ » + **Alt+↓ / Alt+↑**.

Outils : `tagger.html`.

---

## [1.4.0] — 2026-06-17

### Ajouté — noms de locuteurs obligatoires + cohérence inter-entretiens (Phase 2)
- **Nommage obligatoire** des locuteurs dans le tagueur, dès la 1re ouverture
  (auto juste **après la réconciliation**, donc avant la phase de coupe ; aussi
  à un chargement sans réconciliation). L'export (`.srt`/`.txt`/`2_coupe`) est
  **bloqué** tant qu'un locuteur utilisé reste « Locuteur N ».
- **Pré-remplissage / cohérence** : le tagueur **suggère les noms de personnes
  déjà connus du client** (lus dans `memoire_client.json` par recherche
  ascendante). En réutilisant le même nom, la même personne reçoit le **même
  pseudonyme d'un entretien à l'autre** (le nom remonte via `[Nom]` →
  `detecter.py` → mémoire). Règle le « regroupage différent à chaque entretien ».
  - `memoire.py` : helper `noms_personnes()`.
  - `serveur_tagueur.py` : `locuteurs_connus` dans `/api/manifest` (recherche
    ascendante du `memoire_client.json`).
  - `tagger.html` : nommage forcé + pré-rempli + garde-fou d'export.

Outils : `memoire.py`, `serveur_tagueur.py`, `tagger.html`.

---

## [1.3.0] — 2026-06-17

### Ajouté — réécoute audio + correction du texte pendant l'analyse (#6, #2, #16)
- **Réécoute audio dans l'éditeur d'alias** : chaque entité a un bouton **▶** qui
  rejoue le tronçon de l'occurrence (clic répété = occurrence suivante → navigation
  entre extraits, #2). `detecter.py` capture les timecodes (champ `positions`) ;
  `serveur_editeur.py` sert l'audio (`/api/audio`, **support Range/seek**, #16) en
  alignant l'audio coupé (`2_coupe`) ou brut (racine) selon `transcript_dir`.
- **Correction « dans la foulée »** : bouton **✎** par occurrence qui rouvre le
  **tagueur** (source de vérité du texte) PILE sur le passage, par recherche de
  **texte** (robuste au décalage de timeline dû à la coupe). `serveur_tagueur.py`
  et `taguer.ps1` acceptent `--find`/`-Find` ; `serveur_editeur.py` lance le
  tagueur via `/api/ouvrir-tagueur` (repli affiché : `ia taguer -Find "…"`).

  Boucle : ✎ → corriger dans le tagueur → ré-exporter (`2_coupe`) →
  `ia identifier` → `ia analyser`.

Outils : `detecter.py`, `serveur_editeur.py`, `editeur_alias.html`,
`serveur_tagueur.py`, `taguer.ps1`, `tagger.html`.

> Phase 2 à suivre : noms de locuteurs obligatoires + persistance via la mémoire
> client (cohérence d'anonymisation entre entretiens).

---

## [1.2.0] — 2026-06-17

### Ajouté / Modifié
- **Scission identification / analyse** de l'étape d'anonymisation (la
  pré-analyse automatique est désormais distincte de la validation humaine) :
  - `ia identifier` — **pré-analyse AUTOMATIQUE** : détection NER (`detecter.py`)
    → candidats dans `3_anonymisation/<x>.etat.json`. N'ouvre **plus** l'éditeur.
  - `ia analyser` — **validation HUMAINE seule** : éditeur d'alias sur les
    candidats déjà identifiés ; exige le `.etat.json` (sinon renvoie vers
    `ia identifier`). À l'export, `validation.faite=true` débloque l'anonymisation.

  Auparavant `ia analyser` enchaînait détection **et** éditeur d'un seul bloc.
- **Orchestrateur** : l'identification est exécutée automatiquement parmi les
  étapes rapides, **avant** la transcription (quick win) → les candidats sont
  prêts quand tu passes à la validation.
- **`etat.py`** : nouvelle action `identifier` (auto) distincte d'`analyser`
  (humain). Colonne *Analyse* : `--` à identifier (auto) · `~~` identifié, à
  valider (toi) · `OK` validé.

Outils touchés : `anonymisation.ps1`, `ia.ps1`, `orchestrer.ps1`, `etat.py`.

> Optimisation de cette étape (points durs) : à traiter ensuite.

---

## [1.1.0] — 2026-06-17

### Ajouté
- **Tâche planifiée « État » dédiée** — découple le rafraîchissement de `ETAT.md`
  de la transcription. La transcription reste *inline* (longue, bloquante) ; une
  2ᵉ tâche légère et **indépendante** (`scripts/_etat_tache.ps1`, toutes les 2 min,
  **lecture seule** sauf `ETAT.md`) régénère `ETAT.md` en continu. Résultat :
  l'état — y compris la **progression `n/total` des tronçons** (lue sur le disque
  par `etat.py`) — reste à jour **même pendant** une transcription qui dure des
  heures. Deux instances de tâches distinctes → l'une ne bloque jamais l'autre.
  `veille.ps1 -Installer` installe désormais les **deux** tâches (nouveau
  paramètre `-IntervalleEtatMin`, défaut 2 min).

### Corrigé
- **#19** — `veille.ps1 -Installer` débloque la batterie pour les tâches
  (`DisallowStartIfOnBatteries`/`StopIfGoingOnBatteries` = False). Auparavant, les
  défauts du Planificateur (True) empêchaient la tâche de tourner / la tuaient sur
  batterie ; le correctif n'était appliqué qu'à la main sur la tâche en service.

### Modifié
- `_tache.ps1` (tâche de transcription) passe `-NoEtatMd` : la tâche « État » est
  l'**unique rédactrice** de `ETAT.md` (évite une course d'écriture entre les deux
  tâches).

---

## [1.0.0] — 2026-06-17

Première version versionnée. Consolide le pipeline complet de traitement des
entretiens — **transcrire → taguer → couper → analyser → anonymiser →
repersonnaliser** — et son orchestration automatique sous Windows.

### Pipeline & industrialisation

- **Commande unique `ia`** (#4, 15/06) — dispatcher + fonction de profil
  PowerShell. Wrappers `transcrire` / `taguer` / `couper` / `anonymiser` dans
  `scripts/`. Arborescence constante par entretien (`1_transcription/`,
  `2_coupe/`, `3_anonymisation/`). `alias`/`table` partagés au niveau d'un
  « périmètre » trouvé par **recherche ascendante**. Les wrappers ciblent le
  `python.exe` du venv en absolu (`ia setenv` active le venv à la demande).
  Voir `scripts/GUIDE-USAGE.md`.
- **`entretien.json` + logging centralisé** (#15, 16/06) — fichier projet à la
  racine de chaque entretien (statut/horodatage/durée par étape + chemin du log),
  schéma dans `scripts/SCHEMA-entretien.md`. Log verbeux centralisé dans
  `<repo>/logs/` (stdout+stderr, temps réel via `Tee-Object`), résumé dans
  `entretien.json`. Tous les wrappers instrumentés ; commande `ia etat`.

### Transcription

- **`transcribe_robuste.py`** — découpage en tronçons (ffmpeg), transcription
  Whisper `large-v3` par tronçon avec **point de reprise** (saute les tronçons
  déjà faits), diarisation optionnelle (étiquettes locales à réconcilier dans le
  tagueur), fusion avec dédoublonnage des chevauchements. Option `--outdir`.
- **Serveurs locaux** `serveur_tagueur.py` / `serveur_editeur.py` (127.0.0.1,
  chargement auto audio+srt, arrêt par heartbeat à la fermeture de l'onglet) +
  repli File System Access API / fichier.

### Anonymisation — modèle de persistance unifié (#14 + #8 + #13 + #7 + #12 + #17, 16/06)

- **`memoire_client.json`** : artefact **unique par client** (remplace
  `alias.yaml` + `table_correspondance.json`) mémorisant pseudos + canoniques +
  variantes + types + faux positifs + locuteurs génériques. Édité/versionnable.
  `config/ignorer_global.json` partagé pour les faux positifs universels. Logique
  centralisée dans `tools/anonymisation/memoire.py`. Les `ignorer`/`generiques`
  **survivent désormais entre séances**.
- **`migrer.py`** — conversion ancien format → nouveau.
- **`desanonymiser.py`** (#12) — repersonnalisation des rapports (mapping inverse
  pseudo → canonique, pseudos longs d'abord ; `.txt`/`.md`/`.srt`/`.docx`).
  ⚠️ La sortie `_REPERSONNALISE` contient à nouveau les vraies données : ne jamais
  la renvoyer vers une IA externe.
- **Corrigé #8** — l'éditeur n'impose plus le suffixe `_<chiffre>` ; pseudos
  parlants (`SOCIETE`, `CONSULTANT_1`) valides. Export via `JSON.stringify` (fini
  le générateur YAML bricolé qui corrompait silencieusement les pseudos).
- **Corrigé #13** — le `type` est un champ explicite par entrée (écrit par
  l'éditeur, lu tel quel par `appliquer.py`) ; fini le « tout devient PRODUIT ».
- **Corrigé #7** — UI dédiée aux locuteurs génériques, inclus à l'export.
- **#17** — l'éditeur fusionne la mémoire existante du périmètre avec les
  nouvelles détections sans écraser les regroupements.

Outils touchés : `memoire.py`, `migrer.py`, `desanonymiser.py` (nouveaux),
`detecter.py`, `appliquer.py`, `reconcilier.py`, `editeur_alias.html`,
`serveur_editeur.py`, `anonymisation.ps1`, `_commun.ps1`, `SCHEMA.md`.
Rétrocompatibilité : `--alias`/`--table` encore acceptés (migration à la volée).

### Orchestration multi-entretiens (#18, 16-17/06)

- **`etat.py`** — moteur d'état **lecture seule** : scanne un périmètre, calcule
  par entretien l'état de chaque étape + la **prochaine action** (auto vs humain),
  en réconciliant le système de fichiers (autoritaire) avec `entretien.json`.
  Rendus `table` / `json` / `md` (`ETAT.md`). Affiche la **progression des
  tronçons** d'une transcription en cours (`.. 3/7`, 17/06).
- **`sync.py`** — aligne les `entretien.json` sur le disque (**upgrade-only**,
  idempotent).
- **`orchestrer.ps1`** — **tick** idempotent : sync + tableau + `ETAT.md` +
  exécution de l'automatisable. `couper`/`anonymiser` synchrones (rapides) ;
  `transcrire` **une seule à la fois** (verrou PID + reprise des `en_cours`
  périmés). Options `-DryRun`, `-NoTranscribe`, `-NoEtatMd`, `-TranscribeInline`.
- **`veille.ps1`** — surveillance continue : boucle terminal **et** tâche
  planifiée Windows (`-Installer`/`-IntervalleMin`/`-Desinstaller`/`-Statut`),
  fenêtre **masquée** (`-WindowStyle Hidden`, 17/06), intervalle par défaut
  **5 min** (17/06).
- **`_tache.ps1`** — lanceur de la tâche planifiée (journalise chaque tick,
  force le mode transcription **inline**).
- **`ia.ps1`** — commandes `ia tableau` / `ia orchestrer` / `ia veille`.
- **Déclenchement de l'anonymisation auto** : `serveur_editeur.py` estampille le
  `.etat.json` (`validation.faite=true`) à l'export réussi de la mémoire ; c'est
  cette trace de **validation humaine** qui autorise l'anonymisation auto.
- **Gotcha planificateur (résolu)** : un process *détaché* serait tué en fin de
  tick → la tâche transcrit **en inline** (synchrone) ; `MultipleInstances=IgnoreNew`
  empêche le chevauchement. Sérialisation **auto-réparante** (reprise aux
  tronçons sauvegardés après un kill).

### Corrigé (17/06)

- **Transcription cassée sur les dossiers accentués** — la tâche tourne en
  `pwsh -NoProfile`, dont `[Console]::OutputEncoding` par défaut est l'OEM
  (CP850) et non UTF-8 : le JSON UTF-8 d'`etat.py` était mal décodé, les chemins
  accentués corrompus (`Pr├®sentation`), et `Push-Location` échouait → la
  transcription ne démarrait jamais. Fix : `[Console]::OutputEncoding = UTF8` en
  tête d'`orchestrer.ps1`.
- **Auto-skip des fichiers qui cassent** — champs durables
  `tentatives_auto`/`progres_auto` dans `entretien.json` (écrits avant le
  lancement, survivent à `Start-Etape`/`sync`/`etat`). Si un fichier meurt sans
  produire de tronçon `$MaxTentatives` (2) fois → statut `echec` (quarantaine) →
  l'orchestrateur passe au suivant au lieu de boucler indéfiniment.

### Notes d'exploitation

- Tâche planifiée : intervalle **5 min**, fenêtre masquée, réglages batterie
  débloqués (`DisallowStartIfOnBatteries`/`StopIfGoingOnBatteries` = False) pour
  ne pas être bloquée/tuée sur batterie. ⚠️ Ces réglages batterie ne sont pas
  encore portés dans `veille.ps1 -Installer` (une réinstallation les remettrait
  par défaut).
- Validé sous Windows (16-17/06) : tableau, couper auto, sérialisation et reprise
  de transcription, sync, cycle install/désinstall de la tâche, transcriptions
  complètes (Nicolas, Cedric), correctif accents.

[1.9.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.9.0
[1.8.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.8.0
[1.7.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.7.0
[1.6.1]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.6.1
[1.6.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.6.0
[1.5.1]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.5.1
[1.5.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.5.0
[1.4.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.4.0
[1.3.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.3.0
[1.2.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.2.0
[1.1.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.1.0
[1.0.0]: https://github.com/nicolasmonnierfr/ia-powered-os/releases/tag/v1.0.0
