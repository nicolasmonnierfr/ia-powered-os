#!/usr/bin/env python3
"""
lancer.py — Synthese multi-entretiens via l'API Claude (appel reel).

Enchaine, a partir d'un manifeste :
  1. GARDE-FOU (barriere) : reutilise garde_fou.verifier ; si un vrai nom
     subsiste dans le payload (ou memoire absente / sources manquantes), on
     ARRETE (rien n'est envoye). Impossible de court-circuiter le garde-fou.
  2. Assemble le prompt (gabarit + corpus anonymise sous labels neutres).
  3. Appelle l'API Claude (modele claude-opus-4-8 par defaut), en STREAMING
     (sorties potentiellement longues).
  4. Ecrit 4_synthese/synthese.md (en pseudonymes -> repersonnalisable) + un
     journal synthese.run.json (modele, horodatage, entrees, usage tokens).

Confidentialite : seul part vers l'IA le payload verifie (id / role /
interviewe / contenu anonymise). La memoire client (vrais noms) ne quitte
JAMAIS la machine.

Cle API : ANTHROPIC_API_KEY dans config/.env (comme HUGGINGFACE_TOKEN).

Usage :
    python lancer.py <manifeste> [--out synthese.md] [--gabarit g.md]
                     [--modele claude-opus-4-8] [--max-tokens 16000]
                     [--dry-run]   # assemble le prompt, NE l'envoie PAS
"""

import argparse
import json
import sys
from pathlib import Path

_ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(_ICI))
import garde_fou as GF    # noqa: E402  (verifier, assembler — reutilise le filet)
import manifeste as MAN   # noqa: E402
# garde_fou a pose le sys.path vers tools/anonymisation : memoire + desanonymiser dispo.
import memoire as MEM           # noqa: E402  (charger_memoire)
import desanonymiser as DES     # noqa: E402  (repersonnalisation automatique)

MODELE_DEFAUT = "claude-opus-4-8"
GABARIT_DEFAUT = _ICI / "gabarits" / "diagnostic_transfo_ia.md"

SYSTEME = (
    "Tu es un consultant senior en transformation par l'IA. On te fournit le "
    "corpus d'entretiens ANONYMISES d'une meme mission : les noms propres sont "
    "des pseudonymes (PERSONNE_1, SOCIETE, PRODUIT_1...) et les locuteurs sont "
    "des roles generiques (Interviewer, Candidat...) ou des pseudonymes. "
    "Produis une synthese structuree suivant le gabarit fourni.\n"
    "Regles imperatives :\n"
    "- cite les entretiens par leur label (E1, E2...) et les personnes par leur "
    "pseudonyme UNIQUEMENT ; n'invente AUCUN nom reel et ne cherche pas a "
    "re-identifier qui que ce soit ;\n"
    "- distingue clairement ce qui est DIT dans les entretiens de tes "
    "INTERPRETATIONS ;\n"
    "- appuie les constats sur des verbatims (pseudonymises) quand c'est utile ;\n"
    "- reste au niveau du diagnostic ; reponds en francais, en Markdown."
)


