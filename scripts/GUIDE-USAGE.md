# Guide d'usage — la commande `ia`

Industrialisation du pipeline : une seule commande `ia`, lancée **depuis le
répertoire racine d'un entretien**, qui range tout dans une arborescence
constante. Plus besoin de retenir les longues lignes de commande ni d'activer
le venv pour l'usage courant.

---

## Installation (une seule fois)

Depuis le repo :

```powershell
.\scripts\installer-ia.ps1
```

Cela ajoute au profil PowerShell :
- la variable `IA_POWERED_OS_HOME` (localisation du repo) ;
- une fonction `ia` disponible dans **tous** les terminaux.

Ouvre ensuite un **nouveau** terminal, puis vérifie :

```powershell
ia aide
```

> Désinstallation : `.\scripts\installer-ia.ps1 -Desinstaller`
> Si tu déplaces le repo, relance l'installateur (le chemin y est figé).

---

## Arborescence d'un entretien

Tu te places dans le dossier de l'entretien (celui qui contient l'audio) et
tu ne le quittes plus. Les commandes créent et remplissent les sous-dossiers :

```
<...>/                              (niveau « périmètre » : voir anonymisation)
├── memoire_client.json              mémoire d'anonymisation unique (LOCALE, jamais envoyée)
│
└── entretien_dupont/                <-- TU LANCES LES COMMANDES ICI
    ├── entretien_dupont.m4a          audio source
    ├── entretien.json                suivi d'avancement + logs (cf. ia etat)
    ├── 1_transcription/              ia transcrire
    │   ├── entretien_dupont.txt
    │   └── entretien_dupont.srt
    ├── 2_coupe/                      ia taguer + ia couper
    │   ├── plan_de_coupe.json
    │   ├── entretien_dupont.edition.json   état d'édition (parties cachées, audio non coupé)
    │   ├── entretien_dupont_coupe.m4a
    │   ├── entretien_dupont_coupe.srt
    │   └── entretien_dupont_coupe.txt
    └── 3_anonymisation/             ia identifier + ia analyser + ia anonymiser
        ├── entretien_dupont_coupe.etat.json     (ia identifier ; validé par ia analyser)
        ├── entretien_dupont_coupe_anonymise.srt
        ├── entretien_dupont_coupe_anonymise.txt    lisible (pour analyse IA)
        └── entretien_dupont_coupe_rapport.txt
```

---

## Le workflow, étape par étape

### 1. Transcrire

```powershell
ia transcrire
```

