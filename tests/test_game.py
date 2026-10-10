import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

spec = importlib.util.spec_from_file_location('game', Path(__file__).resolve().parents[1] / 'server.py')
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)

class GameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        game.DB = Path(self.temp.name) / 'game.sqlite3'
        game.initialize()
        self.server = game.ThreadingHTTPServer(('127.0.0.1', 0), game.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, data=None):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        c.request('GET' if data is None else 'POST', path, body=None if data is None else json.dumps(data), headers={'Content-Type': 'application/json'})
        r = c.getresponse()
        status, result = r.status, json.loads(r.read())
        c.close()
        return status, result

    def solve(self, team=1):
        self.request('/api/start', {'team': team})
        for n, answer in enumerate([' 111% ', 'LEARNING', 'Dachshund', 'SEPTEMBER', 'Favorable'], 1):
            status, result = self.request('/api/answer', {'team': team, 'number': n, 'answer': answer})
            self.assertEqual(status, 200)
            self.assertEqual(result['progress'], n)
        return result

    def test_full_round_and_team_isolation(self):
        self.solve()
        status, result = self.request('/api/final', {'team': 1, 'killer': 'THE CHEF', 'weapon': 'poisoned DRINK', 'motive': 'JEALOUSY'})
        self.assertEqual(status, 200)
        self.assertTrue(result['correct'])
        self.assertTrue(result['ended'])
        status, other = self.request('/api/state?team=2')
        self.assertEqual(other['progress'], 0)
        self.assertIsNone(other['started'])
        self.assertNotIn('solution', other)
        self.assertEqual(self.request('/api/final', {'team': 1})[0], 409)

    def test_wrong_answer_stale_clue_and_early_final(self):
        self.request('/api/start', {'team': 1})
        status, result = self.request('/api/answer', {'team': 1, 'number': 1, 'answer': '110%'})
        self.assertEqual(status, 422)
        self.assertEqual(result['progress'], 0)
        self.assertEqual(self.request('/api/answer', {'team': 1, 'number': 2, 'answer': 'learning'})[0], 409)
        self.assertEqual(self.request('/api/final', {'team': 1, **game.SOLUTION})[0], 422)
        self.assertNotIn('solution', result)

    def test_expiry_enforced_and_persistent_start(self):
        _, first = self.request('/api/start', {'team': 1})
        _, second = self.request('/api/start', {'team': 1})
        self.assertEqual(first['started'], second['started'])
        game.initialize()
        self.assertEqual(self.request('/api/state?team=1')[1]['started'], first['started'])
        with game.connect() as c:
            c.execute('UPDATE teams SET started=? WHERE id=1', (time.time() - 1801,))
        status, result = self.request('/api/answer', {'team': 1, 'number': 1, 'answer': '111%'})
        self.assertEqual(status, 409)
        self.assertTrue(result['expired'])
        self.assertEqual(result['remaining'], 0)

    def test_wrong_accusation_and_invalid_team(self):
        self.solve()
        _, result = self.request('/api/final', {'team': 1, 'killer': 'waitress', 'weapon': 'knife', 'motive': 'Money Motive'})
        self.assertFalse(result['correct'])
        self.assertTrue(result['ended'])
        self.assertEqual(self.request('/api/start', {'team': 3})[0], 400)

if __name__ == '__main__':
    unittest.main()
