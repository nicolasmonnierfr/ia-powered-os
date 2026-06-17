#!/usr/bin/env python3
"""
reconcilier.py — Reconciliation AUTOMATIQUE des locuteurs entre troncons, par
empreinte vocale (approche "B").

Probleme resolu
---------------
La diarisation de transcribe_robuste.py tourne PAR TRONCON, independamment. Les
locuteurs y sont donc nommes LOCALEMENT (T1-A, T2-B...) sans aucun lien entre
troncons : rien ne dit que "T1-A" et "T2-A" sont la meme personne. Jusqu'ici, ce
recollage etait 100 % manuel (1re etape du tagueur).

Ce script l'AUTOMATISE : pour chaque etiquette locale, il extrait une empreinte
vocale (embedding) representative a partir de l'audio des troncons (conserves en
WAV 16 kHz mono dans data/.chunks/), puis regroupe les etiquettes par similarite
de voix (clustering agglomeratif sur distance cosinus). Le resultat est une
SUGGESTION de mapping  T<n>-X -> Locuteur global  avec un score de confiance.

Philosophie (identique a identifier/analyser) : on PRE-REMPLIT, on ne remplace
pas. Le tagueur s'ouvre avec le mapping deja propose + la confiance par
etiquette ; l'humain valide d'un clic les cas francs et ne corrige a l'oreille
que les cas ambigus (voix proches, segments courts).

Sortie
------
Ecrit  <root>/1_transcription/<stem>.reconcile.json :
    {
      "version": 1, "method": "embedding", "model": "...",
      "speakers": K,
      "map": { "T1-A": 0, "T1-B": 1, "T2-A": 0, ... },
      "labels": [ {label, cluster, chunk, n_segments, duration,
                   sim_own, margin, confidence}, ... ]
    }
serveur_tagueur.py l'expose dans /api/manifest ; tagger.html pre-remplit la
fenetre de reconciliation.

Usage (depuis le dossier d'entretien, comme les autres outils) :
    python <repo>/tools/transcription/reconcilier.py --root "<dossier_entretien>"
    python ... --root "<dossier>" --speakers 2     # force le nombre de locuteurs
    python ... --self-test                          # test unitaire (sans audio)

Le script est relancable a l'identique (idempotent).
"""

import argparse
import json
import os
import re
import sys
import wave
from pathlib import Path

AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".mp4", ".mkv", ".webm", ".flac", ".ogg",
              ".aac", ".wma", ".opus"}

# Bornes d'extraction d'empreinte par etiquette.
MIN_SEG_SEC = 0.4        # on ignore les segments plus courts (embedding bruite)
MAX_TOTAL_SEC = 90.0     # audio cumule max par etiquette (borne le calcul)
DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "speechbrain/spkrec-ecapa-voxceleb")
FALLBACK_MODEL = "pyannote/embedding"


