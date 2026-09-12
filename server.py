"""Caissa server: static app + JSON API over the game library.

Dependency-free on purpose — standard library only.

    python server.py                 # http://localhost:8000
    PORT=3000 python server.py
    DATA_DIR=D:\\chess python server.py

On Railway, PORT is provided and DATA_DIR should point at a mounted volume
(for example /data) so the library survives deploys.
"""

import json
import os
import sys
import traceback
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.api import Api, ApiError          # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(ROOT, "library")
MAX_BODY = 256 * 1024 * 1024                   # PGN pastes can be large

NO_CACHE = {".html", ".json", ".pgn"}
LONG_CACHE_SECONDS = 60 * 60 * 24 * 7

api = Api(DATA_DIR)


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".svg": "image/svg+xml",
        ".json": "application/json",
        ".wasm": "application/wasm",
        ".pgn": "application/x-chess-pgn",
        ".md": "text/markdown",
    }

    # ---------- api ----------

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return None
        if length > MAX_BODY:
            raise ApiError("that upload is too large", 413)
        raw = self.rfile.read(length)
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if ctype == "application/json":
            try:
                return json.loads(raw.decode("utf-8"))
            except ValueError as err:
                raise ApiError("invalid JSON body") from err
        if ctype in ("application/x-chess-pgn", "text/plain", "application/octet-stream"):
            return {"pgn": raw.decode("utf-8", "replace")}
        return {"raw": raw.decode("utf-8", "replace")}

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_api(self, method):
        parsed = urllib.parse.urlparse(self.path)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        try:
            body = self._read_body()
            status, payload = api.handle(method, parsed.path, query, body)
            if isinstance(payload, tuple):                      # raw download
                data, ctype = payload
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._send_json(status, payload)
        except ApiError as err:
            self._send_json(err.status, {"error": err.message})
        except BrokenPipeError:
            pass
        except Exception as err:                                # noqa: BLE001
            traceback.print_exc()
            self._send_json(500, {"error": "%s: %s" % (type(err).__name__, err)})

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._serve_api("GET")
        return super().do_GET()

    def do_HEAD(self):
        if self.path.startswith("/api/"):
            return self._serve_api("GET")
        return super().do_HEAD()

    def do_POST(self):
        return self._serve_api("POST")

    def do_PUT(self):
        return self._serve_api("PUT")

    def do_DELETE(self):
        return self._serve_api("DELETE")

    # ---------- static ----------

    def end_headers(self):
        if not self.path.startswith("/api/"):
            ext = os.path.splitext(self.path.split("?")[0])[1].lower()
            if ext in NO_CACHE or self.path in ("/", ""):
                self.send_header("Cache-Control", "no-cache")
            elif ext:
                self.send_header("Cache-Control", "public, max-age=%d" % LONG_CACHE_SECONDS)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stdout.write("%s %s\n" % (self.address_string(), fmt % args))
        sys.stdout.flush()


def main():
    port = int(os.environ.get("PORT", "8000"))
    handler = partial(Handler, directory=ROOT)
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print("Caissa on http://0.0.0.0:%d" % port, flush=True)
    print("library: %s" % DATA_DIR, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()
