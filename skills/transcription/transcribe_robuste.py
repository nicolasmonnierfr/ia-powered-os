#!/usr/bin/env python3
"""
transcribe_robuste.py — Transcription d'audios longs, resistante aux interruptions.

Strategie :
  1. Decoupe l'audio en troncons de N minutes (ffmpeg), avec un leger chevauchement.
  2. Transcrit chaque troncon separement ; le resultat est ecrit sur disque
     IMMEDIATEMENT apres chaque troncon.
  3. Reprise : au demarrage, saute les troncons deja transcrits.
  4. Fusion : recolle les troncons en decalant les timestamps, produit
     <nom>.txt / <nom>.srt / <nom>.json finaux.

La diarisation N'EST PAS faite ici (pyannote n'est pas coherent entre fichiers
separes). Le decoupage produit une transcription SANS locuteurs ; l'attribution
se fait ensuite dans le tagueur (tagger.html).

Usage :
    python skills/transcription/transcribe_robuste.py "data/entretien_1h30.m4a"

Options :
    --chunk-min    Duree d'un troncon en minutes (defaut 15)
    --overlap-sec  Chevauchement entre troncons en secondes (defaut 2)
    --model        Modele Whisper (defaut large-v3)
    --language     Langue (defaut fr)
    --work-dir     Dossier de travail des troncons (defaut data/.chunks/<nom>)
    --output-dir   Dossier de sortie final (defaut data/transcriptions)

Le script est relancable a l'identique : il reprend ou il s'etait arrete.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def load_config():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve()
    for parent in here.parents:
        env_path = parent / "config" / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return
    load_dotenv()


def run(cmd):
    """Execute une commande, leve si echec, renvoie stdout."""
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Commande echouee : {' '.join(cmd)}\n{res.stderr}")
    return res.stdout


def ffprobe_duration(audio_path):
    """Duree de l'audio en secondes (via ffprobe)."""
    out = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
    ])
    return float(out.strip())


