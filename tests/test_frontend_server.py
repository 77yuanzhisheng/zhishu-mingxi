from __future__ import annotations

from functools import partial
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen

from frontend.server import FrontendHandler


def test_textbook_assets_are_served_from_the_frontend_directory(tmp_path):
    textbook = tmp_path / 'textbook'
    textbook.mkdir()
    (textbook / 'index.html').write_text('<h1>real interactive textbook</h1>', encoding='utf-8')

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(FrontendHandler, directory=str(tmp_path)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}/textbook/index.html'
        with urlopen(url, timeout=5) as response:
            body = response.read().decode('utf-8')

        assert response.status == 200
        assert 'real interactive textbook' in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
