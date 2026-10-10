"""Dependency-free, two-team mystery game. Run: python3 server.py."""
import argparse
import json
import os
import sqlite3
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('GAME_DB', str(ROOT / '.runtime/game.sqlite3')))
QUESTIONS = [
    ('By what percentage did the Collection Team exceed their September cash target?', '111%', 'The Food', 'No poison was found in the food.'),
    ('In the feature article, complete the title: Alvin’s Next Chapter: Balancing Work, Life, and _______.', 'learning', 'The Glass', "The waitress saw the Chef handling the victim’s glass before dinner."),
    ('In the feature article “A Furmom’s Heart: Krisselle and Her Beloved Companions”, what breed is Dachi, her lively 2-year-old dog?', 'dachshund', 'The Secret Message', '“You promised me we would be together. I’m tired of being your secret.”'),
    ('According to the headline “Liaison Desk Lifts Completion Rate to 89.1% on a Heavier September Load”, which month carried the heavier workload?', 'september', 'The Hidden Photo', 'A photo shows the Victim and Chef together privately.'),
    ('Overdue AR dropped to ₱55.1M while cash collections nearly doubled to ₱146.4M. Does this outcome indicate a favorable or not favorable performance? Enter “favorable” or “not favorable”.', 'favorable', 'The Waitress', "The waitress admits she saw the Chef with the victim’s glass but kept quiet because she secretly loved the Chef."),
]
SOLUTION = {'killer': 'The Chef', 'weapon': 'Poisoned Drink', 'motive': 'Jealousy'}

def normalize(value):
    return ' '.join(str(value).strip().casefold().split())

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    return c

def initialize():
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS teams (id INTEGER PRIMARY KEY, started REAL, progress INTEGER DEFAULT 0, submission TEXT, finished REAL)')
        c.executemany('INSERT OR IGNORE INTO teams (id) VALUES (?)', [(1,), (2,)])

def state(row):
    now = time.time()
    remaining = max(0, 1800 - ((row['finished'] or now) - row['started'])) if row['started'] else 1800
    ended = bool(row['submission']) or remaining <= 0
    result = {'team': row['id'], 'started': row['started'], 'remaining': remaining,
              'progress': row['progress'], 'ended': ended, 'expired': remaining <= 0,
              'clues': [{'number': i + 1, 'title': q[2], 'text': q[3]} for i, q in enumerate(QUESTIONS[:row['progress']])]}
    if row['started'] and row['progress'] < 5 and not ended:
        result['question'] = QUESTIONS[row['progress']][0]
    if ended:
        submitted = json.loads(row['submission']) if row['submission'] else None
        result.update(solution=SOLUTION, submission=submitted,
                      correct=bool(submitted) and all(normalize(submitted[k]) in ({'chef', 'the chef'} if k == 'killer' else {normalize(v)}) for k, v in SOLUTION.items()),
                      elapsed=round((row['finished'] or row['started'] + 1800) - row['started']))
    return result

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'public'), **kwargs)

    def respond(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlsplit(self.path).path == '/api/state':
            try:
                team = int(parse_qs(urlsplit(self.path).query).get('team', ['0'])[0])
                if team not in (1, 2):
                    raise ValueError()
                with connect() as c:
                    self.respond(state(c.execute('SELECT * FROM teams WHERE id=?', (team,)).fetchone()))
            except ValueError:
                self.respond({'error': 'Choose team 1 or 2.'}, 400)
        else:
            super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path not in ('/api/start', '/api/answer', '/api/final'):
            return self.respond({'error': 'Unknown action.'}, 404)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                raise ValueError()
            data = json.loads(self.rfile.read(size))
            team = int(data.get('team', 0))
            if team not in (1, 2):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            return self.respond({'error': 'Invalid request.'}, 400)
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM teams WHERE id=?', (team,)).fetchone()
            current = state(row)
            message = ''
            status = 200
            if self.path == '/api/start':
                if not row['started']:
                    c.execute('UPDATE teams SET started=? WHERE id=?', (time.time(), team))
            elif not row['started'] or current['ended']:
                message, status = 'This investigation is not active.', 409
            elif self.path == '/api/answer':
                index = row['progress']
                if index >= 5 or data.get('number') != index + 1:
                    message, status = 'This clue has already changed. Your case file has been refreshed.', 409
                elif normalize(data.get('answer', '')) != QUESTIONS[index][1]:
                    message, status = 'That answer does not unlock the evidence. Check your source and try again.', 422
                else:
                    c.execute('UPDATE teams SET progress=progress+1 WHERE id=?', (team,))
            elif self.path == '/api/final':
                submission = {k: str(data.get(k, '')).strip() for k in SOLUTION}
                if row['progress'] < 5 or not all(submission.values()):
                    message, status = 'Unlock all five clues and complete your accusation first.', 422
                else:
                    c.execute('UPDATE teams SET submission=?, finished=? WHERE id=?', (json.dumps(submission), time.time(), team))
            result = state(c.execute('SELECT * FROM teams WHERE id=?', (team,)).fetchone())
            c.commit()
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
