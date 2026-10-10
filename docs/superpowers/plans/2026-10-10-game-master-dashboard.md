# Game Master Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Team One/Team Two entry buttons and a password-protected game-master dashboard for live team monitoring, persistent event history, and starting fresh rounds.

**Architecture:** Extend the existing Python HTTP server and SQLite database. Add server-side hashed session tokens, round and event history, authenticated dashboard APIs, and atomic round reset. Update the current single-page frontend with a landing screen, login screen, and live dashboard while preserving each team’s independent timer start.

**Tech Stack:** Python standard library, SQLite, HTML/CSS/JavaScript, `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-10-game-master-dashboard-design.md`

## Global Constraints

- Keep the application dependency-free and on the current Python/SQLite server.
- “Game 1” and “Game 2” map to the existing Team One and Team Two slots.
- Team timers start independently when each team starts its investigation.
- `GAME_MASTER_PASSWORD` configures game-master login; there is no default password.
- Store only a hash of an opaque random session token; use HttpOnly and SameSite cookies and configurable Secure cookies.
- Keep event history across round resets; never store passwords, cookies, or session tokens in events.
- Require confirmation before resetting both teams and make the reset atomic.

## Review Focus

- Existing SQLite database migration preserves active team progress while adding round/event/session tables; test with the old schema.
- Missing or incorrect passwords never expose dashboard data and produce generic errors; test unset configuration and wrong credentials.
- Malformed, expired, logged-out, or forged-origin sessions cannot read protected data or reset rounds; test each rejection path.
- Incorrect question answers and final accusations are logged without changing clue progress incorrectly; test both correct and incorrect submissions.
- Reset clears both teams' live state but preserves previous event history and starts team timers stopped; test both teams and old events.

## File Map

- Modify `server.py`: database migrations, session helpers, authenticated routes, dashboard data, event recording, and atomic round reset.
- Modify `tests/test_game.py`: HTTP-level regression tests for migration, authentication, protected routes, event history, and resets.
- Modify `public/index.html`: add a dedicated landing root/navigation affordance only if needed by the single-page flow.
- Modify `public/app.js`: landing, team entry, login, dashboard, polling, log rendering, and confirmed round reset.
- Modify `public/style.css`: responsive styles for login, dashboard cards, activity feed, and accessible controls.
- Modify `README.md`: password/cookie configuration and game-master dashboard instructions.

### Task 1: Database schema, migrations, and event helpers

**Files:**
- Modify: `server.py`
- Test: `tests/test_game.py`

**Interfaces:**
- `initialize()` creates `rounds`, `game_master_sessions`, and `game_events` tables and migrates existing installations without resetting team rows.
- `log_event(connection, round_id, event_type, team=None, payload=None, correct=None, summary='')` inserts an event in the caller's transaction.
- `current_round_id(connection)` returns the active round id, creating the initial round when needed.

- [ ] **Step 1: Add failing migration and log-retention tests**

Create an old-schema SQLite database with teams at nonzero progress, call `initialize()`, and assert progress remains while an initial round and event/session tables exist. Add an event, run initialization again, and assert the event remains.

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `python -m unittest discover -s tests -p test_game.py -v`

Expected: schema assertions fail because the round, session, and event tables do not exist.

- [ ] **Step 3: Add schema migration and event helpers**

Use `CREATE TABLE IF NOT EXISTS`, inspect existing columns before `ALTER TABLE`, and create exactly one initial round for a migrated database. Event writes use the caller's connection so event and game changes can commit together.

- [ ] **Step 4: Run the focused tests and confirm they pass**

Run: `python -m unittest discover -s tests -p test_game.py -v`

Expected: migration preserves team progress and repeated initialization preserves history.

### Task 2: Game-master authentication and protected APIs

**Files:**
- Modify: `server.py`
- Test: `tests/test_game.py`

**Interfaces:**
- `POST /api/gm/login` accepts `{ "password": "..." }`, issues a random opaque session token in a cookie, and stores only its SHA-256 hash.
- `POST /api/gm/logout` invalidates the current session.
- `GET /api/gm/session` reports whether the cookie has a valid session.
- `require_game_master(handler, connection)` returns the authenticated session or sends an error response.
- `SESSION_COOKIE_SECURE` controls the cookie's Secure attribute; `GAME_MASTER_PASSWORD` supplies the configured password.

- [ ] **Step 1: Add failing login/session tests**

Test successful login and session cookie flags, incorrect password, missing configured password, session endpoint with and without a cookie, logout invalidation, expiry, and server initialization clearing old sessions.

- [ ] **Step 2: Run focused tests and confirm authentication failures**

Run: `python -m unittest discover -s tests -p test_game.py -v`

Expected: login routes are missing or return the current unknown-action response.

- [ ] **Step 3: Implement password login and server-side sessions**

Use `secrets.token_urlsafe(32)`, constant-time password comparison, and `hashlib.sha256(token.encode()).hexdigest()` for database lookup. Set HttpOnly, SameSite=Strict, Path=/, a bounded Max-Age, and the configured Secure flag. Delete all sessions during server initialization. Never return or log the raw token or configured password.

- [ ] **Step 4: Add centralized authentication and origin checks**

Require a valid unexpired cookie for future dashboard APIs. For authenticated POSTs, reject an Origin that does not match the request's scheme and host. Keep public team APIs unchanged.

