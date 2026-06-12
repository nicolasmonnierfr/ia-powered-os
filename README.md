# IA-Powered-OS

Environnement de travail personnel pour le traitement de missions de conseil
assisté par IA. Regroupe des scripts, skills et configurations réutilisables et
redéployables sur n'importe quelle machine.

## Philosophie

Ce repo ne contient **pas** l'environnement installé, mais **la recette pour le
reconstruire**. Sur une nouvelle machine :

```
git clone <url>
cd IA-Powered-OS
# suivre bootstrap/setup-windows.ps1
```

## Structure

```
IA-Powered-OS/
├── bootstrap/        Scripts d'installation (prérequis système, venv)
├── skills/           Modules métier autonomes
│   └── transcription/  Transcription d'entretiens (WhisperX)
├── scripts/          Utilitaires transversaux
├── config/           Modèles de configuration (.env.example)
├── data/             Données locales (gitignoré : audios, transcriptions)
└── requirements.txt  Dépendances Python
```

## Règles d'or

- **Aucun secret dans Git** : tokens et clés vont dans `config/.env`
  (gitignoré). Le modèle est `config/.env.example`.
- **Aucune donnée sensible dans Git** : tout `data/` est exclu.
- **Tout est reproductible** : tout binaire installé manuellement doit être
  documenté dans un script de `bootstrap/`.

## Skills disponibles

| Skill | Description | État |
|-------|-------------|------|
| `transcription` | Transcription + diarisation d'entretiens (WhisperX, local) | En cours |

## Plateforme

Conçu et testé sous **Windows 11**. Les scripts d'install sont en PowerShell.
Portage Linux/macOS possible (ffmpeg + Python identiques, scripts à adapter).
