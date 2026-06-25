#!/usr/bin/env python3
"""
garde_fou.py — Filet anti-fuite avant tout envoi a l'IA (synthese multi-entretiens).

Principe : on assemble le PAYLOAD exact qui partirait vers l'IA — uniquement
`id` (label neutre), `role`, `interviewe` (pseudonyme) et le CONTENU anonymise —,
puis on le confronte a la memoire client (LOCALE, jamais envoyee). Les `variantes`
et `canonique` de la memoire SONT les vrais noms ; l'anonymiseur les a deja tous
remplaces. On rejoue donc son matcher (memes frontieres \b, insensible a la casse)
sur le texte deja anonymise : la moindre correspondance = un RATE d'anonymisation
=> on BLOQUE l'envoi.

Deux protections distinctes :
  1. Le nom de FICHIER ne part jamais : le payload ne porte que `id` + contenu
     (garantie STRUCTURELLE — aucun champ chemin/nom de fichier).
  2. Le CONTENU est scanne contre les vrais noms de la memoire (+ nom du client).

100% local, stdlib uniquement.

Usage :
    python garde_fou.py <manifeste> [--dump payload.json]
    # code de sortie : 0 = sur a envoyer ; 2 = fuite/probleme detecte.
"""

import argparse
import json
import re
import sys
from pathlib import Path

_ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(_ICI))
sys.path.insert(0, str(_ICI.parent / "anonymisation"))
import memoire as MEM      # noqa: E402
import manifeste as MAN    # noqa: E402


def _placeholder(s: str) -> bool:
    """Etiquette technique a ignorer (pas un vrai nom) : '', NON_AFFECTE, 'Locuteur N'."""
    return (not s) or s.strip().upper() == "NON_AFFECTE" or bool(
        re.match(r"(?i)\s*locuteur\s*\d+\s*$", s or ""))


def noms_interdits(mem: dict) -> list[str]:
    """Vrais noms qui ne doivent JAMAIS apparaitre dans le payload :
    toutes les variantes + canoniques (hors placeholders) + le nom du client.
    On exclut les faux positifs declares (`ignorer`) et les pseudos eux-memes."""
    interdits = set()
    for e in mem.get("entrees", []):
        for v in e.get("variantes", []):
            if not _placeholder(v):
                interdits.add(v)
        c = e.get("canonique")
        if c and not _placeholder(c):
            interdits.add(c)
    cli = mem.get("client")
    if cli and not _placeholder(cli):
        interdits.add(cli)
    ignorer = {x.lower() for x in mem.get("ignorer", [])}
    pseudos = {(e.get("pseudo") or "").lower() for e in mem.get("entrees", [])}
    return [t for t in interdits if t.lower() not in ignorer and t.lower() not in pseudos]


def _compiler(termes: list[str]):
    """Compile les motifs comme l'anonymiseur (appliquer.make_replacer) : frontiere
    \\b si le bord est alphanumerique, insensible a la casse, plus longs d'abord."""
    pats = []
    for t in sorted(set(termes), key=len, reverse=True):
        if not t:
            continue
        left = r"\b" if t[:1].isalnum() else ""
        right = r"\b" if t[-1:].isalnum() else ""
        pats.append((t, re.compile(left + re.escape(t) + right, re.IGNORECASE)))
    return pats


def scanner_texte(texte: str, pats) -> list[dict]:
    """Toutes les occurrences interdites trouvees (terme, forme, extrait)."""
    trouve = []
    for terme, pat in pats:
        for m in pat.finditer(texte):
            i = m.start()
            extrait = texte[max(0, i - 30): i + len(m.group(0)) + 30]
            trouve.append({"terme": terme, "forme": m.group(0),
                           "extrait": " ".join(extrait.split())})
            break  # une occurrence suffit a signaler le terme pour cet entretien
    return trouve


