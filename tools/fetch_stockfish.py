"""Download the Stockfish binary the app ships with.

    py tools/fetch_stockfish.py            # latest release for this machine
    py tools/fetch_stockfish.py --list     # show what the release offers

The binary lands in vendor/stockfish/ and is deliberately not committed: it is
~80 MB, it is platform specific, and the build script fetches it on demand.

Stockfish is GPLv3 (https://github.com/official-stockfish/Stockfish); bundling it
makes the distributed application GPLv3 too. See SCOPE.md.
"""

import argparse
import io
import json
import os
import platform
import stat
import sys
import urllib.request
import zipfile

RELEASES = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "vendor", "stockfish")
UA = {"User-Agent": "Caissa-build/1.0"}


def latest_release():
    req = urllib.request.Request(RELEASES, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode("utf-8"))


def pick_asset(assets):
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        want = "windows-arm64" if "arm" in machine else "windows-x86-64"
    elif system == "darwin":
        want = "macos-m1-apple-silicon" if machine in ("arm64", "aarch64") else "macos-x86-64"
    else:
        want = "ubuntu-x86-64"

    candidates = [a for a in assets if want in a["name"].lower()]
    if not candidates:
        raise SystemExit("no Stockfish build matched %s/%s" % (system, machine))
    # "universal" bundles several CPU levels and picks at runtime; prefer it.
    for asset in candidates:
        if "universal" in asset["name"].lower():
            return asset
    return candidates[0]


def best_binary(names):
    """Inside the zip, prefer the fastest build this CPU can run."""
    order = ["avx512", "bmi2", "avx2", "sse41-popcnt", "modern", "universal", ""]
    exes = [n for n in names if n.lower().endswith(".exe") or "/stockfish" in n.lower()]
    exes = [n for n in exes if "stockfish" in os.path.basename(n).lower()]
    for token in order:
        for name in sorted(exes):
            if token and token in name.lower():
                return name
    return exes[0] if exes else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="list assets and exit")
    args = parser.parse_args()

    release = latest_release()
    print("Stockfish release:", release.get("tag_name"))
    if args.list:
        for asset in release.get("assets", []):
            print("  %-52s %6.1f MB" % (asset["name"], asset["size"] / 1e6))
        return

    asset = pick_asset(release.get("assets", []))
    print("downloading %s (%.1f MB)…" % (asset["name"], asset["size"] / 1e6))
    req = urllib.request.Request(asset["browser_download_url"], headers=UA)
    with urllib.request.urlopen(req, timeout=600) as res:
        blob = res.read()

    os.makedirs(DEST, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        target = best_binary(names)
        if not target:
            raise SystemExit("no stockfish executable inside %s" % asset["name"])
        print("extracting", target)
        data = archive.read(target)
        out_name = "stockfish.exe" if platform.system().lower() == "windows" else "stockfish"
        out_path = os.path.join(DEST, out_name)
        with open(out_path, "wb") as handle:
            handle.write(data)
        os.chmod(out_path, os.stat(out_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        # NNUE files sit next to the binary in some releases; take them along.
        for name in names:
            if name.lower().endswith(".nnue"):
                with open(os.path.join(DEST, os.path.basename(name)), "wb") as handle:
                    handle.write(archive.read(name))
                print("extracting", name)

    with open(os.path.join(DEST, "VERSION.txt"), "w", encoding="utf-8") as handle:
        handle.write("%s\n%s\n" % (release.get("tag_name"), asset["name"]))

    print("ready:", out_path, "(%.1f MB)" % (os.path.getsize(out_path) / 1e6))


if __name__ == "__main__":
    sys.exit(main())
