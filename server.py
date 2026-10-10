"""Dependency-free, two-team mystery game. Run: python3 server.py."""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from game_rules import FINAL_ANSWERS, QUESTIONS, SOLUTION, correct_submission, event_record, normalize, state

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('GAME_DB', str(ROOT / '.runtime/game.sqlite3')))
GAME_MASTER_PASSWORD = os.environ.get('GAME_MASTER_PASSWORD', 'game')
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '1').casefold() in ('1', 'true', 'yes', 'on')
SESSION_MAX_AGE = 8 * 60 * 60
SESSION_COOKIE = 'reunion_gm_session'
TEAM_SESSION_MAX_AGE = 8 * 60 * 60
TEAM_SESSION_COOKIE_PREFIX = 'reunion_team_'
TEAM_CODE_ITERATIONS = 310_000
TEAM_LOGIN_FAILURE_LIMIT = 10
TEAM_LOGIN_WINDOW_SECONDS = 900
TEAM_LOGIN_LOCK_SECONDS = 300

DATA_BACKEND = os.environ.get('DATA_BACKEND', 'sqlite').casefold()
FIRESTORE_STORE = None


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


class closing_connection:
    def __enter__(self):
        self.connection = connect()
        return self.connection.__enter__()

    def __exit__(self, *args):
        try:
            return self.connection.__exit__(*args)
        finally:
            self.connection.close()


def initialize():
    global FIRESTORE_STORE
    if DATA_BACKEND == 'firestore':
        from firestore_store import FirestoreGameStore
        FIRESTORE_STORE = FirestoreGameStore(project_id=os.environ.get('GOOGLE_CLOUD_PROJECT'))
        FIRESTORE_STORE.initialize()
        return
    if DATA_BACKEND != 'sqlite':
        raise RuntimeError('DATA_BACKEND must be either "sqlite" or "firestore".')
    with closing_connection() as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS teams (id INTEGER PRIMARY KEY, started REAL, progress INTEGER DEFAULT 0, submission TEXT, last_attempt TEXT, finished REAL, wrong_attempts INTEGER DEFAULT 0)')
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(teams)')}
        if 'wrong_attempts' not in columns:
            connection.execute('ALTER TABLE teams ADD COLUMN wrong_attempts INTEGER DEFAULT 0')
        if 'last_attempt' not in columns:
            connection.execute('ALTER TABLE teams ADD COLUMN last_attempt TEXT')
        connection.executemany('INSERT OR IGNORE INTO teams (id) VALUES (?)', [(1,), (2,)])
        connection.execute('CREATE TABLE IF NOT EXISTS rounds (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, active INTEGER NOT NULL DEFAULT 1)')
        connection.execute('CREATE TABLE IF NOT EXISTS game_master_sessions (token_hash TEXT PRIMARY KEY, created_at REAL NOT NULL, expires_at REAL NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS team_access_codes (team_id INTEGER PRIMARY KEY CHECK(team_id IN (1,2)), salt TEXT NOT NULL, code_hash TEXT NOT NULL, iterations INTEGER NOT NULL, code_value TEXT, updated_at REAL NOT NULL)')
        code_columns = {row['name'] for row in connection.execute('PRAGMA table_info(team_access_codes)')}
        if 'code_value' not in code_columns:
            connection.execute('ALTER TABLE team_access_codes ADD COLUMN code_value TEXT')
        connection.execute('CREATE TABLE IF NOT EXISTS team_sessions (token_hash TEXT PRIMARY KEY, team_id INTEGER NOT NULL CHECK(team_id IN (1,2)), created_at REAL NOT NULL, expires_at REAL NOT NULL)')
        connection.execute('CREATE INDEX IF NOT EXISTS team_sessions_team_id ON team_sessions(team_id)')
        connection.execute('CREATE TABLE IF NOT EXISTS team_login_attempts (team_id INTEGER NOT NULL CHECK(team_id IN (1,2)), client_hash TEXT NOT NULL, failures INTEGER NOT NULL, window_started REAL NOT NULL, locked_until REAL NOT NULL DEFAULT 0, PRIMARY KEY(team_id, client_hash))')
        connection.execute('CREATE TABLE IF NOT EXISTS game_events (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, round_id INTEGER NOT NULL, team_id INTEGER, event_type TEXT NOT NULL, payload TEXT, correct INTEGER, summary TEXT NOT NULL)')
        connection.execute('CREATE INDEX IF NOT EXISTS game_events_round_id_id ON game_events(round_id, id DESC)')
        connection.execute('CREATE INDEX IF NOT EXISTS game_events_created_at ON game_events(created_at DESC)')
        active_round = connection.execute('SELECT id FROM rounds WHERE active=1 ORDER BY id DESC LIMIT 1').fetchone()
        if active_round is None:
            connection.execute('INSERT INTO rounds (created_at, active) VALUES (?, 1)', (time.time(),))
        else:
            connection.execute('UPDATE rounds SET active=0 WHERE active=1 AND id<>?', (active_round['id'],))
        # Sessions are deliberately transient; a server restart logs the game master out.
        connection.execute('DELETE FROM game_master_sessions')


