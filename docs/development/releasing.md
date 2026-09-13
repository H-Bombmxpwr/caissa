# Releasing

## Why there are three downloads

PyInstaller cannot cross-compile. A Windows `.exe` has to be built on Windows, a macOS
`.app` on macOS, and a Linux binary on Linux — the bundled Python runtime, the native
web view and the Stockfish binary are all platform-specific. There is no way to produce
all three from one machine.

So the build runs three times, once on each GitHub-hosted runner, and the three archives
are attached to a single GitHub Release. You do not need a Mac or a Linux box of your own.

## Cutting a release

```bash
git tag v2.1.0
git push origin v2.1.0
```

That starts `.github/workflows/release.yml`, which on each runner fetches the engine and
the bundled data, builds with `caissa.spec`, checks that no proprietary audio got in,
packages, and uploads. The `publish` job then creates the release with all three files
attached. Running the workflow by hand instead builds the artifacts without publishing
anything, which is the way to test a change to it.

| Platform | Asset | Built on |
| --- | --- | --- |
| Windows x64 | `Caissa-windows-x64.zip` | `windows-latest` |
| macOS (Apple silicon) | `Caissa-macos-arm64.zip` | `macos-latest` |
| Linux x64 | `Caissa-linux-x64.tar.gz` | `ubuntu-latest` |

> **The engine download is the part that breaks**
>
> Stockfish renames its release assets from time to time, and when it does the old name
> keeps matching on one platform and stops matching on the others — which is exactly how
> a release ends up shipping Windows only. `tests/test_fetch_stockfish.py` pins the
> current and historical naming for all six platform/architecture combinations, and pins
> both archive formats, so a rename fails a test instead of a release.

## What each platform needs

- **Windows** — Edge WebView2, which ships with Windows 10 and 11. An unsigned build
  trips SmartScreen; *More info → Run anyway* gets past it. Signing needs a code-signing
  certificate.
- **macOS** — WKWebView is built in. The app is not notarised, so Gatekeeper blocks a
  double-click on first run; *right-click → Open* works. Proper notarisation needs an
  Apple Developer ID at $99/year, after which the warning goes away.
- **Linux** — pywebview uses WebKitGTK, which is not always installed:
  `sudo apt install gir1.2-webkit2-4.1 python3-gi`. The workflow installs it on the
  runner so the build itself works; the note in the release body tells users.

> **The macOS and Linux builds are untested on real hardware**
>
> The code is portable — engine download, library paths and the folder-opening helper
> all branch per platform — and the workflow builds all three. Nobody has yet run the
> result on a Mac or a Linux desktop. Treat those two as beta until someone has.

## The download page

`deploy/` is a self-contained folder — that is the whole point of it. It holds the page,
the logo, and a forty-line standard-library server, and nothing else:

```
deploy/
  index.html          the page
  assets/             the logo
  serve.py            standard library only
  railway.json        start command and health check
  Procfile            the same, for hosts that read one
  requirements.txt    deliberately empty
```

**Point the host's root directory at `deploy`.** On Railway that is
*Service → Settings → Source → Root Directory*. The host then builds and copies those
eighteen kilobytes instead of the whole repository — no engine, no database, no
dependencies to install, and nothing to keep in step with the application.

The page never hosts a binary. It reads the visitor's platform and points the button at
the matching asset under
`https://github.com/H-Bombmxpwr/caissa/releases/latest/download/…`, so GitHub serves the
files and this stays the same size however large the builds become.

Any static host does the same job: GitHub Pages, Netlify or Cloudflare Pages will serve
`index.html` and `assets/` for nothing, and then `serve.py` is not needed at all.

```bash
python deploy/serve.py          # http://localhost:8000, to see it before deploying
```

The page reads the asset list from the release itself through GitHub's API rather than
guessing a filename, so it survives a rename and, more importantly, survives there being
no release at all: before the first tag it offers *Build from source* instead of a link
that 404s. `tests/deploy_browser.py` drives all four states — a matching build, a release
without one for this platform, no releases yet, and an unreachable API.

The only thing that must hold is that each asset name contains `windows`, `macos` or
`linux`, which is how the page matches one to the visitor. That is checked too.
