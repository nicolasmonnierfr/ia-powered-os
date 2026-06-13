#!/usr/bin/env python3
"""
reconcilier.py — Réconciliation CLI du pipeline d'anonymisation (local).

Lit l'état intermédiaire produit par detecter.py et propose un parcours rapide
au clavier pour :
  - confirmer / corriger le pseudonyme et le type de chaque entité,
  - regrouper des variantes d'une même entité (Thomas/Tom, Marie/Marie Lefebvre)
    via des SUGGESTIONS automatiques que tu valides,
  - exclure les faux positifs,
  - déclarer des étiquettes de locuteurs génériques.

En sortie : un alias.yaml (mémoire de tes décisions), relisible par detecter.py
et par l'éditeur HTML. Pour les cas complexes, préférer l'éditeur HTML.

Usage :
    python reconcilier.py exemple.etat.json
    python reconcilier.py exemple.etat.json --out alias_acme.yaml
    python reconcilier.py exemple.etat.json --auto-fusion   # applique les fusions évidentes sans demander
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

TYPES = ["PERSONNE", "LIEU", "ORG", "PRODUIT", "EMAIL", "TEL"]


def die(msg, code=1):
    print(f"[ERREUR] {msg}", file=sys.stderr)
    sys.exit(code)


def norm(s):
    """Minuscule sans accents, pour comparer les variantes."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def type_from_pseudo(p):
    b = (p.split("_")[0] or "").upper()
    return b if b in TYPES else "PRODUIT"


# ---------------------------------------------------------------------------
# Suggestions de fusion : deux variantes PERSONNE probablement la même personne
# ---------------------------------------------------------------------------
def suggest_merges(groups):
    """
    Retourne une liste de paires (i, j) de groupes à fusionner probablement.
    Heuristiques prudentes (à confirmer par l'humain) :
      - l'un est sous-chaîne de l'autre en mots entiers (Marie ⊂ Marie Lefebvre) ;
      - même type PERSONNE et l'un est un prénom seul inclus dans l'autre.
    On ne fusionne JAMAIS d'office : on suggère.
    """
    suggestions = []
    pers = [g for g in groups if g["type"] == "PERSONNE"]
    for a in range(len(pers)):
        for b in range(a + 1, len(pers)):
            ga, gb = pers[a], pers[b]
            ta = " ".join(v["texte"] for v in ga["variants"])
            tb = " ".join(v["texte"] for v in gb["variants"])
            wa, wb = set(norm(ta).split()), set(norm(tb).split())
            # un ensemble de mots inclus dans l'autre (prénom ⊂ nom complet)
            if wa and wb and (wa <= wb or wb <= wa):
                suggestions.append((ga, gb, "un nom est inclus dans l'autre"))
    return suggestions


# ---------------------------------------------------------------------------
# Chargement état -> groupes
# ---------------------------------------------------------------------------
def load_groups(etat):
    by = {}
    for c in etat.get("candidats", []):
        key = c.get("pseudo_propose") or (c["type"] + "_?")
        if key not in by:
            by[key] = {"pseudo": key, "type": c["type"], "variants": []}
        by[key]["variants"].append({
            "texte": c["texte"], "occurrences": c.get("occurrences", 1),
            "score": c.get("score", 0), "source": c.get("source", "ner"),
            "exemple": (c.get("exemples") or [""])[0],
        })
    return list(by.values())


def merge_group(into, other, groups):
    for v in other["variants"]:
        if not any(x["texte"] == v["texte"] for x in into["variants"]):
            into["variants"].append(v)
    groups.remove(other)


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------
def ask(prompt, choices=None, default=None):
    while True:
        r = input(prompt).strip()
        if r == "" and default is not None:
            return default
        if choices is None or r.lower() in choices:
            return r.lower()
        print(f"  Réponse attendue : {', '.join(choices)}")