def current_round_id(connection):
    row = connection.execute('SELECT id FROM rounds WHERE active=1 ORDER BY id DESC LIMIT 1').fetchone()
    if row:
        return row['id']
    cursor = connection.execute('INSERT INTO rounds (created_at, active) VALUES (?, 1)', (time.time(),))
    return cursor.lastrowid


def log_event(connection, round_id, event_type, team=None, payload=None, correct=None, summary=''):
    connection.execute(
        'INSERT INTO game_events (created_at, round_id, team_id, event_type, payload, correct, summary) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (time.time(), round_id, team, event_type, json.dumps(payload, ensure_ascii=False) if payload is not None else None,
         None if correct is None else int(bool(correct)), summary),
    )


def both_teams_finished(connection, round_id):
    rows = connection.execute('SELECT * FROM teams ORDER BY id').fetchall()
    return len(rows) == 2 and all(state(row, round_id)['ended'] for row in rows)


def session_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def team_cookie_name(team):
    return f'{TEAM_SESSION_COOKIE_PREFIX}{team}_session'


def team_code_hash(code, salt, iterations=TEAM_CODE_ITERATIONS):
    return hashlib.pbkdf2_hmac('sha256', code.encode('utf-8'), bytes.fromhex(salt), iterations).hex()


def create_team_code_record(code):
    salt = secrets.token_hex(16)
    return salt, team_code_hash(code, salt), TEAM_CODE_ITERATIONS


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'public'), **kwargs)

    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # Browsers may cancel media or navigation while a static file is streaming.
            self.close_connection = True

    def respond(self, data, status=200, headers=None):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def cookie_token(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
        except Exception:
            return ''
        morsel = cookies.get(SESSION_COOKIE)
        return morsel.value if morsel else ''

    def team_cookie_token(self, team):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
        except Exception:
            return ''
        morsel = cookies.get(team_cookie_name(team))
        return morsel.value if morsel else ''

    def authenticated_session(self, connection):
        token = self.cookie_token()
        if not token:
            return None
        return connection.execute('SELECT token_hash, expires_at FROM game_master_sessions WHERE token_hash=? AND expires_at>?',
                                  (session_hash(token), time.time())).fetchone()

    def require_game_master(self, connection):
        if not GAME_MASTER_PASSWORD:
            self.respond({'error': 'Game master login is not configured on this server.'}, 503)
            return None
        session = self.authenticated_session(connection)
        if not session:
            self.respond({'error': 'Game master login required.'}, 401)
            return None
        return session

    def same_origin(self):
        origin = self.headers.get('Origin')
        if not origin:
            return False
        parsed = urlsplit(origin)
        trusted_hosts = {self.headers.get('Host', '').casefold()}
        forwarded_host = self.headers.get('X-Forwarded-Host', '').split(',', 1)[0].strip()
        if forwarded_host:
            trusted_hosts.add(forwarded_host.casefold())
        return (parsed.scheme in ('http', 'https') and not parsed.path and not parsed.query and not parsed.fragment
                and parsed.username is None and parsed.password is None
                and parsed.netloc.casefold() in trusted_hosts)

    def set_session_cookie(self, token, max_age):
        parts = [f'{SESSION_COOKIE}={token}', 'Path=/', 'HttpOnly', 'SameSite=Strict', f'Max-Age={max_age}']
        if SESSION_COOKIE_SECURE:
            parts.append('Secure')
        return '; '.join(parts)

    def set_team_session_cookie(self, team, token, max_age):
        parts = [f'{team_cookie_name(team)}={token}', 'Path=/', 'HttpOnly', 'SameSite=Strict', f'Max-Age={max_age}']
        if SESSION_COOKIE_SECURE:
            parts.append('Secure')
        return '; '.join(parts)

    def authenticated_team(self, connection, team):
        token = self.team_cookie_token(team)
        if not token:
            return None
        return connection.execute('SELECT token_hash, team_id, expires_at FROM team_sessions WHERE token_hash=? AND team_id=? AND expires_at>?',
                                  (session_hash(token), team, time.time())).fetchone()

    def firestore_game_master_authenticated(self):
        token = self.cookie_token()
        return bool(token and FIRESTORE_STORE.gm_session(session_hash(token), time.time()))

    def firestore_team_authenticated(self, team):
        token = self.team_cookie_token(team)
        return bool(token and FIRESTORE_STORE.team_session(session_hash(token), team, time.time()))

    def firestore_require_game_master(self):
        if not GAME_MASTER_PASSWORD:
            self.respond({'error': 'Game master login is not configured on this server.'}, 503)
            return False
        if not self.firestore_game_master_authenticated():
            self.respond({'error': 'Game master login required.'}, 401)
            return False
        return True

    def firestore_get(self, path, parsed_url):
        if path == '/api/state':
            try:
                team = int(parse_qs(parsed_url.query).get('team', ['0'])[0])
                if team not in (1, 2):
                    raise ValueError()
            except (ValueError, TypeError):
                return self.respond({'error': 'Choose team 1 or 2.'}, 400)
            if not self.firestore_team_authenticated(team):
                return self.respond({'error': 'Team access code required.'}, 401)
            result = FIRESTORE_STORE.team_state(team)
            if result.get('error'):
                return self.respond(result, 409)
            return self.respond(result)
        if path == '/api/gm/session':
            return self.respond({'authenticated': bool(GAME_MASTER_PASSWORD and self.firestore_game_master_authenticated())})
        if path.startswith('/api/gm/') and not self.firestore_require_game_master():
            return
        if path == '/api/gm/dashboard':
            return self.respond(FIRESTORE_STORE.dashboard())
        if path == '/api/gm/team-codes':
            return self.respond(FIRESTORE_STORE.team_codes())
        if path == '/api/gm/team-codes/reveal':
            try:
                team = int(parse_qs(parsed_url.query).get('team', ['0'])[0])
                if team not in (1, 2):
                    raise ValueError()
            except (ValueError, TypeError):
                return self.respond({'error': 'Choose team 1 or 2.'}, 400)
            status, result = FIRESTORE_STORE.reveal_team_code(team)
            return self.respond(result, status)
        if path == '/api/gm/events':
            query = parse_qs(parsed_url.query)
            try:
                limit = int(query.get('limit', ['30'])[0])
                before = int(query['before'][0]) if query.get('before') else None
                team = int(query['team'][0]) if query.get('team') else None
                if (not 1 <= limit <= 100 or (before is not None and before <= 0)
                        or (team is not None and team not in (1, 2))):
                    raise ValueError()
            except (ValueError, TypeError):
                return self.respond({'error': 'Invalid event page.'}, 400)
            return self.respond(FIRESTORE_STORE.events(team, limit, before))
        return super().do_GET()

    def do_GET(self):
        parsed_url = urlsplit(self.path)
        path = parsed_url.path
        if path == '/healthz':
            return self.respond({'ok': True, 'backend': DATA_BACKEND})
        if DATA_BACKEND == 'firestore':
            return self.firestore_get(path, parsed_url)
        if path == '/api/state':
            try:
                team = int(parse_qs(parsed_url.query).get('team', ['0'])[0])
                if team not in (1, 2):
                    raise ValueError()
                with closing_connection() as connection:
                    round_id = current_round_id(connection)
                    if not self.authenticated_team(connection, team):
                        self.respond({'error': 'Team access code required.'}, 401)
                        return
                    reveal = both_teams_finished(connection, round_id)
                    self.respond(state(connection.execute('SELECT * FROM teams WHERE id=?', (team,)).fetchone(), round_id, reveal))
            except ValueError:
                self.respond({'error': 'Choose team 1 or 2.'}, 400)
        elif path == '/api/gm/session':
            with closing_connection() as connection:
                authenticated = bool(GAME_MASTER_PASSWORD and self.authenticated_session(connection))
                self.respond({'authenticated': authenticated})
        elif path == '/api/gm/dashboard':
            with closing_connection() as connection:
                if not self.require_game_master(connection):
                    return
                round_id = current_round_id(connection)
                teams = []
                for team in (1, 2):
                    team_state = state(connection.execute('SELECT * FROM teams WHERE id=?', (team,)).fetchone(), round_id)
                    teams.append({'team': team, 'started': team_state['started'], 'progress': team_state['progress'],
                                  'remaining': team_state['remaining'], 'ended': team_state['ended'],
                                  'expired': team_state['expired'], 'wrong_attempts': team_state['wrong_attempts'],
                                  'submission': team_state.get('submission'), 'correct': team_state.get('correct')})
                self.respond({'round_id': round_id, 'teams': teams})
        elif path == '/api/gm/team-codes':
            with closing_connection() as connection:
                if not self.require_game_master(connection):
                    return
                rows = connection.execute('SELECT team_id FROM team_access_codes ORDER BY team_id').fetchall()
                configured = {row['team_id'] for row in rows}
                self.respond({'teams': [{'team': team, 'configured': team in configured} for team in (1, 2)]})
        elif path == '/api/gm/team-codes/reveal':
            try:
                team = int(parse_qs(parsed_url.query).get('team', ['0'])[0])
                if team not in (1, 2):
                    raise ValueError()
            except (ValueError, TypeError):
                self.respond({'error': 'Choose team 1 or 2.'}, 400)
                return
            with closing_connection() as connection:
                if not self.require_game_master(connection):
                    return
                row = connection.execute('SELECT code_value FROM team_access_codes WHERE team_id=?', (team,)).fetchone()
                if row is None:
                    self.respond({'error': 'No access code has been set for this team.'}, 404)
                elif row['code_value'] is None:
                    self.respond({'error': 'This code was saved before reveal support. Replace it once to make it viewable.'}, 409)
                else:
                    self.respond({'team': team, 'code': row['code_value']})
        elif path == '/api/gm/events':
            query = parse_qs(parsed_url.query)
            try:
                limit = int(query.get('limit', ['30'])[0])
                before = int(query['before'][0]) if query.get('before') else None
                team_filter = int(query['team'][0]) if query.get('team') else None
                if (not 1 <= limit <= 100 or (before is not None and before <= 0)
                        or (team_filter is not None and team_filter not in (1, 2))):
                    raise ValueError()
            except (ValueError, TypeError):
                self.respond({'error': 'Invalid event page.'}, 400)
                return
            with closing_connection() as connection:
                if not self.require_game_master(connection):
                    return
                filters, params = [], []
                if team_filter is not None:
                    filters.append('team_id=?')
                    params.append(team_filter)
                if before:
                    filters.append('id<?')
                    params.append(before)
                where = f" WHERE {' AND '.join(filters)}" if filters else ''
                rows = connection.execute(f'SELECT * FROM game_events{where} ORDER BY id DESC LIMIT ?',
                                          (*params, limit + 1)).fetchall()
                has_more = len(rows) > limit
                self.respond({'events': [event_record(row) for row in rows[:limit]], 'has_more': has_more})
        else:
            super().do_GET()

    def read_json(self, maximum=8192):
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 < size <= maximum:
            raise ValueError()
        data = json.loads(self.rfile.read(size))
        if not isinstance(data, dict):
            raise ValueError()
        return data

    def firestore_post(self, path, data):
        if path == '/api/gm/login':
            if not GAME_MASTER_PASSWORD:
                return self.respond({'error': 'Game master login is not configured on this server.'}, 503)
            if not self.same_origin():
                return self.respond({'error': 'Request origin could not be verified.'}, 403)
            password = data.get('password')
            if not isinstance(password, str) or not hmac.compare_digest(password.encode('utf-8'), GAME_MASTER_PASSWORD.encode('utf-8')):
                return self.respond({'error': 'Incorrect game master password.'}, 401)
            token, now = secrets.token_urlsafe(32), time.time()
            FIRESTORE_STORE.create_gm_session(session_hash(token), now, now + SESSION_MAX_AGE)
            return self.respond({'authenticated': True}, headers={'Set-Cookie': self.set_session_cookie(token, SESSION_MAX_AGE)})

        if path == '/api/team/login':
            if not self.same_origin():
                return self.respond({'error': 'Request origin could not be verified.'}, 403)
            team = int(data.get('team', 0))
            code = data.get('code')
            if not isinstance(code, str) or not 8 <= len(code.strip()) <= 200:
                return self.respond({'error': 'Enter the team access code.'}, 400)
            token, now = secrets.token_urlsafe(32), time.time()
            forwarded_for = self.headers.get('X-Forwarded-For', '').split(',', 1)[0].strip()
            client_address = forwarded_for or self.client_address[0]
            status, result = FIRESTORE_STORE.team_login(team, code.strip(), session_hash(client_address),
                                                        session_hash(token), now, now + TEAM_SESSION_MAX_AGE)
            headers = {'Set-Cookie': self.set_team_session_cookie(team, token, TEAM_SESSION_MAX_AGE)} if status == 200 else None
            return self.respond(result, status, headers)

        if path.startswith('/api/gm/'):
            if not self.firestore_require_game_master():
                return
            if not self.same_origin():
                return self.respond({'error': 'Request origin could not be verified.'}, 403)
            token = self.cookie_token()
            if path == '/api/gm/logout':
                if token:
                    FIRESTORE_STORE.delete_gm_session(session_hash(token))
                return self.respond({'authenticated': False}, headers={'Set-Cookie': self.set_session_cookie('', 0)})
            if path == '/api/gm/team-codes':
                team = int(data.get('team', 0))
                code = data.get('code')
                if not isinstance(code, str) or not 8 <= len(code.strip()) <= 200:
                    return self.respond({'error': 'Team access codes must contain at least 8 characters.'}, 400)
                return self.respond(FIRESTORE_STORE.replace_team_code(team, code.strip(), time.time()))
            if path == '/api/gm/clear-team-events':
                team = int(data.get('team', 0))
                return self.respond({'team': team, 'deleted': FIRESTORE_STORE.clear_team_events(team)})
            if path == '/api/gm/new-round':
                return self.respond(FIRESTORE_STORE.new_round(time.time()))
            return self.respond({'error': 'Unknown action.'}, 404)

        if not self.same_origin():
            return self.respond({'error': 'Request origin could not be verified.'}, 403)
        team = int(data.get('team', 0))
        if not self.firestore_team_authenticated(team):
            return self.respond({'error': 'Team access code required.'}, 401)
        if path == '/api/start':
            status, result = FIRESTORE_STORE.start_team(team, time.time(), data.get('round_id'))
        elif path == '/api/answer':
            status, result = FIRESTORE_STORE.submit_answer(team, data.get('number'), data.get('answer', ''),
                                                           time.time(), data.get('round_id'))
        elif path == '/api/final':
            submission = {key: str(data.get(key, '')).strip()[:100] for key in SOLUTION}
            status, result = FIRESTORE_STORE.submit_final(team, submission, time.time(), data.get('round_id'))
        else:
            return self.respond({'error': 'Unknown action.'}, 404)
        return self.respond(result, status)

    def do_POST(self):
        path = urlsplit(self.path).path
        allowed = ('/api/start', '/api/answer', '/api/final', '/api/team/login', '/api/gm/login', '/api/gm/logout',
                   '/api/gm/team-codes',
                   '/api/gm/new-round', '/api/gm/clear-team-events')
        if path not in allowed:
            return self.respond({'error': 'Unknown action.'}, 404)
        try:
            data = self.read_json()
            if path in ('/api/start', '/api/answer', '/api/final', '/api/team/login'):
                team = int(data.get('team', 0))
                if team not in (1, 2):
                    raise ValueError()
            elif path == '/api/gm/team-codes':
                team = int(data.get('team', 0))
                if team not in (1, 2):
                    raise ValueError()
            elif path == '/api/gm/clear-team-events':
                team = int(data.get('team', 0))
                if team not in (1, 2):
                    raise ValueError()
        except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
            return self.respond({'error': 'Invalid request.'}, 400)

        if DATA_BACKEND == 'firestore':
            return self.firestore_post(path, data)

        if path == '/api/gm/login':
            if not GAME_MASTER_PASSWORD:
                return self.respond({'error': 'Game master login is not configured on this server.'}, 503)
            if not self.same_origin():
                return self.respond({'error': 'Request origin could not be verified.'}, 403)
            password = data.get('password')
            if not isinstance(password, str) or not hmac.compare_digest(password.encode('utf-8'), GAME_MASTER_PASSWORD.encode('utf-8')):
                return self.respond({'error': 'Incorrect game master password.'}, 401)
            token = secrets.token_urlsafe(32)
            now = time.time()
            with closing_connection() as connection:
                connection.execute('DELETE FROM game_master_sessions WHERE expires_at<=?', (now,))
                connection.execute('INSERT INTO game_master_sessions (token_hash, created_at, expires_at) VALUES (?, ?, ?)',
                                   (session_hash(token), now, now + SESSION_MAX_AGE))
            return self.respond({'authenticated': True}, headers={'Set-Cookie': self.set_session_cookie(token, SESSION_MAX_AGE)})

        if path == '/api/team/login':
            if not self.same_origin():
                return self.respond({'error': 'Request origin could not be verified.'}, 403)
            code = data.get('code')
            if not isinstance(code, str) or not 8 <= len(code.strip()) <= 200:
                return self.respond({'error': 'Enter the team access code.'}, 400)
            now = time.time()
            with closing_connection() as connection:
                record = connection.execute('SELECT salt, code_hash, iterations FROM team_access_codes WHERE team_id=?', (team,)).fetchone()
                if record is None:
                    return self.respond({'error': 'The Game Master has not set this team’s access code yet.'}, 409)
                client_hash = session_hash(self.client_address[0])
                attempts = connection.execute('SELECT failures, window_started, locked_until FROM team_login_attempts WHERE team_id=? AND client_hash=?', (team, client_hash)).fetchone()
                if attempts and attempts['locked_until'] > now:
                    return self.respond({'error': 'Too many incorrect codes. Please wait five minutes and try again.'}, 429)
                candidate = team_code_hash(code.strip(), record['salt'], record['iterations'])
                if not hmac.compare_digest(candidate, record['code_hash']):
                    if attempts and now - attempts['window_started'] < TEAM_LOGIN_WINDOW_SECONDS:
                        failures, window_started = attempts['failures'] + 1, attempts['window_started']
                    else:
                        failures, window_started = 1, now
                    locked_until = now + TEAM_LOGIN_LOCK_SECONDS if failures >= TEAM_LOGIN_FAILURE_LIMIT else 0
                    connection.execute('INSERT INTO team_login_attempts (team_id, client_hash, failures, window_started, locked_until) VALUES (?, ?, ?, ?, ?) ON CONFLICT(team_id, client_hash) DO UPDATE SET failures=excluded.failures, window_started=excluded.window_started, locked_until=excluded.locked_until',
                                       (team, client_hash, failures, window_started, locked_until))
                    if locked_until:
                        return self.respond({'error': 'Too many incorrect codes. Please wait five minutes and try again.'}, 429)
                    return self.respond({'error': 'That access code is incorrect.'}, 401)
                connection.execute('DELETE FROM team_login_attempts WHERE team_id=? AND client_hash=?', (team, client_hash))
                token = secrets.token_urlsafe(32)
                connection.execute('DELETE FROM team_sessions WHERE expires_at<=?', (now,))
                connection.execute('INSERT INTO team_sessions (token_hash, team_id, created_at, expires_at) VALUES (?, ?, ?, ?)',
                                   (session_hash(token), team, now, now + TEAM_SESSION_MAX_AGE))
            return self.respond({'authenticated': True, 'team': team}, headers={'Set-Cookie': self.set_team_session_cookie(team, token, TEAM_SESSION_MAX_AGE)})

        if path.startswith('/api/gm/'):
            with closing_connection() as connection:
                session = self.require_game_master(connection)
                if not session:
                    return
                if not self.same_origin():
                    return self.respond({'error': 'Request origin could not be verified.'}, 403)
                if path == '/api/gm/logout':
                    connection.execute('DELETE FROM game_master_sessions WHERE token_hash=?', (session['token_hash'],))
                    return self.respond({'authenticated': False}, headers={'Set-Cookie': self.set_session_cookie('', 0)})
                if path == '/api/gm/clear-team-events':
                    cursor = connection.execute('DELETE FROM game_events WHERE team_id=?', (team,))
                    return self.respond({'team': team, 'deleted': cursor.rowcount})
                if path == '/api/gm/team-codes':
                    code = data.get('code')
                    if not isinstance(code, str) or not 8 <= len(code.strip()) <= 200:
                        return self.respond({'error': 'Team access codes must contain at least 8 characters.'}, 400)
                    salt, code_hash, iterations = create_team_code_record(code.strip())
                    connection.execute('INSERT INTO team_access_codes (team_id, salt, code_hash, iterations, code_value, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(team_id) DO UPDATE SET salt=excluded.salt, code_hash=excluded.code_hash, iterations=excluded.iterations, code_value=excluded.code_value, updated_at=excluded.updated_at',
                                       (team, salt, code_hash, iterations, code.strip(), time.time()))
                    cursor = connection.execute('DELETE FROM team_sessions WHERE team_id=?', (team,))
                    connection.execute('DELETE FROM team_login_attempts WHERE team_id=?', (team,))
                    return self.respond({'team': team, 'configured': True, 'sessions_revoked': cursor.rowcount})
                if path == '/api/gm/new-round':
                    connection.execute('UPDATE rounds SET active=0 WHERE active=1')
                    cursor = connection.execute('INSERT INTO rounds (created_at, active) VALUES (?, 1)', (time.time(),))
                    round_id = cursor.lastrowid
                    connection.execute('DELETE FROM game_events WHERE team_id IN (1, 2)')
                    connection.execute('UPDATE teams SET started=NULL, progress=0, submission=NULL, last_attempt=NULL, finished=NULL, wrong_attempts=0')
                    log_event(connection, round_id, 'round_started', payload={'round': round_id}, summary=f'Round {round_id} started; both teams are ready.')
                    return self.respond({'round_id': round_id, 'message': f'Round {round_id} is ready. Team timers start when each team enters.'})

        with closing_connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if not self.same_origin():
                return self.respond({'error': 'Request origin could not be verified.'}, 403)
            if not self.authenticated_team(connection, team):
                return self.respond({'error': 'Team access code required.'}, 401)
            row = connection.execute('SELECT * FROM teams WHERE id=?', (team,)).fetchone()
            round_id = current_round_id(connection)
            current = state(row, round_id)
            message = ''
            status = 200
            if path == '/api/start':
                if not row['started']:
                    started = time.time()
                    connection.execute('UPDATE teams SET started=? WHERE id=?', (started, team))
                    log_event(connection, round_id, 'team_started', team=team, payload={'started_at': started}, summary=f'Team {team} started its investigation.')
            elif not row['started'] or current['ended']:
                message, status = 'This investigation is not active.', 409
            elif path == '/api/answer':
                index = row['progress']
                if index >= 5 or data.get('number') != index + 1:
                    message, status = 'This clue has already changed. Your case file has been refreshed.', 409
                else:
                    answer = str(data.get('answer', ''))[:200]
                    correct = normalize(answer) == QUESTIONS[index][1]
                    log_event(connection, round_id, 'answer_attempt', team=team,
                              payload={'question': index + 1, 'answer': answer}, correct=correct,
                              summary=f'Team {team} submitted an answer for question {index + 1}: {"correct" if correct else "incorrect"}.')
                    if not correct:
                        message, status = 'That answer does not unlock the evidence. Check your source and try again.', 422
                    else:
                        connection.execute('UPDATE teams SET progress=progress+1 WHERE id=?', (team,))
                        log_event(connection, round_id, 'clue_unlocked', team=team,
                                  payload={'clue': index + 1, 'title': QUESTIONS[index][2]}, correct=True,
                                  summary=f'Team {team} unlocked clue {index + 1}: {QUESTIONS[index][2]}.')
            elif path == '/api/final':
                submission = {key: str(data.get(key, '')).strip()[:100] for key in SOLUTION}
                if not all(submission.values()):
                    message, status = 'Complete all three accusation fields first.', 422
                else:
                    connection.execute('UPDATE teams SET last_attempt=? WHERE id=?',
                                       (json.dumps(submission, ensure_ascii=False), team))
                    correct = correct_submission(submission)
                    attempt_payload = {**submission, 'penalty_seconds': 0 if correct else 180}
                    log_event(connection, round_id, 'final_attempt', team=team, payload=attempt_payload, correct=correct,
                              summary=f'Team {team} submitted a {"correct" if correct else "incorrect"} final accusation.')
                    if not correct:
                        connection.execute('UPDATE teams SET wrong_attempts=wrong_attempts+1 WHERE id=?', (team,))
                        updated = connection.execute('SELECT * FROM teams WHERE id=?', (team,)).fetchone()
                        if state(updated, round_id)['ended']:
                            message, status = 'That combination is incorrect. Three minutes have been deducted, and the investigation has ended.', 409
                        else:
                            message, status = 'That combination is incorrect. Three minutes have been deducted. Review the evidence and try again.', 422
                    else:
                        finished = time.time()
                        connection.execute('UPDATE teams SET submission=?, finished=? WHERE id=?', (json.dumps(submission), finished, team))
                        log_event(connection, round_id, 'final_accusation', team=team, payload=submission, correct=True,
                                  summary=f'Team {team} solved the case with its final accusation.')
            reveal = both_teams_finished(connection, round_id)
            result = state(connection.execute('SELECT * FROM teams WHERE id=?', (team,)).fetchone(), round_id, reveal)
            connection.commit()
        if message:
            result['error'] = message
        self.respond(result, status)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=3000)
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()
    initialize()
    print(f'The Last Reunion Dinner — listening on port {args.port}', flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
