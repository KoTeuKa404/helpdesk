"""Standalone persistent mock, intentionally not reachable outside localhost in Compose."""
import json
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

DB_PATH = Path(os.environ.get("MOCK_DB_PATH", "/data/replies.sqlite3"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(DB_PATH) as db:
    db.execute("CREATE TABLE IF NOT EXISTS replies (id INTEGER PRIMARY KEY, idem TEXT UNIQUE NOT NULL, ticket_id TEXT NOT NULL, message TEXT NOT NULL)")
lock = threading.Lock()

class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, data, extra=None):
        result = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(result)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(result)

    def do_GET(self):
        if urlsplit(self.path).path != "/replies":
            return self.send_json(404, {"error": "not found"})
        with lock, sqlite3.connect(DB_PATH) as db:
            rows = db.execute("SELECT ticket_id, message FROM replies ORDER BY id DESC LIMIT 100").fetchall()
        self.send_json(200, [{"ticket_id": x, "message": y} for x, y in rows])

    def do_POST(self):
        path = urlsplit(self.path).path
        if not (path.startswith("/tickets/") and path.endswith("/replies")):
            return self.send_json(404, {"error": "not found"})
        if int(self.headers.get("Content-Length", "0")) > 8192:
            return self.send_json(413, {"error": "too large"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            key = self.headers.get("Idempotency-Key", "")
            ticket_id = path[len("/tickets/"):-len("/replies")].strip("/")
            if not key or not isinstance(body.get("message"), str) or len(body["message"]) > 5000 or body.get("ticket_id") != ticket_id:
                return self.send_json(400, {"error": "invalid payload"})
        except (ValueError, TypeError):
            return self.send_json(400, {"error": "invalid JSON"})
        with lock, sqlite3.connect(DB_PATH) as db:
            cur = db.execute("INSERT OR IGNORE INTO replies (idem, ticket_id, message) VALUES (?, ?, ?)", (key, ticket_id, body["message"]))
            is_replay = cur.rowcount == 0
            db.commit()
        self.send_json(201, {"ok": True, "duplicate": is_replay}, {"X-Idempotent-Replay": "1"} if is_replay else {})

ThreadingHTTPServer(("0.0.0.0", 8001), Handler).serve_forever()
