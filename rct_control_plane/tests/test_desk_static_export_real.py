"""HTTP regression for Next's colliding route HTML/data directories."""
from functools import partial
from http.server import ThreadingHTTPServer
import threading
import urllib.request
import urllib.error

from scripts.serve_desk_static import DeskStaticHandler


def test_static_routes_headers_and_directory_refusal(tmp_path):
    (tmp_path / 'index.html').write_text('home', encoding='utf-8')
    (tmp_path / 'settings.html').write_text('<h1>ตั้งค่า</h1>', encoding='utf-8')
    (tmp_path / 'settings').mkdir()
    (tmp_path / 'settings' / 'data.txt').write_text('route data', encoding='utf-8')
    (tmp_path / 'internal').mkdir()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(DeskStaticHandler, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for path in ('/settings', '/settings/', '/settings?lang=th'):
            with opener.open(f'http://127.0.0.1:{server.server_port}{path}') as response:
                assert response.read().decode() == '<h1>ตั้งค่า</h1>'
                assert response.headers['X-Frame-Options'] == 'DENY'
                assert response.headers['X-Content-Type-Options'] == 'nosniff'
        with opener.open(f'http://127.0.0.1:{server.server_port}/settings/data.txt') as response:
            assert response.read() == b'route data'
        try:
            opener.open(f'http://127.0.0.1:{server.server_port}/internal/')
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError('directory listing was exposed')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
