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
import tarfile
import zipfile

RELEASES = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "vendor", "stockfish")
UA = {"User-Agent": "Caissa-build/1.0"}


def latest_release():
    req = urllib.request.Request(RELEASES, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode("utf-8"))


# Stockfish has renamed its assets more than once — the Linux build was "ubuntu-…"
# before it was "linux-…", and macOS used to ship a build per architecture where it now
# ships one universal binary. So each platform lists the names it will accept, best
# first, rather than assuming one.
WANTED = {
    ("windows", "arm"): ["windows-arm64"],
    ("windows", ""):    ["windows-x86-64"],
    ("darwin", "arm"):  ["macos-universal", "macos-m1-apple-silicon", "macos"],
    ("darwin", ""):     ["macos-universal", "macos-x86-64", "macos"],
    ("linux", "arm"):   ["linux-arm64", "ubuntu-arm64"],
    ("linux", ""):      ["linux-x86-64", "ubuntu-x86-64"],
}


def pick_asset(assets, system=None, machine=None):
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    if system not in ("windows", "darwin"):
        system = "linux"
    arch = "arm" if ("arm" in machine or "aarch64" in machine) else ""

    names = [(a, a["name"].lower()) for a in assets]
    for want in WANTED[(system, arch)]:
        candidates = [a for a, name in names if want in name]
        if not candidates:
            continue
        # "universal" bundles several CPU levels and chooses at runtime; prefer it.
        for asset in candidates:
            if "universal" in asset["name"].lower():
                return asset
        return candidates[0]
    raise SystemExit("no Stockfish build matched %s/%s. Available: %s"
                     % (system, machine, ", ".join(name for _, name in names)))


def members(blob, filename):
    """The names inside the archive, and a reader for one of them.

    Windows builds ship a zip; macOS and Linux ship a .tar.gz. Handling only the first
    is why those two platforms used to fail even once the name matched.
    """
    if filename.lower().endswith(".zip"):
        archive = zipfile.ZipFile(io.BytesIO(blob))
        return archive.namelist(), archive.read, archive
    archive = tarfile.open(fileobj=io.BytesIO(blob), mode="r:*")
    names = [m.name for m in archive.getmembers() if m.isfile()]

    def read(name):
        handle = archive.extractfile(name)
        if handle is None:
            raise SystemExit("could not read %s from %s" % (name, filename))
        return handle.read()

    return names, read, archive


def best_binary(names):
    """Inside the archive, prefer the fastest build this CPU can run."""
    order = ["avx512", "bmi2", "avx2", "sse41-popcnt", "modern", "universal", ""]
    exes = [n for n in names if "stockfish" in os.path.basename(n).lower()]
    # Documentation and source files travel in the same archive.
    exes = [n for n in exes
            if not os.path.splitext(n)[1].lower() in (".txt", ".md", ".nnue", ".html", ".cpp", ".h")]
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
    names, read, archive = members(blob, asset["name"])
    try:
        target = best_binary(names)
        if not target:
            raise SystemExit("no stockfish executable inside %s" % asset["name"])
        print("extracting", target)
        data = read(target)
        out_name = "stockfish.exe" if platform.system().lower() == "windows" else "stockfish"
        out_path = os.path.join(DEST, out_name)
        with open(out_path, "wb") as handle:
            handle.write(data)
        os.chmod(out_path, os.stat(out_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        # NNUE files sit next to the binary in some releases; take them along.
        for name in names:
            if name.lower().endswith(".nnue"):
                with open(os.path.join(DEST, os.path.basename(name)), "wb") as handle:
                    handle.write(read(name))
                print("extracting", name)
    finally:
        archive.close()

    with open(os.path.join(DEST, "VERSION.txt"), "w", encoding="utf-8") as handle:
        handle.write("%s\n%s\n" % (release.get("tag_name"), asset["name"]))

    print("ready:", out_path, "(%.1f MB)" % (os.path.getsize(out_path) / 1e6))


if __name__ == "__main__":
    sys.exit(main())