- Transcrit l'audio du dossier courant (diarisation **activée par défaut**).
- Sorties dans `1_transcription\`.
- Options : `-NoDiarize`, `-ChunkMin 10`, `-Model large-v3`, `-Language fr`,
  ou un fichier explicite : `ia transcrire monaudio.m4a`.

### 2. Taguer (locuteurs + coupe)

```powershell
ia taguer
```

- Ouvre le tagueur dans Chrome avec l'audio (racine) et le `.srt`
  (`1_transcription\`) **déjà chargés**.
- Tu identifies les locuteurs et marques les passages à couper (🙈 « Cacher »,
  réversible).
- Bouton **« Exporter vers 2_coupe »** : écrit `plan_de_coupe.json` +
  `..._coupe.srt` + `..._coupe.txt` (recalés, **sans** les parties cachées) **et**
  `....edition.json` (état d'édition complet, **avec** les parties cachées, sur la
  timeline de l'audio non coupé), cohérents, directement dans `2_coupe\`.
- **Deux versions à la réouverture** (bouton **✏️ Édition / 🎬 Finalisée** en
  haut) :
  - **Édition** (par défaut) : audio **non coupé** + transcript **avec les parties
    cachées** → tu reprends le travail, tu peux **dé-cacher** et réajuster le plan,
    sans décalage.
  - **Finalisée** : audio **coupé** + transcript **recalé** → relecture du livrable
    (lecture seule). Disponible une fois `ia couper` passé.
- **Principe** : `2_coupe\<nom>.edition.json` est **le** document de travail (source
  de vérité). `plan_de_coupe.json`, `_coupe.srt`, `_coupe.txt` et l'audio coupé en
  sont des **sorties régénérées** — ne les édite jamais à la main. Pour corriger un
  texte (y compris depuis « ✎ corriger » de l'anonymisation), on rouvre **l'Édition**,
  puis on ré-exporte ; un entretien plus ancien sans `edition.json` est reconstruit
  automatiquement à l'ouverture (noms + parties cachées restaurés).
- Le serveur local s'arrête **quand tu fermes l'onglet** (ou Ctrl+C dans la
  fenêtre PowerShell).

### 3. Couper l'audio

```powershell
ia couper
```

- Trouve `plan_de_coupe.json` dans `2_coupe\` et reconstruit l'audio raccourci
  `..._coupe.m4a` (réencodage précis à la milliseconde).

### 4. Anonymiser (quatre temps)

L'anonymisation se fait en deux sous-étapes distinctes : **`ia identifier`**
(détection automatique des entités) puis **`ia analyser`** (validation humaine
dans l'éditeur). Cette séparation permet à l'orchestrateur de pré-détecter tout
seul ; seule la validation te revient.

```powershell
ia identifier
```

- Détecte les entités (NER local, 100 % hors ligne) → écrit
  `3_anonymisation\<nom>.etat.json` (candidats à valider).
- **Automatique** : `ia orchestrer` le lance pour toi dès que le transcript est
  prêt. En flux manuel, lance-le **avant** `ia analyser`.

```powershell
ia analyser
```

- Ouvre l'**éditeur** dans Chrome sur les candidats déjà identifiés (exige donc
  que `ia identifier` ait tourné) : tu valides les entités, corriges les types,
  exclus les faux positifs.
- Bouton **« Exporter la mémoire »** : écrit `memoire_client.json` au niveau du
  **périmètre** (voir ci-dessous) et marque la validation comme faite — c'est ce
  signal qui débloque l'anonymisation automatique.

```powershell
ia anonymiser
```

- Applique la mémoire : produit `..._anonymise.srt` + un rapport dans
  `3_anonymisation\`, et met à jour `memoire_client.json` au périmètre.

> ⚠️ Relis toujours le transcript anonymisé avant tout envoi à une IA externe.
> ⚠️ `memoire_client.json` contient les vrais noms : ne JAMAIS l'envoyer.

```powershell
ia repersonnaliser -Rapport "rapport.md"
```

- **Chemin inverse (#12)** : une fois l'analyse revenue de l'IA externe (avec
  des pseudos), réinjecte les vrais noms pour livrer au client. Produit un
  fichier `..._REPERSONNALISE` (formats `.md`/`.txt`/`.srt`/`.docx`).
- Sans `-Rapport`, prend le rapport le plus récent de `3_anonymisation\`.
  Option `-Court` pour les prénoms plutôt que les noms complets.

> ⚠️ Le fichier `..._REPERSONNALISE` contient les vrais noms : usage **local**,
> ne jamais le renvoyer à une IA externe.

---

## Synthèse multi-entretiens (`ia synthese`)

Pour analyser **plusieurs entretiens d'un coup** (synthèse croisée), sans repasser
par un chat externe. La synthèse porte sur une **sélection** d'entretiens décrite
dans un **manifeste**, jamais sur un dossier entier.

```powershell
cd C:\...\Mission                 # le périmètre (dossier des entretiens)
ia synthese creer                 # crée le manifeste INTERACTIVEMENT (scan + questions)
ia synthese verifier              # GARDE-FOU : aucun vrai nom ne doit subsister
ia synthese lancer                # synthèse via l'API Claude : anonyme + REPERSONNALISÉE (livrable)
```

- **`creer`** scanne le périmètre (récursif), liste les entretiens **anonymisés**
  trouvés (label neutre `E1`, `E2`…) et te pose les questions : titre, **nom de
  base des fichiers de sortie**, puis par entretien `inclure` / `role` (générique)
  / `interviewe` (pseudonyme — il te liste les interlocuteurs connus). Écrit
  `synthese.manifeste.json`. _(`ia synthese init` produit le même fichier en
  modèle non interactif, à éditer à la main.)_
- **`verifier`** = **garde-fou anti-fuite** : il assemble le contenu qui partirait
  (uniquement labels neutres + texte **anonymisé**, **jamais** les noms de
  fichiers) et le confronte à la `memoire_client.json` (locale). Tout vrai nom
  résiduel **bloque** l'envoi — le rapport indique le **fichier** concerné (pas
  seulement `E1`/`E2`) pour aller corriger directement. `-Dump payload.local.json`
  écrit le payload pour inspection locale.
- **`lancer`** appelle l'**API Claude** (`claude-opus-4-8` par défaut) puis écrit
  **deux versions au niveau de la mission** (nom de base = champ `sortie` du
  manifeste, ou `-Out`) + un journal `<sortie>.run.json` :
  - `<sortie>.md` — **anonyme** (pseudonymes), trace de ce qui a été envoyé ;
  - `<sortie>_REPERSONNALISE.md` — **le livrable** (vrais noms), produit
    **automatiquement** (la repersonnalisation est intégrée — plus besoin de la
    lancer à part). ⚠️ vrais noms : usage local.

  Le garde-fou y est **rejoué en barrière** (impossible d'envoyer avec un vrai
  nom). Options : `-DryRun` (prompt local, sans appel API), `-Court` (prénoms),
  `-Modele`, `-MaxTokens`, `-Gabarit`, `-Out`.

> Requiert `ANTHROPIC_API_KEY` dans `config\.env`. Toute la boucle d'analyse
> reste en interne — plus de copier-coller dans un chat externe.

---

## Le « périmètre » d'anonymisation

`memoire_client.json` est **partagé entre plusieurs
entretiens** (mêmes pseudonymes d'un entretien à l'autre). Ils ne vivent donc
PAS dans le dossier de l'entretien, mais à un niveau **au-dessus**, que tu
choisis librement.

`ia anonymiser` **remonte les dossiers parents** depuis l'entretien jusqu'à
trouver un `memoire_client.json`. Le premier trouvé (le plus proche) définit le
périmètre. Tu peux donc placer la `memoire_client.json` au niveau client, mission ou
département — la profondeur en dessous est libre.

Au tout premier entretien d'un nouveau périmètre (aucune `memoire_client.json` en
remontant), il est créé dans le **parent immédiat** de l'entretien. Tu peux le
déplacer plus haut ensuite pour élargir le périmètre.

---

## Suivi, logs et reprise

Chaque commande écrit **deux traces** :

- **Résumé d'avancement** : `entretien.json` à la racine de l'entretien
  (statut de chaque étape, horodatage, durée, chemin du log). Consultable avec :

  ```powershell
  ia etat
  ```

- **Log détaillé** centralisé dans `<repo>\logs\` :
  `<date>-<heure>-<entretien>-<étape>.log`. Il capture toute la sortie
  (y compris les erreurs) — utile pour déboguer un run nocturne même après
  fermeture du terminal.

> ⚠️ Avant cette version, un run lancé la nuit puis fermé ne laissait aucune
> trace. Désormais tout est consigné : en cas de blocage, ouvre le `.log`
> correspondant (son chemin est rappelé à l'écran et listé par `ia etat`).

### Enchaîner plusieurs entretiens (la nuit)

Les transcriptions étant longues en CPU, lance-les **en série** (pas en
parallèle : elles se disputeraient le processeur) :

```powershell
cd C:\...\entretien_A ; ia transcrire ; cd C:\...\entretien_B ; ia transcrire
```

Le `;` enchaîne la suivante même si la précédente échoue (souhaitable la nuit :
un échec ne bloque pas le reste). Au matin, `ia etat` dans chaque dossier — ou
les logs dans `<repo>\logs\` — te disent ce qui a réussi.

---

## Activer le venv à la main (cas avancé)

Les commandes `ia` n'ont pas besoin du venv activé : elles utilisent
directement l'interpréteur du venv. Mais si tu veux taper `python` / `pip` à la
main :

```powershell
ia setenv
```

Active le venv dans la session courante.

---

## Aide-mémoire

| Commande | Effet | Sortie |
|----------|-------|--------|
| `ia transcrire` | transcription + diarisation | `1_transcription\` |
| `ia reconcilier` | recollage des locuteurs entre tronçons (empreinte vocale) | `1_transcription\<nom>.reconcile.json` |
| `ia taguer` | tagging locuteurs + plan de coupe (lance `reconcilier` au besoin) | `2_coupe\` |
| `ia couper` | audio raccourci | `2_coupe\` |
| `ia identifier` | détection NER (auto) → candidats | `3_anonymisation\<nom>.etat.json` |
| `ia analyser` | validation humaine (éditeur) | `memoire_client.json` (périmètre) |
| `ia anonymiser` | application du remplacement | `3_anonymisation\` |
| `ia repersonnaliser` | réinjection des vrais noms (#12) | `..._REPERSONNALISE` |
| `ia synthese creer/verifier/lancer` | synthèse multi-entretiens : config interactive + garde-fou + API Claude | `synthese.manifeste.json` → `<sortie>.md` + `_REPERSONNALISE` |
| `ia etat` | avancement de l'entretien **courant** | lit `entretien.json` |
| `ia tableau [périm]` | vue **globale** de tous les entretiens | tableau console |
| `ia orchestrer [périm]` | une passe : tableau + exécute l'automatisable | `ETAT.md` + livrables |
| `ia veille [périm]` | surveillance **continue** (boucle terminal) | — |
| `ia veille -Inscrire/-Desinscrire/-Lister` | gère les dossiers scannés par la tâche planifiée | `config\perimetres.json` |
| `ia setenv` | active le venv | session courante |
| `ia aide` | liste les commandes | — |

---

## Orchestration & vision permanente

Au-delà du suivi par entretien (`ia etat`), trois commandes pilotent **tout un
périmètre** (le dossier qui contient les sous-dossiers d'entretien). Le
**périmètre** par défaut est le répertoire courant ; on peut le passer en
argument.

### `ia tableau` — la vue globale

```powershell
cd C:\...\Interviews
ia tableau
```

Affiche, pour chaque entretien, l'état de chaque étape et la **prochaine
action** en distinguant ce qui est **automatisable** (`auto`) de ce qui te
revient (`toi`). Lecture seule, n'exécute rien.

> **Détection récursive.** Les entretiens sont cherchés **jusqu'à 4 niveaux** sous
> le périmètre (1 = sous-dossiers directs) : tu peux regrouper les entretiens dans
> des sous-dossiers (par client, vague, thème…). Un dossier est reconnu comme
> entretien **dès qu'il contient un audio** ; les imbriqués apparaissent avec leur
> chemin relatif (`GroupeA/entretien_x`). Cela vaut pour `ia tableau`,
> `ia orchestrer` et `ia veille`.

```
  Entretien            Transcr  Tag  Coupe  Analyse  Anonym  Prochaine action (qui)
  ...
  Légende : OK=fait  --=à faire  ..=en cours  ~~=détecté (analyse non validée)  !!=échec
