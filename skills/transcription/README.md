# Skill : Transcription d'entretiens

Transcription automatique d'entretiens audio/vidéo avec séparation des
locuteurs (diarisation 2 voix), en local via WhisperX. Aucune donnée n'est
envoyée sur Internet (hors téléchargement initial des modèles).

## Prérequis

- Environnement installé via `bootstrap/setup-windows.ps1`
- Token Hugging Face renseigné dans `config/.env`
- Licences pyannote acceptées (voir ci-dessous)

## Acceptation des licences pyannote (à faire UNE fois)

Connecté à ton compte Hugging Face, visiter et accepter les conditions sur :

- https://huggingface.co/pyannote/speaker-diarization-3.1
- https://huggingface.co/pyannote/segmentation-3.0

## Utilisation

Depuis la racine du repo, environnement activé :

```powershell
python skills\transcription\transcribe.py "data\mon_entretien.m4a"
```

Options :

```
--model      large-v3 (defaut) | medium | small ...
--language   fr (defaut)
--speakers   2 (defaut, nb de locuteurs attendus)
--no-diarize Desactive la diarisation (plus rapide, sans "qui parle")
--output-dir Dossier de sortie (defaut : data/transcriptions)
```

## Sorties

Pour chaque entretien, génère dans `data/transcriptions/` :

- `<nom>.txt`  : transcription lisible, format `[locuteur] texte`
- `<nom>.json` : données complètes (segments, timestamps, locuteurs)

## Formats d'entrée acceptés

Tout ce que ffmpeg lit : mp3, m4a, wav, flac, ogg, mp4, mkv, webm...

## Note sur la performance

⚠️ En CPU (sans GPU NVIDIA), la diarisation est lente : compter un temps de
traitement supérieur à la durée de l'audio. Pour un entretien d'1h, lancer le
traitement et faire autre chose. La transcription seule (--no-diarize) est
nettement plus rapide.
