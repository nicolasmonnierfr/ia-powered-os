#!/usr/bin/env python3
"""
appliquer.py — APPLICATION finale du pipeline d'anonymisation (local).

Prend un transcript taggé + un alias.yaml (issu de l'éditeur HTML ou de
reconcilier.py), et éventuellement une table de correspondance existante, puis
produit :
  - <nom>_anonymise.<ext>      : transcript anonymisé (à envoyer à l'IA)
  - table_correspondance.json  : table pseudonyme <-> réel (À GARDER EN LOCAL)
  - <nom>_rapport.txt          : rapport de relecture (qui a été remplacé)

Le remplacement applique les variantes les PLUS LONGUES d'abord (« Jean Dupont »
avant « Jean »), insensible à la casse, en préservant la structure du .srt et
les étiquettes de locuteurs génériques.

100% local. Voir tools/anonymisation/README.md et SCHEMA.md.

Usage :
    python appliquer.py exemple.srt --alias alias.yaml
    python appliquer.py exemple.srt --alias alias.yaml --table table_acme.json
    python appliquer.py exemple.srt --alias alias.yaml --client Acme
"""

import argparse
import json
import re
import sys
from pathlib import Path

TYPES = ["PERSONNE", "LIEU", "ORG", "PRODUIT", "EMAIL", "TEL"]


def die(msg, code=1):
    print(f"[ERREUR] {msg}", file=sys.stderr)
    sys.exit(code)


def load_yaml(path):
    try:
        import yaml
    except ImportError:
        die("pyyaml requis. Installe-le (voir bootstrap).")
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    data.setdefault("forcer", {})
    data.setdefault("ignorer", [])
    data.setdefault("locuteurs_generiques", [])
    return data


def type_from_pseudo(p):
    b = (p.split("_")[0] or "").upper()
    return b if b in TYPES else "PRODUIT"


# ---------------------------------------------------------------------------
# Construction de la table : fusionne alias + table existante
# ---------------------------------------------------------------------------
def build_table(alias, existing, client):
    """Construit la table de correspondance à partir de l'alias (et d'une table
    existante à enrichir). Retourne (table, mapping) où mapping est la liste de
    (variante, pseudo) triée par longueur décroissante pour le remplacement."""
    entries = {}     # pseudo -> entrée
    counters = {}

    def bump(pseudo):
        m = re.match(r"([A-ZÉ]+)_(\d+)$", pseudo)
        if m:
            counters[m.group(1)] = max(counters.get(m.group(1), 0), int(m.group(2)))

    # 1. reprendre la table existante
    if existing:
        for e in existing.get("entrees", []):
            entries[e["pseudo"]] = {
                "pseudo": e["pseudo"], "type": e["type"],
                "canonique": e.get("canonique", ""),
                "variantes": list(e.get("variantes", [])),
                "source": e.get("source", "ner"),
            }
            bump(e["pseudo"])
        counters.update({k: max(counters.get(k, 0), v)
                         for k, v in existing.get("compteurs", {}).items()})

    # 2. injecter les alias (forcer)
    for pseudo, variantes in alias.get("forcer", {}).items():
        bump(pseudo)
        if pseudo not in entries:
            entries[pseudo] = {"pseudo": pseudo, "type": type_from_pseudo(pseudo),
                               "canonique": variantes[0] if variantes else pseudo,
                               "variantes": [], "source": "alias"}
        for v in variantes:
            if v not in entries[pseudo]["variantes"]:
                entries[pseudo]["variantes"].append(v)
        # canonique = variante la plus longue
        if entries[pseudo]["variantes"]:
            entries[pseudo]["canonique"] = max(entries[pseudo]["variantes"], key=len)

    table = {
        "version": 1,
        "client": client or (existing.get("client") if existing else None),
        "compteurs": counters,
        "entrees": list(entries.values()),
    }

    # mapping pour remplacement : (variante, pseudo), plus longues d'abord
    mapping = []
    for e in table["entrees"]:
        for v in e["variantes"]:
            mapping.append((v, e["pseudo"]))
    mapping.sort(key=lambda t: -len(t[0]))
    return table, mapping


# ---------------------------------------------------------------------------
# Remplacement dans le texte (insensible à la casse, mots entiers si alpha)
# ---------------------------------------------------------------------------
def make_replacer(mapping, ignorer):
    ignorer_low = {x.lower() for x in ignorer}
    compiled = []
    for variante, pseudo in mapping:
        if variante.lower() in ignorer_low:
            continue
        # \b si la variante commence/finit par un caractère "mot"
        left = r"\b" if variante[:1].isalnum() else ""
        right = r"\b" if variante[-1:].isalnum() else ""
        pat = re.compile(left + re.escape(variante) + right, flags=re.IGNORECASE)
        compiled.append((pat, pseudo))
    counts = {}

    def replace_in(text):
        for pat, pseudo in compiled:
            def _sub(m):
                counts[pseudo] = counts.get(pseudo, 0) + 1
                return pseudo
            text = pat.sub(_sub, text)
        return text
    return replace_in, counts


