"""Read a local .env into the environment. No dependency, no secrets in the repo.

.env is gitignored and is deliberately absent from caissa.spec's bundle list, so a
built Caissa.exe carries no key: anyone running a build of their own supplies their
own .env, and a key pasted here never reaches anybody else's machine.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def candidates():
    """Where a .env may live: beside a built exe first, then the source tree.

    A frozen app's modules live inside the bundle, so the source-tree path is useless
    there; looking next to the executable is what lets someone drop in their own key.
    """
    found = []
    if getattr(sys, "frozen", False):
        found.append(os.path.join(os.path.dirname(sys.executable), ".env"))
    found.append(os.path.join(ROOT, ".env"))
    return found


def load(path=None):
    """Set any KEY=value lines that are not already in the environment."""
    lines = None
    for attempt in ([path] if path else candidates()):
        try:
            with open(attempt, encoding="utf-8") as handle:
                lines = handle.readlines()
            break
        except OSError:
            continue
    if lines is None:
        return {}
    found = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if not key or not value:
            continue
        found[key] = value
        os.environ.setdefault(key, value)     # a real environment variable still wins
    return found
