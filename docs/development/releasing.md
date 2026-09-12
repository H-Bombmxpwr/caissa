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

`landing/index.html` is a static page that offers the build matching the visitor's
platform and links to the documentation. It is what a public deployment serves:
`server.py` swaps `/` for it when `CAISSA_LANDING=1`, which `railway.json` and the
`Procfile` set. Locally the variable is unset, so `py server.py` still serves the
workbench.

The page only links to GitHub Releases — it never hosts the binaries itself, so the host
serves a few kilobytes rather than hundreds of megabytes. GitHub Pages would do the same
job for nothing if you would rather not run a host at all.