# ---------------------------------------------------------------------------
# Traitement du transcript en préservant la structure
# ---------------------------------------------------------------------------
def anonymize_transcript(path, replace_in, generiques):
    """Anonymise en préservant la structure. Pour .srt : ne touche ni l'index ni
    les timecodes. Les étiquettes [Locuteur] sont anonymisées via replace_in,
    sauf si génériques (on les laisse intactes)."""
    raw = path.read_text(encoding="utf-8")
    ext = path.suffix.lower()
    gen_low = {g.lower() for g in generiques}

    def handle_label_line(line):
        # remplace l'étiquette [X] en début de ligne sauf si générique
        m = re.match(r"^(\s*\[)([^\]]+)(\]\s*)(.*)$", line)
        if not m:
            return replace_in(line)
        pre, label, post, rest = m.groups()
        if label.strip().lower() in gen_low:
            new_label = label
        else:
            new_label = replace_in(label)
        return pre + new_label + post + replace_in(rest)

    if ext == ".srt" or "-->" in raw:
        out_blocks = []
        for chunk in raw.replace("\r", "").split("\n\n"):
            lines = chunk.split("\n")
            new_lines = []
            for l in lines:
                if re.fullmatch(r"\s*\d+\s*", l) or "-->" in l:
                    new_lines.append(l)               # index / timecode : intacts
                elif l.strip() == "":
                    new_lines.append(l)
                else:
                    new_lines.append(handle_label_line(l))
            out_blocks.append("\n".join(new_lines))
        return "\n\n".join(out_blocks)
    else:
        out = []
        for l in raw.replace("\r", "").split("\n"):
            out.append(handle_label_line(l) if l.strip() else l)
        return "\n".join(out)


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Applique l'anonymisation et produit les sorties.")
    ap.add_argument("transcript", help="Fichier .txt ou .srt taggé.")
    ap.add_argument("--alias", required=True, help="alias.yaml (éditeur HTML / reconcilier.py).")
    ap.add_argument("--table", help="table_correspondance.json existante à enrichir.")
    ap.add_argument("--client", help="Nom du client (stocké dans la table).")
    ap.add_argument("--outdir", help="Dossier de sortie (défaut : à côté du transcript).")
    args = ap.parse_args()

    tpath = Path(args.transcript)
    if not tpath.exists():
        die(f"Transcript introuvable : {tpath}")
    alias = load_yaml(args.alias)
    existing = None
    if args.table and Path(args.table).exists():
        existing = json.loads(Path(args.table).read_text(encoding="utf-8"))

    table, mapping = build_table(alias, existing, args.client)
    if not mapping:
        die("Aucune correspondance à appliquer (alias vide ?).")

    replace_in, counts = make_replacer(mapping, alias.get("ignorer", []))
    anonymized = anonymize_transcript(tpath, replace_in, alias.get("locuteurs_generiques", []))

    outdir = Path(args.outdir) if args.outdir else tpath.parent
    outdir.mkdir(parents=True, exist_ok=True)
    out_transcript = outdir / f"{tpath.stem}_anonymise{tpath.suffix}"
    out_table = outdir / "table_correspondance.json"
    out_report = outdir / f"{tpath.stem}_rapport.txt"

    out_transcript.write_text(anonymized, encoding="utf-8")
    out_table.write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")

    # Rapport de relecture
    lines = ["RAPPORT D'ANONYMISATION", "=" * 40,
             f"Transcript      : {tpath.name}",
             f"Sortie          : {out_transcript.name}",
             f"Client          : {table.get('client') or '(non précisé)'}",
             f"Entités         : {len(table['entrees'])}", "",
             "Remplacements effectués (pseudo <- variantes) :"]
    for e in sorted(table["entrees"], key=lambda x: x["pseudo"]):
        n = sum(counts.get(e["pseudo"], 0) for _ in [0])
        used = counts.get(e["pseudo"], 0)
        lines.append(f"  {e['pseudo']:12} <- {', '.join(e['variantes'])}   "
                     f"({used} remplacement(s) dans ce transcript)")
    # vérif : pseudos jamais appliqués (présents dans la table mais absents du texte)
    jamais = [e["pseudo"] for e in table["entrees"] if counts.get(e["pseudo"], 0) == 0]
    if jamais:
        lines += ["", "Pseudos de la table non rencontrés dans ce transcript :",
                  "  " + ", ".join(jamais)]
    lines += ["", "⚠ RELECTURE RECOMMANDÉE : vérifier qu'aucune information",
              "  ré-identifiante (surnom, détail indirect) ne subsiste avant envoi.",
              "⚠ table_correspondance.json contient les vrais noms : NE PAS l'envoyer."]
    out_report.write_text("\n".join(lines), encoding="utf-8")

    print(f"[OK] Transcript anonymisé : {out_transcript}")
    print(f"[OK] Table (LOCALE)       : {out_table}")
    print(f"[OK] Rapport              : {out_report}")
    total = sum(counts.values())
    print(f"\n{total} remplacement(s) sur {len(table['entrees'])} entité(s).")
    if jamais:
        print(f"Note : {len(jamais)} entité(s) de la table absente(s) de ce transcript.")
    print("\n⚠ Relis le transcript anonymisé avant de l'envoyer. "
          "Garde table_correspondance.json en local.")


if __name__ == "__main__":
    main()
