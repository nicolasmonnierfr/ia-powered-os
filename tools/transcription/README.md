# Skill : Transcription d'entretiens

Transcription automatique d'entretiens audio/vidéo en local via WhisperX, avec
un **tagueur de locuteurs** pour corriger ou réaliser l'attribution des voix à
la main quand la diarisation automatique est insuffisante (voix proches,
audio de visio compressé).

Aucune donnée n'est envoyée sur Internet (hors téléchargement initial des
modèles WhisperX/pyannote).

## Composants

| Fichier | Rôle |
|---------|------|
| `transcribe.py` | Transcription simple → `.txt`, `.srt`, `.json` (audios courts) |
| `transcribe_robuste.py` | Transcription d'audios **longs** : tronçons + reprise sur interruption |
| `reconcilier.py` | **Réconciliation automatique** des locuteurs entre tronçons par **empreinte vocale** (pré-remplit le tagueur) |
| `tagger.html`   | Lecteur audio + transcription synchronisée + tagging des locuteurs + **édition du texte** + **coupe de passages** |
| `couper_audio.py` | Reconstruit l'audio **raccourci** à partir du plan de coupe exporté par le tagueur (ffmpeg) |

---

## 1. Transcription (`transcribe.py`)

### Prérequis
- Environnement installé via `bootstrap/setup-windows.ps1`
- Token Hugging Face dans `config/.env` (pour la diarisation)
- Licences pyannote acceptées (voir plus bas)

### Utilisation
Depuis la racine du repo, environnement activé (`(.venv)` visible) :

```powershell
python tools\transcription\transcribe.py "data\mon_entretien.m4a"
```

Options :
```
--model       large-v3 (defaut) | medium | small ...
--language    fr (defaut)
--speakers    2 (defaut, nb de locuteurs attendus)
--no-diarize  Desactive la diarisation auto (plus rapide)
--output-dir  Dossier de sortie (defaut : data/transcriptions)
```

### Deux workflows selon l'audio
- **Audio net, voix distinctes** : laisser la diarisation auto. Le `.srt`
  sortira pré-étiqueté ; le tagueur **importe ces étiquettes** et tu n'as plus
  qu'à vérifier / corriger (plus rapide que tout taguer à blanc).
- **Audio difficile (voix proches, visio)** : utiliser `--no-diarize`
  (plus rapide), puis **tout attribuer dans le tagueur**. Recommandé quand la
  diarisation auto est mauvaise.

### Sorties (dans `data/transcriptions/`)
- `<nom>.txt`  : transcription lisible, regroupée par locuteur
- `<nom>.srt`  : un sous-titre horodaté par segment (entrée du tagueur)
- `<nom>.json` : données complètes (segments, timestamps, locuteurs)

### Acceptation des licences pyannote (une seule fois)
Connecté à ton compte Hugging Face, accepter les conditions sur :
- https://huggingface.co/pyannote/speaker-diarization-community-1
- https://huggingface.co/pyannote/segmentation-3.0

> Note : les versions récentes de WhisperX utilisent le modèle
> `speaker-diarization-community-1`. Si la diarisation renvoie une erreur 403,
> c'est que la licence de CE modèle n'a pas été acceptée.

---

## 2. Tagueur de locuteurs (`tagger.html`)

Outil autonome qui tourne dans le navigateur (rien à installer). Il charge un
audio + un `.srt`, joue l'audio en surlignant le segment courant, et permet
d'attribuer chaque passage à un locuteur.

