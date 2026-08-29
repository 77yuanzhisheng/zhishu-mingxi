"""Static frontend server with history-route fallback for local development."""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


FRONTEND_DIR = Path(__file__).resolve().parent
DEFAULT_TEXTBOOK_DIR = Path('D:/') / '\u6311\u6218\u676f' / 'textbook_2.0'


def resolve_textbook_directory() -> Path | None:
    """Resolve the configured textbook directory or the existing local junction."""
    configured = os.getenv('TEXTBOOK_DIR', '').strip()
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend((FRONTEND_DIR / 'textbook', DEFAULT_TEXTBOOK_DIR))
    for candidate in candidates:
        if (candidate / 'index.html').is_file():
            return candidate.resolve()
    return None


def textbook_fallback_path() -> Path:
    """Provide a visible in-repo page instead of an opaque iframe 404."""
    return FRONTEND_DIR / 'textbook-unavailable.html'


FRONTEND_ROUTES = {
    "/",
    "/dashboard",
    "/chat",
    "/truth-table",
    "/relation",
    "/knowledge-graph",
    "/practice",
    "/grading",
    "/learning",
    "/classes",
    "/exam",
    "/tools",
}


class FrontendHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == '/textbook' or path.startswith('/textbook/'):
            textbook_dir = resolve_textbook_directory()
            if textbook_dir is None:
                self.path = '/textbook-unavailable.html'
            else:
                relative_path = path[len('/textbook'):].lstrip('/') or 'index.html'
                self.directory = str(textbook_dir)
                self.path = f'/{relative_path}'
        elif path in FRONTEND_ROUTES:
            self.path = "/index.html"
        super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the learning platform frontend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5500)
    args = parser.parse_args()

    handler = partial(FrontendHandler, directory=str(FRONTEND_DIR))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Frontend running on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
