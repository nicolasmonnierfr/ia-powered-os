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
| `tagger.html`   | Lecteur audio + transcription synchronisée + tagging des locuteurs |

---

## 1. Transcription (`transcribe.py`)

### Prérequis
- Environnement installé via `bootstrap/setup-windows.ps1`
- Token Hugging Face dans `config/.env` (pour la diarisation)
- Licences pyannote acceptées (voir plus bas)

### Utilisation
Depuis la racine du repo, environnement activé (`(.venv)` visible) :

```powershell
python skills\transcription\transcribe.py "data\mon_entretien.m4a"
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
Double-clic sur `skills\transcription\tagger.html` (s'ouvre dans le navigateur).

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

### Utilisation
```powershell
python skills\transcription\transcribe_robuste.py "data\entretien_1h30.m4a"
```

Options : `--chunk-min` (défaut 15), `--overlap-sec` (défaut 2),
`--model`, `--language`, `--work-dir`, `--output-dir`.

En cas d'interruption, **relancer exactement la même commande** : la reprise
est automatique.

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
python skills\transcription\transcribe_robuste.py "data\entretien.m4a" --diarize
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
