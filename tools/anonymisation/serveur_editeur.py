#!/usr/bin/env python3
"""
serveur_editeur.py — Serveur local pour l'editeur d'alias (editeur_alias.html).

Sert l'editeur ET les fichiers necessaires a la validation d'anonymisation :
  - le .etat.json (produit par detecter.py) du dossier 3_anonymisation/ de
    l'entretien courant ;
  - le memoire_client.json du PERIMETRE (trouve par recherche ascendante,
    transmis par le wrapper) s'il existe deja, pour pre-remplir l'editeur.
A l'export, ecrit le memoire_client.json AU NIVEAU DU PERIMETRE (chemin transmis).

Serveur sur 127.0.0.1 uniquement. Arret par HEARTBEAT (comme le tagueur).

Usage (lance par anonymisation.ps1) :
    python serveur_editeur.py --etat "<...3_anonymisation/x.etat.json>" \
        --memoire "<...perimetre/memoire_client.json>" \
        --editeur "<chemin editeur_alias.html>" [--port 8770]

Routes :
    GET  /                 -> editeur_alias.html
    GET  /api/manifest     -> {etat: bool, memoire_existe: bool, memoire_path}
    GET  /api/etat         -> contenu du .etat.json
    GET  /api/memoire      -> contenu du memoire_client.json existant (ou 404)
    GET  /api/audio        -> audio de l'entretien (support Range/206 pour le seek)
    POST /api/export       -> ecrit le memoire_client.json au chemin du perimetre
                              ET estampille le .etat.json (validation.faite=true),
                              trace exploitee par l'orchestrateur pour l'anonym. auto.
    POST /api/ping         -> heartbeat
    POST /api/ouvrir-tagueur -> relance le tagueur (serveur_tagueur.py) sur
                              l'entretien, positionne sur le terme a corriger
                              (?find=), pour editer le texte du transcript.
    POST /api/reidentifier -> relance detecter.py sur le transcript (corrige) et
                              reecrit le .etat.json (extraits a jour + nouveaux
                              alias). Manuel, apres une correction de texte.
"""

import argparse
import json
import mimetypes
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, quote

GRACE_SEC = 60.0   # tolere le ralentissement des timers d'un onglet en arriere-plan
                   # (ex. pendant une correction dans le tagueur ouvert en parallele)
CHECK_EVERY = 3.0

AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".mp4", ".mkv", ".webm", ".flac",
              ".ogg", ".aac", ".wma", ".opus"}
# Type MIME explicite : mimetypes.guess_type renvoie souvent octet-stream pour
# .m4a -> le <audio> du navigateur refuse de decoder (bouton ▶ sans effet).
MIME_AUDIO = {
    ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".mp4": "video/mp4",
    ".mkv": "video/x-matroska", ".webm": "audio/webm", ".flac": "audio/flac",
    ".ogg": "audio/ogg", ".aac": "audio/aac", ".wma": "audio/x-ms-wma", ".opus": "audio/opus",
}


def _trouver_audio(etat_path: Path, etat_data: dict):
    """Localise l'audio dont les timecodes des `positions` du .etat.json sont
    relatifs. Le .etat.json vit dans <entretien>/3_anonymisation/ ; le champ
    `transcript_dir` indique d'ou vient le transcript :
      - "2_coupe"         -> audio COUPE (timecodes relatifs au montage) ;
      - "1_transcription" -> audio BRUT (a la racine de l'entretien).
    Retourne un Path ou None.
    """
    entretien = etat_path.parent.parent
    tdir = (etat_data or {}).get("transcript_dir") or ""
    stem = Path((etat_data or {}).get("transcript") or "").stem

    def audios_dans(d):
        if not d.is_dir():
            return []
        prio = [d / f"{stem}{e}" for e in AUDIO_EXTS]
        prio = [p for p in prio if p.is_file()]
        reste = sorted(p for p in d.iterdir()
                       if p.is_file() and p.suffix.lower() in AUDIO_EXTS)
        return prio + [p for p in reste if p not in prio]

    if tdir == "2_coupe":
        ordre = [entretien / "2_coupe", entretien]
    else:
        ordre = [entretien, entretien / "2_coupe"]
    for d in ordre:
        cands = audios_dans(d)
        if cands:
            return cands[0]
    return None


