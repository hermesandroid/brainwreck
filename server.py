#!/usr/bin/env python3
"""
BrainWreck Scoreboard Server
Persists scores to GitHub repo via REST API — survives Render sleep cycles.
Username ownership via secret key (no passwords, no registration).
"""
import json
import os
import time
import hashlib
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO_OWNER = 'hermesandroid'
REPO_NAME = 'brainwreck'
LEADERBOARD_PATH = 'leaderboard.json'
GITHUB_API = f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{LEADERBOARD_PATH}'

# In-memory cache — reduces GitHub API calls
_cache = None
_cache_time = 0
CACHE_TTL = 30  # seconds

def _github_request(method, url, data=None):
    """Make an authenticated GitHub API request."""
    req = urllib.request.Request(url, method=method)
    req.add_header('Authorization', f'Bearer {GITHUB_TOKEN}')
    req.add_header('Accept', 'application/vnd.github.v3+json')
    req.add_header('User-Agent', 'BrainWreck/1.0')
    if data:
        req.add_header('Content-Type', 'application/json')
        req.data = json.dumps(data).encode()
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        print(f'GitHub API error {e.code}: {body[:200]}')
        return None
    except Exception as e:
        print(f'GitHub API request failed: {e}')
        return None

def load_scores():
    """Load scores from GitHub (with in-memory cache)."""
    global _cache, _cache_time
    now = time.time()
    if _cache is not None and (now - _cache_time) < CACHE_TTL:
        return _cache
    if not GITHUB_TOKEN:
        return _cache or []
    data = _github_request('GET', GITHUB_API)
    if data and 'content' in data:
        import base64
        try:
            content = base64.b64decode(data['content']).decode('utf-8')
            _cache = json.loads(content)
            _cache_time = now
            return _cache
        except Exception as e:
            print(f'Failed to decode leaderboard: {e}')
    return _cache or []

def save_scores(scores):
    """Save scores to GitHub and update cache."""
    global _cache, _cache_time
    _cache = scores
    _cache_time = time.time()
    if not GITHUB_TOKEN:
        return True  # fallback: pretend it worked
    content = json.dumps(scores, indent=2, ensure_ascii=False)
    import base64
    encoded = base64.b64encode(content.encode('utf-8')).decode('ascii')
    # Get current SHA (needed for update)
    existing = _github_request('GET', GITHUB_API)
    sha = existing.get('sha', '') if existing else ''
    payload = {
        'message': f'Update leaderboard — {len(scores)} scores',
        'content': encoded,
    }
    if sha:
        payload['sha'] = sha
    result = _github_request('PUT', GITHUB_API, payload)
    if result is None:
        print('Warning: GitHub API save failed — scores in memory only')
        return False
    return True

def make_secret(username, key):
    """Derive a stable secret hash from username + random key."""
    return hashlib.sha256(f'{username}:{key}'.encode()).hexdigest()[:16]


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
            scores = [s for s in scores if s.get('country', '').upper() == country.upper()]
        scores.sort(key=lambda x: x['score'], reverse=True)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors(); self.end_headers()
        self.wfile.write(json.dumps(scores[:limit]).encode())

    def do_POST(self):
        cl = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(cl)
        try:
            data = json.loads(body)
        except Exception:
            self.send_response(400); self._cors(); self.end_headers(); return

        username = data.get('username', '').strip()
        score = int(data.get('score', 0))
        country = data.get('country', 'XX').upper()
        secret = data.get('secret', '').strip()

        if not username or len(username) > 20:
            self.send_response(400); self._cors(); self.end_headers(); return

        scores = load_scores()

        if data.get('action') == 'delete':
            # Only allow delete with correct secret
            for s in scores:
                if s['username'] == username:
                    if s.get('secret') != secret:
                        self._respond_json({'status': 'error', 'reason': 'wrong_secret'}, 403)
                        return
            scores = [s for s in scores if s['username'] != username]
            save_scores(scores)
            self._respond_json({'status': 'ok'})
            return

        # Check if username exists
        existing = None
        for s in scores:
            if s['username'] == username:
                existing = s
                break

        if existing:
            # Username exists — must provide correct secret
            if existing.get('secret') and existing.get('secret') != secret:
                self._respond_json({'status': 'error', 'reason': 'name_taken'}, 409)
                return
            # Update score (only if higher)
            if score > existing['score']:
                existing['score'] = score
                existing['country'] = country
                existing['time'] = int(time.time())
        else:
            # New username — first claim wins
            if not secret:
                self._respond_json({'status': 'error', 'reason': 'secret_required'}, 400)
                return
            scores.append({
                'username': username,
                'score': score,
                'country': country,
                'time': int(time.time()),
                'secret': secret,
            })

        save_scores(scores)
        self._respond_json({'status': 'ok'})

    def _respond_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self._cors(); self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8081))
    print(f'BrainWreck on port {port}')
    if GITHUB_TOKEN:
        print(f'GitHub persistence: enabled ({REPO_OWNER}/{REPO_NAME})')
    else:
        print('Warning: GITHUB_TOKEN not set — in-memory only (scores lost on sleep)')
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
