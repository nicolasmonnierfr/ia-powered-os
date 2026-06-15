#!/usr/bin/env python3
"""
memoire.py — Modèle de persistance unifié du pipeline d'anonymisation (v2).

Ce module est le CONTRAT DE DONNÉES central, partagé par detecter.py,
appliquer.py, desanonymiser.py et l'éditeur (via le serveur). Il remplace
l'ancien couple `alias.yaml` (entrée) + `table_correspondance.json` (sortie)
par un ARTEFACT UNIQUE par client : `memoire_client.json`.

Pourquoi un seul fichier (refonte #14) :
  - L'ancien système séparait la mémoire des PSEUDOS (table.json) de la mémoire
    des DÉCISIONS de tri (ignorer/génériques, dans alias.yaml). Or les décisions
    de tri sont réutilisables d'un entretien à l'autre, mais ne survivaient pas :
    `--table` ne réinjectait que les pseudos. On re-triait les mêmes faux
    positifs à chaque transcript.
  - En fusionnant tout dans un artefact unique, réutilisé par client, la mémoire
    inter-séances devient complète : pseudos + canoniques + variantes + types +
    faux positifs + locuteurs génériques.

Pourquoi JSON (et plus YAML) :
  - L'édition se fait à 95 % par l'éditeur HTML, qui sérialise en JSON.stringify
    (fiable), au lieu d'un générateur YAML bricolé — source des bugs #8/#13.
  - detecter.py / appliquer.py manipulaient déjà du JSON pour la table.
  - L'édition manuelle marginale reste possible (indent=2, ordre stable).

Le TYPE est désormais un CHAMP EXPLICITE de chaque entrée (corrige #13) : il
n'est plus déduit du préfixe du pseudo. Les pseudos « parlants » (SOCIETE,
CONSULTANT_1) sont donc pleinement autorisés (corrige #8).

----------------------------------------------------------------------------
SCHÉMA de `memoire_client.json` (version 2) :

{
  "version": 2,
  "client": "Acme",
  "compteurs": { "PERSONNE": 3, "ORG": 1, "PRODUIT": 1 },
  "entrees": [
    {
      "pseudo": "PERSONNE_1",
      "type": "PERSONNE",
      "canonique": "Jean Dupont",
      "variantes": ["Jean Dupont", "Jean", "M. Dupont"],
      "source": "ner"           # ner | alias | manuel | etiquette
    },
    ...
  ],
  "ignorer": ["Ancienneté", "Synergie"],        # faux positifs SPÉCIFIQUES client
  "locuteurs_generiques": ["Interviewer", "Candidat"],
  "reglages": { "seuil_score": 0.5, "types": [...] }
}

`ignorer_global.json` (partagé tous clients, faux positifs universels) :
{ "version": 1, "ignorer": ["Bonjour", "Merci", "Madame", "Monsieur", ...] }
----------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Types internes du pipeline et mapping vers Presidio.
TYPES = ["PERSONNE", "LIEU", "ORG", "PRODUIT", "EMAIL", "TEL"]
TYPE_FROM_PRESIDIO = {
    "PERSON": "PERSONNE",
    "LOCATION": "LIEU",
    "ORGANIZATION": "ORG",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "TEL",
}
PRESIDIO_FROM_TYPE = {v: k for k, v in TYPE_FROM_PRESIDIO.items()}

# Nom canonique de l'artefact unique (marqueur de périmètre).
NOM_MEMOIRE = "memoire_client.json"
NOM_IGNORER_GLOBAL = "ignorer_global.json"

DEFAULT_REGLAGES = {
    "seuil_score": 0.5,
    "types": list(TYPE_FROM_PRESIDIO.keys()),
}


# ===========================================================================
# Structure vide / valeurs par défaut
# ===========================================================================
def memoire_vide(client: str | None = None) -> dict:
    return {
        "version": 2,
        "client": client,
        "compteurs": {},
        "entrees": [],
        "ignorer": [],
        "locuteurs_generiques": [],
        "reglages": dict(DEFAULT_REGLAGES),
    }


def _normaliser(mem: dict) -> dict:
    """Complète les clés manquantes d'une mémoire chargée (robustesse)."""
    mem.setdefault("version", 2)
    mem.setdefault("client", None)
    mem.setdefault("compteurs", {})
    mem.setdefault("entrees", [])
    mem.setdefault("ignorer", [])
    mem.setdefault("locuteurs_generiques", [])
    mem.setdefault("reglages", {})
    mem["reglages"].setdefault("seuil_score", DEFAULT_REGLAGES["seuil_score"])
    mem["reglages"].setdefault("types", list(DEFAULT_REGLAGES["types"]))
    # Compléter chaque entrée
    for e in mem["entrees"]:
        e.setdefault("pseudo", "")
        e.setdefault("type", type_from_pseudo(e.get("pseudo", "")))
        e.setdefault("variantes", [])
        e.setdefault("canonique",
                     max(e["variantes"], key=len) if e["variantes"] else e["pseudo"])
        e.setdefault("source", "ner")
    return mem


