# SDD ledger — plan: docs/superpowers/plans/2026-10-10-team-access-codes.md

Base: workspace has no Git metadata, so worktree isolation and task-start BASE capture are unavailable. User authorized implementation in the current workspace.

Pre-flight: server team-session APIs feed both the team portal (`public/app.js`) and API tests (`tests/test_game.py`); database schema in `server.py` must precede both. Dashboard codes APIs also feed `public/app.js`; tests cover the API contract.

Ruling: use distinct HttpOnly cookies per team, but require separate browser profiles/devices for team isolation — browser tabs in one profile share cookies, so storing both team cookies in one profile authorizes both teams. This avoids weakening session protection to tab-scoped JavaScript storage.

Task 1: complete — added HTTP tests for wrong/missing codes, team-bound reads and actions, origin checks, session expiry/restart, code rotation, status privacy, and state preservation. Ran red tests before server implementation.

Task 2: complete — PBKDF2-HMAC-SHA256 code hashes and hashed 8-hour team sessions persist in SQLite; protected state/game endpoints and Game Master code APIs are implemented. Login is limited to 10 failures per team/client per 15 minutes, followed by a five-minute lock; changing that team's code clears its lockout.

Task 3: complete — added the team code prompt and Game Master dashboard code controls. Playwright verified the UI, code rejection/acceptance, separate browser context isolation, refresh persistence, and code revocation.

Task 4: complete — README and spec/plan document code setup, browser-profile limits, and temporary login lockout. Fresh final verification: 20 Python tests passed; `py_compile` and `node --check` succeeded; no sample team codes are in the served frontend source.
