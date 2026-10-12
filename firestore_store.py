"""Firestore persistence for Cloud Run. All authorization stays in the Python API."""
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid

from game_rules import (QUESTIONS, TEAM_CODE_ITERATIONS, TEAM_LOGIN_FAILURE_LIMIT,
                        TEAM_LOGIN_LOCK_SECONDS, TEAM_LOGIN_WINDOW_SECONDS,
                        correct_submission, event_record, normalize, state)

try:
    from google.cloud import firestore
except ImportError:  # Keep local/Render SQLite startup independent from this optional backend.
    firestore = None


def firestore_client(project_id=None):
    """Create Firestore via emulator credentials or ADC (including GOOGLE_APPLICATION_CREDENTIALS)."""
    if firestore is None:
        raise RuntimeError('Firestore backend requires firebase-admin. Install requirements.txt.')
    project_id = project_id or os.environ.get('GOOGLE_CLOUD_PROJECT') or os.environ.get('GCLOUD_PROJECT')
    if os.environ.get('FIRESTORE_EMULATOR_HOST'):
        from google.auth.credentials import AnonymousCredentials
        return firestore.Client(project=project_id or 'demo-mystery-cfa', credentials=AnonymousCredentials())

    import firebase_admin
    from firebase_admin import firestore as admin_firestore
    if not firebase_admin._apps:
        options = {'projectId': project_id} if project_id else None
        firebase_admin.initialize_app(options=options)
    return admin_firestore.client()


