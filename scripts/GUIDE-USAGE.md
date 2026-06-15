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
    ├── 1_transcription/              ia transcrire
    │   ├── entretien_dupont.txt
    │   └── entretien_dupont.srt
    ├── 2_coupe/                      ia taguer + ia couper
    │   ├── plan_de_coupe.json
    │   ├── entretien_dupont_coupe.m4a
    │   ├── entretien_dupont_coupe.srt
    │   └── entretien_dupont_coupe.txt
    └── 3_anonymisation/             ia anonymiser
        ├── entretien_dupont_coupe.etat.json
        ├── entretien_dupont_coupe_anonymise.srt
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
- Tu identifies les locuteurs et marques les passages à couper.
- Bouton **« Exporter vers 2_coupe »** : écrit `plan_de_coupe.json` +
  `..._coupe.srt` + `..._coupe.txt`, cohérents, directement dans `2_coupe\`.
- Le serveur local s'arrête **quand tu fermes l'onglet** (ou Ctrl+C dans la
  fenêtre PowerShell).

### 3. Couper l'audio

```powershell
ia couper
```

- Trouve `plan_de_coupe.json` dans `2_coupe\` et reconstruit l'audio raccourci
  `..._coupe.m4a` (réencodage précis à la milliseconde).

### 4. Anonymiser (trois temps)

```powershell
ia analyser
```

- Détecte les entités (NER local, 100 % hors ligne).
- Ouvre l'**éditeur** dans Chrome : tu valides les entités, corriges
  les types, exclus les faux positifs.
- Bouton **« Exporter la mémoire »** : écrit `memoire_client.json` au niveau du
  **périmètre** (voir ci-dessous).

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
| `ia taguer` | tagging locuteurs + plan de coupe | `2_coupe\` |
| `ia couper` | audio raccourci | `2_coupe\` |
| `ia analyser` | détection + validation | `memoire_client.json` (périmètre) |
| `ia anonymiser` | application du remplacement | `3_anonymisation\` |
| `ia repersonnaliser` | réinjection des vrais noms (#12) | `..._REPERSONNALISE` |
| `ia setenv` | active le venv | session courante |
| `ia aide` | liste les commandes | — |
