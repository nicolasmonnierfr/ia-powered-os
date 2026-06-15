# Outil : Anonymisation de transcripts

Produit, à partir d'un transcript taggé (sortie du tagueur), une version
**anonymisée** envoyable à une IA externe, tout en gardant en local une
**mémoire client** qui permet de ré-identifier. Tout tourne **en local** via
Presidio (spaCy FR) ; aucun texte n'est envoyé en ligne par l'outil.

## Ce qui est anonymisé
Personnes, lieux, organisations, emails, téléphones (FR). Les noms de produits
ou de projets (que le modèle ne détecte pas) se déclarent dans la mémoire.
Dates et montants ne sont pas traités par défaut.

Remplacement par **pseudonymes typés cohérents** : `PERSONNE_1`, `LIEU_1`,
`ORG_1`, `PRODUIT_1`, `EMAIL_1`, `TEL_1` — ou des pseudos **parlants** au choix
(`SOCIETE`, `CONSULTANT_1`). Une même entité et toutes ses variantes
(ex. « Thomas »/« Tom ») reçoivent toujours le même pseudonyme.

## Mémoire unique par client (refonte #14)
Toute la mémoire d'un client tient dans **un seul fichier**,
`memoire_client.json` : pseudos + canoniques + variantes + types + faux
positifs (propres au client) + locuteurs génériques + réglages. Il est trouvé
par **recherche ascendante** depuis l'entretien (= le « périmètre »). Un second
fichier partagé, `config/ignorer_global.json`, liste les faux positifs
universels (politesses, titres). Voir `SCHEMA.md` pour le contrat complet.

> Migration depuis l'ancien format (`alias.yaml` + `table_correspondance.json`) :
> voir `migrer.py` plus bas.

## Composants

