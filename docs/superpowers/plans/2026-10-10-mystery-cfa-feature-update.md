# Mystery CFA Feature Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. All implementation steps below are complete.

**Goal:** Apply the requested briefing, clue media, final-answer, game-master dashboard, round-reset, timer-suspense, and victory-screen changes to the existing mystery game.

**Architecture:** Extend the current SQLite team state and authenticated APIs, then update the existing single-page client and CSS. Team pages use the existing short polling interval to detect round changes; no new package or service is introduced.

**Tech Stack:** Python standard library, SQLite, HTML, CSS, JavaScript, `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-10-mystery-cfa-feature-update-design.md`

## Global Constraints

- Keep the Python standard-library server, SQLite database, and current single-page frontend; add no runtime dependencies.
- A new round permanently removes Team One and Team Two event rows, resets their stored investigation state, and records a fresh round-start event. Old team activity is not archived.
- An open team briefing or investigation detects a changed round ID through the existing polling pattern and returns to the landing screen without a document reload.
- A wrong final accusation remains retryable after its penalty. The submitted values stay visible in disabled fields until the team deliberately chooses to enter another accusation.
- Honor `prefers-reduced-motion` for countdown and victory effects.

## Review Focus

- A team page that is open on its briefing or investigation sees a changed round ID, clears its local state, stops audio, and reaches the landing page without reloading; cover both screen states in manual verification.
- The round reset deletes only team-associated events, atomically clears both team rows, and adds a round-start record; cover retained round-control state and deleted team events in a server test.
- Wrong final submissions persist across refresh and stay visible/disabled until an explicit retry; cover latest-attempt persistence in an API test and retry behavior in a manual UI pass.
- Both per-team feeds paginate independently and reject an invalid team filter; cover ascending/descending IDs, filter isolation, and invalid values in endpoint tests.
- Countdown color interpolation and confetti honor reduced-motion preferences and do not obscure controls; cover both preference states in manual UI verification.

## File Map

- Modify `server.py`: team-state migration, latest final attempt, round ID in state, filtered event pagination, weapon alias, atomic reset deletion.
- Modify `tests/test_game.py`: API regression coverage for state, alias, events, final attempts, and new-round behavior.
- Modify `public/app.js`: briefing, clue media, live round redirect, locked final values/retry, separated team feeds, suspense, and win celebration.
- Modify `public/style.css`: responsive activity columns, color transitions, critical timer pulse, and reduced-motion-aware victory effects.
- Add `public/media/chief.mp4`: provided Chief statement video.
- Modify `docs/superpowers/specs/2026-10-10-mystery-cfa-feature-update-design.md` only if implementation uncovers a design change; otherwise leave the approved spec unchanged.

### Task 1: Round state, final attempt, event filtering, and reset semantics

**Files:**
- Modify: `server.py`
- Test: `tests/test_game.py`

**Interfaces:**
- `state(row, round_id=None)` returns the team state plus active `round_id` and parsed `last_attempt` when present.
- `GET /api/gm/events?team=1|2&limit=<n>&before=<id>` remains game-master authenticated and returns a page containing only that team's events; omitting `team` preserves the current all-events behavior for compatible callers.
- `POST /api/gm/new-round` deletes rows with `team_id IN (1, 2)`, resets both teams, creates a round-start event, and returns the new `round_id` in one transaction.
- `correct_submission()` accepts `poison drink` case-insensitively as a weapon alias.

- [x] **Step 1: Add failing tests for the new team-state contract**

In `tests/test_game.py`, extend `test_full_round_and_team_isolation` to assert that both team states include the same integer `round_id`. Add a wrong final attempt assertion that `last_attempt` equals the submitted values, then request `/api/state?team=1` again and assert the values remain. Add a successful final attempt assertion that `last_attempt` still shows the submitted values.

```python
    def test_state_exposes_round_and_latest_final_attempt(self):
        self.solve()
        attempt = {'team': 1, 'killer': 'waitress', 'weapon': 'wine', 'motive': 'money'}
        status, result = self.request('/api/final', attempt)
        self.assertEqual(status, 422)
        self.assertEqual(result['last_attempt'], {key: attempt[key] for key in ('killer', 'weapon', 'motive')})
        _, refreshed = self.request('/api/state?team=1')
        self.assertEqual(refreshed['last_attempt'], result['last_attempt'])
        self.assertIsInstance(refreshed['round_id'], int)
```

- [x] **Step 2: Run focused tests and verify the expected failures**

