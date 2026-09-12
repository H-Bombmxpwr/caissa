"""Rebuild dist/Caissa/Caissa.exe. Run this any time; it is safe to repeat.

    py tools/build_exe.py              # normal rebuild
    py tools/build_exe.py --clean      # throw away build/ and dist/ first
    py tools/build_exe.py --skip-tests # build without running the backend tests

Fetches Stockfish and draws the icon if either is missing, checks that nothing secret
is about to be bundled, then runs PyInstaller against caissa.spec. Nothing it produces
is tracked by git: build/ and dist/ are already ignored.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
if not os.path.exists(PYTHON):
    PYTHON = sys.executable
OUT = os.path.join(ROOT, "dist", "Caissa", "Caissa.exe")


def run(args, what):
    print("==> " + what)
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit("%s failed (exit %d)" % (what, result.returncode))


def ensure(path, script, what):
    if os.path.exists(os.path.join(ROOT, path)):
        return
    run([PYTHON, os.path.join(ROOT, "tools", script)], what)


def check_no_secrets():
    """A key belongs in .env on this machine, never inside something you hand out."""
    spec = open(os.path.join(ROOT, "caissa.spec"), encoding="utf-8").read()
    for leak in (".env", "GEMINI_API_KEY"):
        if leak in spec:
            raise SystemExit("caissa.spec would bundle %s. Remove it before building." % leak)
    print("==> checked: no .env or API key is in the bundle list")


def main():
    parser = argparse.ArgumentParser(description="Build Caissa.exe")
    parser.add_argument("--clean", action="store_true", help="delete build/ and dist/ first")
    parser.add_argument("--skip-tests", action="store_true", help="do not run the backend tests")
    args = parser.parse_args()

    started = time.time()
    if args.clean:
        for folder in ("build", "dist"):
            target = os.path.join(ROOT, folder)
            if os.path.isdir(target):
                print("==> removing " + folder + os.sep)
                shutil.rmtree(target, ignore_errors=True)

    ensure(os.path.join("vendor", "stockfish", "stockfish.exe"), "fetch_stockfish.py", "Fetching Stockfish")
    ensure(os.path.join("assets", "caissa.ico"), "make_icon.py", "Drawing the application icon")
    if not os.path.exists(os.path.join(ROOT, "data", "openings.eco.json")):
        run([PYTHON, os.path.join(ROOT, "tools", "fetch_openings.py")], "Building the opening index")
    check_no_secrets()

    if not args.skip_tests:
        run([PYTHON, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], "Backend tests")

    run([PYTHON, "-m", "PyInstaller", "--noconfirm", os.path.join(ROOT, "caissa.spec")], "PyInstaller")

    if not os.path.exists(OUT):
        raise SystemExit("PyInstaller reported success but %s is missing" % OUT)
    size = sum(os.path.getsize(os.path.join(base, name))
               for base, _, names in os.walk(os.path.dirname(OUT)) for name in names)
    print("\nBuilt %s" % OUT)
    print("  folder: %.0f MB · %.0f seconds" % (size / 1024 / 1024, time.time() - started))
    print("  the app carries no API key; set GEMINI_API_KEY in a .env beside the exe to enable the AI note")


if __name__ == "__main__":
    main()