def _audio_reference(entretien: Path):
    """Audio ORIGINAL a la racine de l'entretien = la REFERENCE du workflow."""
    if not entretien.is_dir():
        return None
    for f in sorted(entretien.iterdir()):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTS:
            return f.name
    return None


class Etat:
    def __init__(self, etat_path: Path, memoire_path: Path, editeur: Path):
        self.etat_path = etat_path
        self.memoire_path = memoire_path
        self.editeur = editeur
        self.last_ping = time.time()
        self.lock = threading.Lock()
        self._audio = False   # sentinelle "non resolu" (sinon None=absent / Path)

    def audio_path(self):
        """Localise (et met en cache) l'audio associe au .etat.json."""
        with self.lock:
            if self._audio is not False:
                return self._audio
        try:
            data = json.loads(self.etat_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        ap = _trouver_audio(self.etat_path, data)
        with self.lock:
            self._audio = ap
        return ap

    def touch(self):
        with self.lock:
            self.last_ping = time.time()

    def idle(self):
        with self.lock:
            return time.time() - self.last_ping


def _stamper_validation(etat_path: Path, memoire_path: Path) -> bool:
    """Marque le .etat.json comme VALIDE (analyse terminee par l'humain).

    Ecrit un bloc `validation` : { faite: true, le: <ISO>, memoire: <chemin> }.
    Idempotent (re-export -> rafraichit l'horodatage). Best-effort : un echec
    n'invalide pas l'export de la memoire (qui, lui, a deja reussi).
    Retourne True si la trace a bien ete ecrite.
    """
    try:
        data = json.loads(etat_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    data["validation"] = {
        "faite": True,
        "le": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "memoire": str(memoire_path),
    }
    try:
        etat_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        return True
    except OSError:
        return False


def make_handler(etat: Etat):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, body=b"", ctype="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                return self._send(200, etat.editeur.read_bytes(), "text/html; charset=utf-8")
            if path == "/api/manifest":
                ap = etat.audio_path()
                return self._json(200, {
                    "etat": etat.etat_path.is_file(),
                    "etat_name": etat.etat_path.name,
                    "memoire_existe": etat.memoire_path.is_file(),
                    "memoire_path": str(etat.memoire_path),
                    "audio": bool(ap),
                    "audio_name": ap.name if ap else None,
                    "reference": _audio_reference(etat.etat_path.parent.parent),
                })
            if path == "/api/audio":
                return self._serve_audio()
            if path == "/api/etat":
                if not etat.etat_path.is_file():
                    return self._json(404, {"error": "etat.json absent"})
                return self._send(200, etat.etat_path.read_bytes(), "application/json; charset=utf-8")
            if path == "/api/memoire":
                if not etat.memoire_path.is_file():
                    return self._json(404, {"error": "memoire_client.json absent"})
                return self._send(200, etat.memoire_path.read_bytes(), "application/json; charset=utf-8")
            self._json(404, {"error": "not found"})

        def _serve_audio(self):
            ap = etat.audio_path()
            if not ap or not ap.is_file():
                return self._json(404, {"error": "audio introuvable"})
            size = ap.stat().st_size
            ctype = (MIME_AUDIO.get(ap.suffix.lower())
                     or mimetypes.guess_type(str(ap))[0] or "application/octet-stream")
            rng = self.headers.get("Range")
            # Requete partielle (seek) -> 206. Lecture du seul tronçon demande.
            if rng:
                m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
                if m and (m.group(1) or m.group(2)):
                    s = int(m.group(1)) if m.group(1) else 0
                    e = int(m.group(2)) if m.group(2) else size - 1
                    s = max(0, s); e = min(e, size - 1)
                    if s > e:
                        s = 0
                    length = e - s + 1
                    with open(ap, "rb") as f:
                        f.seek(s)
                        data = f.read(length)
                    self.send_response(206)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Range", f"bytes {s}-{e}/{size}")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(length))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return self.wfile.write(data)
            # Réponse complète.
            data = ap.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/ping":
                etat.touch()
                return self._json(200, {"ok": True})
            if path == "/api/export":
                return self._export()
            if path == "/api/ouvrir-tagueur":
                return self._ouvrir_tagueur()
            if path == "/api/reidentifier":
                return self._reidentifier()
            self._json(404, {"error": "not found"})

        def _reidentifier(self):
            """Relance la DETECTION (detecter.py) sur le transcript courant et
            REECRIT le .etat.json : candidats rafraichis depuis le transcript
            CORRIGE (extraits a jour) + tout NOUVEL alias eventuel. Declenche
            manuellement par l'editeur apres une correction de texte (bouton).
            NB : reecrire le .etat.json efface la trace de validation -> il faut
            re-exporter la memoire pour re-valider (coherent : le transcript a
            change)."""
            etat_path = etat.etat_path
            try:
                data = json.loads(etat_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                return self._json(500, {"error": f".etat.json illisible : {e}"})
            entretien = etat_path.parent.parent
            tdir = (data.get("transcript_dir") or "").strip()
            tname = (data.get("transcript") or "").strip()
            if not tname:
                return self._json(400, {"error": "transcript inconnu dans .etat.json"})
            transcript = (entretien / tdir / tname) if tdir else (entretien / tname)
            if not transcript.is_file():
                return self._json(404, {"error": f"transcript introuvable : {transcript}"})
            repo = Path(__file__).resolve().parents[2]
            detecter = repo / "tools" / "anonymisation" / "detecter.py"
            if not detecter.is_file():
                return self._json(500, {"error": "detecter.py introuvable"})
            cmd = [sys.executable, str(detecter), str(transcript), "--out", str(etat_path)]
            if etat.memoire_path.is_file():
                cmd += ["--memoire", str(etat.memoire_path)]
            ign = repo / "config" / "ignorer_global.json"
            if ign.is_file():
                cmd += ["--ignorer-global", str(ign)]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(entretien))
            except OSError as e:
                return self._json(500, {"error": f"lancement detecter.py : {e}"})
            if r.returncode != 0:
                return self._json(500, {"error": f"detecter.py code {r.returncode}",
                                        "detail": (r.stderr or "")[-600:]})
            try:
                n = len(json.loads(etat_path.read_text(encoding="utf-8")).get("candidats", []))
            except (OSError, ValueError):
                n = None
            return self._json(200, {"ok": True, "candidats": n})

        def _ouvrir_tagueur(self):
            """Relance le tagueur sur l'entretien, positionne sur le terme a
            corriger (saut par TEXTE -> robuste au decoupage). Le tagueur reste
            la source de verite du texte ; apres correction + re-export, relancer
            l'identification. Renvoie une commande de repli si le lancement echoue.
            """
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n) if n else b""
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except (ValueError, UnicodeDecodeError):
                payload = {}
            texte = (payload.get("texte") or "").strip()
            if not texte:
                return self._json(400, {"error": "champ 'texte' attendu"})
            repo = Path(__file__).resolve().parents[2]
            serveur_tg = repo / "tools" / "transcription" / "serveur_tagueur.py"
            tagger = repo / "tools" / "transcription" / "tagger.html"
            entretien = etat.etat_path.parent.parent
            cmd_aide = f'ia taguer -Find "{texte}"'
            if not serveur_tg.is_file() or not tagger.is_file():
                return self._json(500, {"error": "serveur_tagueur/tagger introuvable",
                                        "cmd": cmd_aide})
            # On choisit un port LIBRE et on le passe au serveur_tagueur, lance en
            # --no-browser : c'est l'EDITEUR (vrai navigateur) qui ouvrira l'onglet
            # via window.open(url). Plus fiable que webbrowser depuis un sous-process
            # detache (qui pouvait ne pas charger en mode serveur -> export en
            # download au lieu d'ecrire dans 2_coupe).
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
                s.close()
            except OSError as e:
                return self._json(500, {"error": str(e), "cmd": cmd_aide})
            try:
                subprocess.Popen(
                    [sys.executable, str(serveur_tg), "--root", str(entretien),
                     "--tagger", str(tagger), "--port", str(port), "--no-browser"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    cwd=str(entretien))
            except OSError as e:
                return self._json(500, {"error": str(e), "cmd": cmd_aide})
            url = f"http://127.0.0.1:{port}/?find={quote(texte)}"
            return self._json(200, {"ok": True, "url": url, "cmd": cmd_aide})

        def _export(self):
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n) if n else b""
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                return self._json(400, {"error": f"corps JSON invalide : {e}"})
            mem = payload.get("memoire")
            if not isinstance(mem, dict) or "entrees" not in mem:
                return self._json(400, {"error": "champ 'memoire' (objet) attendu"})
            try:
                content = json.dumps(mem, ensure_ascii=False, indent=2)
                etat.memoire_path.parent.mkdir(parents=True, exist_ok=True)
                etat.memoire_path.write_text(content, encoding="utf-8")
            except (OSError, TypeError) as e:
                return self._json(500, {"error": f"ecriture memoire_client.json : {e}"})
            # Trace de validation : l'export reussi de la memoire EST l'evenement
            # qui prouve que l'humain a valide l'analyse. On l'estampille dans le
            # .etat.json pour que l'orchestrateur puisse declencher l'anonymisation
            # automatique (etape "analyser" = la seule non automatisable).
            valide = _stamper_validation(etat.etat_path, etat.memoire_path)
            self._json(200, {"ok": True, "memoire_path": str(etat.memoire_path),
                             "validation_tracee": valide})

    return Handler


def watchdog(etat, httpd):
    time.sleep(GRACE_SEC)
    while True:
        if etat.idle() > GRACE_SEC:
            print(f"[serveur] Aucun ping depuis {GRACE_SEC:.0f}s -> arret.")
            threading.Thread(target=httpd.shutdown, daemon=True).start()
            return
        time.sleep(CHECK_EVERY)


def main():
    ap = argparse.ArgumentParser(description="Serveur local de l'editeur d'alias.")
    ap.add_argument("--etat", required=True, help="Chemin du .etat.json a editer.")
    ap.add_argument("--memoire", required=True, help="Chemin du memoire_client.json du perimetre (existant ou a creer).")
    ap.add_argument("--editeur", required=True, help="Chemin de editeur_alias.html.")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    etat_path = Path(args.etat).resolve()
    memoire_path = Path(args.memoire).resolve()
    editeur = Path(args.editeur).resolve()
    if not editeur.is_file():
        print(f"[ERREUR] editeur_alias.html introuvable : {editeur}", file=sys.stderr); sys.exit(1)
    if not etat_path.is_file():
        print(f"[ERREUR] .etat.json introuvable : {etat_path}", file=sys.stderr); sys.exit(1)

    etat = Etat(etat_path, memoire_path, editeur)
    Handler = make_handler(etat)

    port = args.port
    httpd = None
    for p in [port] + list(range(8771, 8791)):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        print("[ERREUR] Aucun port libre entre 8770 et 8790.", file=sys.stderr); sys.exit(1)

    url = f"http://127.0.0.1:{port}/"
    print(f"[serveur] Etat de detection : {etat_path}")
    print(f"[serveur] Memoire perimetre : {memoire_path}  ({'existe' if memoire_path.is_file() else 'sera creee a l export'})")
    print(f"[serveur] Editeur servi sur : {url}")
    print(f"[serveur] Ferme l'onglet pour arreter (auto apres {GRACE_SEC:.0f}s), ou Ctrl+C.")

    threading.Thread(target=watchdog, args=(etat, httpd), daemon=True).start()
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(url)), daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[serveur] Interruption clavier -> arret.")
    finally:
        httpd.server_close()
        print("[serveur] Arrete.")


if __name__ == "__main__":
    main()
