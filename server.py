#!/usr/bin/env python3
"""
BrainWreck Scoreboard Server — GitHub-backed persistent storage.
Scores survive Render restarts via GitHub repo.
"""
import json
import os
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO_API = 'https://api.github.com/repos/hermesandroid/brainwreck/contents/scores.json'
REPO_RAW = 'https://raw.githubusercontent.com/hermesandroid/brainwreck/main/scores.json'

# In-memory cache (avoids hitting GitHub on every GET)
_cache = None
_cache_time = 0
CACHE_TTL = 5  # seconds

def _github_request(url, method='GET', data=None):
    """Make an authenticated GitHub API request."""
    headers = {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if data:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(data).encode()
    else:
        body = None

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return None
    except Exception:
        return None

def load_scores():
    """Load scores from GitHub (cached in memory)."""
    global _cache, _cache_time
    now = time.time()

    if _cache is not None and (now - _cache_time) < CACHE_TTL:
        return _cache

    try:
        req = urllib.request.Request(REPO_RAW)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        _cache = data if isinstance(data, list) else []
        _cache_time = now
        return _cache
    except Exception:
        return _cache if _cache is not None else []

def save_scores(scores):
    """Save scores to GitHub. Updates cache."""
    global _cache, _cache_time

    # Get current file SHA (needed for GitHub update)
    current = _github_request(REPO_API)
    sha = current.get('sha', '') if current else ''

    data = {
        'message': 'Update scores',
        'content': json.dumps(scores, ensure_ascii=False),
        'sha': sha,
    }

    result = _github_request(REPO_API, method='PUT', data=data)
    if result:
        _cache = scores
        _cache_time = time.time()
        return True
    return False


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

        scores.sort(key=lambda x: x['score'], reverse=True)
        scores = scores[:limit]

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(scores).encode())

    def do_POST(self):
        cl = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(cl)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400); self._cors(); self.end_headers()
            self.wfile.write(b'{"error":"invalid json"}'); return

        username = data.get('username', '').strip()
        score = data.get('score', 0)
        country = data.get('country', 'XX').strip().upper()
        action = data.get('action', 'set')

        if not username or len(username) > 20:
            self.send_response(400); self._cors(); self.end_headers()
            self.wfile.write(b'{"error":"invalid username"}'); return

        scores = load_scores()

        if action == 'delete':
            scores = [s for s in scores if s['username'] != username]
            ok = save_scores(scores)
            self.send_response(200 if ok else 500)
            self.send_header('Content-Type', 'application/json')
            self._cors(); self.end_headers()
            self.wfile.write(json.dumps({'status':'deleted' if ok else 'error'}).encode())
            return

        # Update or add
        found = False
        for s in scores:
            if s['username'] == username:
                if score > s['score']:
                    s['score'] = score; s['country'] = country
                    s['time'] = int(time.time())
                found = True; break

        if not found:
            scores.append({'username':username,'score':score,'country':country,'time':int(time.time())})

        ok = save_scores(scores)
        self.send_response(200 if ok else 500)
        self.send_header('Content-Type', 'application/json')
        self._cors(); self.end_headers()
        self.wfile.write(json.dumps({'status':'ok' if ok else 'error'}).encode())

    def log_message(self, format, *args):
        pass


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8081))
    print(f'BrainWreck Scoreboard on port {port}')
    print('Storage: GitHub (persistent)')
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
