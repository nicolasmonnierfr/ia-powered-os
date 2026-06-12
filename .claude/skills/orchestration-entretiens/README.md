# Orchestration des entretiens via Claude Code

Ce skill permet de piloter le pipeline de transcription depuis **Claude Code**,
qui s'exécute sur ta machine Windows et peut donc lancer les scripts WhisperX
(contrairement à Cowork, isolé dans un VM Linux).

## Pourquoi Claude Code et pas Cowork
Cowork s'exécute dans un VM Linux cloisonné : il ne voit pas ton `.venv`
Windows ni WhisperX. Claude Code, lancé dans un terminal Windows, atteint
l'interpréteur réel — il peut donc orchestrer la transcription.

## Mise en place (une fois)

1. Claude Code installé et fonctionnel (`claude --version`).
2. Lancer Claude Code depuis la racine du repo :
   ```powershell
   cd D:\Nicolas\IA-Powered-OS
   claude
   ```
3. Claude Code découvre automatiquement ce skill (dossier `.claude/skills/`).

## Usage

Dépose tes audios dans `data/a_traiter/`, puis demande à Claude Code, en langage
naturel :

- « Traite les entretiens en attente » → lance la transcription de chaque audio,
  un par un, range les sorties, te dit lesquels sont prêts à taguer.
- « Où en est le pipeline ? » → état (en attente / en cours / transcrit / à taguer).
- « Prépare le tagging » → liste les `.srt` prêts et rappelle comment ouvrir le tagueur.

Le tagging lui-même reste **manuel** (jugement humain) : ouvre
`tools/transcription/tagger.html`, charge l'audio + le `.srt`, réconcilie les
locuteurs.

## Circulation des fichiers

```
data/a_traiter/  ->  data/en_cours/  ->  data/transcrit/
                                    \->  data/a_taguer/ (le .srt)
```

Les transcriptions finales (.txt/.srt/.json) sont dans `data/transcriptions/`.

## Déclenchement planifié (optionnel)

Claude Code Desktop permet de planifier une tâche récurrente (onglet Routines /
tâches planifiées) qui exécute « traite les entretiens en attente » à une
cadence donnée. ⚠️ La tâche ne tourne que si la machine est éveillée et
Claude Code ouvert. Voir la doc Claude Code pour la configuration exacte.

## Limites importantes

- ⚠️ La transcription reste longue (CPU). Claude Code supprime la gestion
  (chemins, suivi), pas le temps de calcul.
- ⚠️ Un seul audio traité à la fois (CPU limité).
- ⚠️ Piloter des transcriptions via Claude Code consomme du quota d'usage.
