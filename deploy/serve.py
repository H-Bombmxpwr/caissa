"""Serve the download page. Standard library only — there is nothing to install.

This folder is deployed on its own: point the host's root directory at `deploy/` and
it copies a few kilobytes of HTML and one PNG. The application itself is a desktop
program that reads your own disk, so there is nothing useful it could do for a stranger
over the internet, and no reason to ship the engine, the database or the dependencies
to a web host.

The binaries are not hosted here either. The page links to GitHub Releases, which does
the file serving, so this stays small however large the builds get.
"""
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FOREVER = ('.png', '.jpg', '.svg', '.ico', '.woff2')


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # The page changes with every release; the logo does not.
        forever = self.path.lower().endswith(CACHE_FOREVER)
        self.send_header('Cache-Control', 'public, max-age=31536000, immutable'
                         if forever else 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        super().end_headers()

    def send_error(self, code, message=None, explain=None):
        # A tidied-up link like /download should land on the page. A request for a file
        # that is genuinely not here — /js/workspace.js, say — should still be a 404,
        # or a missing asset would quietly come back as a page of HTML.
        name = self.path.split('?')[0].rstrip('/').rsplit('/', 1)[-1]
        if code == 404 and '.' not in name:
            self.path = '/index.html'
            return SimpleHTTPRequestHandler.do_GET(self)
        return super().send_error(code, message, explain)

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))


def main():
    port = int(os.environ.get('PORT', 8000))
    server = ThreadingHTTPServer(('0.0.0.0', port), partial(Handler, directory=HERE))
    print('Download page on http://0.0.0.0:%d' % port, flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