class FirestoreGameStore:
    """The domain persistence operations required by the existing HTTP API."""
    def __init__(self, client=None, project_id=None):
        if client is None:
            client = firestore_client(project_id)
        self.db = client
        self.meta = self.db.collection('game').document('meta')
        self.teams = self.db.collection('teams')
        self.rounds = self.db.collection('rounds')

    @staticmethod
    def _transactional(callback, transaction):
        if firestore is None:
            raise RuntimeError('Firestore backend is unavailable.')
        # Transaction callbacks in this store are already decorated with
        # @firestore.transactional. Wrapping them again nests two commit
        # cycles on the same transaction and the outer commit has no ID.
        return callback(transaction)

    @staticmethod
    def _team_defaults(team):
        return {'id': team, 'started': None, 'progress': 0, 'submission': None,
                'last_attempt': None, 'finished': None, 'wrong_attempts': 0}

    def initialize(self):
        team_refs = [self.teams.document(str(team)) for team in (1, 2)]

        @firestore.transactional
        def initialize_transaction(transaction):
            meta_snapshot = self.meta.get(transaction=transaction)
            active_id = meta_snapshot.get('active_round_id') if meta_snapshot.exists else 1
            round_ref = self.rounds.document(str(active_id))
            team_snapshots = [ref.get(transaction=transaction) for ref in team_refs]
            round_snapshot = round_ref.get(transaction=transaction)
            if not meta_snapshot.exists:
                transaction.set(self.meta, {'active_round_id': 1, 'next_round_id': 2, 'next_event_id': 1})
            if not round_snapshot.exists:
                transaction.set(round_ref, {'id': active_id, 'created_at': time.time(), 'active': True})
            for team, ref, snapshot in zip((1, 2), team_refs, team_snapshots):
                if not snapshot.exists:
                    transaction.set(ref, self._team_defaults(team))

        initialize_transaction(self.db.transaction())

    def gm_session(self, token_hash, now):
        snapshot = self.db.collection('gm_sessions').document(token_hash).get()
        if not snapshot.exists or snapshot.get('expires_at') <= now:
            return None
        return snapshot.to_dict()

    def create_gm_session(self, token_hash, now, expires_at):
        self.db.collection('gm_sessions').document(token_hash).set({'created_at': now, 'expires_at': expires_at})

    def delete_gm_session(self, token_hash):
        self.db.collection('gm_sessions').document(token_hash).delete()

    def team_session(self, token_hash, team, now):
        session_ref = self.db.collection('team_sessions').document(token_hash)
        session = session_ref.get()
        if not session.exists:
            return None
        record = session.to_dict()
        if record.get('team_id') != team or record.get('expires_at', 0) <= now:
            return None
        code = self.db.collection('team_codes').document(str(team)).get()
        if not code.exists or code.get('code_version') != record.get('code_version'):
            return None
        return record

    def team_login(self, team, code, client_hash, token_hash, now, expires_at):
        code_ref = self.db.collection('team_codes').document(str(team))
        attempt_ref = self.db.collection('login_attempts').document(f'{team}_{client_hash}')
        session_ref = self.db.collection('team_sessions').document(token_hash)

        @firestore.transactional
        def login_transaction(transaction):
            code_snapshot = code_ref.get(transaction=transaction)
            attempt_snapshot = attempt_ref.get(transaction=transaction)
            if not code_snapshot.exists:
                return 409, {'error': 'The Game Master has not set this team’s access code yet.'}
            code_record = code_snapshot.to_dict()
            attempts = attempt_snapshot.to_dict() if attempt_snapshot.exists else None
            if attempts and attempts.get('locked_until', 0) > now:
                return 429, {'error': 'Too many incorrect codes. Please wait five minutes and try again.'}
            candidate = hashlib.pbkdf2_hmac(
                'sha256', code.encode('utf-8'), bytes.fromhex(code_record['salt']), code_record['iterations']
            ).hex()
            if not hmac.compare_digest(candidate, code_record['code_hash']):
                if attempts and now - attempts.get('window_started', 0) < TEAM_LOGIN_WINDOW_SECONDS:
                    failures, window_started = attempts.get('failures', 0) + 1, attempts['window_started']
                else:
                    failures, window_started = 1, now
                locked_until = now + TEAM_LOGIN_LOCK_SECONDS if failures >= TEAM_LOGIN_FAILURE_LIMIT else 0
                transaction.set(attempt_ref, {'team_id': team, 'client_hash': client_hash, 'failures': failures,
                                              'window_started': window_started, 'locked_until': locked_until})
                if locked_until:
                    return 429, {'error': 'Too many incorrect codes. Please wait five minutes and try again.'}
                return 401, {'error': 'That access code is incorrect.'}
            transaction.delete(attempt_ref)
            transaction.set(session_ref, {'team_id': team, 'created_at': now, 'expires_at': expires_at,
                                          'code_version': code_record['code_version']})
            return 200, {'authenticated': True, 'team': team}

        return self._transactional(login_transaction, self.db.transaction())

    def replace_team_code(self, team, code, now):
        old_sessions = list(self.db.collection('team_sessions').where('team_id', '==', team).stream())
        salt = secrets.token_hex(16)
        code_hash = hashlib.pbkdf2_hmac('sha256', code.encode('utf-8'), bytes.fromhex(salt), TEAM_CODE_ITERATIONS).hex()
        code_version = uuid.uuid4().hex
        ref = self.db.collection('team_codes').document(str(team))
        ref.set({'team_id': team, 'salt': salt, 'code_hash': code_hash,
                 'iterations': TEAM_CODE_ITERATIONS, 'code_value': code,
                 'code_version': code_version, 'updated_at': now})
        batch = self.db.batch()
        for session in old_sessions:
            batch.delete(session.reference)
        if old_sessions:
            batch.commit()
        # Code-version checks revoke existing sessions immediately without a racy collection query.
        query = self.db.collection('login_attempts').where('team_id', '==', team)
        self._delete_query(query)
        return {'team': team, 'configured': True, 'sessions_revoked': len(old_sessions)}

    def team_codes(self):
        configured = {team for team in (1, 2) if self.db.collection('team_codes').document(str(team)).get().exists}
        return {'teams': [{'team': team, 'configured': team in configured} for team in (1, 2)]}

    def reveal_team_code(self, team):
        snapshot = self.db.collection('team_codes').document(str(team)).get()
        if not snapshot.exists:
            return 404, {'error': 'No access code has been set for this team.'}
        code = snapshot.get('code_value')
        if code is None:
            return 409, {'error': 'This code was saved before reveal support. Replace it once to make it viewable.'}
        return 200, {'team': team, 'code': code}

    def _round_id(self):
        return self.meta.get().get('active_round_id')

    def team_state(self, team):
        meta = self.meta.get().to_dict()
        round_id = meta['active_round_id']
        row = self.teams.document(str(team)).get().to_dict() or self._team_defaults(team)
        other = self.teams.document(str(3 - team)).get().to_dict() or self._team_defaults(3 - team)
        reveal = state(row, round_id)['ended'] and state(other, round_id)['ended']
        return state(row, round_id, reveal)

    def dashboard(self):
        meta = self.meta.get().to_dict()
        round_id = meta['active_round_id']
        teams = []
        for team in (1, 2):
            result = state(self.teams.document(str(team)).get().to_dict() or self._team_defaults(team), round_id)
            teams.append({'team': team, 'started': result['started'], 'progress': result['progress'],
                          'remaining': result['remaining'], 'ended': result['ended'], 'expired': result['expired'],
                          'wrong_attempts': result['wrong_attempts'], 'submission': result.get('submission'),
                          'correct': result.get('correct')})
        return {'round_id': round_id, 'teams': teams}

    def events(self, team, limit, before):
        query = self.db.collection_group('events')
        if team is not None:
            query = query.where('team_id', '==', team)
        if before is not None:
            query = query.where('id', '<', before)
        query = query.order_by('id', direction=firestore.Query.DESCENDING).limit(limit + 1)
        rows = [snapshot.to_dict() for snapshot in query.stream()]
        return {'events': [event_record(row) for row in rows[:limit]], 'has_more': len(rows) > limit}

    def _delete_query(self, query):
        while True:
            snapshots = list(query.limit(400).stream())
            if not snapshots:
                return
            batch = self.db.batch()
            for snapshot in snapshots:
                batch.delete(snapshot.reference)
            batch.commit()

    def clear_team_events(self, team):
        meta = self.meta.get().to_dict() or {}
        latest_round_id = max(meta.get('active_round_id', 1), meta.get('next_round_id', 2) - 1)
        total = 0
        for round_id in range(1, latest_round_id + 1):
            query = self.rounds.document(str(round_id)).collection('events').where('team_id', '==', team)
            while True:
                snapshots = list(query.limit(400).stream())
                if not snapshots:
                    break
                batch = self.db.batch()
                for snapshot in snapshots:
                    batch.delete(snapshot.reference)
                batch.commit()
                total += len(snapshots)
        return total

    def _append_events(self, transaction, meta, round_id, specs):
        next_id = meta['next_event_id']
        records = []
        for offset, spec in enumerate(specs):
            event_id = next_id + offset
            row = {'id': event_id, 'created_at': spec.get('created_at', time.time()), 'round_id': round_id,
                   'team_id': spec.get('team_id'), 'event_type': spec['event_type'],
                   'payload': spec.get('payload'), 'correct': spec.get('correct'), 'summary': spec['summary']}
            ref = self.rounds.document(str(round_id)).collection('events').document(f'{event_id:020d}')
            transaction.create(ref, row)
            records.append(row)
        transaction.update(self.meta, {'next_event_id': next_id + len(specs)})
        return records

    @staticmethod
    def _event(event_type, summary, team=None, payload=None, correct=None, created_at=None):
        record = {'event_type': event_type, 'summary': summary, 'team_id': team, 'payload': payload, 'correct': correct}
        if created_at is not None:
            record['created_at'] = created_at
        return record

    def new_round(self, now):
        team_refs = [self.teams.document(str(team)) for team in (1, 2)]

        @firestore.transactional
        def round_transaction(transaction):
            meta_snapshot = self.meta.get(transaction=transaction)
            meta = meta_snapshot.to_dict()
            prior_id = meta['active_round_id']
            next_id = meta['next_round_id']
            prior_ref = self.rounds.document(str(prior_id))
            next_ref = self.rounds.document(str(next_id))
            prior_snapshot = prior_ref.get(transaction=transaction)
            team_snapshots = [ref.get(transaction=transaction) for ref in team_refs]
            transaction.update(prior_ref, {'active': False})
            transaction.create(next_ref, {'id': next_id, 'created_at': now, 'active': True})
            for team, ref in zip((1, 2), team_refs):
                transaction.set(ref, self._team_defaults(team))
            event_id = meta['next_event_id']
            event_ref = next_ref.collection('events').document(f'{event_id:020d}')
            transaction.create(event_ref, {
                'id': event_id, 'created_at': now, 'round_id': next_id, 'team_id': None,
                'event_type': 'round_started', 'payload': {'round': next_id}, 'correct': None,
                'summary': f'Round {next_id} started; both teams are ready.',
            })
            transaction.update(self.meta, {'active_round_id': next_id, 'next_round_id': next_id + 1,
                                           'next_event_id': event_id + 1})
            return prior_id, next_id

        prior_id, next_id = self._transactional(round_transaction, self.db.transaction())
        # Delete old team events by their containing round. New round events cannot be removed by this cleanup.
        for round_snapshot in self.rounds.where('id', '<', next_id).stream():
            old_round_id = round_snapshot.get('id')
            query = self.rounds.document(str(old_round_id)).collection('events').where('team_id', 'in', [1, 2])
            self._delete_query(query)
        return {'round_id': next_id, 'message': f'Round {next_id} is ready. Team timers start when each team enters.'}

    def start_team(self, team, now, expected_round_id=None):
        team_ref = self.teams.document(str(team))

        @firestore.transactional
        def start_transaction(transaction):
            meta_snapshot = self.meta.get(transaction=transaction)
            team_snapshot = team_ref.get(transaction=transaction)
            meta, row = meta_snapshot.to_dict(), team_snapshot.to_dict()
            if expected_round_id is not None and expected_round_id != meta['active_round_id']:
                return {'error': 'A new round has started. Return to team selection.', 'round_id': meta['active_round_id']}
            if not row.get('started'):
                row['started'] = now
                transaction.update(team_ref, {'started': now})
                self._append_events(transaction, meta, meta['active_round_id'], [self._event(
                    'team_started', f'Team {team} started its investigation.', team=team,
                    payload={'started_at': now}, created_at=now)])
            return state(row, meta['active_round_id'])

        result = self._transactional(start_transaction, self.db.transaction())
        return (409 if result.get('error') else 200), result

    def submit_answer(self, team, number, answer, now, expected_round_id=None):
        team_ref = self.teams.document(str(team))

        @firestore.transactional
        def answer_transaction(transaction):
            meta_snapshot = self.meta.get(transaction=transaction)
            team_snapshot = team_ref.get(transaction=transaction)
            meta, row = meta_snapshot.to_dict(), team_snapshot.to_dict()
            round_id = meta['active_round_id']
            if expected_round_id is not None and expected_round_id != round_id:
                return 409, {'error': 'A new round has started. Return to team selection.'}, None
            current = state(row, round_id)
            if not row.get('started') or current['ended']:
                return 409, {'error': 'This investigation is not active.'}, None
            index = row.get('progress', 0)
            if index >= len(QUESTIONS) or number != index + 1:
                return 409, {'error': 'This clue has already changed. Your case file has been refreshed.'}, None
            clean_answer = str(answer)[:200]
            correct = normalize(clean_answer) == QUESTIONS[index][1]
            specs = [self._event('answer_attempt',
                                 f'Team {team} submitted an answer for question {index + 1}: {"correct" if correct else "incorrect"}.',
                                 team=team, payload={'question': index + 1, 'answer': clean_answer},
                                 correct=correct, created_at=now)]
            if correct:
                row['progress'] = index + 1
                transaction.update(team_ref, {'progress': index + 1})
                specs.append(self._event('clue_unlocked', f'Team {team} unlocked clue {index + 1}: {QUESTIONS[index][2]}.',
                                         team=team, payload={'clue': index + 1, 'title': QUESTIONS[index][2]},
                                         correct=True, created_at=now))
            self._append_events(transaction, meta, round_id, specs)
            result = state(row, round_id)
            if not correct:
                result['error'] = 'That answer does not unlock the evidence. Check your source and try again.'
            return (200 if correct else 422), result, round_id

        status, result, round_id = self._transactional(answer_transaction, self.db.transaction())
        if round_id is not None:
            refreshed = self._team_state_for_round(team, round_id)
            if result.get('error') and not refreshed.get('error'):
                refreshed['error'] = result['error']
            return status, refreshed
        return status, result

    def submit_final(self, team, submission, now, expected_round_id=None):
        team_ref = self.teams.document(str(team))

        @firestore.transactional
        def final_transaction(transaction):
            meta_snapshot = self.meta.get(transaction=transaction)
            team_snapshot = team_ref.get(transaction=transaction)
            meta, row = meta_snapshot.to_dict(), team_snapshot.to_dict()
            round_id = meta['active_round_id']
            if expected_round_id is not None and expected_round_id != round_id:
                return 409, {'error': 'A new round has started. Return to team selection.'}, None
            current = state(row, round_id)
            if not row.get('started') or current['ended']:
                return 409, {'error': 'This investigation is not active.'}, None
            if not all(submission.values()):
                return 422, {'error': 'Complete all three accusation fields first.'}, None
            row['last_attempt'] = submission
            correct = correct_submission(submission)
            specs = [self._event('final_attempt',
                                 f'Team {team} submitted a {"correct" if correct else "incorrect"} final accusation.',
                                 team=team, payload={**submission, 'penalty_seconds': 0 if correct else 180},
                                 correct=correct, created_at=now)]
            if correct:
                row['submission'], row['finished'] = submission, now
                transaction.update(team_ref, {'last_attempt': submission, 'submission': submission, 'finished': now})
                specs.append(self._event('final_accusation', f'Team {team} solved the case with its final accusation.',
                                         team=team, payload=submission, correct=True, created_at=now))
            else:
                row['wrong_attempts'] = row.get('wrong_attempts', 0) + 1
                transaction.update(team_ref, {'last_attempt': submission, 'wrong_attempts': row['wrong_attempts']})
            self._append_events(transaction, meta, round_id, specs)
            result = state(row, round_id)
            if not correct:
                result['error'] = ('That combination is incorrect. Three minutes have been deducted, and the investigation has ended.'
                                   if result['ended'] else
                                   'That combination is incorrect. Three minutes have been deducted. Review the evidence and try again.')
            return (200 if correct else (409 if result['ended'] else 422)), result, round_id

        status, result, round_id = self._transactional(final_transaction, self.db.transaction())
        if round_id is not None:
            refreshed = self._team_state_for_round(team, round_id)
            if result.get('error') and not refreshed.get('error'):
                refreshed['error'] = result['error']
            return status, refreshed
        return status, result

    def _team_state_for_round(self, team, expected_round):
        result = self.team_state(team)
        if result['round_id'] != expected_round:
            result['error'] = 'A new round has started. Return to team selection.'
        return result