| Fichier | Rôle |
|---------|------|
| `memoire.py` | **Module central** : lecture/écriture de `memoire_client.json`, mappings, migration. |
| `detecter.py` | Détecte les entités (Presidio + mémoire) → état intermédiaire `.etat.json` |
| `editeur_alias.html` | Édite/regroupe visuellement les entités, exporte `memoire_client.json` |
| `reconcilier.py` | Réconciliation CLI rapide (suggestions de fusion) → `memoire_client.json` |
| `appliquer.py` | Applique l'anonymisation → transcript anonymisé + mémoire à jour + rapport |
| `desanonymiser.py` | **Chemin inverse (#12)** : réinjecte les vrais noms dans un rapport |
| `migrer.py` | Convertit l'ancien `alias.yaml` (+ table) en `memoire_client.json` |
| `memoire_client.example.json` | Modèle de mémoire (à copier/adapter) |
| `SCHEMA.md` | Format des fichiers (contrat de données) |

## Workflow

```
transcript taggé (.txt/.srt)
        │
        ▼
  detecter.py  ──►  <nom>.etat.json   (entités détectées)
        │
        ▼  (validation humaine : un des deux)
  editeur_alias.html   OU   reconcilier.py   ──►  memoire_client.json
        │
        ▼
  appliquer.py  ──►  <nom>_anonymise.{txt,srt}   (à envoyer)
                     memoire_client.json (mise à jour, À GARDER EN LOCAL)
                     <nom>_rapport.txt            (relecture)
        │
        ▼  (après analyse par l'IA externe, pour livrer au client)
  desanonymiser.py  ──►  <nom>_REPERSONNALISE.{md,docx,…}   (vrais noms — LOCAL)
```

### 1. Détecter
```powershell
python tools\anonymisation\detecter.py "data\entretien.srt"
# réutiliser la mémoire d'un précédent entretien du même client :
python tools\anonymisation\detecter.py "data\entretien.srt" --memoire memoire_client.json --ignorer-global config\ignorer_global.json
```

### 2. Valider / regrouper (au choix)
- **Visuel** : ouvrir `editeur_alias.html`, charger `entretien.etat.json` (et
  éventuellement une `memoire_client.json` existante), regrouper les variantes
  (glisser-déposer), corriger les types, exclure les faux positifs, déclarer les
  locuteurs génériques, exporter `memoire_client.json`.
- **CLI rapide** :
  ```powershell
  python tools\anonymisation\reconcilier.py "data\entretien.etat.json" --out memoire_client.json
  # enrichir une mémoire existante :
  python tools\anonymisation\reconcilier.py "data\entretien.etat.json" --memoire memoire_client.json
  ```
  Propose les fusions probables (« Marie » ⊂ « Marie Lefebvre »), validation
  au clavier.

> Les deux produisent le même `memoire_client.json`. On peut enchaîner CLI puis HTML.

### 3. Appliquer
```powershell
python tools\anonymisation\appliquer.py "data\entretien.srt" --memoire memoire_client.json --client Acme --ignorer-global config\ignorer_global.json
```
La mémoire est mise à jour en place (nouveaux pseudos ajoutés). Au prochain
entretien du même client, elle réutilise les pseudonymes déjà attribués et ne
traite que les entités nouvelles : le système est **cumulatif par client**.

### 4. Repersonnaliser un rapport (#12)
Une fois l'analyse revenue de l'IA externe (avec des pseudos), réinjecte les
vrais noms pour livrer au dirigeant :
```powershell
python tools\anonymisation\desanonymiser.py "rapport.md" --memoire memoire_client.json
# variante la plus courte (prénoms) au lieu du nom complet :
python tools\anonymisation\desanonymiser.py "rapport.md" --memoire memoire_client.json --court
```
Formats pris en charge : `.txt`, `.md`, `.srt`, `.docx`.
> ⚠️ Le fichier produit (`…_REPERSONNALISE`) contient les **vrais noms** :
> ne jamais le renvoyer à une IA externe.

## Migration depuis l'ancien format
```powershell
# convertit alias.yaml (+ table) du dossier client en memoire_client.json
python tools\anonymisation\migrer.py --dir "D:\Missions\Acme"
```
Récupère au passage les `ignorer`/`locuteurs_generiques` de l'alias, qui
n'étaient pas mémorisés entre séances auparavant. Les scripts acceptent aussi
l'ancien format à la volée (`--alias`/`--table`) sans réécriture.

## La mémoire client : pivot du système
`memoire_client.json` joue **trois rôles** :
1. **Sortie** : la correspondance pseudonyme ↔ réel (+ décisions de tri).
2. **Clé de ré-identification**, gardée en local — **ne jamais l'envoyer**.
3. **Mémoire d'entrée** : rechargée pour le prochain entretien du même client,
   elle réutilise les pseudonymes déjà attribués et ne traite que les entités
   nouvelles.

## Limites — à connaître
- ⚠️ **Aucune anonymisation auto n'est fiable à 100 %.** Le modèle rate des
  entités (surnoms, noms mal transcrits, infos ré-identifiantes indirectes type
  « le DAF de Toulouse en 2019 »). **Relire le transcript anonymisé avant
  envoi** (le rapport aide).
- Le filet de sécurité, c'est la **mémoire** : plus tu l'enrichis (et la
  réutilises par client), plus le résultat est sûr.
- Les téléphones FR sont détectés par une règle regex dédiée (le détecteur
  générique de Presidio les rate). Formats couverts : `0X XX XX XX XX` et
  `+33 X …` avec séparateurs espace/point/tiret.
- Modèle spaCy `fr_core_news_md` (équilibré). Pour plus de précision au prix du
  poids, basculer sur `fr_core_news_lg` (voir bootstrap).

## Prérequis
Installés par `bootstrap/setup-windows.ps1` : `presidio-analyzer`,
`presidio-anonymizer`, `pyyaml` (pour la migration), `python-docx` (pour
repersonnaliser des .docx), et le modèle `fr_core_news_md`.
