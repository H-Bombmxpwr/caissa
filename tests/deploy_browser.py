"""The download page, served the way the host serves it.

Run with .venv/Scripts/python tests/landing_browser.py

This drives `deploy/serve.py` rather than the application's own server, because that is
what is deployed: the point of the folder is that it stands alone.
"""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright

PORT = '8931'
url = 'http://127.0.0.1:' + PORT

# The folder must run with nothing installed, so it is started as its own process with
# the repository deliberately not on the path.
server = subprocess.Popen([sys.executable, str(ROOT / 'deploy' / 'serve.py')],
                          cwd=str(ROOT / 'deploy'),
                          env=dict(os.environ, PORT=PORT, PYTHONPATH=''),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            urllib.request.urlopen(url, timeout=1).read()
            break
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)
    else:
        raise AssertionError('deploy/serve.py did not come up')

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        errors = []

        # Each platform is offered its own build, and the button is never dead.
        wanted = {
            'Windows NT 10.0; Win64; x64': ('Caissa-windows-x64.zip', 'Windows'),
            'Macintosh; Intel Mac OS X 10_15_7': ('Caissa-macos-arm64.zip', 'macOS'),
            'X11; Linux x86_64': ('Caissa-linux-x64.tar.gz', 'Linux'),
        }
        for fragment, (asset, label) in wanted.items():
            page = browser.new_page(
                user_agent='Mozilla/5.0 (%s) AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120 Safari/537.36' % fragment)
            page.on('pageerror', lambda e: (errors.append(str(e)), print('Browser error:', e, flush=True)))
            page.goto(url)
            page.wait_for_selector('#download')
            href = page.locator('#download').get_attribute('href')
            assert href.endswith(asset), (fragment, href)
            assert label in page.locator('#download-label').inner_text(), fragment
            assert page.locator('#note').inner_text().strip(), 'no guidance for ' + label
            page.close()

        page = browser.new_page()
        page.on('pageerror', lambda e: (errors.append(str(e)), print('Browser error:', e, flush=True)))
        page.goto(url)
        page.wait_for_selector('#download')

        # It is a download page, not the workbench: none of the app is reachable.
        assert page.evaluate('typeof window.Caissa') == 'undefined', 'the app leaked in'
        assert page.locator('#workspace').count() == 0
        assert 'Caissa' in page.title()
        assert page.request.get(url + '/api/health').status in (200, 404), 'no API is expected'
        assert page.request.get(url + '/js/workspace.js').status != 200, 'app files must not be served'

        # The logo, the explanation and the documentation link are all there.
        assert page.locator('header img').is_visible()
        assert len(page.locator('.lede').inner_text()) > 80
        links = page.eval_on_selector_all('a', 'els=>els.map(e=>e.href)')
        assert any('h-bombmxpwr.github.io/caissa' in l for l in links), links
        assert any('github.com/H-Bombmxpwr/caissa' in l for l in links), links

        # Every asset the page asks for really is served from this folder.
        for src in page.eval_on_selector_all('img,link[rel=icon]', 'els=>els.map(e=>e.src||e.href)'):
            if src.startswith(url):
                assert page.request.get(src).status == 200, src

        # An unknown path lands on the page rather than on a stack trace.
        stray = page.request.get(url + '/download')
        assert stray.status == 200 and 'Caissa' in stray.text(), stray.status

        # It reads on a phone without scrolling sideways.
        page.set_viewport_size({'width': 390, 'height': 800})
        page.wait_for_timeout(200)
        overflow = page.evaluate(
            'document.documentElement.scrollWidth-document.documentElement.clientWidth')
        assert overflow <= 2, '%dpx of horizontal overflow at 390px' % overflow

        assert not errors, errors
        browser.close()

    # The asset names on the page have to match what the release workflow produces.
    workflow = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
    page_html = (ROOT / 'deploy/index.html').read_text(encoding='utf-8')
    for asset, _ in wanted.values():
        assert asset in workflow, '%s is not built by the release workflow' % asset
        assert asset in page_html, '%s is not offered by the page' % asset

    # Nothing in the folder may depend on the application.
    assert not (ROOT / 'deploy/requirements.txt').read_text(encoding='utf-8').strip(), \
        'the download page should need no dependencies'
    size = sum(f.stat().st_size for f in (ROOT / 'deploy').rglob('*') if f.is_file())
    assert size < 512 * 1024, 'deploy/ has grown to %d bytes' % size

    print('PASS: deploy/ stands alone, offers the right build per platform, and matches '
          'the release workflow')
finally:
    server.terminate()
    server.wait(timeout=10)