Run: `python tests/test_game.py GameTests.test_state_exposes_round_and_latest_final_attempt -v`

Expected: FAIL because team state does not yet return `round_id` or `last_attempt`.

- [x] **Step 3: Add failing tests for aliases, event filtering, and reset deletion**

Add a direct `correct_submission()` test for each of `poison drink`, `drink`, and `wine`; assert authenticated team-filtered event requests contain only the selected `event.team`; and assert a filter of 3 returns HTTP 400. For reset, create events for both teams, call authenticated `/api/gm/new-round`, then assert both teams have zero progress, no start, no successful submission, no `last_attempt`, no penalties, no old team events, and a new `round_started` event with the returned round ID. Add `gm_login()` to POST `/api/gm/login`, set `game.GAME_MASTER_PASSWORD = 'host-secret'`, save the first `Set-Cookie` segment, and return it. Add `gm_request(path, data, cookie)` to send that cookie and `Origin: http://127.0.0.1:<server port>`; use these helpers for dashboard, events, and reset calls.

```python
    def gm_login(self):
        game.GAME_MASTER_PASSWORD = 'host-secret'
        origin = f'http://127.0.0.1:{self.server.server_port}'
        status, result, headers = self.request_with_headers(
            '/api/gm/login', {'password': 'host-secret'}, {'Origin': origin})
        self.assertEqual(status, 200)
        return headers['Set-Cookie'].split(';', 1)[0]
```

Implement `request_with_headers()` by extending `request()` to accept `headers=None` and return `status, json.loads(response.read()), dict(response.getheaders())`. Implement `gm_request()` to call it with `headers={'Content-Type': 'application/json', 'Cookie': cookie, 'Origin': f'http://127.0.0.1:{self.server.server_port}'}`. The matching local Origin satisfies the server's same-origin check.

```python
    def request_with_headers(self, path, data=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        request_headers = {'Content-Type': 'application/json', **(headers or {})}
        connection.request('GET' if data is None else 'POST', path,
                           body=None if data is None else json.dumps(data), headers=request_headers)
        response = connection.getresponse()
        result = (response.status, json.loads(response.read()), dict(response.getheaders()))
        connection.close()
        return result

    def gm_request(self, path, data, cookie):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        return self.request_with_headers(path, data, {
            'Cookie': cookie,
            'Origin': origin,
        })
```

- [x] **Step 4: Run focused tests and verify the expected failures**

Run: `python tests/test_game.py -v`

Expected: new alias/filter/reset assertions fail until the server routes and database migration are updated.

- [x] **Step 5: Implement the database migration and state payload**

In `initialize()`, add `last_attempt TEXT` to new team tables and use `PRAGMA table_info(teams)` plus `ALTER TABLE` when upgrading an existing database. Update `state()` to accept or look up the active round ID and parse the nullable JSON value. In `/api/state`, obtain the active round in the same connection and pass it to `state()`. In `/api/final`, persist the submitted values as JSON on every valid final attempt, in the same transaction as its event and any penalty or successful completion.

```python
submission = {key: str(data.get(key, '')).strip()[:100] for key in SOLUTION}
connection.execute('UPDATE teams SET last_attempt=? WHERE id=?',
                   (json.dumps(submission, ensure_ascii=False), team))
```

- [x] **Step 6: Implement alias, filtered event paging, and atomic new-round reset**

Add `poison drink` to `FINAL_ANSWERS['weapon']`. Parse an optional `team` query in `/api/gm/events`, accept only 1 or 2, and add `team_id=?` to both first-page and cursor-page queries when supplied. During `/api/gm/new-round`, delete team events, reset `last_attempt` along with existing team fields, and insert the new round and round-start event within the same transaction.

- [x] **Step 7: Run the full Python suite and confirm the server tests pass**

Run: `python -m unittest discover -s tests -v`

Expected: all existing and new HTTP/database tests pass. If the existing reset test still targets the obsolete `/api/reset` route, update it to exercise the current authenticated `/api/gm/new-round` API rather than restoring the obsolete endpoint.

### Task 2: Team briefing, clue videos, and live round redirect

**Files:**
- Modify: `public/app.js`
- Add: `public/media/chief.mp4`

**Interfaces:**
- Team portal state captures `current.round_id` on entry and compares it during the polling interval while on either `brief` or `game` screens.
- A different round ID calls the existing landing renderer after stopping music and clearing selected clue/client-only final-form state.
- Clue 2 renders `waitress.mp4` and `intro.mp4`; Clue 5 renders the copied Chief media file.

