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

## 5. Premier test

Dépose un fichier audio dans `data\`, puis :

```powershell
python skills\transcription\transcribe.py "data\ton_entretien.m4a"
```

Les résultats apparaissent dans `data\transcriptions\`.

---

## Réinstallation sur une autre machine

Identique : `git clone` → bootstrap → token → c'est tout. Le repo porte la
recette complète ; seuls le token et les audios sont propres à la machine.
