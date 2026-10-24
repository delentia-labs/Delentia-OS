"""Serve a Desk static export on loopback, resolving Next route HTML first.

Demo/review utility, not an authenticated public deployment server.
"""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class DeskStaticHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        translated = super().translate_path(path)
        # Next exports both settings.html and settings/ containing route data.
        # Prefer the page even when that data directory already exists.
        html = translated.rstrip('/') + '.html'
        return html if Path(html).is_file() else translated

    def list_directory(self, path):
        self.send_error(404, 'No public directory listing')
        return None

    def end_headers(self):
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1] / 'apps/gui/out')
    parser.add_argument('--port', type=int, default=3021)
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / 'index.html').is_file():
        parser.error('root must contain the built static export index.html')
    handler = partial(DeskStaticHandler, directory=str(root))
    ThreadingHTTPServer(('127.0.0.1', args.port), handler).serve_forever()


if __name__ == '__main__':
    main()
