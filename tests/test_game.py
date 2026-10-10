import http.client
import importlib.util
import io
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
        self.gm_cookie = self.gm_login()
        self.set_team_code(1, 'test-team-one-code', self.gm_cookie)
        self.set_team_code(2, 'test-team-two-code', self.gm_cookie)
        self.team_cookies = {}
        for team, code in ((1, 'test-team-one-code'), (2, 'test-team-two-code')):
            status, _, headers = self.team_login(team, code)
            if status == 200:
                self.team_cookies[team] = headers['Set-Cookie'].split(';', 1)[0]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_static_file_client_disconnect_is_handled_without_request_thread_traceback(self):
        class DisconnectedWriter:
            def write(self, _data):
                raise ConnectionResetError(10054, 'connection was forcibly closed')

        handler = game.Handler.__new__(game.Handler)
        handler.close_connection = False
        handler.copyfile(io.BytesIO(b'static content'), DisconnectedWriter())
        self.assertTrue(handler.close_connection)

    def request(self, path, data=None):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        headers = {'Content-Type': 'application/json'}
        if data is not None:
            headers['Origin'] = f'http://127.0.0.1:{self.server.server_port}'
            try:
                team = int(data.get('team', 0))
            except (AttributeError, TypeError, ValueError):
                team = 0
        else:
            from urllib.parse import parse_qs, urlsplit
            try:
                team = int(parse_qs(urlsplit(path).query).get('team', ['0'])[0])
            except (TypeError, ValueError):
                team = 0
        if team in self.team_cookies:
            headers['Cookie'] = self.team_cookies[team]
        c.request('GET' if data is None else 'POST', path, body=None if data is None else json.dumps(data), headers=headers)
        r = c.getresponse()
        status, result = r.status, json.loads(r.read())
        c.close()
        return status, result

    def request_with_headers(self, path, data=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        request_headers = {'Content-Type': 'application/json', **(headers or {})}
        c.request('GET' if data is None else 'POST', path, body=None if data is None else json.dumps(data), headers=request_headers)
        r = c.getresponse()
        result = r.status, json.loads(r.read()), dict(r.getheaders())
        c.close()
        return result

    def gm_login(self):
        game.GAME_MASTER_PASSWORD = 'host-secret'
        origin = f'http://127.0.0.1:{self.server.server_port}'
        status, result, headers = self.request_with_headers(
            '/api/gm/login', {'password': 'host-secret'}, {'Origin': origin})
        self.assertEqual(status, 200)
        return headers['Set-Cookie'].split(';', 1)[0]

    def gm_request(self, path, data, cookie):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        return self.request_with_headers(path, data, {
            'Cookie': cookie,
            'Origin': origin,
        })

    def team_login(self, team, code):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        return self.request_with_headers('/api/team/login', {'team': team, 'code': code}, {'Origin': origin})

    def team_request(self, path, data, cookie):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        return self.request_with_headers(path, data, {'Cookie': cookie, 'Origin': origin})

    def set_team_code(self, team, code, cookie):
        return self.gm_request('/api/gm/team-codes', {'team': team, 'code': code}, cookie)

    def test_team_codes_require_game_master_and_create_team_scoped_sessions(self):
        with game.closing_connection() as connection:
            connection.execute('DELETE FROM team_access_codes')
            connection.execute('DELETE FROM team_sessions')
        self.assertEqual(self.request('/api/state?team=1')[0], 401)
        gm_cookie = self.gm_login()
        status, _, _ = self.gm_request('/api/gm/team-codes', None, '')
        self.assertEqual(status, 401)
        status, settings, _ = self.gm_request('/api/gm/team-codes', None, gm_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(settings, {'teams': [{'team': 1, 'configured': False}, {'team': 2, 'configured': False}]})

        self.assertEqual(self.set_team_code(1, 'night-owls-31', '')[0], 401)
        self.assertEqual(self.set_team_code(1, 'short', gm_cookie)[0], 400)
        self.assertEqual(self.set_team_code(1, 'night-owls-31', gm_cookie)[0], 200)
        self.assertEqual(self.set_team_code(2, 'silent-witnesses-72', gm_cookie)[0], 200)
        self.assertEqual(self.team_login(1, 'wrong-code')[0], 401)

        status, _, headers_one = self.team_login(1, 'night-owls-31')
        self.assertEqual(status, 200)
        cookie_one = headers_one['Set-Cookie'].split(';', 1)[0]
        self.assertTrue(cookie_one.startswith('reunion_team_1_session='))
        self.assertIn('HttpOnly', headers_one['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers_one['Set-Cookie'])
        status, _, headers_two = self.team_login(2, 'silent-witnesses-72')
        self.assertEqual(status, 200)
        cookie_two = headers_two['Set-Cookie'].split(';', 1)[0]
        self.assertTrue(cookie_two.startswith('reunion_team_2_session='))

        self.assertEqual(self.team_request('/api/state?team=1', None, cookie_one)[0], 200)
        self.assertEqual(self.team_request('/api/state?team=2', None, cookie_one)[0], 401)
        self.assertEqual(self.team_request('/api/state?team=2', None, cookie_two)[0], 200)
        self.assertNotIn('night-owls-31', json.dumps(settings))
        with game.closing_connection() as connection:
            stored_hash = connection.execute('SELECT code_hash FROM team_access_codes WHERE team_id=1').fetchone()['code_hash']
            stored_session = connection.execute('SELECT token_hash FROM team_sessions WHERE team_id=1').fetchone()['token_hash']
        self.assertNotEqual(stored_hash, 'night-owls-31')
        self.assertNotEqual(stored_session, cookie_one.split('=', 1)[1])

    def test_team_endpoints_reject_missing_session_and_cross_origin_posts(self):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        for path, payload in (
            ('/api/start', {'team': 1}),
            ('/api/answer', {'team': 1, 'number': 1, 'answer': '111%'}),
            ('/api/final', {'team': 1, 'killer': 'sam', 'weapon': 'wine', 'motive': 'jealousy'}),
        ):
            status, _, _ = self.request_with_headers(path, payload, {'Origin': origin})
            self.assertEqual(status, 401)
        self.assertEqual(self.request_with_headers('/api/team/login', {'team': 1, 'code': 'test-team-one-code'})[0], 403)
        self.assertEqual(self.request_with_headers('/api/team/login', {'team': 1, 'code': 'test-team-one-code'}, {'Origin': 'http://attacker.invalid'})[0], 403)

    def test_expired_team_session_is_rejected(self):
        cookie = self.team_cookies[1]
        token = cookie.split('=', 1)[1]
        with game.closing_connection() as connection:
            connection.execute('UPDATE team_sessions SET expires_at=? WHERE token_hash=?', (time.time() - 1, game.session_hash(token)))
        status, response, _ = self.team_request('/api/state?team=1', None, cookie)
        self.assertEqual(status, 401)
        self.assertNotIn('progress', response)

    def test_repeated_bad_team_codes_are_temporarily_rate_limited(self):
        for attempt in range(game.TEAM_LOGIN_FAILURE_LIMIT):
            status, _, _ = self.team_login(1, 'incorrect-team-access-code')
            self.assertEqual(status, 401 if attempt < game.TEAM_LOGIN_FAILURE_LIMIT - 1 else 429)
        self.assertEqual(self.team_login(1, 'test-team-one-code')[0], 429)
        self.assertEqual(self.team_login(2, 'test-team-two-code')[0], 200)

        self.assertEqual(self.set_team_code(1, 'fresh-team-one-code', self.gm_cookie)[0], 200)
        self.assertEqual(self.team_login(1, 'fresh-team-one-code')[0], 200)

    def test_replacing_team_code_revokes_only_that_team_session_and_preserves_state(self):
        gm_cookie = self.gm_login()
        self.set_team_code(1, 'night-owls-31', gm_cookie)
        self.set_team_code(2, 'silent-witnesses-72', gm_cookie)
        _, _, headers_one = self.team_login(1, 'night-owls-31')
        _, _, headers_two = self.team_login(2, 'silent-witnesses-72')
        cookie_one = headers_one['Set-Cookie'].split(';', 1)[0]
        cookie_two = headers_two['Set-Cookie'].split(';', 1)[0]

        status, started, _ = self.team_request('/api/start', {'team': 1}, cookie_one)
        self.assertEqual(status, 200)
        self.assertEqual(started['progress'], 0)
        status, progressed, _ = self.team_request('/api/answer', {'team': 1, 'number': 1, 'answer': '111%'}, cookie_one)
        self.assertEqual(status, 200)
        self.assertEqual(progressed['progress'], 1)
        self.assertEqual(self.set_team_code(1, 'night-owls-92', gm_cookie)[0], 200)
        self.assertEqual(self.team_request('/api/state?team=1', None, cookie_one)[0], 401)
        self.assertEqual(self.team_request('/api/state?team=2', None, cookie_two)[0], 200)

        _, _, renewed_headers = self.team_login(1, 'night-owls-92')
        renewed_cookie = renewed_headers['Set-Cookie'].split(';', 1)[0]
        status, state, _ = self.team_request('/api/state?team=1', None, renewed_cookie)
        self.assertEqual(status, 200)
        self.assertIsNotNone(state['started'])
        self.assertEqual(state['progress'], 1)

        self.gm_request('/api/gm/new-round', {}, gm_cookie)
        status, settings, _ = self.gm_request('/api/gm/team-codes', None, gm_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(settings['teams'], [{'team': 1, 'configured': True}, {'team': 2, 'configured': True}])

    def test_team_sessions_reject_cross_team_mutations_and_survive_restart(self):
        cookie_one = self.team_cookies[1]
        for path, payload in (
            ('/api/start', {'team': 2}),
            ('/api/answer', {'team': 2, 'number': 1, 'answer': '111%'}),
            ('/api/final', {'team': 2, 'killer': 'sam', 'weapon': 'wine', 'motive': 'jealousy'}),
        ):
            self.assertEqual(self.team_request(path, payload, cookie_one)[0], 401)
        status, denied, _ = self.team_request('/api/state?team=2', None, cookie_one)
        self.assertEqual(status, 401)
        self.assertNotIn('started', denied)

        game.initialize()
        status, state, _ = self.team_request('/api/state?team=1', None, cookie_one)
        self.assertEqual(status, 200)
        self.assertEqual(state['progress'], 0)
        status, settings, _ = self.gm_request('/api/gm/team-codes', None, self.gm_login())
        self.assertEqual(status, 200)
        self.assertEqual(settings['teams'], [{'team': 1, 'configured': True}, {'team': 2, 'configured': True}])

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

    def test_solution_is_hidden_until_both_teams_finish(self):
        self.solve(team=1)
        status, result = self.request('/api/final', {'team': 1, 'killer': 'SAM', 'weapon': 'wine', 'motive': 'jealousy'})
        self.assertEqual(status, 200)
        self.assertTrue(result['correct'])
        self.assertNotIn('solution', result)
        _, team_one = self.request('/api/state?team=1')
        self.assertNotIn('solution', team_one)

        self.solve(team=2)
        status, result = self.request('/api/final', {'team': 2, 'killer': 'waitress', 'weapon': 'knife', 'motive': 'money'})
        self.assertEqual(status, 422)
        self.assertNotIn('solution', result)
        status, result = self.request('/api/final', {'team': 2, 'killer': 'sam', 'weapon': 'drink', 'motive': 'jealousy'})
        self.assertEqual(status, 200)
        self.assertIn('solution', result)
        _, team_one = self.request('/api/state?team=1')
        self.assertIn('solution', team_one)

    def test_frontend_bundle_does_not_include_solution_reveal(self):
        source = (Path(__file__).resolve().parents[1] / 'public' / 'app.js').read_text(encoding='utf-8')
        self.assertNotIn('The poison was in the drink', source)
        self.assertNotIn('Jealousy turned that secret into murder', source)

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
        with game.closing_connection() as c:
            c.execute('UPDATE teams SET started=? WHERE id=1', (time.time() - 1801,))
        status, result = self.request('/api/answer', {'team': 1, 'number': 1, 'answer': '111%'})
        self.assertEqual(status, 409)
        self.assertTrue(result['expired'])
        self.assertEqual(result['remaining'], 0)

    def test_wrong_accusation_and_invalid_team(self):
        self.solve()
        status, result = self.request('/api/final', {'team': 1, 'killer': 'waitress', 'weapon': 'knife', 'motive': 'Money Motive'})
        self.assertEqual(status, 422)
        self.assertFalse(result['ended'])
        self.assertEqual(self.request('/api/start', {'team': 3})[0], 400)

    def test_wrong_final_attempt_deducts_three_minutes_and_allows_retry(self):
        self.solve()
        before = self.request('/api/state?team=1')[1]['remaining']
        status, result = self.request('/api/final', {'team': 1, 'killer': 'waitress', 'weapon': 'knife', 'motive': 'Money Motive'})
        self.assertEqual(status, 422)
        self.assertEqual(result['wrong_attempts'], 1)
        self.assertFalse(result['ended'])
        self.assertGreaterEqual(before - result['remaining'], 180)
        self.assertLessEqual(before - result['remaining'], 181)

    def test_final_answer_aliases_are_accepted(self):
        self.solve()
        status, result = self.request('/api/final', {'team': 1, 'killer': 'SAM', 'weapon': 'WINE', 'motive': 'JEALOUSY'})
        self.assertEqual(status, 200)
        self.assertTrue(result['correct'])

    def test_state_exposes_round_and_latest_final_attempt(self):
        _, team_one = self.request('/api/state?team=1')
        _, team_two = self.request('/api/state?team=2')
        self.assertEqual(team_one['round_id'], team_two['round_id'])
        self.solve()
        attempt = {'team': 1, 'killer': 'waitress', 'weapon': 'wine', 'motive': 'money'}
        status, result = self.request('/api/final', attempt)
        self.assertEqual(status, 422)
        expected = {key: attempt[key] for key in ('killer', 'weapon', 'motive')}
        self.assertEqual(result['last_attempt'], expected)
        _, refreshed = self.request('/api/state?team=1')
        self.assertEqual(refreshed['last_attempt'], expected)
        self.assertEqual(refreshed['round_id'], team_one['round_id'])

    def test_weapon_alias_poison_drink_is_accepted(self):
        for weapon in ('Poison Drink', 'DRINK', 'wine'):
            self.assertTrue(game.correct_submission({'killer': 'sam', 'weapon': weapon, 'motive': 'JEALOUSY'}))

    def test_game_master_event_filter_and_pagination_are_team_specific(self):
        self.request('/api/start', {'team': 1})
        self.request('/api/answer', {'team': 1, 'number': 1, 'answer': 'bad one'})
        self.request('/api/start', {'team': 2})
        self.request('/api/answer', {'team': 2, 'number': 1, 'answer': 'bad two'})
        cookie = self.gm_login()
        status, first_page, _ = self.gm_request('/api/gm/events?team=1&limit=1', None, cookie)
        self.assertEqual(status, 200)
        self.assertEqual([event['team'] for event in first_page['events']], [1])
        first_id = first_page['events'][0]['id']
        status, older_page, _ = self.gm_request(f'/api/gm/events?team=1&limit=10&before={first_id}', None, cookie)
        self.assertEqual(status, 200)
        self.assertTrue(all(event['team'] == 1 for event in older_page['events']))
        self.assertTrue(all(event['id'] < first_id for event in older_page['events']))
        status, second_page, _ = self.gm_request('/api/gm/events?team=2', None, cookie)
        self.assertEqual(status, 200)
        self.assertTrue(second_page['events'])
        self.assertTrue(all(event['team'] == 2 for event in second_page['events']))
        self.assertEqual(self.gm_request('/api/gm/events?team=3', None, cookie)[0], 400)

    def test_game_master_can_clear_one_team_log_without_resetting_game_state(self):
        self.solve(1)
        self.request('/api/final', {'team': 1, 'killer': 'SAM', 'weapon': 'wine', 'motive': 'jealousy'})
        self.solve(2)
        self.request('/api/final', {'team': 2, 'killer': 'waitress', 'weapon': 'knife', 'motive': 'money'})
        cookie = self.gm_login()
        _, before_one, _ = self.gm_request('/api/gm/events?team=1', None, cookie)
        _, before_two, _ = self.gm_request('/api/gm/events?team=2', None, cookie)
        self.assertTrue(before_one['events'])
        self.assertTrue(before_two['events'])
        self.assertEqual(self.gm_request('/api/gm/clear-team-events', {'team': 1}, '')[0], 401)
        self.assertEqual(self.gm_request('/api/gm/clear-team-events', {'team': 3}, cookie)[0], 400)
        _, state_one_before = self.request('/api/state?team=1')
        _, state_two_before = self.request('/api/state?team=2')

        status, result, _ = self.gm_request('/api/gm/clear-team-events', {'team': 1}, cookie)

        self.assertEqual(status, 200)
        self.assertEqual(result['team'], 1)
        self.assertGreater(result['deleted'], 0)
        _, cleared_one, _ = self.gm_request('/api/gm/events?team=1', None, cookie)
        _, retained_two, _ = self.gm_request('/api/gm/events?team=2', None, cookie)
        self.assertEqual(cleared_one['events'], [])
        self.assertEqual([event['id'] for event in retained_two['events']],
                         [event['id'] for event in before_two['events']])
        _, state_one_after = self.request('/api/state?team=1')
        _, state_two_after = self.request('/api/state?team=2')
        for before, after in ((state_one_before, state_one_after), (state_two_before, state_two_after)):
            for field in ('started', 'progress', 'last_attempt', 'wrong_attempts', 'ended'):
                self.assertEqual(after[field], before[field])
            for field in ('submission', 'correct'):
                self.assertEqual(after.get(field), before.get(field))

    def test_game_master_can_reset_both_teams_with_password(self):
        self.solve(1)
        self.request('/api/final', {'team': 1, 'killer': 'waitress', 'weapon': 'wine', 'motive': 'money'})
        self.solve(2)
        self.request('/api/final', {'team': 2, 'killer': 'The Chef', 'weapon': 'poisoned drink', 'motive': 'Jealousy'})
        cookie = self.gm_login()
        _, before_one, _ = self.gm_request('/api/gm/events?team=1', None, cookie)
        _, before_two, _ = self.gm_request('/api/gm/events?team=2', None, cookie)
        self.assertTrue(before_one['events'])
        self.assertTrue(before_two['events'])
        status, result, _ = self.gm_request('/api/gm/new-round', {}, cookie)
        self.assertEqual(status, 200)
        for team in (1, 2):
            _, state = self.request(f'/api/state?team={team}')
            self.assertEqual(state['progress'], 0)
            self.assertIsNone(state['started'])
            self.assertEqual(state['wrong_attempts'], 0)
            self.assertIsNone(state['last_attempt'])
            self.assertEqual(state['round_id'], result['round_id'])
            with game.closing_connection() as connection:
                stored = connection.execute('SELECT submission, last_attempt, finished FROM teams WHERE id=?',
                                            (team,)).fetchone()
                self.assertIsNone(stored['submission'])
                self.assertIsNone(stored['last_attempt'])
                self.assertIsNone(stored['finished'])
            _, events, _ = self.gm_request(f'/api/gm/events?team={team}', None, cookie)
            self.assertEqual(events['events'], [])
        _, all_events, _ = self.gm_request('/api/gm/events', None, cookie)
        self.assertTrue(any(event['type'] == 'round_started' and event['round_id'] == result['round_id']
                            for event in all_events['events']))

    def test_question_four_uses_month_only_headline(self):
        self.assertIn('which month carried the heavier workload?', game.QUESTIONS[3][0].casefold())
        self.assertIn('heavier workload', game.QUESTIONS[3][0].casefold())
        self.assertEqual(game.QUESTIONS[3][1], 'september')

if __name__ == '__main__':
    unittest.main()
