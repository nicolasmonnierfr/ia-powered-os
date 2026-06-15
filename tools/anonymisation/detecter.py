#!/usr/bin/env python3
"""
detecter.py — Étape de DÉTECTION du pipeline d'anonymisation (local).

Lit un transcript taggé (.txt ou .srt produit par le tagueur), repère les
entités à anonymiser (personnes, lieux, organisations, emails, téléphones) via
Presidio (spaCy FR) + la mémoire client existante, puis écrit un état
intermédiaire JSON (`.etat.json`) décrivant les candidats.

NOUVEAU FORMAT (refonte #14) : la mémoire d'entrée est un artefact UNIQUE par
client, `memoire_client.json` (pseudos + variantes + types + faux positifs +
locuteurs génériques + réglages). Voir memoire.py pour le schéma.

Rétrocompatibilité : si on ne dispose que d'anciens fichiers (alias.yaml +
table.json), passe-les via --alias/--table : ils sont migrés à la volée en
mémoire (sans réécrire de fichier ; pour convertir définitivement, voir
migrer.py).

100% local. Voir tools/anonymisation/README.md et SCHEMA.md.

Usage :
    python detecter.py exemple.srt
    python detecter.py exemple.srt --memoire memoire_client.json
    python detecter.py exemple.srt --ignorer-global ignorer_global.json
    python detecter.py exemple.srt --out etat.json
    # rétrocompat :
    python detecter.py exemple.srt --alias alias.yaml --table table.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memoire as M  # noqa: E402


def die(msg, code=1):
    print(f"[ERREUR] {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# 1. Parsing du transcript taggé
# ---------------------------------------------------------------------------
def parse_transcript(path: Path):
    """
    Retourne une liste de blocs : { 'label': str|None, 'text': str }.
    - .srt : texte de chaque sous-titre (index/timecodes ignorés), étiquette
      [Locuteur] de tête si présente.
    - .txt : chaque bloc commençant par [Locuteur] ; le texte suit jusqu'au
      prochain [Locuteur].
    """
    raw = path.read_text(encoding="utf-8")
    ext = path.suffix.lower()
    blocks = []

    if ext == ".srt" or "-->" in raw:
        for chunk in re.split(r"\n\s*\n", raw.replace("\r", "")):
            lines = [l for l in chunk.split("\n") if l.strip() != ""]
            if not lines:
                continue
            body_lines = []
            for l in lines:
                if re.fullmatch(r"\d+", l.strip()):
                    continue
                if "-->" in l:
                    continue
                body_lines.append(l)
            if not body_lines:
                continue
            text = " ".join(body_lines).strip()
            label, text = _split_label(text)
            blocks.append({"label": label, "text": text})
    else:
        for line in raw.replace("\r", "").split("\n"):
            if line.strip() == "":
                continue
            label, text = _split_label(line.strip())
            if label is not None or not blocks:
                blocks.append({"label": label, "text": text})
            else:
                blocks[-1]["text"] += " " + text
    return blocks


def _split_label(text):
    """Sépare une étiquette [Locuteur] de tête du reste. Retourne (label, reste)."""
    m = re.match(r"^\s*\[([^\]]+)\]\s*", text)
    if m:
        return m.group(1).strip(), text[m.end():]
    return None, text


# ---------------------------------------------------------------------------
# 2. Détection Presidio
# ---------------------------------------------------------------------------
def build_analyzer():
    from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    config = {"nlp_engine_name": "spacy",
              "models": [{"lang_code": "fr", "model_name": "fr_core_news_md"}]}
    nlp_engine = NlpEngineProvider(nlp_configuration=config).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["fr"])

    tel_patterns = [
        Pattern(name="tel_fr_national",
                regex=r"\b0[1-9]([ .\-]?\d{2}){4}\b", score=0.9),
        Pattern(name="tel_fr_international",
                regex=r"\+33\s?[1-9]([ .\-]?\d{2}){4}\b", score=0.9),
    ]
    tel_reco = PatternRecognizer(supported_entity="PHONE_NUMBER",
                                 patterns=tel_patterns, supported_language="fr")
    analyzer.registry.add_recognizer(tel_reco)
    return analyzer


def resolve_overlaps(results):
    """Si deux détections se chevauchent, garder la meilleure (score puis longueur)."""
    results = sorted(results, key=lambda r: (-r.score, -(r.end - r.start)))
    kept = []
    for r in results:
        if any(not (r.end <= k.start or r.start >= k.end) for k in kept):
            continue
        kept.append(r)
    return kept


def detect_in_text(analyzer, text, types, seuil):
    results = analyzer.analyze(text=text, language="fr", entities=types)
    results = [r for r in results if r.score >= seuil]
    results = resolve_overlaps(results)
    return [(text[r.start:r.end], r.entity_type, r.score) for r in results]


# ---------------------------------------------------------------------------
# 3. Pipeline principal
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Détection d'entités à anonymiser.")
    ap.add_argument("transcript", help="Fichier .txt ou .srt taggé.")
    ap.add_argument("--memoire", help=f"{M.NOM_MEMOIRE} existant (mémoire client).")
    ap.add_argument("--ignorer-global", help="ignorer_global.json (faux positifs universels).")
    ap.add_argument("--out", help="Fichier de sortie (défaut: <nom>.etat.json).")
    ap.add_argument("--alias", help="[ancien] alias.yaml (migré à la volée).")
    ap.add_argument("--table", help="[ancien] table_correspondance.json (migré à la volée).")
    args = ap.parse_args()

    tpath = Path(args.transcript)
    if not tpath.exists():
        die(f"Transcript introuvable : {tpath}")

    # --- Charger la mémoire client (nouveau format prioritaire) -------------
    if args.memoire:
        mem = M.charger_memoire(Path(args.memoire))
    elif args.alias or args.table:
        mem = M.migrer_depuis_ancien(
            Path(args.alias) if args.alias else None,
            Path(args.table) if args.table else None)
    else:
        mem = M.memoire_vide()

    ignorer_global = M.charger_ignorer_global(
        Path(args.ignorer_global) if args.ignorer_global else None)

    seuil = float(mem["reglages"]["seuil_score"])
    types = mem["reglages"]["types"]
    ignorer = {x.lower() for x in mem.get("ignorer", [])} | {x.lower() for x in ignorer_global}
    generiques = {x.lower() for x in mem.get("locuteurs_generiques", [])}

    existing = M.index_variantes(mem)
    forced_map = {}
    for e in mem.get("entrees", []):
        if e.get("source") == "alias":
            for v in e.get("variantes", []):
                forced_map[v.lower()] = e["pseudo"]

    blocks = parse_transcript(tpath)
    full_text = "\n".join(b["text"] for b in blocks)

    print(f"Transcript : {tpath.name}  ({len(blocks)} blocs)")
    print("Chargement du modèle FR (Presidio + spaCy)…")
    analyzer = build_analyzer()

    found = {}

    def add_occurrence(txt, typ_interne, score, contexte, source):
        key = txt.strip()
        if not key or key.lower() in ignorer:
            return
        if key not in found:
            found[key] = {"texte": key, "type": typ_interne, "occurrences": 0,
                          "score": score, "source": source, "exemples": []}
        c = found[key]
        c["occurrences"] += 1
        c["score"] = max(c["score"], score)
        if len(c["exemples"]) < 2 and contexte:
            c["exemples"].append(contexte)

    for b in blocks:
        if b["label"] and b["label"].lower() not in generiques:
            add_occurrence(b["label"], "PERSONNE", 0.99,
                           f"[{b['label']}] {b['text'][:40]}…", "etiquette")
        for (txt, ptype, score) in detect_in_text(analyzer, b["text"], types, seuil):
            typ = M.TYPE_FROM_PRESIDIO.get(ptype, ptype)
            ctx = _context(b["text"], txt)
            add_occurrence(txt, typ, score, ctx, "ner")

    # Forçages connus : ré-exposés en candidats (cohérence dans l'éditeur)
    for e in mem.get("entrees", []):
        if e.get("source") != "alias":
            continue
        for v in e.get("variantes", []):
            if v in found:
                found[v]["source"] = "alias"
                found[v]["type"] = e["type"]
            elif v.lower() not in ignorer:
                occ = len(re.findall(re.escape(v), full_text, flags=re.IGNORECASE))
                found[v] = {"texte": v, "type": e["type"], "occurrences": occ,
                            "score": 1.0, "source": "alias", "exemples": []}
                ctx = _context(full_text, v)
                if ctx:
                    found[v]["exemples"].append(ctx)

    candidats = assign_pseudos(list(found.values()), forced_map, existing, mem)

    etat = {
        "transcript": tpath.name,
        "candidats": candidats,
        "memoire_source": args.memoire or None,
    }
    out = Path(args.out) if args.out else tpath.with_suffix(".etat.json")
    out.write_text(json.dumps(etat, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(candidats)} entité(s) candidate(s) :")
    for c in sorted(candidats, key=lambda x: (x["type"], -x["occurrences"])):
        print(f"  {c['pseudo_propose']:14} <- {c['texte']!r:30} "
              f"[{c['type']}, {c['occurrences']}x, {c['source']}, score {c['score']:.2f}]")
    print(f"\nÉtat intermédiaire écrit : {out}")
    print("Étape suivante : valider dans l'éditeur HTML, puis appliquer.")


def _context(text, needle, width=35):
    i = text.lower().find(needle.lower())
    if i < 0:
        return ""
    a = max(0, i - width)
    b = min(len(text), i + len(needle) + width)
    return ("…" if a > 0 else "") + text[a:b].strip() + ("…" if b < len(text) else "")


def assign_pseudos(cands, forced_map, existing, mem):
    """Attribue un pseudo proposé à chaque candidat, en réutilisant la mémoire."""
    counters = M.compteurs_depuis_entrees(mem.get("entrees", []))
    for k, v in mem.get("compteurs", {}).items():
        counters[k] = max(counters.get(k, 0), v)
    for p in set(forced_map.values()):
        m = re.match(r"([A-ZÉ]+)_(\d+)$", p)
        if m:
            counters[m.group(1)] = max(counters.get(m.group(1), 0), int(m.group(2)))

    for c in cands:
        key = c["texte"].lower()
        if key in forced_map:
            c["pseudo_propose"] = forced_map[key]
        elif key in existing:
            c["pseudo_propose"] = existing[key]
        else:
            c["pseudo_propose"] = M.prochain_pseudo(c["type"], counters)
    return cands


if __name__ == "__main__":
    main()