def charger_env():
    """Charge config/.env depuis le repo (pour ANTHROPIC_API_KEY)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for parent in _ICI.resolve().parents:
        env_path = parent / "config" / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return
    load_dotenv()


def construire_prompt(titre, gabarit_txt, payload):
    """Message utilisateur : gabarit + corpus anonymise sous labels neutres."""
    parties = [f"# Mission : {titre}", "",
               "## Gabarit de la synthese", gabarit_txt.strip(), "",
               "## Corpus (entretiens anonymises)", ""]
    for item in payload:
        meta = []
        if item.get("role"):       meta.append(f"role : {item['role']}")
        if item.get("interviewe"): meta.append(f"interviewe : {item['interviewe']}")
        suffixe = f"  ({' ; '.join(meta)})" if meta else ""
        parties.append(f"### {item['id']}{suffixe}")
        parties.append(item["texte"].strip())
        parties.append("")
    return "\n".join(parties)


def estimer_tokens(texte):
    """Estimation grossiere (4 caracteres ~ 1 token) pour un garde-fou de taille."""
    return len(texte) // 4


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Synthese multi-entretiens via l'API Claude.")
    ap.add_argument("manifeste", help="Chemin du synthese.manifeste.json.")
    ap.add_argument("--out", help="Fichier de sortie (defaut : 4_synthese/synthese.md au perimetre).")
    ap.add_argument("--gabarit", help=f"Gabarit Markdown (defaut : {GABARIT_DEFAUT.name}).")
    ap.add_argument("--modele", default=MODELE_DEFAUT, help=f"Modele Claude (defaut : {MODELE_DEFAUT}).")
    ap.add_argument("--max-tokens", type=int, default=16000, help="Plafond de sortie (defaut 16000).")
    ap.add_argument("--court", action="store_true", help="Repersonnaliser avec la variante courte (prenoms) au lieu du nom complet.")
    ap.add_argument("--dry-run", action="store_true", help="Assemble le prompt et l'ecrit en local, SANS appeler l'API.")
    args = ap.parse_args()

    mp = Path(args.manifeste).resolve()
    if not mp.is_file():
        print(f"[ERREUR] Manifeste introuvable : {mp}", file=sys.stderr)
        sys.exit(1)

    # --- 1. GARDE-FOU (barriere infranchissable) ---------------------------
    rap = GF.verifier(mp)
    if not rap["memoire_existe"] or rap["nb_interdits"] == 0:
        print("[ERREUR] Memoire absente/vide : impossible de garantir l'absence de fuite. Abandon.", file=sys.stderr)
        sys.exit(2)
    if rap["manquants"]:
        print("[ERREUR] Sources manquantes pour : "
              + ", ".join(m["id"] for m in rap["manquants"]) + ". Abandon.", file=sys.stderr)
        sys.exit(2)
    if rap["total_fuites"] > 0:
        print(f"[FUITE] {rap['total_fuites']} vrai(s) nom(s) dans le payload — ENVOI BLOQUE.", file=sys.stderr)
        for r in rap["resultats"]:
            for v in r["violations"]:
                print(f"        - {r['id']}  [{r.get('source') or '?'}] : « {v['forme']} »", file=sys.stderr)
        print("        Corrige l'anonymisation (editeur d'alias / memoire) puis recommence.", file=sys.stderr)
        sys.exit(2)

    payload = rap["payload"]
    if not payload:
        print("[ERREUR] Aucun entretien inclus dans le manifeste.", file=sys.stderr)
        sys.exit(2)

    data = MAN.charger(mp)
    titre = data.get("titre") or mp.parent.name

    gabarit_path = Path(args.gabarit).resolve() if args.gabarit else GABARIT_DEFAUT
    if not gabarit_path.is_file():
        print(f"[ERREUR] Gabarit introuvable : {gabarit_path}", file=sys.stderr)
        sys.exit(1)
    gabarit_txt = gabarit_path.read_text(encoding="utf-8")

    user_msg = construire_prompt(titre, gabarit_txt, payload)
    approx = estimer_tokens(SYSTEME + user_msg)
    print(f"[i] {len(payload)} entretien(s) — garde-fou OK ({rap['nb_interdits']} vrais noms verifies).")
    print(f"[i] Prompt estime ~{approx} tokens (entree).")

    # Sortie AU NIVEAU DE LA MISSION (pas de sous-dossier : le manifeste vit deja
    # au niveau mission). Nom de base : --out, sinon champ "sortie" du manifeste,
    # sinon "synthese". Les autres fichiers en derivent (stem partage).
    base = args.out or data.get("sortie") or "synthese"
    out = Path(base)
    if not out.is_absolute():
        out = mp.parent / out
    if out.suffix == "":
        out = out.with_suffix(".md")
    out = out.resolve()
    out_dir = out.parent
    prompt_path = out.with_name(f"{out.stem}.prompt.txt")
    run_path = out.with_name(f"{out.stem}.run.json")

    # --- DRY-RUN : on ecrit le prompt en local et on s'arrete ---------------
    if args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text("=== SYSTEME ===\n" + SYSTEME + "\n\n=== UTILISATEUR ===\n" + user_msg,
                               encoding="utf-8")
        print(f"[OK] (dry-run) Prompt ecrit (LOCAL, non envoye) : {prompt_path}")
        return

    # --- 2. Appel API Claude (streaming) -----------------------------------
    charger_env()
    import os
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("[ERREUR] ANTHROPIC_API_KEY absente. Renseigne-la dans config/.env.", file=sys.stderr)
        sys.exit(3)
    try:
        import anthropic
    except ImportError:
        print("[ERREUR] Paquet 'anthropic' non installe. Installe-le : "
              "& .venv\\Scripts\\pip.exe install anthropic", file=sys.stderr)
        sys.exit(3)

    client = anthropic.Anthropic()
    print(f"[i] Appel du modele {args.modele} (streaming)...")
    texte = ""
    usage = None
    try:
        with client.messages.stream(
            model=args.modele,
            max_tokens=args.max_tokens,
            thinking={"type": "adaptive"},
            system=SYSTEME,
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            for bloc in stream.text_stream:
                print(bloc, end="", flush=True)
                texte += bloc
            final = stream.get_final_message()
            usage = final.usage
        print()
    except anthropic.APIError as e:
        print(f"\n[ERREUR] Appel API echoue : {e}", file=sys.stderr)
        sys.exit(3)

    if not texte.strip():
        print("[ERREUR] Reponse vide du modele.", file=sys.stderr)
        sys.exit(3)

    # --- 3. Ecriture des sorties ------------------------------------------
    # Deux versions, toujours : la synthese ANONYME (preuve de ce qui a ete
    # envoye) et la version REPERSONNALISEE (le livrable). La version anonyme
    # n'ayant pas d'usage propre, on enchaine la repersonnalisation
    # automatiquement -- en memoire, sur le texte deja produit.
    out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(texte.rstrip() + "\n", encoding="utf-8")

    out_rep = out.with_name(f"{out.stem}_REPERSONNALISE{out.suffix}")
    nb_rep = None
    try:
        mem = MEM.charger_memoire(MAN.resoudre_memoire(mp, data))
        mapping = DES.construire_mapping(mem, court=args.court)
        replace_in, counts = DES.make_replacer(mapping)
        out_rep.write_text(replace_in(texte.rstrip() + "\n"), encoding="utf-8")
        nb_rep = sum(counts.values())
    except Exception as ex:   # la synthese anonyme reste produite quoi qu'il arrive
        print(f"\n[AVERT] Repersonnalisation automatique echouee : {ex}", file=sys.stderr)
        out_rep = None

    journal = {
        "manifeste": str(mp),
        "titre": titre,
        "modele": args.modele,
        "gabarit": gabarit_path.name,
        "entretiens": [{"id": i["id"], "role": i.get("role"), "interviewe": i.get("interviewe")}
                       for i in payload],
        "usage": ({"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
                  if usage else None),
        "sortie_anonyme": str(out),
        "sortie_repersonnalisee": (str(out_rep) if out_rep else None),
    }
    run_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[OK] Synthese ANONYME (pseudonymes) : {out}")
    if out_rep:
        print(f"[OK] Synthese REPERSONNALISEE (vrais noms, LOCAL) : {out_rep}  ({nb_rep} pseudo(s) remplace(s))")
    print(f"[OK] Journal : {run_path}")
    if usage:
        print(f"[i] Tokens : {usage.input_tokens} entree / {usage.output_tokens} sortie.")
    print("\n/!\\ Le fichier _REPERSONNALISE contient les VRAIS NOMS : usage LOCAL, ne jamais l'envoyer a une IA externe.")


if __name__ == "__main__":
    main()