def main():
    ap = argparse.ArgumentParser(description="Réconciliation CLI des entités détectées.")
    ap.add_argument("etat", help="État intermédiaire JSON (detecter.py).")
    ap.add_argument("--out", help="alias.yaml de sortie (défaut: alias.yaml).")
    ap.add_argument("--auto-fusion", action="store_true",
                    help="Applique les fusions suggérées sans confirmation (prudent : à relire).")
    args = ap.parse_args()

    epath = Path(args.etat)
    if not epath.exists():
        die(f"État introuvable : {epath}")
    etat = json.loads(epath.read_text(encoding="utf-8"))
    groups = load_groups(etat)
    ignored, generiques = [], []

    print(f"\n=== Réconciliation — {etat.get('transcript','?')} ===")
    print(f"{len(groups)} entité(s) détectée(s).\n")

    # 1) Suggestions de fusion
    sugg = suggest_merges(groups)
    if sugg:
        print(f"-- {len(sugg)} fusion(s) probable(s) --")
    for ga, gb, raison in sugg:
        if ga not in groups or gb not in groups:
            continue  # déjà fusionné
        va = ", ".join(v["texte"] for v in ga["variants"])
        vb = ", ".join(v["texte"] for v in gb["variants"])
        print(f"\n  « {va} »  +  « {vb} »   ({raison})")
        if args.auto_fusion:
            r = "o"
        else:
            r = ask("  Même entité ? [o/N] ", ["o", "n", ""], default="n")
        if r == "o":
            # garde le groupe au nom le plus complet comme cible
            target = ga if len(" ".join(v["texte"] for v in ga["variants"])) >= \
                len(" ".join(v["texte"] for v in gb["variants"])) else gb
            other = gb if target is ga else ga
            merge_group(target, other, groups)
            print(f"    -> fusionnés sous {target['pseudo']}")

    # 2) Parcours des entités : valider / ignorer / générique / changer type
    print("\n-- Validation entité par entité --")
    print("   [Entrée]=garder  i=ignorer (faux positif)  g=locuteur générique")
    print("   t=changer type  q=finir maintenant\n")
    i = 0
    while i < len(groups):
        g = groups[i]
        va = ", ".join(v["texte"] for v in g["variants"])
        ex = next((v["exemple"] for v in g["variants"] if v["exemple"]), "")
        print("─" * 60)
        print(f"  Entité {i+1}/{len(groups)}")
        print(f"  Pseudo : {g['pseudo']}   Type : {g['type']}")
        print(f"  Texte  : « {va} »")
        if ex:
            print(f"  Contexte : {ex}")
        r = ask("  > action [Entrée/i/g/t/q] : ", ["", "i", "g", "t", "q"], default="")
        if r == "q":
            print("  (arrêt demandé — les entités restantes sont gardées telles quelles)")
            break
        elif r == "i":
            for v in g["variants"]:
                ignored.append(v["texte"])
            print(f"  -> « {va} » ignoré (ne sera pas anonymisé)")
            groups.pop(i)
            continue
        elif r == "g":
            for v in g["variants"]:
                generiques.append(v["texte"])
            print(f"  -> « {va} » marqué comme locuteur générique (conservé tel quel)")
            groups.pop(i)
            continue
        elif r == "t":
            nt = ask(f"    nouveau type {TYPES} : ", [x.lower() for x in TYPES])
            g["type"] = nt.upper()
            if "_?" in g["pseudo"] or not re.search(r"_\d+$", g["pseudo"]):
                g["pseudo"] = g["type"] + "_?"
            print(f"  -> type changé en {g['type']}")
            continue  # re-afficher l'entité
        i += 1

    # 3) Export alias.yaml
    out = Path(args.out) if args.out else Path("alias.yaml")
    write_yaml(out, groups, ignored, generiques, etat.get("transcript", ""))
    print(f"\n[OK] alias.yaml écrit : {out}")
    print("     Relis-le, puis relance detecter.py --alias, ou applique avec appliquer.py.")
    if any(not re.search(r"_\d+$", g["pseudo"]) for g in groups):
        print("     /!\\ Certains pseudos sont incomplets (PERSONNE_?). "
              "Numérote-les dans l'éditeur HTML ou à la main.")


def yq(s):
    return '"' + str(s).replace('"', '\\"') + '"'


def write_yaml(path, groups, ignored, generiques, transcript):
    out = "# alias.yaml — généré par reconcilier.py\n"
    if transcript:
        out += f"# Transcript de référence : {transcript}\n"
    out += "\nforcer:\n"
    for g in groups:
        out += f"  {g['pseudo']}:\n"
        for v in g["variants"]:
            out += f"    - {yq(v['texte'])}\n"
    out += "\nignorer:\n"
    out += "  []\n" if not ignored else "".join(f"  - {yq(x)}\n" for x in ignored)
    out += "\nlocuteurs_generiques:\n"
    out += "  []\n" if not generiques else "".join(f"  - {yq(x)}\n" for x in generiques)
    out += "\nreglages:\n  seuil_score: 0.5\n"
    out += '  types: ["PERSON","LOCATION","ORGANIZATION","EMAIL_ADDRESS","PHONE_NUMBER"]\n'
    path.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
