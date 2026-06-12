---
name: orchestration-entretiens
description: >
  Orchestre le pipeline de transcription d'entretiens audio sur cette machine.
  À utiliser quand l'utilisateur demande de traiter, transcrire, lancer, suivre
  ou faire avancer des entretiens ; de regarder les entretiens en attente ou
  prêts à taguer ; de ranger les transcriptions ; ou de faire le point sur l'état
  du pipeline. Couvre la découverte des audios déposés, le lancement de la
  transcription robuste (tronçons + reprise + diarisation par tronçon), le suivi
  d'état par dossiers, et le rangement des sorties.
---

# Orchestration du pipeline d'entretiens

Ce skill pilote la transcription d'entretiens via les scripts du repo. Le calcul
lourd (WhisperX) est fait par les scripts Python ; ce skill se charge de
**découvrir le travail, lancer, suivre et ranger**.

## Environnement (à respecter strictement)

- Les commandes Python DOIVENT utiliser l'interpréteur du venv du repo :
  `.venv\Scripts\python.exe` (Windows). Ne jamais appeler `python` nu (un
  `python.ps1` parasite peut exister sur le système).
- Travailler depuis la racine du repo (le dossier contenant `.venv` et `skills`).
- Ne jamais committer, déplacer ou supprimer le contenu de `config/.env`.

## Convention de dossiers (pipeline)

Les audios circulent dans `data/` selon leur état :

| Dossier | Sens |
|---------|------|
| `data/a_traiter/`  | Audios déposés, en attente de transcription |
| `data/en_cours/`   | Audio en cours de transcription (un seul à la fois) |
| `data/transcrit/`  | Audios dont la transcription est terminée |
| `data/a_taguer/`   | Transcriptions `.srt` prêtes pour le tagueur |
| `data/archive/`    | Audios sources archivés après traitement |

Les transcriptions finales (`.txt`, `.srt`, `.json`) vont dans
`data/transcriptions/` (comportement par défaut des scripts).

## Procédure : traiter les entretiens en attente

Quand l'utilisateur demande de traiter / lancer / faire avancer les entretiens :

1. **Lister** les audios présents dans `data/a_traiter/` (extensions audio/vidéo
   courantes : .m4a .mp3 .wav .mp4 .mkv .webm .flac .ogg .aac).
   - Si vide : le dire et s'arrêter.
2. **Pour chaque audio**, dans l'ordre alphabétique, séquentiellement (jamais en
   parallèle — le CPU ne suffit pas) :
   a. Déplacer l'audio de `a_traiter/` vers `en_cours/`.
   b. Lancer la transcription robuste avec diarisation par tronçon :
      ```
      .venv\Scripts\python.exe tools\transcription\transcribe_robuste.py "data\en_cours\<fichier>" --diarize
      ```
   c. ⚠️ Cette commande est LONGUE (souvent supérieure à la durée de l'audio).
      La laisser finir. Si elle est interrompue, la relancer À L'IDENTIQUE :
      le script reprend tout seul là où il s'était arrêté (tronçons déjà faits
      sautés).
   d. Quand elle réussit (sorties `.txt`/`.srt`/`.json` présentes dans
      `data/transcriptions/` pour ce fichier) :
      - copier le `.srt` produit vers `data/a_taguer/`,
      - déplacer l'audio de `en_cours/` vers `transcrit/` (garder le nom original),
      - laisser une copie de l'audio dans `archive/` si demandé.
3. **Rendre compte** : nombre d'entretiens traités, en attente, prêts à taguer.

## Procédure : faire le point (état du pipeline)

Quand l'utilisateur demande l'état / le point / "où on en est" :

- Compter et lister les fichiers de chaque dossier (`a_traiter`, `en_cours`,
  `transcrit`, `a_taguer`).
- Présenter un récapitulatif court, par exemple :
  « 6 entretiens : 4 transcrits, 1 en cours, 1 en attente. 4 prêts à taguer. »
- Ne PAS relancer de transcription sans demande explicite.

## Procédure : préparer le tagging

Quand l'utilisateur veut taguer :

- Lister les `.srt` dans `data/a_taguer/`.
- Rappeler que le tagging est manuel : ouvrir `tools/transcription/tagger.html`
  dans le navigateur, y charger l'audio (depuis `transcrit/` ou `archive/`) et le
  `.srt` correspondant. La réconciliation des locuteurs (étiquettes T1-A, T2-B…)
  se fait dans le tagueur.
- Ne pas tenter de taguer automatiquement : c'est un travail de jugement humain.

## Règles de sécurité et de prudence

- ⚠️ Traiter un seul audio à la fois (CPU limité).
- ⚠️ Ne jamais supprimer un audio source tant que sa transcription n'est pas
  confirmée présente. En cas de doute, déplacer plutôt que supprimer.
- ⚠️ Si une transcription échoue 2 fois de suite sur le même fichier, ne pas
  insister : le signaler à l'utilisateur avec le message d'erreur, et passer au
  suivant.
- Toujours montrer à l'utilisateur les commandes lancées et leur sortie.
- Demander confirmation avant tout déplacement massif ou toute suppression.

## Référence des scripts

- `tools/transcription/transcribe_robuste.py` — transcription longue, robuste
  (tronçons + reprise). Option `--diarize` pour la diarisation par tronçon.
- `tools/transcription/transcribe.py` — transcription simple (audios courts).
- `tools/transcription/tagger.html` — tagueur de locuteurs (manuel).
- Voir `tools/transcription/README.md` pour le détail des options.
