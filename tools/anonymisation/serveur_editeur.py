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
    POST /api/export       -> ecrit le memoire_client.json au chemin du perimetre
    POST /api/ping         -> heartbeat
"""

import argparse
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

GRACE_SEC = 15.0
CHECK_EVERY = 3.0


class Etat:
    def __init__(self, etat_path: Path, memoire_path: Path, editeur: Path):
        self.etat_path = etat_path
        self.memoire_path = memoire_path
        self.editeur = editeur
        self.last_ping = time.time()
        self.lock = threading.Lock()

    def touch(self):
        with self.lock:
            self.last_ping = time.time()

    def idle(self):
        with self.lock:
            return time.time() - self.last_ping


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
                return self._json(200, {
                    "etat": etat.etat_path.is_file(),
                    "etat_name": etat.etat_path.name,
                    "memoire_existe": etat.memoire_path.is_file(),
                    "memoire_path": str(etat.memoire_path),
                })
            if path == "/api/etat":
                if not etat.etat_path.is_file():
                    return self._json(404, {"error": "etat.json absent"})
                return self._send(200, etat.etat_path.read_bytes(), "application/json; charset=utf-8")
            if path == "/api/memoire":
                if not etat.memoire_path.is_file():
                    return self._json(404, {"error": "memoire_client.json absent"})
                return self._send(200, etat.memoire_path.read_bytes(), "application/json; charset=utf-8")
            self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/ping":
                etat.touch()
                return self._json(200, {"ok": True})
            if path == "/api/export":
                return self._export()
            self._json(404, {"error": "not found"})

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
            self._json(200, {"ok": True, "memoire_path": str(etat.memoire_path)})

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
