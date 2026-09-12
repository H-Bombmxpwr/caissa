# The download page

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

The page never hosts a binary. It reads the visitor's platform and points the button at
the matching asset under
`https://github.com/H-Bombmxpwr/caissa/releases/latest/download/…`, so GitHub does the
file serving and this page stays the same size however large the builds become.

The asset names come from `.github/workflows/release.yml`. If you rename one there,
rename it in `index.html` too — there is no build step to catch the mismatch.