```

### `ia orchestrer` — une passe automatique

```powershell
ia orchestrer                 # depuis le périmètre
ia orchestrer -DryRun         # montre ce qui serait lancé, sans rien exécuter
ia orchestrer -NoTranscribe   # n'enclenche pas de transcription
```

Affiche le tableau, écrit `ETAT.md` au périmètre, puis **réalise
l'automatisable** :
- **couper** (rapide) dès qu'un `plan_de_coupe.json` est présent sans audio coupé ;
- **anonymiser** (rapide) dès que l'analyse a été **validée** (voir ci-dessous)
  et que la mémoire existe ;
- **transcrire** (longue) : lancée en **arrière-plan**, **une seule à la fois**
  (sérialisation par verrou + détection de l'`en_cours`). Un échec n'est **pas**
  relancé automatiquement (il est signalé pour décision manuelle).

À chaque passe, l'orchestrateur **synchronise aussi les `entretien.json`** avec
la réalité du disque (étapes déjà faites « ailleurs » marquées `fait`), pour que
la mémoire par projet ne mente jamais.

> **Étape `analyser` = la seule non automatisable.** La validation humaine des
> entités (éditeur d'alias) laisse désormais une **trace** dans le `.etat.json`
> (`validation.faite`) au moment où tu cliques **« Exporter la mémoire »**. C'est
> cette trace qui autorise l'anonymisation automatique. Tant qu'elle n'est pas
> là, l'orchestrateur affiche « Analyser (toi) » et n'anonymise pas.

### `ia veille` — surveillance continue (les deux modes)

```powershell
# 1) Boucle terminal (vision live ; Ctrl+C pour arrêter) — sur UN périmètre
ia veille                       # tick toutes les 60 s, périmètre = dossier courant
ia veille "D:\...\Interviews"   # périmètre explicite
ia veille -Intervalle 30 -Clair # 30 s, écran rafraîchi

