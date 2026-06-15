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

En sortie : un memoire_client.json (refonte #14), relisible par detecter.py,
appliquer.py et l'éditeur HTML. Pour les cas complexes, préférer l'éditeur HTML.

Usage :
    python reconcilier.py exemple.etat.json
    python reconcilier.py exemple.etat.json --out memoire_client.json
    python reconcilier.py exemple.etat.json --memoire memoire_client.json  # fusionne dans une mémoire existante
    python reconcilier.py exemple.etat.json --auto-fusion
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import memoire as M  # noqa: E402

TYPES = M.TYPES


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
    ap.add_argument("--out", help=f"Sortie (défaut: {M.NOM_MEMOIRE}).")
    ap.add_argument("--memoire", help="memoire_client.json existant à enrichir.")
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

    # 3) Export memoire_client.json (refonte #14)
    out = Path(args.out) if args.out else Path(M.NOM_MEMOIRE)
    mem = M.charger_memoire(Path(args.memoire)) if args.memoire else M.memoire_vide()
    fusionner_dans_memoire(mem, groups, ignored, generiques)
    M.ecrire_memoire(out, mem)
    print(f"\n[OK] memoire_client.json écrit : {out}")
    print("     Relis-le, puis relance detecter.py --memoire, ou applique avec appliquer.py.")
    incomplets = [g["pseudo"] for g in groups if "_?" in g["pseudo"] or not g["pseudo"].strip()]
    if incomplets:
        print(f"     /!\\ Pseudos incomplets : {', '.join(incomplets)}. "
              "Corrige-les dans l'éditeur HTML ou à la main.")


def fusionner_dans_memoire(mem, groups, ignored, generiques):
    """Injecte les groupes/ignorer/generiques validés dans une mémoire (refonte #14)."""
    par_pseudo = {e["pseudo"]: e for e in mem["entrees"]}
    for g in groups:
        pseudo = (g["pseudo"] or "").strip()
        if not pseudo:
            continue
        variantes = [v["texte"] for v in g["variants"]]
        canonique = max(variantes, key=len) if variantes else pseudo
        if pseudo in par_pseudo:
            e = par_pseudo[pseudo]
            for vt in variantes:
                if vt not in e["variantes"]:
                    e["variantes"].append(vt)
            e["type"] = g["type"]
            e["canonique"] = max(e["variantes"], key=len)
        else:
            e = {"pseudo": pseudo, "type": g["type"], "canonique": canonique,
                 "variantes": variantes,
                 "source": "alias" if any(v.get("source") == "alias" for v in g["variants"]) else "manuel"}
            mem["entrees"].append(e); par_pseudo[pseudo] = e
    for x in ignored:
        if x not in mem["ignorer"]:
            mem["ignorer"].append(x)
    for x in generiques:
        if x not in mem["locuteurs_generiques"]:
            mem["locuteurs_generiques"].append(x)
    mem["compteurs"] = M.compteurs_depuis_entrees(mem["entrees"])


if __name__ == "__main__":
    main()