# ===========================================================================
# Lecture / écriture de l'artefact unique
# ===========================================================================
def charger_memoire(path: Path | None) -> dict:
    """Charge un memoire_client.json. Retourne une mémoire vide si absent."""
    if not path or not Path(path).exists():
        return memoire_vide()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return _normaliser(data)


def ecrire_memoire(path: Path, mem: dict) -> None:
    """Écrit la mémoire en JSON lisible (édition manuelle marginale possible)."""
    mem = _normaliser(mem)
    Path(path).write_text(
        json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")


def charger_ignorer_global(path: Path | None) -> list[str]:
    """Charge la liste des faux positifs universels (ou liste vide)."""
    if not path or not Path(path).exists():
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return list(data.get("ignorer", []))


# ===========================================================================
# Helpers de typage et de pseudos
# ===========================================================================
def type_from_pseudo(pseudo: str) -> str:
    """
    Déduit un type à partir du préfixe du pseudo. N'est plus qu'un FALLBACK :
    le type réel est porté par le champ `type` de l'entrée. Sert quand on n'a
    qu'un pseudo nu (ex. parsing d'un ancien alias.yaml).
    """
    base = (pseudo.split("_")[0] or "").upper() if pseudo else ""
    return base if base in TYPES else "PRODUIT"


def compteurs_depuis_entrees(entrees: list[dict]) -> dict:
    """(Re)calcule les compteurs (plus grand numéro par type) à partir des pseudos."""
    counters: dict[str, int] = {}
    for e in entrees:
        m = re.match(r"([A-ZÉ]+)_(\d+)$", e.get("pseudo", ""))
        if m:
            typ, num = m.group(1), int(m.group(2))
            counters[typ] = max(counters.get(typ, 0), num)
    return counters


def prochain_pseudo(typ: str, compteurs: dict) -> str:
    """Réserve et retourne le prochain pseudo libre d'un type (ex. PERSONNE_3)."""
    n = compteurs.get(typ, 0) + 1
    compteurs[typ] = n
    return f"{typ}_{n}"


# ===========================================================================
# Index pratiques (variante -> pseudo / entrée)
# ===========================================================================
def index_variantes(mem: dict) -> dict:
    """variante.lower() -> pseudo (pour réutiliser les pseudos d'une séance à l'autre)."""
    idx = {}
    for e in mem.get("entrees", []):
        for v in e.get("variantes", []):
            idx[v.lower()] = e["pseudo"]
    return idx


def mapping_remplacement(mem: dict) -> list[tuple[str, str]]:
    """
    Liste (variante, pseudo) triée par longueur décroissante, pour l'aller
    (anonymisation). Plus longues d'abord : « Jean Dupont » avant « Jean ».
    """
    mapping = []
    for e in mem.get("entrees", []):
        for v in e.get("variantes", []):
            mapping.append((v, e["pseudo"]))
    mapping.sort(key=lambda t: -len(t[0]))
    return mapping


def mapping_inverse(mem: dict, cible: str = "canonique") -> list[tuple[str, str]]:
    """
    Liste (pseudo, remplacement) pour le RETOUR (dé-anonymisation, #12).
    `cible` = "canonique" (forme longue) par défaut. Triée pour que PERSONNE_10
    soit traité avant PERSONNE_1 (sinon PERSONNE_1 casserait PERSONNE_10).
    """
    out = []
    for e in mem.get("entrees", []):
        repl = e.get(cible) or e.get("canonique") or e["pseudo"]
        out.append((e["pseudo"], repl))
    # Trier par longueur de pseudo décroissante (PERSONNE_10 avant PERSONNE_1).
    out.sort(key=lambda t: -len(t[0]))
    return out


# ===========================================================================
# Migration : ancien (alias.yaml + table.json) -> memoire_client.json
# ===========================================================================
def migrer_depuis_ancien(alias_path: Path | None, table_path: Path | None,
                         client: str | None = None) -> dict:
    """
    Construit une memoire v2 à partir d'un ancien alias.yaml et/ou table.json.

    - table.json fournit les entrées riches (pseudo/type/canonique/variantes).
    - alias.yaml fournit : les forçages (fusionnés comme entrées source=alias),
      les `ignorer` et `locuteurs_generiques` (qui étaient PERDUS auparavant).

    Le type des entrées issues de la table est conservé tel quel ; pour les
    forçages de l'alias sans entrée correspondante, on type via le préfixe
    (fallback) — l'utilisateur pourra corriger dans l'éditeur.
    """
    mem = memoire_vide(client)

    # 1. Reprendre la table existante (entrées riches).
    table = None
    if table_path and Path(table_path).exists():
        table = json.loads(Path(table_path).read_text(encoding="utf-8"))
        if not client and table.get("client"):
            mem["client"] = table["client"]
        for e in table.get("entrees", []):
            mem["entrees"].append({
                "pseudo": e["pseudo"],
                "type": e.get("type", type_from_pseudo(e["pseudo"])),
                "canonique": e.get("canonique", ""),
                "variantes": list(e.get("variantes", [])),
                "source": e.get("source", "ner"),
            })

    # 2. Reprendre l'alias.yaml (forçages + ignorer + génériques + réglages).
    if alias_path and Path(alias_path).exists():
        alias = _lire_ancien_alias_yaml(Path(alias_path))
        # forçages -> entrées (si pas déjà présentes via la table)
        existants = {e["pseudo"] for e in mem["entrees"]}
        for pseudo, variantes in alias.get("forcer", {}).items():
            if pseudo in existants:
                # compléter les variantes manquantes
                ent = next(e for e in mem["entrees"] if e["pseudo"] == pseudo)
                for v in variantes:
                    if v not in ent["variantes"]:
                        ent["variantes"].append(v)
            else:
                mem["entrees"].append({
                    "pseudo": pseudo,
                    "type": type_from_pseudo(pseudo),
                    "canonique": max(variantes, key=len) if variantes else pseudo,
                    "variantes": list(variantes),
                    "source": "alias",
                })
        # ignorer + génériques (l'info inter-séances jusque-là perdue)
        mem["ignorer"] = list(alias.get("ignorer", []))
        mem["locuteurs_generiques"] = list(alias.get("locuteurs_generiques", []))
        if alias.get("reglages"):
            mem["reglages"].update(alias["reglages"])

    # 3. Recalculer canoniques manquants + compteurs.
    for e in mem["entrees"]:
        if not e.get("canonique") and e["variantes"]:
            e["canonique"] = max(e["variantes"], key=len)
    mem["compteurs"] = compteurs_depuis_entrees(mem["entrees"])
    return _normaliser(mem)


def _lire_ancien_alias_yaml(path: Path) -> dict:
    """Lecture tolérante d'un ancien alias.yaml (nécessite pyyaml)."""
    try:
        import yaml
    except ImportError:
        raise SystemExit(
            "[ERREUR] pyyaml requis pour migrer un ancien alias.yaml. "
            "Installe-le (voir bootstrap).")
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    data.setdefault("forcer", {})
    data.setdefault("ignorer", [])
    data.setdefault("locuteurs_generiques", [])
    data.setdefault("reglages", {})
    return data