- [ ] **Step 5: Run authentication tests and confirm they pass**

Run: `python -m unittest discover -s tests -p test_game.py -v`

Expected: only valid login cookies access protected resources; logout, expiry, and origin rejection behave as specified.

### Task 3: Team/event logging, dashboard API, and new-round transaction

**Files:**
- Modify: `server.py`
- Test: `tests/test_game.py`

**Interfaces:**
- `GET /api/gm/dashboard` requires a session and returns Team One/Two summaries with progress, remaining seconds, started/ended flags, wrong-attempt counts, and submitted final accusation.
- `GET /api/gm/events?before=<id>&limit=<n>` requires a session and returns newest-first events with a bounded maximum page size.
- `POST /api/gm/new-round` requires a session and same-origin request, clears both teams, advances the active round, appends a round-start event, and returns success.
- Team start, answer, final-answer, and wrong-attempt transitions append event records in the same transaction as their state updates.

- [ ] **Step 1: Add failing event and dashboard API tests**

Assert a correct answer logs the submitted answer and a clue-unlocked event; an incorrect answer logs a failed attempt but leaves progress unchanged. Assert wrong and correct final combinations are logged with their values and outcome. Assert the dashboard reports both teams and unauthenticated requests are rejected.

- [ ] **Step 2: Add failing bounded-history and reset tests**

Assert event pagination caps limits and orders by descending id. Assert authenticated reset clears both teams' timers, progress, submissions, and penalties; increments the round; preserves old events; and logs the round event. Assert missing/invalid sessions and forged Origin requests cannot reset.

- [ ] **Step 3: Run focused tests and confirm missing behavior**

Run: `python -m unittest discover -s tests -p test_game.py -v`

Expected: dashboard/event/reset API tests fail because routes and event writes are absent.

- [ ] **Step 4: Implement API routes and transactional event recording**

Use one SQLite transaction for every team mutation plus its event rows. Create both `answer_attempt` and `clue_unlocked` events on correct question answers; create only the attempt event for incorrect answers. Record each final combination and correctness, including the 3-minute penalty outcome. Return safe bounded event pages and dashboard summaries. Reset both teams and advance the round atomically without deleting old events.

- [ ] **Step 5: Run focused tests and confirm API behavior**

Run: `python -m unittest discover -s tests -p test_game.py -v`

Expected: all dashboard, logging, authentication, migration, and reset tests pass.

### Task 4: Landing, login, dashboard, and responsive styles

**Files:**
- Modify: `public/app.js`
- Modify: `public/style.css`
- Modify: `public/index.html` only if the existing root shell needs accessible navigation updates.

**Interfaces:**
- Landing exposes Team One, Team Two, and Game Master login actions.
- Team entry preserves the current briefing and investigation screens.
- Login stores no password client-side; session state relies on the HttpOnly cookie.
- Dashboard polls `/api/gm/dashboard` and `/api/gm/events`, displaying progress, independent timers, status, final accusations, and event history.
- Start New Round asks for confirmation, posts to `/api/gm/new-round`, refreshes the dashboard, and displays success/error feedback.
- Logout posts to `/api/gm/logout` and returns to landing.

- [ ] **Step 1: Implement landing and login states using existing visual language**

Add explicit Game One/Team One and Game Two/Team Two entry buttons. Add labeled password input, visible error status, and a submit button. Keep game master password only in the input and submit it over same-origin HTTPS in hosted deployments.

- [ ] **Step 2: Implement the dashboard and event feed**

Render two responsive team cards, visible progress counts and timers, accusation status/details, newest-first events, a refresh/poll loop, logout, and confirmed new-round action. Escape all dynamic event and accusation strings before rendering HTML.

- [ ] **Step 3: Add responsive and accessible styles**

Match the existing dark restaurant-mystery style. Preserve visible keyboard focus, semantic heading hierarchy, explicit labels, live status feedback, and usable mobile card/feed layout without horizontal overflow.

- [ ] **Step 4: Check JavaScript syntax and targeted UI strings**

Run: `node --check public/app.js`

Expected: command succeeds and the three landing actions plus dashboard controls render from the relevant screen states.

### Task 5: Configuration docs and full verification

**Files:**
- Modify: `README.md`
- Test: `tests/test_game.py`
- Verify: `server.py`, `public/app.js`, `public/style.css`

- [ ] **Step 1: Document password and cookie configuration**

Provide PowerShell and POSIX examples for `GAME_MASTER_PASSWORD`, `SESSION_COOKIE_SECURE`, and starting the server. State that hosted use must be behind HTTPS and that a fresh round clears both teams but leaves their timers stopped until they enter.

- [ ] **Step 2: Run the full Python test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all game and newly added dashboard tests pass.

- [ ] **Step 3: Run frontend syntax and whitespace checks**

Run: `node --check public/app.js`

Expected: no syntax errors. Review edited file output for accidental encoding changes and verify no password/token is included in event payloads.

- [ ] **Step 4: Review migration, game flow, login, dashboard, and reset behavior**

Check an old database preserves both teams, protected APIs reject anonymous access, both team timers remain individually started, events survive reset, and the dashboard refreshes after game actions.

## Execution Notes

- Execute in this current workspace; no Git worktree is available because the directory has no `.git` folder.
- Do not install dependencies.
- Do not change existing game content or accepted answer rules.
