"""Caissa — desktop entry point.

Starts the local API server on a free port and opens it in a native window
(Edge WebView2 on Windows) via pywebview. If pywebview is missing, it falls back
to your default browser so the app still runs.

    py desktop.py                 # normal launch
    py desktop.py --browser       # skip the native window
    py desktop.py --smoke         # start, check health, exit (for tests)
"""

import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

APP_NAME = "Caissa"


class DesktopSettings:
    """Native folder access is exposed only to the desktop window.

    pywebview walks this object's public attributes to build window.pywebview.api,
    so the window reference has to stay private: a public one sends that walk into
    the WinForms control's .NET properties, which recurses without end and touches
    the WebView2 controller off the UI thread before the page can finish loading.
    """
    def __init__(self, data_dir, overridden=False):
        self.data_dir = data_dir
        self.overridden = overridden
        self._window = None
        self.selected_folder = None

    def storage_info(self):
        from backend.paths import storage_preferences
        prefs = storage_preferences()
        return {'path': self.data_dir, 'overridden': self.overridden,
                'pending': prefs.get('pending', {}).get('target'), 'error': prefs.get('error')}

    def choose_storage_folder(self):
        import webview
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=self.data_dir)
        self.selected_folder = result[0] if result else None
        return self.selected_folder

    def use_storage_folder(self):
        from backend.paths import schedule_storage_change
        if self.overridden:
            return {'error': 'DATA_DIR controls this launch. Remove that override before changing storage in Settings.'}
        if not self.selected_folder:
            return {'error': 'Choose a folder first.'}
        try:
            target = schedule_storage_change(self.data_dir, self.selected_folder)
            self.selected_folder = None
            return {'pending': target}
        except (OSError, ValueError) as err:
            return {'error': str(err)}

    def cancel_storage_change(self):
        from backend.paths import storage_preferences, save_storage_preferences
        prefs = storage_preferences()
        prefs.pop('pending', None)
        prefs.pop('error', None)
        save_storage_preferences(prefs)
        self.selected_folder = None
        return {'cancelled': True}


def bundle_root():
    """Where the app's files live — the source tree, or the PyInstaller bundle."""
    return getattr(sys, "_MEIPASS", ROOT)


def default_data_dir():
    """Installed apps keep their library in the user's app data, not next to the exe."""
    from backend.paths import default_data_dir as resolve
    return resolve()


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(port, data_dir):
    os.environ["DATA_DIR"] = data_dir
    import server                                   # imported after DATA_DIR is set

    handler = partial(server.Handler, directory=bundle_root())
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def wait_for_health(port, timeout=20):
    url = "http://127.0.0.1:%d/api/health" % port
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception:                            # noqa: BLE001 - server still coming up
            time.sleep(0.15)
    raise RuntimeError("the local server did not come up")


def main():
    parser = argparse.ArgumentParser(description="%s desktop app" % APP_NAME)
    parser.add_argument("--browser", action="store_true", help="open in the default browser")
    parser.add_argument("--smoke", action="store_true", help="start, check, and exit")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    overridden = bool(os.environ.get('DATA_DIR'))
    data_dir = default_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    port = args.port or free_port()

    start_server(port, data_dir)
    health = wait_for_health(port)
    url = "http://127.0.0.1:%d/" % port

    print("%s ready" % APP_NAME)
    print("  url     : %s" % url)
    print("  library : %s" % health.get("data_dir"))
    print("  games   : %s" % health.get("games"))

    if args.smoke:
        try:
            from backend.engine import default_binary
            print("  engine  : %s" % (default_binary() or "not bundled (run tools/fetch_stockfish.py)"))
        except Exception as err:                     # noqa: BLE001
            print("  engine  : unavailable (%s)" % err)
        return 0

    if not args.browser:
        try:
            import webview                           # pywebview

            settings = DesktopSettings(data_dir, overridden)
            window = webview.create_window(
                APP_NAME, url,
                js_api=settings,
                width=1440, height=940, min_size=(1000, 680),
                background_color="#161512",
                text_select=True,
            )
            settings._window = window
            start_args = {
                "gui": None,
                "private_mode": False,
                "storage_path": os.path.join(data_dir, "webview"),
            }
            icon = os.path.join(bundle_root(), "assets", "caissa.ico")
            if os.path.exists(icon):
                start_args["icon"] = icon          # ignored by back-ends that set it from the exe
            try:
                webview.start(**start_args)
            except TypeError:                      # older pywebview without icon support
                start_args.pop("icon", None)
                webview.start(**start_args)
            del window
            return 0
        except ImportError:
            print("pywebview is not installed — falling back to the browser.")
            print("  py -m pip install pywebview")

    import webbrowser
    webbrowser.open(url)
    print("Press Ctrl+C to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