def assembler_payload(manifeste_path: Path, data: dict):
    """Construit le payload (ce qui PARTIRAIT) + la liste des sources manquantes.

    Le payload ne contient QUE des champs surs : id / role / interviewe / texte.
    Aucun chemin, aucun nom de fichier.
    """
    payload, manquants = [], []
    for e in data["entretiens"]:
        if not e.get("inclure", True):
            continue
        src = e.get("source", "")
        sp = MAN.resoudre_source(manifeste_path, src) if src else None
        if not sp or not sp.is_file():
            manquants.append({"id": e.get("id", "?"), "source": src})
            continue
        payload.append({
            "id": e.get("id", "?"),
            "role": e.get("role", "") or None,
            "interviewe": e.get("interviewe", "") or None,
            "texte": sp.read_text(encoding="utf-8"),
            # 'source' sert UNIQUEMENT au rapport local (localiser une fuite) ;
            # il n'est jamais envoye a l'IA (lancer.construire_prompt l'ignore,
            # et --dump le retire de "ce qui partirait").
            "source": src,
        })
    return payload, manquants


def verifier(manifeste_path: Path) -> dict:
    """Assemble + scanne. Retourne un rapport complet (sans rien envoyer)."""
    data = MAN.charger(manifeste_path)
    mem_path = MAN.resoudre_memoire(manifeste_path, data)
    mem = MEM.charger_memoire(mem_path)
    interdits = noms_interdits(mem)
    pats = _compiler(interdits)

    payload, manquants = assembler_payload(manifeste_path, data)
    resultats = []
    for item in payload:
        violations = scanner_texte(item["texte"], pats)
        resultats.append({"id": item["id"], "source": item.get("source"),
                          "violations": violations, "longueur": len(item["texte"])})

    total_fuites = sum(len(r["violations"]) for r in resultats)
    return {
        "memoire": str(mem_path),
        "memoire_existe": mem_path.is_file(),
        "nb_interdits": len(interdits),
        "inclus": len(payload),
        "manquants": manquants,
        "resultats": resultats,
        "total_fuites": total_fuites,
        "payload": payload,
    }


# ---------------------------------------------------------------------------
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Garde-fou anti-fuite d'une synthese.")
    ap.add_argument("manifeste", help="Chemin du synthese.manifeste.json.")
    ap.add_argument("--dump", help="Ecrit le payload assemble dans ce fichier (LOCAL, pour inspection).")
    args = ap.parse_args()

    mp = Path(args.manifeste).resolve()
    if not mp.is_file():
        print(f"[ERREUR] Manifeste introuvable : {mp}", file=sys.stderr)
        sys.exit(1)

    try:
        rap = verifier(mp)
    except (ValueError, OSError) as ex:
        print(f"[ERREUR] {ex}", file=sys.stderr)
        sys.exit(1)

    if args.dump:
        # On ecrit EXACTEMENT ce qui partirait (sans 'source', usage local).
        sent = [{k: it.get(k) for k in ("id", "role", "interviewe", "texte")}
                for it in rap["payload"]]
        Path(args.dump).write_text(
            json.dumps(sent, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[i] Payload (ce qui PARTIRAIT) ecrit (LOCAL) : {args.dump}")

    print(f"Memoire           : {rap['memoire']}  ({'OK' if rap['memoire_existe'] else 'ABSENTE'})")
    print(f"Vrais noms charges : {rap['nb_interdits']}")
    print(f"Entretiens inclus  : {rap['inclus']}")

    probleme = False

    if not rap["memoire_existe"] or rap["nb_interdits"] == 0:
        print("\n/!\\ Memoire vide ou absente : impossible de garantir l'absence de fuite.")
        print("    Verifie le champ 'memoire' du manifeste.")
        probleme = True

    if rap["manquants"]:
        print("\n/!\\ Sources manquantes (entretiens inclus sans transcript lisible) :")
        for m in rap["manquants"]:
            print(f"    - {m['id']} : {m['source'] or '(source vide)'}")
        probleme = True

    if rap["total_fuites"] > 0:
        print(f"\n[FUITE] {rap['total_fuites']} occurrence(s) de vrais noms dans le payload :")
        for r in rap["resultats"]:
            for v in r["violations"]:
                print(f"    - {r['id']}  [{r.get('source') or '?'}]")
                print(f"        « {v['forme']} » (entree « {v['terme']} ») … {v['extrait']}")
        print("\n=> ENVOI BLOQUE. Corrige l'anonymisation (mémoire/relance) avant de continuer.")
        sys.exit(2)

    if probleme:
        print("\n=> A corriger avant envoi (voir ci-dessus).")
        sys.exit(2)

    print("\n[OK] Aucun vrai nom detecte dans le payload — SUR a envoyer.")


if __name__ == "__main__":
    main()
