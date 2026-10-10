# Team Access Codes Design

## Goal

Let the Game Master set a private access code for each team, then require the matching code before a browser can access or change that team's game state. A session authenticated for one team must never authorize actions for the other team.

## User flow

1. The Game Master logs in and sees a Team Access Codes section in the dashboard.
2. The Game Master enters and saves a separate code for Team One and Team Two. The dashboard shows whether each code is set, but never displays a saved code again.
3. A player selects a team and enters that team's code. A correct code establishes a server-side team session; an incorrect code leaves the player at the code prompt with a clear error.
4. The team session is held in an HttpOnly, SameSite=Strict cookie. Team state, start, clue-answer, and final-answer routes require a valid session bound to the requested team.
5. Refreshing or reopening that team's URL in the same browser profile keeps the session. Changing the URL to the other team does not switch identity; that team requires its own code in its own browser profile or device.
6. The Game Master can replace either code. Replacing a code invalidates existing sessions for that team, requiring the team to sign in again.

## Security and behavior

- Codes are entered and verified by the server; they are never embedded in the HTML, JavaScript, URL, team state, or Game Master dashboard response.
- Store only salted password hashes (PBKDF2-HMAC-SHA256) for codes. Compare using constant-time verification and enforce a minimum length of 8 characters.
- Rate-limit incorrect code attempts per team and client: after 10 failed attempts within 15 minutes, block that client from that team for five minutes. Replacing that team's code clears its lockout records.
- Store only hashes of random team-session tokens in SQLite, associated with team id and expiry. Team cookies are HttpOnly, SameSite=Strict, and Secure when HTTPS is enabled, following the existing Game Master cookie policy.
- Login and code-setting POST requests must pass same-origin validation. Team gameplay requests require the session cookie to match the team id; a caller cannot choose another team merely by editing the query or request body.
- Game Master dashboard access-code changes require the existing Game Master session.
- A new round preserves access-code hashes. Changing a code invalidates only that team's sessions; it does not reset that team's progress, timer, or logs.
- Each team must use a separate browser profile or device. Browser tabs in one profile share cookies; if both team codes are entered into one profile, that profile is authorized for both teams.
- If either code has not been configured, the team portal explains that the Game Master must set it before play. No team gameplay API is allowed until the correct code is set and authenticated.
- Codes are shared secrets. Players can still share their own code or use another logged-in device; this feature prevents casual outsiders and cross-team URL switching, not collusion or a compromised device.

## Interface changes

- Add `POST /api/team/login` accepting `{team, code}` and setting a team-scoped cookie after successful verification.
- Add a protected team-session check or derive authentication from the existing state request; return an unauthenticated response that the team portal can handle by showing the code prompt.
- Require team authentication for `GET /api/state` and `POST /api/start`, `/api/answer`, and `/api/final`.
- Add Game Master protected read/write operations for access-code status and code replacement. Status contains only configured booleans; write accepts one team's replacement code and never returns the saved code.
- Keep existing team selection buttons and `?team=1` / `?team=2` URLs. The URL selects which login prompt to show, not who the caller is authorized as.

## Persistence and migration

- Add SQLite tables for team access-code hashes and team sessions, with migrations safe for existing databases.
- Existing team rows, rounds, activity history, timers, and results remain intact. Codes begin unset, so the Game Master must configure both codes before teams can continue using protected game routes.
- Team sessions expire after eight hours, matching the existing Game Master session lifetime. Valid sessions survive a server restart because only token hashes and expiration times are stored in SQLite; logout, expiry, or changing that team's code invalidates them.
- Use a separate cookie name per team. Teams should authenticate in separate browser profiles/devices; tabs in a single profile share both cookies.

## Acceptance checks

- The dashboard can set and replace each team's code and never returns plaintext codes.
- Missing codes, incorrect codes, malformed requests, expired sessions, and Team One sessions used against Team Two routes are rejected.
- Correct codes authorize only their corresponding team; authorized sessions survive refresh and preserve the team's current game state. Verify cross-team denial using separate browser cookie jars.
- Updating a code invalidates old sessions for that team without resetting game state.
- New-round reset preserves both code hashes.
- Existing game APIs, timers, answer validation, Game Master access, and new-round behavior continue to work.
- Tests verify authentication at the HTTP/API boundary as well as frontend code-entry and error handling.