- [x] **Step 1: Copy the provided media file into the public asset directory**

Copy `C:\Users\63938\Downloads\mystery_cfa-main\mystery_cfa-main\d06f133c-b316-4d36-954a-95d8bbaaf1d6.mp4` to `public/media/chief.mp4`. Confirm the source exists and the copied file has nonzero length.

- [x] **Step 2: Remove only the requested briefing content**

Edit `brief()` in `public/app.js` to remove the paragraph beginning “But old relationships, jealousy...” and remove the full “YOUR 30-MINUTE INVESTIGATION” heading and timeline block. Preserve the opening paragraph, source-article guidance, and both actions.

- [x] **Step 3: Reassign videos to their requested clues**

In `evidence(content)`, render the Waitress (`waitress.mp4`) and Chef (`intro.mp4`) statements in Clue 2 with visible labels. Render the supplied `/media/chief.mp4` as the statement in Clue 5, replacing its previous Chef video. Preserve Clue 4 image and video assets.

- [x] **Step 4: Poll round changes in briefing and investigation screens**

Update the state polling loop to run while `screen === 'brief' || screen === 'game'`. On a successful poll, compare `previous.round_id` to the response `round_id`; if changed, set `current` to the new state, clear `selectedClue` and local accusation UI state, stop background music, set a landing notice, and call `home()`. Leave current content untouched on a network error and retain the connection-status message while in the investigation.

- [x] **Step 5: Run frontend syntax validation**

Run: `node --check public/app.js`

Expected: no syntax error.

### Task 3: Locked final accusation values and retry flow

**Files:**
- Modify: `public/app.js`
- Test: `tests/test_game.py`

**Interfaces:**
- `current.last_attempt` contains the latest submitted `{killer, weapon, motive}` values from Task 1.
- `finalForm(content)` renders populated disabled controls when a stored attempt exists and an explicit retry action when the team has remaining time.
- The completed-case result renders the final attempt in disabled controls, including the correct solve.

- [x] **Step 1: Confirm server tests cover attempt persistence and penalty behavior**

Run the focused Python tests from Task 1 and verify a wrong attempt remains present after a fresh `/api/state` request, while `wrong_attempts` and remaining time reflect the three-minute deduction.

- [x] Run: `python tests/test_game.py GameTests.test_state_exposes_round_and_latest_final_attempt GameTests.test_wrong_final_attempt_deducts_three_minutes_and_allows_retry -v` (persistence and 3-minute deduction verified; full suite also passes).

- [x] **Step 2: Render submitted accusation fields as visible and disabled**

Update `finalForm(content)` to use stored values for `killer`, `weapon`, and `motive`, set their `disabled` properties when showing a previous attempt, and render a “Try another accusation” button. Clicking it sets a local retry flag and re-renders blank, enabled fields. A new submission replaces `last_attempt`; refresh or reconnect returns to the latest stored values.

- [x] **Step 3: Preserve submitted values on completed case screens**

Update `reveal(content)` to render the team's final attempt using the same disabled inputs, retaining visible values after a correct solve or timer expiry. Keep the readable solution section and case result.

- [x] **Step 4: Manually verify retry and completion states**

In a browser, unlock all five clues, submit a wrong combination, and confirm all three values remain visible and disabled while the 3-minute deduction appears. Reload the team page and confirm the values remain. Choose retry and verify the form clears/enables; then submit the accepted solution and confirm the completed screen shows the final values disabled.

### Task 4: Separate game-master activity columns

**Files:**
- Modify: `public/app.js`
- Modify: `public/style.css`
- Test: `tests/test_game.py`

**Interfaces:**
- The authenticated event API's `team=1` and `team=2` pages are defined in Task 1.
- The client stores independent event arrays, cursors, and `has_more` flags per team.
- Desktop dashboard shows two columns; mobile dashboard stacks them.

- [x] **Step 1: Verify event filtering and cursor pagination tests**

Run the event endpoint tests from Task 1. Assert each page contains only its requested team and later pages contain IDs lower than the prior page's oldest ID.

- [x] **Step 2: Load both team's logs independently**

Replace the single `gmEvents` feed state with per-team arrays and pagination state. In the dashboard loader, request `/api/gm/events?team=1&limit=30` and `/api/gm/events?team=2&limit=30`; keep each list newest-first and refresh without duplicating IDs. Add separate load-older handlers that pass each team's cursor.

