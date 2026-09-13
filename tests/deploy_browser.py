"""The download page, served the way the host serves it.

Run with .venv/Scripts/python tests/deploy_browser.py

This drives `deploy/serve.py` rather than the application's own server, because that is
what is deployed: the point of the folder is that it stands alone. GitHub's API is
stubbed, so the page is exercised in all four states it can be in — including the one
where no release has been published yet, which is how it starts life.
"""
import json
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
API = '**/api.github.com/repos/*/*/releases/latest'

AGENTS = {
    'windows': ('Windows NT 10.0; Win64; x64', 'Windows', 'Caissa-windows-x64.zip'),
    'macos': ('Macintosh; Intel Mac OS X 10_15_7', 'macOS', 'Caissa-macos-arm64.zip'),
    'linux': ('X11; Linux x86_64', 'Linux', 'Caissa-linux-x64.tar.gz'),
}


def release(assets):
    return {'tag_name': 'v2.1.0', 'html_url': 'https://github.com/x/y/releases/tag/v2.1.0',
            'assets': [{'name': name,
                        'size': 96 * 1024 * 1024,
                        'browser_download_url': 'https://example.test/' + name}
                       for name in assets]}


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

        def open_page(agent=None, api=None):
            page = browser.new_page(user_agent=(
                'Mozilla/5.0 (%s) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 '
                'Safari/537.36' % agent) if agent else None)
            page.on('pageerror', lambda e: (errors.append(str(e)),
                                            print('Browser error:', e, flush=True)))
            if api is not None:
                page.route(API, api)
            page.goto(url)
            page.wait_for_selector('#download')
            return page

        all_assets = [a[2] for a in AGENTS.values()]

        # 1. A published release: each platform is offered its own build, by the name the
        #    release actually carries rather than one assumed here.
        for key, (agent, label, asset) in AGENTS.items():
            page = open_page(agent, lambda r: r.fulfill(json=release(all_assets)))
            page.wait_for_function(
                '''()=>document.getElementById('download-label').textContent.startsWith('Download for')''')
            assert page.locator('#download').get_attribute('href').endswith(asset), key
            assert label in page.locator('#download-label').inner_text(), key
            note = page.locator('#note').inner_text()
            assert 'v2.1.0' in note and '96 MB' in note, note
            page.close()

        # 2. No release yet — the first state the page is ever in. It must not offer a
        #    link that 404s; it should send the reader to the source instructions.
        page = open_page(AGENTS['windows'][0],
                         lambda r: r.fulfill(status=404, json={'message': 'Not Found'}))
        page.wait_for_function(
            '''()=>document.getElementById('download-label').textContent==='Build from source' ''')
        href = page.locator('#download').get_attribute('href')
        assert href.endswith('#install'), href
        assert 'releases/latest/download' not in href, href
        assert 'No builds have been published' in page.locator('#note').inner_text()
        page.close()

        # 3. A Windows-only release, which is how this starts: a Linux or macOS visitor
        #    is told their build is not out yet and sent to the source, not to a guess.
        for key in ('linux', 'macos'):
            page = open_page(AGENTS[key][0],
                             lambda r: r.fulfill(json=release(['Caissa-windows-x64.zip'])))
            page.wait_for_function(
                '''()=>document.getElementById('download-label').textContent==='Build from source' ''')
            assert page.locator('#download').get_attribute('href').endswith('#install')
            note = page.locator('#note').inner_text()
            assert AGENTS[key][1] in note and 'Windows only so far' in note, note
            page.close()

        # An unrecognised platform still gets the release page rather than nothing.
        # Chromium derives client hints from the real OS, so the identity is replaced
        # before the page loads rather than through the user-agent string.
        page = browser.new_page()
        page.on('pageerror', lambda e: (errors.append(str(e)), print('Browser error:', e, flush=True)))
        page.add_init_script('''Object.defineProperty(navigator,'userAgentData',{get:()=>undefined});
            Object.defineProperty(navigator,'userAgent',{get:()=>'SomeUnknownOS/1.0'});''')
        page.route(API, lambda r: r.fulfill(json=release(all_assets)))
        page.goto(url)
        page.wait_for_function(
            '''()=>document.getElementById('download-label').textContent.includes('v2.1.0')''')
        assert 'releases/tag/v2.1.0' in page.locator('#download').get_attribute('href')
        assert 'Windows and macOS and Linux' in page.locator('#note').inner_text()
        page.close()

        # 4. Offline or rate limited: the button keeps its releases link and still works.
        page = open_page(AGENTS['macos'][0], lambda r: r.abort())
        page.wait_for_timeout(600)
        href = page.locator('#download').get_attribute('href')
        assert href == 'https://github.com/H-Bombmxpwr/caissa/releases/latest', href
        page.close()

        # The page itself: logo, explanation, documentation, and none of the application.
        page = open_page()
        assert page.evaluate('typeof window.Caissa') == 'undefined', 'the app leaked in'
        assert page.locator('#workspace').count() == 0
        assert 'Caissa' in page.title()
        assert page.request.get(url + '/js/workspace.js').status != 200, 'app files must not be served'
        assert page.locator('header img').is_visible()
        assert len(page.locator('.lede').inner_text()) > 80
        links = page.eval_on_selector_all('a', 'els=>els.map(e=>e.href)')
        assert any('h-bombmxpwr.github.io/caissa' in l for l in links), links
        assert any('github.com/H-Bombmxpwr/caissa' in l for l in links), links
        for src in page.eval_on_selector_all('img,link[rel=icon]', 'els=>els.map(e=>e.src||e.href)'):
            if src.startswith(url):
                assert page.request.get(src).status == 200, src

        # A tidied-up link lands on the page; a missing file is still a 404.
        stray = page.request.get(url + '/download')
        assert stray.status == 200 and 'Caissa' in stray.text(), stray.status

        page.set_viewport_size({'width': 390, 'height': 800})
        page.wait_for_timeout(200)
        overflow = page.evaluate(
            'document.documentElement.scrollWidth-document.documentElement.clientWidth')
        assert overflow <= 2, '%dpx of horizontal overflow at 390px' % overflow

        assert not errors, errors
        browser.close()

    # The release workflow has to produce an asset whose name each platform can match.
    workflow = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
    for key, (_, _, asset) in AGENTS.items():
        assert asset in workflow, '%s is not built by the release workflow' % asset
        assert key in asset.lower(), '%s must contain %r for the page to match it' % (asset, key)

    # Nothing in the folder may depend on the application.
    assert not (ROOT / 'deploy/requirements.txt').read_text(encoding='utf-8').strip(), \
        'the download page should need no dependencies'
    size = sum(f.stat().st_size for f in (ROOT / 'deploy').rglob('*') if f.is_file())
    assert size < 512 * 1024, 'deploy/ has grown to %d bytes' % size

    print('PASS: deploy/ stands alone; the button offers the real asset, admits when '
          'there are no builds, and never links to a 404')
finally:
    server.terminate()
    server.wait(timeout=10)
