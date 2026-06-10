#!/usr/bin/env python3
"""
BrainWreck Scoreboard Server
Stores scores globally, returns leaderboards filtered by country or worldwide.
"""
import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

SCORES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scores.json')

def load_scores():
    if os.path.exists(SCORES_FILE):
        with open(SCORES_FILE) as f:
            return json.load(f)
    return []

def save_scores(scores):
    with open(SCORES_FILE, 'w') as f:
        json.dump(scores, f)

class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        country = params.get('country', [None])[0]
        limit = int(params.get('limit', [20])[0])

        scores = load_scores()

        if country:
            scores = [s for s in scores if s.get('country', '').upper() == country.upper()]

        # Sort by score descending
        scores.sort(key=lambda x: x['score'], reverse=True)
        scores = scores[:limit]

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(scores).encode())

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"error":"invalid json"}')
            return

        # Required fields
        username = data.get('username', '').strip()
        score = data.get('score', 0)
        country = data.get('country', 'XX').strip().upper()
        action = data.get('action', 'set')  # 'set' or 'delete'

        if not username or len(username) > 20:
            self.send_response(400)
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"error":"invalid username"}')
            return

        scores = load_scores()

        if action == 'delete':
            scores = [s for s in scores if s['username'] != username]
            save_scores(scores)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({'status':'deleted'}).encode())
            return

        # Update existing or add new (keep only one entry per username)
        found = False
        for s in scores:
            if s['username'] == username:
                if score > s['score']:
                    s['score'] = score
                    s['country'] = country
                    s['time'] = int(time.time())
                found = True
                break

        if not found:
            scores.append({
                'username': username,
                'score': score,
                'country': country,
                'time': int(time.time())
            })

        save_scores(scores)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'ok'}).encode())

    def do_DELETE(self):
        """Remove a player's score — for admin cleanup."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        username = params.get('username', [None])[0]
        if not username:
            self.send_response(400); self._cors(); self.end_headers()
            self.wfile.write(b'{"error":"need username"}'); return
        scores = load_scores()
        scores = [s for s in scores if s['username'] != username]
        save_scores(scores)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps({'status':'deleted','username':username}).encode())

    def log_message(self, format, *args):
        pass  # quiet

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8081))
    print(f'BrainWreck Scoreboard running on port {port}')
    print(f'Scores stored in: {SCORES_FILE}')
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
