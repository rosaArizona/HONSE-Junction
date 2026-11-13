#!/usr/bin/env python3
"""Spread console: serves index.html and proxies /api/* to the Spread server.

    export SPREAD_KEY=<team-key>
    python3 server.py            # then open http://localhost:8765

No packages needed (Python 3.8+). The key stays on this machine: the browser
never sees it, and the proxy sidesteps browser CORS limits.
"""
import json, os, sys, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.environ.get("SPREAD_URL", "https://spread.bahnexpress.com").rstrip("/")
KEY = os.environ.get("SPREAD_KEY", "")
PORT = int(os.environ.get("PORT", "8765"))
HERE = os.path.dirname(os.path.abspath(__file__))
PASS_HEADERS = ("Content-Type", "Retry-After", "RateLimit-Policy",
                "RateLimit-Limit", "RateLimit-Remaining", "RateLimit-Reset")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def _send(self, code, data=b"", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD" and code != 204:
            self.wfile.write(data)

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(BASE + self.path[4:], data=body, method=self.command)
        req.add_header("User-Agent", "spread-console/1.0")
        if KEY:
            req.add_header("Authorization", "Bearer " + KEY)
        if body:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                code, data, hdrs = r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            code, data, hdrs = e.code, e.read(), e.headers
        except Exception as e:  # network down, DNS, timeout...
            msg = json.dumps({"error": "proxy could not reach %s: %s" % (BASE, e)})
            return self._send(502, msg.encode(), {"Content-Type": "application/json"})
        out = {h: hdrs[h] for h in PASS_HEADERS if hdrs.get(h)}
        self._send(code, data, out)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        if self.path == "/config":
            body = json.dumps({"base": BASE, "hasKey": bool(KEY)}).encode()
            return self._send(200, body, {"Content-Type": "application/json"})
        if self.path.split("?")[0] in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), {"Content-Type": "text/html; charset=utf-8"})
        self._send(404, b"not found", {"Content-Type": "text/plain"})

    do_POST = do_DELETE = do_PUT = lambda self: (
        self._proxy() if self.path.startswith("/api/") else self._send(404, b"not found"))


if __name__ == "__main__":
    if not KEY:
        print("Warning: SPREAD_KEY is not set. Get a key at %s/join and run:\n"
              "  export SPREAD_KEY=<your team key>" % BASE, file=sys.stderr)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("Spread console on http://localhost:%d  (upstream %s)" % (PORT, BASE))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