# ---------------------------------------------------------------------------
# Localisation repo / config (meme convention que transcribe_robuste.py)
# ---------------------------------------------------------------------------
def resolve_repo_home():
    env = os.getenv("IA_POWERED_OS_HOME", "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p
    return Path(__file__).resolve().parents[2]


def load_env(repo_home):
    env_path = repo_home / "config" / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            pass


def audio_stem_from_root(root):
    audios = sorted(f for f in root.iterdir()
                    if f.is_file() and f.suffix.lower() in AUDIO_EXTS)
    return audios[0].stem if audios else None


def find_chunk_dir(repo_home, stem):
    """Dossier des troncons pour ce stem : data/.chunks/AAAAMMJJ-<stem>/.
    Si plusieurs dates, on prend le plus recent contenant des chunk_*.json."""
    base = repo_home / "data" / ".chunks"
    if not base.is_dir():
        return None
    rx = re.compile(r"^\d{8}-" + re.escape(stem) + r"$")
    cands = [d for d in base.iterdir()
             if d.is_dir() and rx.match(d.name)
             and any(d.glob("chunk_*.json"))]
    if not cands:
        return None
    # nom = AAAAMMJJ-stem -> tri lexical = tri chronologique
    return sorted(cands, key=lambda d: d.name)[-1]


# ---------------------------------------------------------------------------
# Lecture des troncons + audio
# ---------------------------------------------------------------------------
def load_chunks(chunk_dir):
    """Charge chunk_000.json, chunk_001.json... avec leur WAV associe.
    Renvoie une liste de dicts {index, offset, overlap, segments, wav}."""
    out = []
    for meta in sorted(chunk_dir.glob("chunk_*.json")):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            print(f"[AVERTISSEMENT] {meta.name} illisible : {e}")
            continue
        idx = data.get("index", int(re.search(r"(\d+)", meta.stem).group(1)))
        wav = chunk_dir / f"chunk_{idx:03d}.wav"
        out.append({
            "index": idx,
            "offset": float(data.get("offset", 0.0)),
            "overlap": float(data.get("overlap", 0.0)),
            "segments": data.get("segments", []),
            "wav": wav,
        })
    return out


def read_wav_mono16k(path):
    """Lit un WAV PCM 16 bits mono -> (numpy float32 [-1,1], sample_rate)."""
    import numpy as np
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(n)
    if sw != 2:
        raise RuntimeError(f"{path.name}: echantillons {sw*8} bits non geres (attendu 16).")
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:                       # repli : moyenne des canaux si stereo
        audio = audio.reshape(-1, ch).mean(axis=1)
    return audio, sr


def gather_label_segments(chunks):
    """Construit, par etiquette locale, la liste de ses segments (chunk-local)
    et quelques metadonnees globales.
    Renvoie label_info: { label: {chunk, wav, segments:[(start,end)],
                                  n_segments, total_dur, first_global} }."""
    info = {}
    per_chunk_letters = {}    # index_chunk -> set(lettres) pour estimer K
    for c in chunks:
        idx = c["index"]
        per_chunk_letters.setdefault(idx, set())
        for s in c["segments"]:
            lab = s.get("local")
            if not lab:
                continue
            m = re.match(r"^T(\d+)-(.+)$", lab)
            if m:
                per_chunk_letters[idx].add(m.group(2))
            st = s.get("start")
            en = s.get("end")
            if st is None or en is None or en <= st:
                continue
            d = info.setdefault(lab, {
                "chunk": idx, "wav": c["wav"], "segments": [],
                "n_segments": 0, "total_dur": 0.0, "first_global": None,
            })
            d["segments"].append((float(st), float(en)))
            d["n_segments"] += 1
            d["total_dur"] += (en - st)
            gstart = c["offset"] + float(st)
            if d["first_global"] is None or gstart < d["first_global"]:
                d["first_global"] = gstart
    max_per_chunk = max((len(v) for v in per_chunk_letters.values()), default=0)
    return info, max_per_chunk


# ---------------------------------------------------------------------------
# Extraction des empreintes (embeddings)
# ---------------------------------------------------------------------------
def build_embedding_model(model_name, hf_token, device):
    """Instancie un extracteur d'empreintes pyannote. Repli sur FALLBACK_MODEL
    si le modele demande echoue (dependance/gating)."""
    import torch
    from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding
    dev = torch.device(device)
    last = None
    for name in [model_name, FALLBACK_MODEL]:
        if name is None:
            continue
        try:
            kw = {"device": dev}
            if name.startswith("pyannote/") and hf_token:
                kw["use_auth_token"] = hf_token
            model = PretrainedSpeakerEmbedding(name, **kw)
            print(f"[INFO] Modele d'empreinte : {name}")
            return model
        except Exception as e:           # noqa: BLE001 (on veut le repli large)
            print(f"[AVERTISSEMENT] Modele '{name}' indisponible : {e}")
            last = e
    raise RuntimeError(f"Aucun modele d'empreinte utilisable. Derniere erreur : {last}")


def embedding_for_label(model, audio, sr, segments):
    """Empreinte d'une etiquette : on concatene ses segments les plus longs
    (jusqu'a MAX_TOTAL_SEC) et on en extrait UNE empreinte (pooling du modele)."""
    import numpy as np
    import torch
    segs = sorted(segments, key=lambda se: se[1] - se[0], reverse=True)
    pieces = []
    total = 0.0
    for (st, en) in segs:
        if (en - st) < MIN_SEG_SEC and pieces:
            continue
        a = int(st * sr); b = int(en * sr)
        a = max(0, a); b = min(len(audio), b)
        if b <= a:
            continue
        pieces.append(audio[a:b])
        total += (b - a) / sr
        if total >= MAX_TOTAL_SEC:
            break
    if not pieces:
        return None
    wav = np.concatenate(pieces).astype(np.float32)
    # (batch=1, channel=1, samples)
    t = torch.from_numpy(wav).unsqueeze(0).unsqueeze(0)
    emb = model(t)                       # -> np.ndarray (1, dim) ou tensor
    if hasattr(emb, "detach"):
        emb = emb.detach().cpu().numpy()
    emb = np.asarray(emb).reshape(-1)
    if not np.all(np.isfinite(emb)):
        return None
    return emb


def extract_all_embeddings(label_info, model):
    """Renvoie (labels, X) : liste d'etiquettes ayant une empreinte + matrice."""
    import numpy as np
    by_wav = {}
    for lab, d in label_info.items():
        by_wav.setdefault(d["wav"], []).append(lab)

    embeddings = {}
    for wav_path, labs in by_wav.items():
        if not wav_path.exists():
            print(f"[AVERTISSEMENT] WAV manquant : {wav_path.name} -> {labs} ignores.")
            continue
        try:
            audio, sr = read_wav_mono16k(wav_path)
        except Exception as e:           # noqa: BLE001
            print(f"[AVERTISSEMENT] {wav_path.name} illisible : {e}")
            continue
        for lab in labs:
            emb = embedding_for_label(model, audio, sr, label_info[lab]["segments"])
            if emb is not None:
                embeddings[lab] = emb
            else:
                print(f"[AVERTISSEMENT] Pas d'empreinte exploitable pour {lab}.")
    labels = sorted(embeddings.keys())
    if not labels:
        return [], None
    X = np.vstack([embeddings[l] for l in labels])
    return labels, X


# ---------------------------------------------------------------------------
# Clustering (PUR : testable sans audio ni torch)
# ---------------------------------------------------------------------------
def cluster_labels(labels, X, n_speakers, first_global):
    """Regroupe les etiquettes par voix.
    - labels      : liste d'etiquettes locales
    - X           : matrice (n_labels, dim) des empreintes
    - n_speakers  : nombre de clusters cible (>=1)
    - first_global: dict label -> 1re apparition globale (pour ordonner les
                    clusters : Locuteur 1 = premier a parler)
    Renvoie (mapping label->cluster_global, details_par_label)."""
    import numpy as np
    n = len(labels)
    Xn = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    K = max(1, min(int(n_speakers), n))

    if K == 1 or n == 1:
        raw = np.zeros(n, dtype=int)
    else:
        from sklearn.cluster import AgglomerativeClustering
        try:
            model = AgglomerativeClustering(n_clusters=K, metric="cosine", linkage="average")
            raw = model.fit_predict(Xn)
        except TypeError:                # sklearn < 1.2 : 'affinity' au lieu de 'metric'
            model = AgglomerativeClustering(n_clusters=K, affinity="cosine", linkage="average")
            raw = model.fit_predict(Xn)

    # Centroides (normalises) par cluster brut
    centroids = {}
    for k in set(raw.tolist()):
        members = Xn[raw == k]
        c = members.mean(axis=0)
        centroids[k] = c / (np.linalg.norm(c) + 1e-9)

    # Ordonner les clusters par 1re apparition globale -> indices Locuteur 1..K
    def cluster_first(k):
        ts = [first_global.get(labels[i]) for i in range(n)
              if raw[i] == k and first_global.get(labels[i]) is not None]
        return min(ts) if ts else float("inf")
    order = sorted(set(raw.tolist()), key=cluster_first)
    remap = {old: new for new, old in enumerate(order)}

    mapping = {}
    details = []
    for i, lab in enumerate(labels):
        k = int(raw[i])
        xi = Xn[i]
        sim_own = float(xi @ centroids[k])
        others = [float(xi @ centroids[o]) for o in centroids if o != k]
        sim_other = max(others) if others else 0.0
        margin = sim_own - sim_other
        if sim_own < 0.15:
            conf = "low"
        elif margin >= 0.20:
            conf = "high"
        elif margin >= 0.08:
            conf = "medium"
        else:
            conf = "low"
        gid = remap[k]
        mapping[lab] = gid
        details.append({
            "label": lab, "cluster": gid,
            "sim_own": round(sim_own, 3), "margin": round(margin, 3),
            "confidence": conf,
        })
    details.sort(key=lambda d: (d["cluster"], d["label"]))
    return mapping, details


# ---------------------------------------------------------------------------
# Pilotage
# ---------------------------------------------------------------------------
def reconcilier(root, stem, n_speakers, repo_home, hf_token, model_name, device):
    chunk_dir = find_chunk_dir(repo_home, stem)
    if not chunk_dir:
        print(f"[ERREUR] Aucun dossier de troncons pour « {stem} » dans "
              f"{repo_home / 'data' / '.chunks'}. (Transcription diarisee requise.)",
              file=sys.stderr)
        return None
    print(f"[INFO] Troncons : {chunk_dir}")

    chunks = load_chunks(chunk_dir)
    label_info, max_per_chunk = gather_label_segments(chunks)
    if not label_info:
        print("[ERREUR] Aucune etiquette locale (T<n>-X) trouvee : la transcription "
              "a-t-elle ete faite avec --diarize ?", file=sys.stderr)
        return None

    # Etiquettes deja globalement coherentes (un seul troncon) ? Rien a faire,
    # mais on produit quand meme une suggestion triviale (chaque etiquette = 1
    # locuteur), utile si plusieurs voix dans l'unique troncon.
    labels_all = sorted(label_info.keys())
    print(f"[INFO] {len(labels_all)} etiquette(s) locale(s) : {', '.join(labels_all)}")

    if n_speakers is None:
        n_speakers = min(max(max_per_chunk or 2, 2), 4)
        print(f"[INFO] Nombre de locuteurs estime (max voix/troncon, borne [2,4]) : {n_speakers}")
    else:
        print(f"[INFO] Nombre de locuteurs impose : {n_speakers}")

    print("[INFO] Extraction des empreintes vocales... [peut etre LENT / 1er telechargement du modele]")
    model = build_embedding_model(model_name, hf_token, device)
    labels, X = extract_all_embeddings(label_info, model)
    if not labels:
        print("[ERREUR] Aucune empreinte exploitable.", file=sys.stderr)
        return None

    first_global = {l: label_info[l]["first_global"] for l in labels}
    mapping, details = cluster_labels(labels, X, n_speakers, first_global)

    # Enrichir les details avec chunk/duree/n_segments
    for d in details:
        li = label_info[d["label"]]
        d["chunk"] = li["chunk"]
        d["n_segments"] = li["n_segments"]
        d["duration"] = round(li["total_dur"], 1)

    result = {
        "version": 1,
        "method": "embedding",
        "model": model_name,
        "stem": stem,
        "speakers": int(max(mapping.values()) + 1) if mapping else 0,
        "map": mapping,
        "labels": details,
    }
    return result


def write_result(root, stem, result):
    """Ecrit la suggestion a cote du .srt brut (1_transcription/)."""
    out_dir = root / "1_transcription"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{stem}.reconcile.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def summarize(result):
    by_cluster = {}
    for d in result["labels"]:
        by_cluster.setdefault(d["cluster"], []).append(d)
    print(f"\n[OK] Suggestion : {result['speakers']} locuteur(s) global(aux).")
    for gid in sorted(by_cluster):
        rows = by_cluster[gid]
        labs = ", ".join(f"{r['label']}({r['confidence'][0]})" for r in rows)
        print(f"  Locuteur {gid + 1} <- {labs}")
    weak = [d["label"] for d in result["labels"] if d["confidence"] == "low"]
    if weak:
        print(f"  /!\\ A verifier a l'oreille (faible confiance) : {', '.join(weak)}")


# ---------------------------------------------------------------------------
# Test unitaire du clustering (sans audio ni torch)
# ---------------------------------------------------------------------------
def self_test():
    import numpy as np
    rng_state = 12345
    # Deux vraies voix (vecteurs base), 3 troncons, bruit leger.
    base = {
        0: np.array([1.0, 0.0, 0.0, 0.2]),
        1: np.array([0.0, 1.0, 0.2, 0.0]),
    }
    labels, vecs, first = [], [], {}
    truth = {}
    # generateur deterministe simple (pas de Random global)
    def noise(seed, k):
        x = (np.sin(np.arange(k) * (seed + 1) * 1.7) * 0.05)
        return x
    t = 0.0
    for chunk in (1, 2, 3):
        for spk, letter in ((0, "A"), (1, "B")):
            lab = f"T{chunk}-{letter}"
            v = base[spk] + noise(rng_state + chunk * 10 + spk, 4)
            labels.append(lab); vecs.append(v); first[lab] = t
            truth[lab] = spk
            t += 1.0
    X = np.vstack(vecs)
    mapping, details = cluster_labels(labels, X, 2, first)
    # Verifie : memes vraies voix -> meme cluster global
    groups = {}
    for lab, g in mapping.items():
        groups.setdefault(g, set()).add(truth[lab])
    ok = all(len(s) == 1 for s in groups.values()) and len(groups) == 2
    # Locuteur 1 = premier a parler (T1-A, vraie voix 0)
    ok = ok and mapping["T1-A"] == 0
    print("mapping:", mapping)
    print("details:", json.dumps(details, ensure_ascii=False))
    print("SELF-TEST:", "OK" if ok else "ECHEC")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(
        description="Reconciliation automatique des locuteurs entre troncons (empreinte vocale).")
    ap.add_argument("--root", default=None, help="Dossier de l'entretien (defaut : repertoire courant).")
    ap.add_argument("--stem", default=None, help="Nom de base de l'audio (defaut : audio a la racine).")
    ap.add_argument("--speakers", type=int, default=None, help="Force le nombre de locuteurs (sinon estime).")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Modele d'empreinte (defaut {DEFAULT_MODEL}).")
    ap.add_argument("--device", default=os.getenv("WHISPER_DEVICE", "cpu"))
    ap.add_argument("--self-test", action="store_true", help="Test unitaire du clustering (sans audio).")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(self_test())

    repo_home = resolve_repo_home()
    load_env(repo_home)

    root = Path(args.root).resolve() if args.root else Path.cwd()
    if not root.is_dir():
        print(f"[ERREUR] Dossier introuvable : {root}", file=sys.stderr); sys.exit(1)
    stem = args.stem or audio_stem_from_root(root)
    if not stem:
        print(f"[ERREUR] Aucun audio a la racine de {root} (et --stem non fourni).", file=sys.stderr)
        sys.exit(1)

    hf_token = os.getenv("HUGGINGFACE_TOKEN", "").strip()
    result = reconcilier(root, stem, args.speakers, repo_home, hf_token, args.model, args.device)
    if not result:
        sys.exit(2)
    out = write_result(root, stem, result)
    summarize(result)
    print(f"\n  -> {out}")


if __name__ == "__main__":
    main()
