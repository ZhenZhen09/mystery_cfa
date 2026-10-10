# Team Access Codes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Game Master set separate team access codes and require a matching server-verified team session for every team data read or game action.

**Architecture:** Keep the existing team selection URLs as identifiers only. Persist salted PBKDF2 code hashes and hashed, expiring session tokens in SQLite; use a separate HttpOnly cookie per team, and require the cookie to match the requested team on all game APIs. Add protected Game Master APIs and dashboard controls for replacing a code, plus a team code-entry view that authenticates before loading the team's current state.

**Tech Stack:** Python standard library `http.server`, SQLite, `hashlib.pbkdf2_hmac`, `hmac`, browser JavaScript, existing CSS, Python `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-10-team-access-codes.md`

## Global Constraints

- No new dependencies.
- Never store or return plaintext team codes or raw session tokens except in the login response cookie.
- All team routes enforce a server-side session bound to the exact team id.
- Do not reset team progress, timers, results, or logs when setting/replacing a code or starting a new round.
- Keep team-specific URLs and existing Game Master authentication behavior.
- Team One and Team Two must use separate browser profiles or devices; cookies are shared across tabs in one profile.

## Review Focus

- Team 1's session must not authorize Team 2 APIs in a separate browser profile, including reads and all three mutations.
- Missing/unconfigured and wrong codes must not start timers or disclose team state; repeated wrong guesses are temporarily rate-limited.
- Replacing a team code must revoke only that team's previous sessions without changing game state.
- Session cookies must be HttpOnly, SameSite=Strict, and Secure under HTTPS; login and mutation POSTs must pass same-origin checks.
- Existing databases and active game state must migrate without data loss; new-round reset must retain code configuration.

## File Map

- `server.py`: schema/migrations, code hashing, team login/session helpers, protected team APIs, Game Master code status/update APIs.
- `public/app.js`: team-code prompt, authenticated team entry/refresh, dashboard code status/replacement forms and feedback.
- `public/styles.css` (or the stylesheet currently linked by `public/index.html`): focused layout for login forms and dashboard controls, preserving existing responsive design.
- `tests/test_game.py`: endpoint-level authentication, isolation, migration, revocation, expiry, and state-preservation tests.
- `README.md`: Game Master setup instructions, code lifecycle, and security limits.

### Task 1: Add failing server/API tests

**Files:**
- Modify: `tests/test_game.py`

- [x] Add test helpers to log the Game Master in, set two team codes through the planned API, log a team in, and send the team-specific cookie.
- [x] Add tests that unset codes and wrong codes return errors without revealing team state or starting a timer; repeated failures receive a temporary per-team/client lockout.
- [x] Add tests that valid Team 1 and Team 2 codes produce distinct cookies and each cookie authorizes only its own team; document that entering both codes in one browser profile grants that profile both sessions.
- [x] Add tests that `/api/state`, `/api/start`, `/api/answer`, and `/api/final` reject missing or cross-team authentication.
- [x] Add tests that Game Master code status reveals only configured flags; unauthenticated updates and forged-origin updates are rejected; code updates revoke only that team's sessions.
- [x] Add tests that code hashes survive `initialize()`/server restart and new-round reset while team state remains untouched on code changes.
- [x] Run `python -m unittest discover -s tests -p test_game.py`; verify the new behavior tests fail for the expected missing routes/authorization.

### Task 2: Implement persistent server-side code/session authorization

**Files:**
- Modify: `server.py`

- [x] Add SQLite tables for per-team PBKDF2 hash/salt/iteration metadata, hashed team sessions (team id, created, expiry), and per-team/client login throttles; preserve existing rows on migration.
- [x] Add helpers for code creation/verification, random opaque session creation, team-specific cookie naming, expiry, revocation, and authenticated-team validation.
- [x] Add `POST /api/team/login`; require same origin, valid team id, configured code, and constant-time hash verification; issue an HttpOnly/SameSite=Strict cookie with Secure determined by existing HTTPS configuration and 8-hour max age.
- [x] Add authenticated, Game Master-only code status and replacement endpoints; reject codes shorter than 8 characters; store only hashes; revoke only updated team's active sessions.
- [x] Protect `GET /api/state` and `POST /api/start`, `/api/answer`, and `/api/final` by team session and same-origin validation for POSTs. Return 401 for missing/mismatched sessions and never reveal state before authentication.
- [x] Keep old database progress, history, timers, and results unchanged. Keep code records across round reset and valid team sessions across process restarts.
- [x] Run the new focused tests and adjust implementation until they pass.

### Task 3: Add team and Game Master UI flows

**Files:**
- Modify: `public/app.js`
- Modify: the stylesheet linked by `public/index.html`

- [x] Change `enterTeam(team)` to request the team's protected state; on 401, show a labeled code form for that team instead of falling back to landing or leaking an error.
- [x] Submit the code to `/api/team/login`, then fetch state only after successful login; preserve the selected team URL and support refresh/re-entry through the cookie.
- [x] Keep distinct Team 1/Team 2 cookies and ensure switching the URL to the other team shows that team's own code prompt if that profile has not authenticated for it.
- [x] Add a Team Access Codes panel to the Game Master dashboard that displays only “Set”/“Not set”, accepts a replacement code for each team, and shows clear success/error messages. Clear the password input after a successful save.
- [x] Wire dashboard requests to the protected Game Master APIs and keep dashboard polling/round reset compatible with the new section.
- [x] Make forms keyboard accessible, provide visible labels and status/error text, and preserve the existing responsive theme.
- [x] Verify manually with two isolated team browser profiles and one GM tab on a local test database; authenticate both teams, refresh both, try cross-team URL switching in each profile, replace one code, and confirm only that team's prior session is revoked.

### Task 4: Document setup and run complete verification

**Files:**
- Modify: `README.md`

- [x] Document that the Game Master must set both codes before teams can use game APIs, should distribute each code privately, can replace codes to revoke sessions, and repeated guessing triggers a short lockout.
- [x] Explain that codes are shared secrets and do not prevent a player sharing a code or using an already authenticated device.
- [x] Run `python -m unittest discover -s tests -p test_game.py` and inspect the complete result.
- [x] Run syntax validation for `server.py` and frontend JavaScript syntax validation using installed runtime tools; do not install a new dependency.
- [x] Inspect the final changed files and verify no code value or raw team session token is embedded in frontend assets, API response bodies, logs, or URLs.