# 2) Tâche planifiée Windows (filet de sécurité, survit au redémarrage)
ia veille -Inscrire "D:\...\Interviews"    # inscrit un dossier (installe les tâches au besoin)
ia veille -Lister                          # dossiers inscrits
ia veille -Desinscrire "D:\...\Interviews" # retire un dossier du scan
ia veille -Statut                          # état des tâches + registre
ia veille -Desinstaller                    # retire les tâches planifiées
```

Boucle et tâche planifiée partagent le **même tick** (`ia orchestrer`) et le
**même verrou de transcription** : les activer toutes les deux est redondant
mais **sans danger** (jamais deux transcriptions en parallèle).

#### Le registre des répertoires surveillés

Les tâches planifiées ne ciblent **plus un seul dossier figé** : elles scannent à
chaque tick **tous les répertoires inscrits** dans un registre local,
`config\perimetres.json` (gitignoré — il contient des chemins de missions).

**La surveillance suit le registre** : les tâches planifiées sont actives **si et
seulement si** au moins un répertoire est inscrit. Tu n'as donc qu'à inscrire /
désinscrire des dossiers ; l'activation et l'arrêt des tâches sont **automatiques**.

- **`ia veille -Inscrire <dossier>`** ajoute un répertoire au registre. Si le
  registre était **vide** (surveillance arrêtée), les deux tâches planifiées sont
  **activées automatiquement** ; si elles tournaient déjà, le nouveau dossier est
  simplement pris au tick suivant — **sans réinstallation**.
- **`ia veille -Desinscrire <dossier>`** le retire. Si c'était le **dernier**
  répertoire inscrit, les tâches planifiées sont **désinstallées automatiquement**
  (plus rien à scanner) ; elles se réactiveront au prochain `-Inscrire`.
- **`ia veille -Lister`** (ou `ia veille -Statut`) affiche les répertoires
  inscrits, en signalant d'un `!` ceux devenus introuvables sur le disque.

> `ia veille -Installer [dossier]` / `-Desinstaller` restent disponibles pour
> forcer le cycle de vie des tâches à la main (un dossier passé à `-Installer` est
> inscrit au passage). Chaque tâche scanne chaque périmètre **l'un après
> l'autre** ; le verrou de transcription garantit qu'une seule transcription
> tourne à la fois, tous périmètres confondus.
