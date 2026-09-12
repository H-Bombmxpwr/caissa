"""The public landing page: a download button, and never the application itself.

Run with .venv/Scripts/python tests/landing_browser.py
"""
import os
from pathlib import Path
import sys
import tempfile
import threading
from functools import partial
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
os.environ['CAISSA_LANDING'] = '1'
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory(prefix='caissa-landing-') as data:
    os.environ['DATA_DIR'] = data
    import server
    assert server.LANDING_ONLY, 'CAISSA_LANDING should switch the public page on'
    server.Handler.log_message = lambda *a: None
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), partial(server.Handler, directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:' + str(httpd.server_port)
    try:
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

            # It is a landing page, not the workbench: none of the app is loaded.
            assert page.evaluate('typeof window.Caissa') == 'undefined', 'the app leaked in'
            assert page.locator('#workspace').count() == 0
            assert 'Caissa' in page.title()

            # The logo, the explanation and the documentation link are all there.
            assert page.locator('header img').is_visible()
            assert len(page.locator('.lede').inner_text()) > 80
            links = page.eval_on_selector_all('a', 'els=>els.map(e=>e.href)')
            assert any('h-bombmxpwr.github.io/caissa' in l for l in links), links
            assert any('github.com/H-Bombmxpwr/caissa' in l for l in links), links

            # Every asset the page asks for really is served.
            for src in page.eval_on_selector_all('img,link[rel=icon]',
                                                 'els=>els.map(e=>e.src||e.href)'):
                if src.startswith(url):
                    assert page.request.get(src).status == 200, src

            # It reads on a phone without scrolling sideways.
            page.set_viewport_size({'width': 390, 'height': 800})
            page.wait_for_timeout(200)
            overflow = page.evaluate(
                'document.documentElement.scrollWidth-document.documentElement.clientWidth')
            assert overflow <= 2, '%dpx of horizontal overflow at 390px' % overflow

            # The API is still reachable, so a health check does not fail.
            assert page.request.get(url + '/api/health').status == 200

            assert not errors, errors
            browser.close()
            print('PASS: landing page offers the right build per platform, links to the '
                  'docs, and never serves the app')
    finally:
        httpd.shutdown()
        server.api.autoimport.stop()
        server.api.library.close()
