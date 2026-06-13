#!/usr/bin/env python3
"""
detecter.py — Étape de DÉTECTION du pipeline d'anonymisation (local).

Lit un transcript taggé (.txt ou .srt produit par le tagueur), repère les
entités à anonymiser (personnes, lieux, organisations, emails, téléphones) via
Presidio (spaCy FR) + une liste d'alias forcés optionnelle, puis écrit un
"état intermédiaire" JSON décrivant les candidats (texte, type, occurrences,
extraits de contexte, score, pseudo proposé).

Cet état intermédiaire est ensuite chargé par l'éditeur/réconciliateur HTML
pour validation humaine, avant l'application finale (appliquer.py).

100% local. Voir tools/anonymisation/README.md et SCHEMA.md.

Usage :
    python detecter.py exemple.srt
    python detecter.py exemple.srt --alias alias_acme.yaml
    python detecter.py exemple.srt --table table_acme.json   # réutilise une table existante
    python detecter.py exemple.srt --out etat.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Mapping type interne <-> type Presidio
TYPE_FROM_PRESIDIO = {
    "PERSON": "PERSONNE",
    "LOCATION": "LIEU",
    "ORGANIZATION": "ORG",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "TEL",
}
PRESIDIO_FROM_TYPE = {v: k for k, v in TYPE_FROM_PRESIDIO.items()}


def die(msg, code=1):
    print(f"[ERREUR] {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# 1. Parsing du transcript taggé
# ---------------------------------------------------------------------------
def parse_transcript(path: Path):
    """
    Retourne une liste de blocs : { 'label': str|None, 'text': str }.
    - .srt : on extrait le texte de chaque sous-titre (en ignorant index et
      timecodes), et l'étiquette [Locuteur] de tête si présente.
    - .txt : chaque bloc commençant par [Locuteur] ; le texte suit jusqu'au
      prochain [Locuteur].
    Le but : séparer proprement l'ÉTIQUETTE du CORPS, pour ne pas polluer la
    détection avec la syntaxe du transcript.
    """
    raw = path.read_text(encoding="utf-8")
    ext = path.suffix.lower()
    blocks = []

    if ext == ".srt" or "-->" in raw:
        for chunk in re.split(r"\n\s*\n", raw.replace("\r", "")):
            lines = [l for l in chunk.split("\n") if l.strip() != ""]
            if not lines:
                continue
            # retirer index numérique et ligne(s) de timecode
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
        # .txt : regrouper par étiquette
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
# 2. Chargement alias + table existante
# ---------------------------------------------------------------------------
def load_alias(path: Path | None):
    if not path:
        return {"forcer": {}, "ignorer": [], "locuteurs_generiques": [],
                "reglages": {"seuil_score": 0.5,
                             "types": list(TYPE_FROM_PRESIDIO.keys())}}
    try:
        import yaml
    except ImportError:
        die("pyyaml requis pour lire le fichier alias. Installe-le (voir bootstrap).")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("forcer", {})
    data.setdefault("ignorer", [])
    data.setdefault("locuteurs_generiques", [])
    data.setdefault("reglages", {})
    data["reglages"].setdefault("seuil_score", 0.5)
    data["reglages"].setdefault("types", list(TYPE_FROM_PRESIDIO.keys()))
    return data


def load_table(path: Path | None):
    if not path or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 3. Détection Presidio
# ---------------------------------------------------------------------------
def build_analyzer():
    from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    config = {"nlp_engine_name": "spacy",
              "models": [{"lang_code": "fr", "model_name": "fr_core_news_md"}]}
    nlp_engine = NlpEngineProvider(nlp_configuration=config).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["fr"])

    # Téléphone FR : Presidio reconnaît mal les formats "06 12 34 56 78" / "+33...".
    # On ajoute un reconnaisseur regex dédié (déterministe, score élevé).
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
# 4. Pipeline principal
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Détection d'entités à anonymiser.")
    ap.add_argument("transcript", help="Fichier .txt ou .srt taggé.")
    ap.add_argument("--alias", help="alias.yaml (termes forcés / ignorés).")
    ap.add_argument("--table", help="table_correspondance.json existante (réutilisation).")
    ap.add_argument("--out", help="Fichier de sortie (défaut: <nom>.etat.json).")
    args = ap.parse_args()

    tpath = Path(args.transcript)
    if not tpath.exists():
        die(f"Transcript introuvable : {tpath}")

    alias = load_alias(Path(args.alias) if args.alias else None)
    table = load_table(Path(args.table) if args.table else None)
    seuil = float(alias["reglages"]["seuil_score"])
    types = alias["reglages"]["types"]
    ignorer = {x.lower() for x in alias.get("ignorer", [])}
    generiques = {x.lower() for x in alias.get("locuteurs_generiques", [])}

    blocks = parse_transcript(tpath)
    full_text = "\n".join(b["text"] for b in blocks)

    print(f"Transcript : {tpath.name}  ({len(blocks)} blocs)")
    print("Chargement du modèle FR (Presidio + spaCy)…")
    analyzer = build_analyzer()

    # 4a. Détection auto dans le corps de chaque bloc
    found = {}  # clé = (texte_normalisé) -> dict candidat
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
        # étiquette de locuteur : anonymisée sauf si générique
        if b["label"] and b["label"].lower() not in generiques:
            # on traite l'étiquette comme une PERSONNE candidate
            add_occurrence(b["label"], "PERSONNE", 0.99,
                           f"[{b['label']}] {b['text'][:40]}…", "etiquette")
        for (txt, ptype, score) in detect_in_text(analyzer, b["text"], types, seuil):
            typ = TYPE_FROM_PRESIDIO.get(ptype, ptype)
            ctx = _context(b["text"], txt)
            add_occurrence(txt, typ, score, ctx, "ner")

    # 4b. Alias forcés : injecter / fusionner (priorité absolue)
    forced_map = {}  # variante.lower() -> pseudo
    for pseudo, variantes in alias.get("forcer", {}).items():
        ptype = _type_from_pseudo(pseudo)
        for v in variantes:
            forced_map[v.lower()] = pseudo
            occ = len(re.findall(re.escape(v), full_text, flags=re.IGNORECASE))
            if v not in found:
                found[v] = {"texte": v, "type": ptype, "occurrences": occ,
                            "score": 1.0, "source": "alias", "exemples": []}
                ctx = _context(full_text, v)
                if ctx:
                    found[v]["exemples"].append(ctx)
            else:
                found[v]["source"] = "alias"
                found[v]["type"] = ptype   # le type suit le pseudo forcé

    # 4c. Attribution des pseudos proposés (en réutilisant la table si fournie)
    candidats = assign_pseudos(list(found.values()), forced_map, table)

    etat = {
        "transcript": tpath.name,
        "candidats": candidats,
        "table_source": args.table or None,
    }
    out = Path(args.out) if args.out else tpath.with_suffix(".etat.json")
    out.write_text(json.dumps(etat, ensure_ascii=False, indent=2), encoding="utf-8")

    # Résumé console
    print(f"\n{len(candidats)} entité(s) candidate(s) :")
    for c in sorted(candidats, key=lambda x: (x["type"], -x["occurrences"])):
        print(f"  {c['pseudo_propose']:12} <- {c['texte']!r:30} "
              f"[{c['type']}, {c['occurrences']}x, {c['source']}, score {c['score']:.2f}]")
    print(f"\nÉtat intermédiaire écrit : {out}")
    print("Étape suivante : éditer/valider dans l'éditeur HTML, puis appliquer.")


def _context(text, needle, width=35):
    i = text.lower().find(needle.lower())
    if i < 0:
        return ""
    a = max(0, i - width)
    b = min(len(text), i + len(needle) + width)
    return ("…" if a > 0 else "") + text[a:b].strip() + ("…" if b < len(text) else "")


def _type_from_pseudo(pseudo):
    base = pseudo.split("_")[0].upper()
    return base if base in PRESIDIO_FROM_TYPE else "PRODUIT" if base == "PRODUIT" else base


def assign_pseudos(cands, forced_map, table):
    """Attribue un pseudo proposé à chaque candidat, en réutilisant la table."""
    existing = {}   # variante.lower() -> pseudo  (depuis la table mémoire)
    counters = {}   # type -> max numéro utilisé
    if table:
        for e in table.get("entrees", []):
            for v in e.get("variantes", []):
                existing[v.lower()] = e["pseudo"]
        counters = dict(table.get("compteurs", {}))

    def bump(pseudo):
        """Réserve le numéro d'un pseudo déjà attribué pour éviter les collisions."""
        m = re.match(r"([A-ZÉ]+)_(\d+)$", pseudo)
        if m:
            typ, num = m.group(1), int(m.group(2))
            counters[typ] = max(counters.get(typ, 0), num)

    # Réserver tous les pseudos déjà connus (table + alias forcés)
    for p in existing.values():
        bump(p)
    for p in set(forced_map.values()):
        bump(p)

    def next_pseudo(typ):
        n = counters.get(typ, 0) + 1
        counters[typ] = n
        return f"{typ}_{n}"

    for c in cands:
        key = c["texte"].lower()
        if key in forced_map:
            c["pseudo_propose"] = forced_map[key]
        elif key in existing:
            c["pseudo_propose"] = existing[key]
        else:
            c["pseudo_propose"] = next_pseudo(c["type"])
    return cands


if __name__ == "__main__":
    main()
