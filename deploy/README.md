# The download page

Live at <https://caissa.hxr.life/>.

This folder is the whole of what gets deployed. It is a static page that links to the
builds on GitHub Releases, plus a standard-library server to hand it out — no engine, no
database, no dependencies.

```
deploy/
  index.html          the page
  assets/             the logo
  serve.py            ~40 lines, standard library only
  railway.json        start command and health check
  Procfile            the same, for hosts that read one
  requirements.txt    deliberately empty
```

## Deploying it

**Set the service's root directory to `deploy`.** On Railway that is
*Service → Settings → Source → Root Directory*. The host then builds and copies this
folder alone — a few kilobytes — instead of the whole repository.

Nothing else is needed: `railway.json` supplies the start command, and the server binds
whatever `$PORT` the host provides.

Any static host works just as well. GitHub Pages, Netlify or Cloudflare Pages will serve
`index.html` and `assets/` for nothing, and then `serve.py` is not needed at all.

## Running it locally

```bash
python deploy/serve.py          # http://localhost:8000
```

## What it links to

Deploying the website does **not** build or upload Caissa.exe. To populate its download
button, run **Actions → Release → Run workflow**, enter a version such as `v2.2.0`,
and enable **Publish the downloads**. Alternatively push a `v*` version tag.
Wait for the Windows build and Publish jobs to finish. A manual run without Publish
only produces Actions artifacts, which are not public release downloads.

Windows uses a portable ZIP containing `Caissa/Caissa.exe` and its `_internal` folder.
Extract the entire ZIP and launch the executable. Distributing the executable alone
does not work: its web view, engine and assets are in the accompanying folder.
An installer is not needed for this layout, and updates retain the external library.

The page queries GitHub's latest published release and chooses an attached asset for
the visitor's platform. It shows a source-install fallback if no build exists.
On API failure it retains the Releases link so downloads remain reachable.

The page never hosts a binary. GitHub serves the selected release asset, so this page
stays the same size however large the builds become.

The asset names come from `.github/workflows/release.yml`. If you rename one there,
keep the platform token (`windows`, `macos`, or `linux`) in the filename so the page
can recognize it.
