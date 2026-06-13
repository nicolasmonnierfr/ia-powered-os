# Outil : Anonymisation de transcripts

Produit, à partir d'un transcript taggé (sortie du tagueur), une version
**anonymisée** envoyable à une IA externe, tout en gardant en local une **table
de correspondance** qui permet de ré-identifier. Tout tourne **en local** via
Presidio (spaCy FR) ; aucun texte n'est envoyé en ligne par l'outil.

## Ce qui est anonymisé
Personnes, lieux, organisations, emails, téléphones (FR). Les noms de produits
ou de projets (que le modèle ne détecte pas) se déclarent dans les alias.
Dates et montants ne sont pas traités par défaut.

Remplacement par **pseudonymes typés cohérents** : `PERSONNE_1`, `LIEU_1`,
`ORG_1`, `PRODUIT_1`, `EMAIL_1`, `TEL_1`. Une même entité (et toutes ses
variantes, ex. « Thomas »/« Tom ») reçoit toujours le même pseudonyme.

## Composants

| Fichier | Rôle |
|---------|------|
| `detecter.py` | Détecte les entités (Presidio + alias) → état intermédiaire `.etat.json` |
| `editeur_alias.html` | Édite/regroupe visuellement les entités, exporte `alias.yaml` |
| `reconcilier.py` | Réconciliation CLI rapide (suggestions de fusion) → `alias.yaml` |
| `appliquer.py` | Applique l'anonymisation → transcript anonymisé + table + rapport |
| `alias.example.yaml` | Modèle de configuration (à copier/adapter) |
| `SCHEMA.md` | Format des fichiers (contrat de données) |

## Workflow

```
transcript taggé (.txt/.srt)
        │
        ▼
  detecter.py  ──►  <nom>.etat.json   (entités détectées)
        │
        ▼  (validation humaine : un des deux)
  editeur_alias.html   OU   reconcilier.py   ──►  alias.yaml
        │
        ▼
  appliquer.py  ──►  <nom>_anonymise.{txt,srt}   (à envoyer)
                     table_correspondance.json   (À GARDER EN LOCAL)
                     <nom>_rapport.txt            (relecture)
```

### 1. Détecter
```powershell
python tools\anonymisation\detecter.py "data\entretien.srt"
# réutiliser une table d'un précédent entretien du même client :
python tools\anonymisation\detecter.py "data\entretien.srt" --table table_acme.json
```

### 2. Valider / regrouper (au choix)
- **Visuel** : ouvrir `editeur_alias.html`, charger `entretien.etat.json`,
  regrouper les variantes (glisser-déposer), corriger les types, exclure les
  faux positifs, exporter `alias.yaml`.
- **CLI rapide** :
  ```powershell
  python tools\anonymisation\reconcilier.py "data\entretien.etat.json" --out alias.yaml
  ```
  Propose les fusions probables (« Marie » ⊂ « Marie Lefebvre »), validation
  au clavier.

> Les deux produisent le même `alias.yaml`. On peut enchaîner CLI puis HTML.

### 3. Appliquer
```powershell
python tools\anonymisation\appliquer.py "data\entretien.srt" --alias alias.yaml --client Acme
# enrichir une table existante (entretien suivant du même client) :
python tools\anonymisation\appliquer.py "data\entretien.srt" --alias alias.yaml --table table_acme.json
```

## La table de correspondance : pivot du système
`table_correspondance.json` joue **trois rôles** :
1. **Sortie** : la correspondance pseudonyme ↔ réel.
2. **Clé de ré-identification**, gardée en local — **ne jamais l'envoyer**.
3. **Mémoire d'entrée** : rechargée (`--table`) pour le prochain entretien du
   même client, elle réutilise les pseudonymes déjà attribués et ne traite que
   les entités nouvelles. Le système devient cumulatif par client.

## Limites — à connaître
- ⚠️ **Aucune anonymisation auto n'est fiable à 100 %.** Le modèle rate des
  entités (surnoms, noms mal transcrits, infos ré-identifiantes indirectes type
  « le DAF de Toulouse en 2019 »). **Relire le transcript anonymisé avant
  envoi** (le rapport aide).
- Le filet de sécurité, c'est la **liste d'alias** : plus tu l'enrichis (et la
  réutilises par client), plus le résultat est sûr.
- Les téléphones FR sont détectés par une règle regex dédiée (le détecteur
  générique de Presidio les rate). Formats couverts : `0X XX XX XX XX` et
  `+33 X …` avec séparateurs espace/point/tiret.
- Modèle spaCy `fr_core_news_md` (équilibré). Pour plus de précision au prix du
  poids, basculer sur `fr_core_news_lg` (voir bootstrap).

## Prérequis
Installés par `bootstrap/setup-windows.ps1` : `presidio-analyzer`,
`presidio-anonymizer`, `pyyaml`, et le modèle `fr_core_news_md`.