**Nombre de locuteurs réglable (2 à 4)** via le sélecteur « Locuteurs » en haut.
Par défaut 2 (cas de l'entretien 1-à-1). Réduire le nombre remet à « non
affecté » les segments d'un locuteur supprimé (avec confirmation).

### Ouverture
Double-clic sur `tools\transcription\tagger.html` (s'ouvre dans le navigateur).

### Procédure
1. **Charger l'audio** (bouton « Audio ») — le même fichier que la transcription.
2. **Charger le `.srt`** (bouton « Transcription .srt »).
3. Lire l'audio et **taguer** au fil de l'écoute.
4. **Exporter** en `.txt` (lisible) ou `.srt` (étiqueté).

> Le navigateur ne peut pas accéder seul à tes fichiers : tu les charges
> manuellement à chaque session. Rien n'est envoyé en ligne, tout reste local.

### Import de la diarisation (pré-remplissage)
Si le `.srt` contient des étiquettes `[SPEAKER_XX]` (diarisation auto), le
tagueur **pré-affecte** les locuteurs à l'import :
- mapping dans l'ordre d'apparition : 1er locuteur vu → Loc 1, 2e → Loc 2, etc.
- le **nombre de locuteurs s'ajuste automatiquement** au contenu du `.srt` ;
- au-delà de 4 locuteurs, l'outil plafonne à 4 et laisse les autres en
  « non affecté » (avec un message) ;
- un `.srt` sans étiquette (issu de `--no-diarize`) arrive vierge : tu tagues
  tout à la main.

Tu n'as alors qu'à **vérifier et corriger** le pré-remplissage.

### Mode réconciliation (SRT diarisé par tronçon)
Si le `.srt` provient de `transcribe_robuste.py --diarize`, il contient des
étiquettes **locales par tronçon** (`T1-A`, `T2-B`…). À l'import, le tagueur
ouvre automatiquement un **panneau de réconciliation** :
- chaque locuteur local est listé avec un bouton **▶ écouter** (joue ~4 s de
  son premier passage) et un extrait de texte ;
- tu cliques le locuteur global correspondant (Loc 1, Loc 2…) ;
- « Appliquer » propage le mapping sur tous les segments.

Le bouton **Réconcilier** (en bas) rouvre ce panneau à tout moment. Après
application, tu peux corriger les segments isolés avec le tagging habituel.

#### Pré-réconciliation automatique par empreinte vocale (`reconcilier.py`)
Avant d'ouvrir le tagueur, `ia taguer` lance automatiquement `reconcilier.py`
(si pas déjà fait) : il extrait une **empreinte vocale** de chaque locuteur
local (`T1-A`, `T2-B`…) à partir des tronçons WAV conservés dans
`data/.chunks/`, puis **regroupe les voix identiques** entre tronçons
(clustering sur distance cosinus). Le panneau de réconciliation s'ouvre alors
**déjà pré-rempli**, avec un indicateur de confiance par étiquette :
- **● sûr** (vert) / **● moyen** (ambre) / **● incertain** (rouge).

Tu n'as plus qu'à **vérifier** (surtout les « incertain ») puis **Appliquer**.
Philosophie identique à `identifier`/`analyser` : on pré-remplit, l'humain
valide — on ne se fie pas aveuglément à la reconnaissance vocale (voix proches,
segments courts).

```powershell
ia reconcilier              # (re)génère la suggestion ; nb de locuteurs estimé
ia reconcilier -Speakers 2  # force le nombre de locuteurs
ia taguer -NoReconcile      # ouvre le tagueur sans pré-réconciliation auto
```

> La suggestion est écrite dans `1_transcription/<nom>.reconcile.json`. Le
> modèle d'empreinte par défaut est `speechbrain/spkrec-ecapa-voxceleb` (repli
> automatique sur `pyannote/embedding`) ; surchargeable via `EMBEDDING_MODEL`
> dans `config/.env`. Premier lancement : téléchargement du modèle (une fois).

### Deux modes de tagging
- **Par segment** : sélectionner un segment, cliquer Loc 1 / Loc 2 (ou touche
  `1` / `2`). Affecte uniquement ce segment. Utile pour les exceptions
  (relance courte au milieu d'un monologue).
- **Par prise de parole** : « Prise de parole → Loc X » (ou `Maj+1` / `Maj+2`).
  Affecte ce segment **et tous les suivants** jusqu'au prochain changement
  marqué. C'est le mode rapide : on ne tague que les **transitions**.

### Repérage visuel
Les segments **non affectés** sont en gris. Couleurs des locuteurs : 1 ambre,
2 bleu, 3 vert, 4 mauve. Le compteur « Non affectés » en haut indique ce qui
reste à traiter.

### Raccourcis clavier
| Touche | Action |
|--------|--------|
| Espace | Lecture / pause |
| 1 … 4 | Affecter le segment au locuteur N (puis avance) |
| Maj+1 … 4 | Nouvelle prise de parole (segment + suivants) |
| 0 | Effacer l'affectation |
| ↑ / ↓ | Segment précédent / suivant |
| ← / → | Reculer / avancer l'audio de 3 s |
| Entrée | Lire le segment sélectionné depuis son début |

Les touches actives dépendent du nombre de locuteurs choisi (1-2, 1-3 ou 1-4).

### Renommer les locuteurs
Bouton « Renommer les locuteurs » : demande successivement le nom de chaque
locuteur actif (ex. « Intervieweur », « Candidat ») ; ces noms apparaissent dans
les exports.

---

## 2 bis. Édition du texte et coupe de passages (tagueur)

Le tagueur permet, au-delà du tagging des locuteurs :

### Éditer le texte d'un segment
**Double-clic** sur le texte d'un segment ouvre un champ éditable (corriger une
faute de transcription). `Entrée` valide, `Maj+Entrée` insère un retour à la
ligne, `Échap` annule. Les segments modifiés portent un petit anneau autour de
leur marqueur. Les corrections sont reprises dans les exports `.txt` / `.srt`.

### Sélection multiple
`Maj+↑` / `Maj+↓` (ou `Maj+clic`) étend la sélection à une plage de segments.
Une touche locuteur (`1`–`4`) tague alors **toute la plage** d'un coup.

### Couper un passage (hors-périmètre)
Pour retirer un passage de l'entretien (digression, hors-sujet) :

1. Sélectionner le(s) segment(s) (un seul, ou une plage avec `Maj+flèche`).
2. Cliquer **✂ Couper** (ou touche `C`). Les segments coupés apparaissent
   barrés/grisés dans la liste et en rouge dans la minimap. **C'est réversible** :
   re-presser `C` rétablit. Rien n'est détruit tant qu'on n'exporte pas.
3. Le compteur « ✂ Coupé » en haut indique le nombre de segments et la durée.

Quand le montage est terminé, **trois exports** :
- **Exporter .txt** / **Exporter .srt** : transcription **raccourcie**, avec la
  timeline **recalée** (segments coupés retirés, timestamps suivants décalés).
- **Exporter plan de coupe** : un fichier `plan_de_coupe.json` décrivant les
  intervalles audio à conserver. C'est l'entrée de `couper_audio.py` (ci-dessous).

> Modèle « montage vidéo » : on édite et on marque les coupes de façon
> non-destructive, puis on exporte une seule fois pour produire les fichiers
> raccourcis. Les fichiers d'origine ne sont jamais modifiés.

---

## 2 ter. Reconstruire l'audio coupé (`couper_audio.py`)

Le tagueur ne peut pas raccourcir l'audio lui-même (navigateur). Il exporte un
**plan de coupe** ; ce script applique la coupe sur l'audio via ffmpeg.

### Utilisation
```powershell
python tools\transcription\couper_audio.py plan_de_coupe.json
```
- Sans `--audio` : l'audio est pris dans le champ `audio_source` du plan
  (cherché dans le dossier courant, puis à côté du plan).
- Sans `--output` : écrit `<nom>_coupe<ext>` à côté de l'audio source.

Options :
```
--audio    Chemin de l'audio source (sinon pris dans le plan)
--output   Fichier de sortie (sinon <nom>_coupe<ext>)
--copy     Coupe en copie de flux (rapide mais IMPRECIS) — déconseillé
```

### Précision de la coupe
Par défaut le script **réencode** l'audio : la coupe est précise à la
milliseconde et **ne dérive pas**, quel que soit le nombre de coupes (l'écart
constaté est un offset de conteneur de l'ordre de ~20 ms, **non cumulatif**).
L'option `--copy` (copie de flux) est plus rapide mais coupe aux keyframes du
fichier compressé : elle peut désynchroniser et n'est pas recommandée.

### Résultat
Un nouvel audio raccourci, **parfaitement synchronisé** avec les `.srt` / `.txt`
exportés par le tagueur (mêmes intervalles). L'original n'est jamais modifié.

### Prérequis
ffmpeg dans le PATH (déjà installé par `bootstrap/setup-windows.ps1`).

---

## 3. Transcription robuste pour audios longs (`transcribe_robuste.py`)

Pour un entretien de plusieurs heures, une transcription d'un seul tenant est
**fragile** : une veille, une fermeture de fenêtre ou une coupure et tout est
perdu (WhisperX n'a pas de reprise native). Ce script découpe le travail en
tronçons sauvegardés au fur et à mesure.

### Fonctionnement
1. Découpe l'audio en tronçons (défaut 15 min) avec un léger chevauchement.
2. Transcrit chaque tronçon ; **le résultat est écrit sur disque dès qu'un
   tronçon est fini** (point de reprise).
3. **Reprise** : relancer la même commande saute les tronçons déjà faits et
   reprend où ça s'était arrêté.
4. **Fusion** : recolle les tronçons en réajustant les timestamps et en
   éliminant les doublons de chevauchement → `.txt` / `.srt` / `.json` finaux.

### Utilisation : appelable depuis le répertoire d'une mission

Ce script se lance **depuis le dossier de la mission** (le répertoire courant).
Il y écrit les livrables, et garde les fichiers intermédiaires côté IA-Powered-OS.

**Prérequis** : définir une fois `IA_POWERED_OS_HOME` vers la racine du repo
(voir plus bas). Sinon le script se rabat sur son propre emplacement, avec un
avertissement.

```powershell
# Depuis le dossier de la mission, ex. D:\Missions\Acme\
& "$env:IA_POWERED_OS_HOME\.venv\Scripts\python.exe" "$env:IA_POWERED_OS_HOME\tools\transcription\transcribe_robuste.py" --diarize
```

- **Sans argument** : traite TOUS les audios du répertoire courant.
- **Avec un nom de fichier** : ne traite que celui-là.

Options : `--chunk-min` (défaut 15, entier), `--overlap-sec` (défaut 2 ; porté
à 5 si `--diarize`), `--model`, `--language`, `--diarize`.

**Où vont les fichiers :**
- **Livrables** (`<nom>.srt`, `<nom>.txt`) → **répertoire de la mission** (courant).
- **Intermédiaires** (tronçons + `<nom>.json` complet) →
  `IA_POWERED_OS_HOME/data/.chunks/AAAAMMJJ-<nom>/` (isolés par date+nom).

En cas d'interruption, **relancer exactement la même commande** : la reprise
est automatique (tronçons déjà faits sautés).

### Définir IA_POWERED_OS_HOME (une fois)
```powershell
[Environment]::SetEnvironmentVariable("IA_POWERED_OS_HOME", "D:\Nicolas\IA-Powered-OS", [EnvironmentVariableTarget]::User)
```
Puis rouvrir PowerShell.

> ⚠️ La réconciliation des locuteurs (tagueur) exporte un `.srt`/`.txt` corrigé
> que tu déposes dans la mission, écrasant les fichiers initiaux. Au pire, seuls
> les locuteurs étaient faux : pas de perte de contenu.

### Diarisation par tronçon (option `--diarize`)
Par défaut, ce script ne diarise pas (sortie `.srt` sans locuteur → tagging
manuel). Avec `--diarize`, chaque tronçon est diarisé **indépendamment** et ses
locuteurs sont nommés **localement** : `T1-A`, `T1-B` (tronçon 1), `T2-A`,
`T2-B` (tronçon 2)…

Pourquoi local : pyannote n'attribue pas les mêmes étiquettes d'un tronçon à
l'autre (`SPEAKER_00` du tronçon 1 ≠ tronçon 2). Plutôt que de deviner la
correspondance automatiquement (fragile), le tagueur propose un **mode
réconciliation** : tu écoutes un extrait de chaque locuteur local et tu
l'associes à un locuteur global. Quelques clics règlent toute la « couture ».

```powershell
python tools\transcription\transcribe_robuste.py "data\entretien.m4a" --diarize
```

> `--diarize` requiert le token HF (config/.env) et porte le chevauchement à 5s
> pour fiabiliser la réconciliation. La diarisation reste imparfaite sur voix
> proches : c'est un pré-remplissage à vérifier, pas une vérité.

### Dossier de travail
Les tronçons sont conservés dans `data/.chunks/<nom>/` (gitignoré). Une fois la
transcription finale vérifiée, ce dossier est supprimable.

## Note sur la performance (CPU sans GPU NVIDIA)
- Transcription : ~1,1× la durée de l'audio (rapide).
- Diarisation auto : plus lente, et peu fiable sur voix proches → préférer
  `--no-diarize` + tagueur dans ce cas.
