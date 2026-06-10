#!/usr/bin/env python3
"""
BrainWreck Scoreboard Server
Stores scores in-memory + periodically syncs. Survives between deploys.
"""
import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

SCORES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scores.json')

def load_scores():
    try:
        if os.path.exists(SCORES_FILE):
            with open(SCORES_FILE) as f:
                return json.load(f)
    except: pass
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
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        country = params.get('country', [None])[0]
        limit = int(params.get('limit', [20])[0])
        scores = load_scores()
        if country:
            scores = [s for s in scores if s.get('country','').upper() == country.upper()]
        scores.sort(key=lambda x: x['score'], reverse=True)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors(); self.end_headers()
        self.wfile.write(json.dumps(scores[:limit]).encode())

    def do_POST(self):
        cl = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(cl)
        try: data = json.loads(body)
        except: self.send_response(400); self._cors(); self.end_headers(); return

        username = data.get('username','').strip()
        score = int(data.get('score', 0))
        country = data.get('country','XX').upper()

        if not username or len(username) > 20:
            self.send_response(400); self._cors(); self.end_headers(); return

        scores = load_scores()

        if data.get('action') == 'delete':
            scores = [s for s in scores if s['username'] != username]
        else:
            found = False
            for s in scores:
                if s['username'] == username:
                    if score > s['score']:
                        s['score'] = score; s['country'] = country; s['time'] = int(time.time())
                    found = True; break
            if not found:
                scores.append({'username':username,'score':score,'country':country,'time':int(time.time())})

        save_scores(scores)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors(); self.end_headers()
        self.wfile.write(json.dumps({'status':'ok'}).encode())

    def log_message(self, *a): pass


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8081))
    print(f'BrainWreck on port {port}')
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
