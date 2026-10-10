"""Pure game rules shared by the SQLite and Firestore backends."""
import json
import time

QUESTIONS = [
    ('By what percentage did the Collection Team exceed their September cash target?', '111%', 'The Food', 'No poison was found in the food.'),
    ('In the feature article, complete the title: Alvin’s Next Chapter: Balancing Work, Life, and _______.', 'learning', 'The Glass', "The waitress saw the Chef handling the victim’s glass before dinner."),
    ('In the feature article “A Furmom’s Heart: Krisselle and Her Beloved Companions”, what breed is Dachi, her lively 2-year-old dog?', 'dachshund', 'The Secret Message', '“You promised me we would be together. I’m tired of being your secret.”'),
    ('According to the headline “Liaison Desk Lifts Completion Rate to 89.1% on a Heavier Load”, which month carried the heavier workload?', 'september', 'The Hidden Photo', 'A photo shows the Victim and Chef together privately.'),
    ('Overdue AR dropped to ₱55.1M while cash collections nearly doubled to ₱146.4M. Does this outcome indicate a favorable or not favorable performance? Enter “favorable” or “not favorable”.', 'favorable', 'The Waitress', "The waitress admits she saw the Chef with the victim’s glass but kept quiet because she secretly loved the Chef."),
]
SOLUTION = {'killer': 'The Chef', 'weapon': 'Poisoned Drink', 'motive': 'Jealousy'}
FINAL_ANSWERS = {
    'killer': {'the chef', 'chef', 'sam'},
    'weapon': {'poisoned drink', 'poison drink', 'drink', 'wine'},
    'motive': {'jealousy'},
}
TEAM_CODE_ITERATIONS = 310_000
TEAM_LOGIN_FAILURE_LIMIT = 10
TEAM_LOGIN_WINDOW_SECONDS = 900
TEAM_LOGIN_LOCK_SECONDS = 300


def normalize(value):
    return ' '.join(str(value).strip().casefold().split())


def correct_submission(submission):
    return all(normalize(submission[k]) in FINAL_ANSWERS[k] for k in SOLUTION)


def _json_value(value):
    if value is None or isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _get(row, key, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None and default is not None else value


def state(row, round_id=None, reveal_solution=False):
    now = time.time()
    started = _get(row, 'started')
    finished = _get(row, 'finished')
    wrong_attempts = _get(row, 'wrong_attempts', 0) or 0
    progress = _get(row, 'progress', 0) or 0
    elapsed = ((finished or now) - started) if started else 0
    remaining = max(0, 1800 - elapsed - wrong_attempts * 180)
    submission = _json_value(_get(row, 'submission'))
    ended = bool(submission) or remaining <= 0
    result = {
        'team': _get(row, 'id'), 'round_id': round_id, 'started': started,
        'remaining': remaining, 'progress': progress,
        'wrong_attempts': wrong_attempts, 'ended': ended,
        'expired': remaining <= 0,
        'last_attempt': _json_value(_get(row, 'last_attempt')),
        'clues': [{'number': i + 1, 'title': q[2], 'text': q[3]} for i, q in enumerate(QUESTIONS[:progress])],
    }
    if started and progress < len(QUESTIONS) and not ended:
        result['question'] = QUESTIONS[progress][0]
    if ended:
        result.update(
            submission=submission,
            correct=bool(submission) and correct_submission(submission),
            elapsed=round((finished or started + 1800) - started) if started else 0,
        )
        if reveal_solution:
            result.update(solution=SOLUTION, solution_explanation=(
                'The food was clean. The poison was in the drink. The Chef handled the glass, '
                'and the hidden message and photo exposed a secret relationship. Jealousy turned '
                'that secret into murder. The waitress witnessed the Chef handling the glass. '
                'Her love for the Chef kept her silent until her confession connected the evidence.'))
    return result


def event_record(row):
    created_at = _get(row, 'created_at', 0) or 0
    return {
        'id': _get(row, 'id'),
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(created_at)),
        'round_id': _get(row, 'round_id'), 'team': _get(row, 'team_id'),
        'type': _get(row, 'event_type'), 'payload': _json_value(_get(row, 'payload')),
        'correct': None if _get(row, 'correct') is None else bool(_get(row, 'correct')),
        'summary': _get(row, 'summary', ''),
    }
