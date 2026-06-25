# Backlog — IA-Powered-OS

Évolutions identifiées, **à traiter**. Chaque item est décrit avec assez de
contexte pour être repris sans rediscussion.

> **Cycle de vie** : ce fichier ne contient QUE ce qui reste à faire. Quand un
> item est réalisé, il est décrit dans [`CHANGELOG.md`](CHANGELOG.md) (sous la
> version concernée, avec son numéro d'origine) **et retiré d'ici**. Les numéros
> sont des identifiants stables — ne pas les renuméroter.

---

## Transcription / diarisation

### 17. Diarisation globale en une passe (alternative à la réconciliation)
**Contexte** : la v1.9.0 a automatisé le recollage des locuteurs entre tronçons
par empreinte vocale (`reconcilier.py`, option « B »). Une approche « A » plus
propre existe : **diariser l'audio entier en une seule passe** pyannote (en
gardant le découpage uniquement pour la transcription Whisper), ce qui rend les
étiquettes **globalement cohérentes par construction** → plus aucune
réconciliation, ni manuelle ni par empreinte.

**Compromis** : perd la « résumabilité » fine de la diarisation et consomme plus
de mémoire/temps sur les très longs fichiers (pyannote reste bien plus léger que
Whisper ; un 1–2 h passe en général). À évaluer comme option de
`transcribe_robuste.py` (ex. `--diarize-global`) si la réconciliation par
empreinte montre ses limites sur certains entretiens (voix très proches).

**Sévérité** : confort / robustesse ; non urgent (B couvre le besoin actuel).

---

## Industrialisation / maintenabilité

### 20. Rationaliser le nommage des fonctions (numérotation / indices)
**Contexte** : le nombre de fonctions a sensiblement augmenté (wrappers
PowerShell `scripts/*.ps1`, helpers de `_commun.ps1`, modules Python de
`tools/`), au point qu'il devient difficile de s'y repérer. Souhait : un schéma
de nommage plus **lisible** — par exemple un préfixe ou un **indice** regroupant
les fonctions par domaine / ordre (`1_`, `2_`… ou un préfixe par module), pour
retrouver vite une fonction et son rôle.

**Pistes** : convention de préfixe par couche (affichage / repo / projet /
registre / synthèse…) ou table d'index en tête de fichier. Renommage **outillé**
(recherche/remplacement) pour ne casser aucun appel — à sécuriser idéalement par
un filet de tests (cf. `TODO.md` : test de bout en bout) avant de se lancer.

**Sévérité** : confort / maintenabilité ; non urgent (aucun impact fonctionnel).
