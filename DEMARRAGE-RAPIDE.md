# Démarrage rapide — IA-Powered-OS

Procédure complète pour une **première installation** sur une machine Windows.

## 1. Récupérer le repo

```powershell
git clone <ton-url-github>/IA-Powered-OS.git
cd IA-Powered-OS
```

## 2. Lancer le bootstrap

```powershell
.\bootstrap\setup-windows.ps1
```

⚠️ Si PowerShell refuse d'exécuter le script (politique d'exécution), lance
d'abord, dans la **même** fenêtre :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Le script peut demander de **fermer/rouvrir PowerShell** après l'installation
de Python ou ffmpeg, puis d'être **relancé**. C'est normal.

## 3. Configurer le token Hugging Face

a. Créer un compte sur https://huggingface.co
b. Générer un token : https://huggingface.co/settings/tokens (type "Read")
c. Accepter les licences (connecté) :
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0
d. Coller le token dans `config\.env` (ligne `HUGGINGFACE_TOKEN=`)

## 4. Activer l'environnement

```powershell
.\.venv\Scripts\Activate.ps1
```

(À refaire à chaque nouvelle session de travail.)

## 5. Installer la commande `ia` (recommandé)

Pour piloter tous les outils sans retenir de longues lignes de commande :

```powershell
.\scripts\installer-ia.ps1
```

Ouvre un **nouveau** terminal, puis :

```powershell
ia aide
```

Détails complets : `scripts\GUIDE-USAGE.md`.

## 6. Premier test

Crée un dossier d'entretien, dépose-y un audio, place-toi dedans :

```powershell
mkdir entretien_test ; cd entretien_test
# (copie un audio ici)
ia transcrire
```

Les résultats apparaissent dans `1_transcription\`. La suite du workflow
(`ia taguer`, `ia couper`, `ia anonymiser`) est décrite dans le guide d'usage.

> Sans la commande `ia`, tu peux toujours appeler les scripts directement,
> p. ex. `python tools\transcription\transcribe_robuste.py "entretien.m4a"`.

---

## Réinstallation sur une autre machine

Identique : `git clone` → bootstrap → token → `installer-ia.ps1`. Le repo porte
la recette complète ; seuls le token et les audios sont propres à la machine.