def split_audio(audio_path, work_dir, chunk_min, overlap_sec):
    """
    Decoupe l'audio en troncons WAV 16kHz mono.
    Renvoie la liste des (index, chemin_troncon, decalage_debut_sec).
    Le decoupage est deterministe : relancer ne reproduit pas si deja present.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    duration = ffprobe_duration(audio_path)
    chunk_sec = chunk_min * 60
    chunks = []
    idx = 0
    start = 0.0
    while start < duration:
        # Debut reel avec chevauchement (sauf le 1er)
        real_start = max(0.0, start - (overlap_sec if idx > 0 else 0))
        seg_len = chunk_sec + (overlap_sec if idx > 0 else 0)
        chunk_path = work_dir / f"chunk_{idx:03d}.wav"
        if not chunk_path.exists():
            # Extraction en WAV 16kHz mono (format attendu par whisper)
            run([
                "ffmpeg", "-y", "-i", str(audio_path),
                "-ss", f"{real_start:.3f}", "-t", f"{seg_len:.3f}",
                "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le",
                str(chunk_path),
            ])
        # Le decalage a appliquer aux timestamps de ce troncon = real_start
        chunks.append((idx, chunk_path, real_start, overlap_sec if idx > 0 else 0.0))
        idx += 1
        start += chunk_sec
    return chunks, duration


def transcribe_chunk(chunk_path, model, language, device, compute_type,
                     diarize=False, hf_token=None, idx=0):
    """
    Transcrit un troncon. Renvoie une liste de segments {start, end, text, local}.
    Si diarize=True, 'local' contient une etiquette de locuteur LOCALE au troncon
    sous la forme 'T{idx+1}-A', 'T{idx+1}-B', ... (a reconcilier ensuite).
    Sinon 'local' vaut None.
    """
    import whisperx
    import gc

    audio = whisperx.load_audio(str(chunk_path))
    wmodel = whisperx.load_model(model, device, compute_type=compute_type, language=language)
    result = wmodel.transcribe(audio, batch_size=8)
    detected = result.get("language", language)
    del wmodel
    gc.collect()

    # Alignement (timestamps mot/segment plus precis)
    try:
        model_a, metadata = whisperx.load_align_model(language_code=detected, device=device)
        result = whisperx.align(result["segments"], model_a, metadata, audio, device,
                                return_char_alignments=False)
        del model_a
        gc.collect()
    except Exception as e:
        print(f"    [AVERTISSEMENT] Alignement ignore : {e}")

    # Diarisation locale (optionnelle)
    if diarize and hf_token:
        try:
            Pipeline = getattr(whisperx, "DiarizationPipeline", None)
            if Pipeline is None:
                from whisperx.diarize import DiarizationPipeline as Pipeline
            diar = None
            for kwarg in ("use_auth_token", "token"):
                try:
                    diar = Pipeline(**{kwarg: hf_token}, device=device)
                    break
                except TypeError:
                    continue
            if diar is None:
                raise RuntimeError("Signature DiarizationPipeline inattendue.")
            diar_segments = diar(audio, min_speakers=1, max_speakers=4)
            result = whisperx.assign_word_speakers(diar_segments, result)
            del diar
            gc.collect()
        except Exception as e:
            print(f"    [AVERTISSEMENT] Diarisation du troncon ignoree : {e}")

    # Construire la table des locuteurs locaux -> lettre (A, B, C...) dans l'ordre d'apparition
    local_map = {}
    next_letter = [0]
    def local_label(spk):
        if spk is None:
            return None
        if spk not in local_map:
            letter = chr(ord("A") + next_letter[0]) if next_letter[0] < 26 else f"Z{next_letter[0]}"
            local_map[spk] = f"T{idx+1}-{letter}"
            next_letter[0] += 1
        return local_map[spk]

    segs = []
    for s in result.get("segments", []):
        segs.append({
            "start": s.get("start"),
            "end": s.get("end"),
            "text": (s.get("text") or "").strip(),
            "local": local_label(s.get("speaker")) if diarize else None,
        })
    return segs


def fmt_srt(seconds):
    if seconds is None or seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:
        ms = 0; s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_hms(seconds):
    if seconds is None:
        return "00:00:00"
    h = int(seconds // 3600); m = int((seconds % 3600) // 60); s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def merge_chunks(work_dir, n_chunks, overlap_sec):
    """
    Lit tous les chunk_XXX.json, decale les timestamps par le decalage stocke,
    elimine le recouvrement, renvoie la liste fusionnee de segments.
    """
    import re
    def norm(t):
        # Normalisation pour comparer deux textes : minuscules, sans ponctuation ni espaces multiples
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (t or "").lower())).strip()

    all_segs = []
    # On garde une petite fenetre des derniers textes normalises pour detecter les doublons de couture
    recent_norms = []   # liste de (norm_text, global_end)
    for idx in range(n_chunks):
        meta_path = work_dir / f"chunk_{idx:03d}.json"
        if not meta_path.exists():
            raise RuntimeError(f"Troncon manquant : {meta_path.name}")
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        offset = data["offset"]          # decalage en secondes
        ov = data.get("overlap", 0.0)    # chevauchement applique au debut du troncon
        useful_start = offset + ov       # debut "non chevauchant" de ce troncon
        for s in data["segments"]:
            st = (s["start"] or 0.0) + offset
            en = (s["end"] or 0.0) + offset
            text = s["text"]
            nt = norm(text)
            # Anti-doublon : on ne supprime QUE si le segment est dans la zone de
            # chevauchement (st < useful_start) ET que son texte duplique un segment
            # recent. Hors de cette zone, on ne supprime jamais (on preserve le contenu).
            if idx > 0 and st < useful_start + 0.5 and nt:
                is_dup = False
                for (rn, rend) in recent_norms:
                    if not rn:
                        continue
                    # doublon si textes identiques, ou l'un contient l'autre (segmentation differente)
                    if rn == nt or (len(nt) > 8 and (nt in rn or rn in nt)):
                        if abs(rend - st) < (ov + 2.0):  # proches dans le temps
                            is_dup = True
                            break
                if is_dup:
                    continue
            all_segs.append({"start": st, "end": en, "text": text,
                             "local": s.get("local")})
            recent_norms.append((nt, en))
            if len(recent_norms) > 12:
                recent_norms.pop(0)
    return all_segs


def write_outputs(segments, out_dir, stem, audio_name, model, language):
    out_dir.mkdir(parents=True, exist_ok=True)
    # JSON
    (out_dir / f"{stem}.json").write_text(
        json.dumps({"segments": segments}, ensure_ascii=False, indent=2), encoding="utf-8")
    # TXT
    txt = [f"# Transcription : {audio_name}", f"# Langue : {language} | Modele : {model}", ""]
    for s in segments:
        txt.append(f"({fmt_hms(s['start'])}) {s['text']}")
    (out_dir / f"{stem}.txt").write_text("\n".join(txt) + "\n", encoding="utf-8")
    # SRT : prefixe l'etiquette locale [T{n}-X] si la diarisation par troncon a tourne.
    # Ces etiquettes locales sont a reconcilier dans le tagueur.
    srt = []
    for i, s in enumerate(segments, 1):
        if not s["text"]:
            continue
        end = s["end"] if (s["end"] and s["end"] > s["start"]) else (s["start"] or 0) + 1
        local = s.get("local")
        prefix = f"[{local}] " if local else ""
        srt.append(f"{i}\n{fmt_srt(s['start'])} --> {fmt_srt(end)}\n{prefix}{s['text']}\n")
    (out_dir / f"{stem}.srt").write_text("\n".join(srt) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Transcription robuste (troncons + reprise).")
    ap.add_argument("audio")
    ap.add_argument("--chunk-min", type=int, default=15)
    ap.add_argument("--overlap-sec", type=float, default=2.0)
    ap.add_argument("--model", default=os.getenv("WHISPER_MODEL", "large-v3"))
    ap.add_argument("--language", default=os.getenv("WHISPER_LANGUAGE", "fr"))
    ap.add_argument("--device", default=os.getenv("WHISPER_DEVICE", "cpu"))
    ap.add_argument("--compute-type", default=os.getenv("WHISPER_COMPUTE_TYPE", "int8"))
    ap.add_argument("--work-dir", default=None)
    ap.add_argument("--output-dir", default="data/transcriptions")
    ap.add_argument("--diarize", action="store_true",
                    help="Diarisation par troncon avec etiquettes locales a reconcilier dans le tagueur")
    args = ap.parse_args()

    load_config()

    # Avec diarisation, un chevauchement plus large fiabilise la reconciliation aux jointures.
    if args.diarize and args.overlap_sec < 5.0:
        args.overlap_sec = 5.0
        print("[INFO] Diarisation activee : chevauchement porte a 5s pour la reconciliation.")

    hf_token = os.getenv("HUGGINGFACE_TOKEN", "").strip()
    if args.diarize:
        if not hf_token or hf_token.startswith("hf_xxxx"):
            print("[ERREUR] --diarize requiert un HUGGINGFACE_TOKEN valide dans config/.env.", file=sys.stderr)
            sys.exit(1)

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"[ERREUR] Fichier introuvable : {audio_path}", file=sys.stderr)
        sys.exit(1)

    stem = audio_path.stem
    work_dir = Path(args.work_dir) if args.work_dir else Path("data/.chunks") / stem
    out_dir = Path(args.output_dir)

    t0 = time.time()
    def el(): return f"[{time.time()-t0:7.1f}s]"

    print(f"{el()} Audio : {audio_path.name}")
    print(f"{el()} Decoupage en troncons de {args.chunk_min} min (chevauchement {args.overlap_sec}s)...")
    chunks, duration = split_audio(audio_path, work_dir, args.chunk_min, args.overlap_sec)
    print(f"{el()} Duree totale : {fmt_hms(duration)} -> {len(chunks)} troncon(s)")

    # Transcription troncon par troncon, avec reprise
    done = 0
    for (idx, chunk_path, offset, ov) in chunks:
        meta_path = work_dir / f"chunk_{idx:03d}.json"
        if meta_path.exists():
            print(f"{el()} Troncon {idx+1}/{len(chunks)} : deja fait, saute.")
            done += 1
            continue
        print(f"{el()} Troncon {idx+1}/{len(chunks)} : transcription{' + diarisation' if args.diarize else ''}... [LENT en CPU]")
        segs = transcribe_chunk(chunk_path, args.model, args.language,
                                args.device, args.compute_type,
                                diarize=args.diarize, hf_token=hf_token, idx=idx)
        # Ecriture IMMEDIATE du resultat du troncon (point de reprise)
        meta_path.write_text(json.dumps({
            "index": idx, "offset": offset, "overlap": ov, "segments": segs,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        done += 1
        print(f"{el()} Troncon {idx+1}/{len(chunks)} : OK ({len(segs)} segments) -> sauvegarde.")

    if done != len(chunks):
        print(f"{el()} [ERREUR] Tous les troncons ne sont pas faits ({done}/{len(chunks)}).")
        sys.exit(2)

    print(f"{el()} Fusion des {len(chunks)} troncons...")
    merged = merge_chunks(work_dir, len(chunks), args.overlap_sec)
    write_outputs(merged, out_dir, stem, audio_path.name, args.model, args.language)

    print(f"{el()} Termine. {len(merged)} segments fusionnes.")
    print(f"  -> {out_dir / (stem + '.txt')}")
    print(f"  -> {out_dir / (stem + '.srt')}")
    print(f"  -> {out_dir / (stem + '.json')}")
    print(f"  (troncons conserves dans {work_dir} ; supprimables une fois le resultat verifie)")


if __name__ == "__main__":
    main()