- [x] **Step 3: Render the two labeled activity columns**

Replace the shared “Activity log” section with “Team One Activity” and “Team Two Activity” panels, each rendering its own events, empty state, and load-older button. Preserve event answers, accusation values, outcomes, timestamps, and HTML escaping.

- [x] **Step 4: Add responsive dashboard layout rules**

Use a two-column CSS grid with `minmax(0, 1fr)` columns on desktop and switch to one column at the existing mobile breakpoint. Keep timestamps, event payloads, and buttons wrapped within their panel without horizontal overflow.

- [x] **Step 5: Manually verify dashboard activity**

Open both team clients and the game-master dashboard. Submit actions for each team and confirm they appear only in the matching column. Load older activity for one team and verify the other team's list and cursor remain unchanged. Check narrow viewport stacking.

### Task 5: Countdown suspense and victory celebration

**Files:**
- Modify: `public/app.js`
- Modify: `public/style.css`

**Interfaces:**
- The existing timer interval computes remaining seconds and applies a normalized CSS property to the page and timer.
- Correctly solved state renders the victory heading and decorative confetti; the animation is hidden from assistive technology.
- `prefers-reduced-motion: reduce` suppresses the pulse, confetti motion, and animated color transitions.

- [x] **Step 1: Add the dynamic timer suspense value**

In the 250 ms timer update, compute `tension = 1 - Math.min(1, remaining() / 1800)` and set `--timer-tension` on the active page root. Clear or reset the property when leaving the team investigation or entering a new round.

- [x] **Step 2: Add gradual page and timer color transitions**

In `public/style.css`, use the suspense custom property to blend the existing gold/neutral accent into orange and then red as `--timer-tension` increases. Apply the blend to the timer, a subtle page accent/background tint, and selected borders. Add a restrained pulse only at the critical end of the timer; keep text contrast readable.

- [x] **Step 3: Add the victory title and confetti**

In `reveal(content)`, when `current.correct` is true, render an animated “YOU WON!” line above “You Uncovered the Truth.” Add a small CSS-only confetti set with `aria-hidden="true"` and a finite animation so it stops naturally. Keep the existing non-victory result title for expired or incorrect cases.

- [x] **Step 4: Honor reduced-motion preferences**

Add or extend `@media (prefers-reduced-motion: reduce)` to disable color transitions, critical pulse, title motion, and confetti animation while keeping all victory text and result content visible.

- [x] **Step 5: Manually verify normal, warning, critical, victory, and reduced-motion states** (victory and reduced-motion rendering checked in-browser; remaining-time colors interpolated from live timer state; critical CSS class is applied under three minutes).

Use browser devtools or a temporary local database update to inspect remaining times near 30, 10, and 3 minutes. Confirm the color shifts smoothly and warning effects remain subtle. Solve once correctly, then repeat with reduced motion enabled and confirm the result is readable without moving effects.

### Task 6: Full verification and documentation update

**Files:**
- Modify: `README.md`
- Verify: `server.py`, `tests/test_game.py`, `public/app.js`, `public/style.css`, `public/media/chief.mp4`

- [x] **Step 1: Run the full Python test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass, including migrations, final attempt persistence, event filtering, aliases, team log deletion, and both-team reset state.

- [x] **Step 2: Check JavaScript syntax**

Run: `node --check public/app.js`

Expected: command exits successfully with no output.

- [x] **Step 3: Run the application and verify the requested flows** (manual browser checks covered clues, accusation retry/success, dashboard columns/responsiveness, and both live redirects; API suite covers answer aliases, penalties, and reset state).

Start the server with local HTTP cookies enabled, open two team browser profiles and a game-master profile, then verify: edited briefing; Clue 2 and Clue 5 media; answer alias; final submission locking/retry; separate activity columns; a wrong final-answer penalty; countdown color changes; victory and reduced-motion presentation; new round clearing both team histories and state; and both team pages redirecting to landing within the polling interval without a document refresh.

- [x] **Step 4: Update the round-reset documentation**

In `README.md`, replace any statement that event history survives every new round. State that starting a new round permanently clears both teams' activity events, progress, saved answers/results, penalties, and timers; game-master event authentication remains unchanged.

- [x] **Step 5: Inspect final changes for safety and asset correctness**

Confirm the Chief video is served from `/media/chief.mp4`, event text remains escaped, reset and event deletion share a transaction, old team events are absent after reset, and no external packages or animation libraries were added.
