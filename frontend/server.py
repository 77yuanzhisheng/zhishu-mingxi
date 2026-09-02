"""Static frontend server with history-route fallback for local development."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


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
    "/companion",
    "/classes",
    "/exam",
    "/lesson-prep",
    "/tools",
}


class FrontendHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path in FRONTEND_ROUTES:
            # 保留 query（如 ?demo=1003），只回退路由到 index.html
            self.path = "/index.html" + (f"?{parsed.query}" if parsed.query else "")
        super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the learning platform frontend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5500)
    args = parser.parse_args()

    frontend_dir = Path(__file__).resolve().parent
    handler = partial(FrontendHandler, directory=str(frontend_dir))
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
