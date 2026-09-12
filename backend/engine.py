"""The bundled Stockfish, spoken to over UCI.

One long-lived process, guarded by a lock, plus a background worker that can
annotate a whole game and store the result. The browser no longer needs its own
engine when the app runs on the desktop.
"""

import os
import platform
import subprocess
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_binary():
    """Where the bundled engine lives, in the source tree or inside a build."""
    name = "stockfish.exe" if platform.system().lower() == "windows" else "stockfish"
    candidates = [
        os.environ.get("STOCKFISH_PATH"),
        os.path.join(ROOT, "vendor", "stockfish", name),
        os.path.join(getattr(__import__("sys"), "_MEIPASS", ROOT), "vendor", "stockfish", name),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


class EngineError(Exception):
    pass


class Engine:
    """A single UCI process. All public methods are safe to call from threads."""

    def __init__(self, path=None, threads=None, hash_mb=256):
        self.path = path or default_binary()
        self.threads = threads or max(1, (os.cpu_count() or 2) - 1)
        self.hash_mb = hash_mb
        self.proc = None
        self.lock = threading.Lock()
        self.name = "unavailable"
        self.options = {}

    # ---------- lifecycle ----------

    def available(self):
        return bool(self.path and os.path.exists(self.path))

    def start(self):
        if self.proc and self.proc.poll() is None:
            return True
        if not self.available():
            raise EngineError(
                "Stockfish is not bundled yet — run: py tools/fetch_stockfish.py"
            )
        flags = 0
        if platform.system().lower() == "windows":
            flags = subprocess.CREATE_NO_WINDOW            # no console flash
        self.proc = subprocess.Popen(
            [self.path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            bufsize=1,
            creationflags=flags,
        )
        self._send("uci")
        for line in self._read_until("uciok"):
            if line.startswith("id name "):
                self.name = line[len("id name "):].strip()
        self.set_option("Threads", self.threads)
        self.set_option("Hash", self.hash_mb)
        self._send("isready")
        self._read_until("readyok")
        return True

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self._send("quit")
                self.proc.wait(timeout=3)
            except Exception:                               # noqa: BLE001
                self.proc.kill()
        self.proc = None

    def _send(self, command):
        if not self.proc or self.proc.poll() is not None:
            raise EngineError("engine is not running")
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()

    def _read_until(self, token, timeout=60):
        deadline = time.time() + timeout
        lines = []
        while True:
            if time.time() > deadline:
                raise EngineError("engine timed out waiting for '%s'" % token)
            line = self.proc.stdout.readline()
            if not line:
                raise EngineError("engine stopped unexpectedly")
            line = line.strip()
            lines.append(line)
            if line == token or line.startswith(token + " "):
                return lines

    def set_option(self, name, value):
        self._send("setoption name %s value %s" % (name, value))
        self.options[name] = value

    def info(self):
        return {
            "available": self.available(),
            "path": self.path,
            "name": self.name,
            "running": bool(self.proc and self.proc.poll() is None),
            "threads": self.threads,
            "hash_mb": self.hash_mb,
        }

    # ---------- analysis ----------

    @staticmethod
    def _parse_info(line):
        parts = line.split()
        out = {}
        i = 0
        while i < len(parts):
            token = parts[i]
            if token == "depth":
                out["depth"] = int(parts[i + 1]); i += 2
            elif token == "seldepth":
                out["seldepth"] = int(parts[i + 1]); i += 2
            elif token == "multipv":
                out["multipv"] = int(parts[i + 1]); i += 2
            elif token == "nodes":
                out["nodes"] = int(parts[i + 1]); i += 2
            elif token == "nps":
                out["nps"] = int(parts[i + 1]); i += 2
            elif token == "score":
                kind = parts[i + 1]
                value = int(parts[i + 2])
                if kind == "cp":
                    out["cp"] = value
                else:
                    out["mate"] = value
                i += 3
            elif token == "pv":
                out["pv"] = parts[i + 1:]
                break
            else:
                i += 1
        return out

    def analyze(self, fen, movetime=None, depth=None, multipv=1, on_update=None):
        """Blocking analysis of one position. Returns the best lines, best first."""
        with self.lock:
            self.start()
            self.set_option("MultiPV", max(1, int(multipv)))
            self._send("position fen " + fen)
            if on_update:
                self._send('go infinite')
            elif depth:
                self._send("go depth %d" % int(depth))
            else:
                self._send("go movetime %d" % int(movetime or 1000))

            lines = {}
            best_move = None
            deadline = float('inf') if on_update else time.time() + 300
            while True:
                if time.time() > deadline:
                    self._send("stop")
                    raise EngineError("analysis timed out")
                raw = self.proc.stdout.readline()
                if not raw:
                    raise EngineError("engine stopped unexpectedly")
                raw = raw.strip()
                if raw.startswith("info ") and " pv " in raw:
                    parsed = self._parse_info(raw)
                    lines[parsed.get("multipv", 1)] = parsed
                    if on_update:
                        on_update([lines[k] for k in sorted(lines)])
                elif raw.startswith("bestmove"):
                    bits = raw.split()
                    best_move = bits[1] if len(bits) > 1 else None
                    break

            ordered = [lines[k] for k in sorted(lines)]
            return {
                "fen": fen,
                "bestmove": best_move,
                "lines": ordered,
                "engine": self.name,
            }


class LiveAnalysis:
    """Dedicated UCI process so batch annotation cannot block live updates."""
    def __init__(self):
        self.engine = Engine()
        self.lock = threading.Lock()
        self.thread = None
        self.state = {'running': False, 'lines': [], 'id': None}
        self.monitor = None

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.engine.stop()
            self.thread.join(timeout=4)
        self.state['running'] = False

    def start(self, fen, multipv):
        import uuid
        with self.lock:
            self.stop()
            self.engine = Engine()
            self.engine.start()
            self.state = dict(id=uuid.uuid4().hex, fen=fen, running=True, lines=[])
            try:
                import psutil
                self.monitor = psutil.Process(self.engine.proc.pid)
                self.monitor.cpu_percent()
            except ImportError:
                self.monitor = None
            self.thread = threading.Thread(target=self._run, args=(fen, multipv), daemon=True)
            self.thread.start()
            return self.status()

    def _run(self, fen, multipv):
        try:
            self.engine.analyze(fen, multipv=multipv,
                on_update=lambda lines: self.state.update(lines=lines))
        except Exception as err:
            self.state['error'] = str(err)
        finally:
            self.state['running'] = False

    def status(self):
        state = self.state.copy()
        if self.monitor and state['running']:
            try:
                state['cpu_percent'] = self.monitor.cpu_percent()
                state['memory_mb'] = round(self.monitor.memory_info().rss / 1048576, 1)
            except Exception:
                pass
        return state


class AnnotationJob:
    """Walks a game's positions and scores every one of them."""

    JUDGMENTS = [
        (300, "blunder"),
        (150, "mistake"),
        (75, "inaccuracy"),
    ]

    def __init__(self, engine, library):
        self.engine = engine
        self.library = library
        self.thread = None
        self.stop_flag = threading.Event()
        self.lock = threading.Lock()
        self.state = {
            "running": False, "game_id": None, "done": 0, "total": 0,
            "error": None, "results": [], "started_at": None, "finished_at": None,
        }

    def status(self):
        with self.lock:
            return dict(self.state)

    def start(self, game_id, positions, movetime=300, depth=None):
        """`positions` is [{ply, fen, san}] worked out by the browser's rules engine."""
        if self.thread and self.thread.is_alive():
            return False
        self.stop_flag.clear()
        with self.lock:
            self.state.update({
                "running": True, "game_id": game_id, "done": 0, "total": len(positions),
                "error": None, "results": [], "started_at": int(time.time()), "finished_at": None,
            })
        self.thread = threading.Thread(
            target=self._run, args=(game_id, positions, movetime, depth), daemon=True
        )
        self.thread.start()
        return True

    def stop(self):
        self.stop_flag.set()

    @classmethod
    def judge(cls, loss):
        for threshold, label in cls.JUDGMENTS:
            if loss >= threshold:
                return label
        return None

    def _run(self, game_id, positions, movetime, depth):
        results = []
        try:
            previous = None
            for index, item in enumerate(positions):
                if self.stop_flag.is_set():
                    break
                out = self.engine.analyze(
                    item["fen"], movetime=movetime, depth=depth, multipv=1
                )
                top = out["lines"][0] if out["lines"] else {}
                score = top.get("cp")
                mate = top.get("mate")
                # scores come from the mover's point of view; store White's
                white_to_move = " w " in item["fen"]
                cp = None
                if score is not None:
                    cp = score if white_to_move else -score
                elif mate is not None:
                    cp = (10000 - abs(mate) * 10) * (1 if (mate > 0) == white_to_move else -1)

                entry = {
                    "ply": item.get("ply", index),
                    "fen": item["fen"],
                    "san": item.get("san"),
                    "cp": cp,
                    "mate": mate,
                    "best": out.get("bestmove"),
                    "pv": top.get("pv", [])[:6],
                    "depth": top.get("depth"),
                    "judgment": None,
                    "loss": None,
                }
                if previous is not None and previous["cp"] is not None and cp is not None:
                    mover_was_white = " w " in previous["fen"]
                    loss = (previous["cp"] - cp) if mover_was_white else (cp - previous["cp"])
                    entry["loss"] = max(0, loss)
                    previous["played_judgment"] = self.judge(max(0, loss))
                    previous["played_loss"] = max(0, loss)
                results.append(entry)
                previous = entry

                with self.lock:
                    self.state["done"] = index + 1
                    self.state["results"] = results
        except Exception as err:                            # noqa: BLE001
            with self.lock:
                self.state["error"] = str(err)
        finally:
            with self.lock:
                self.state["running"] = False
                self.state["finished_at"] = int(time.time())
                self.state["results"] = results
