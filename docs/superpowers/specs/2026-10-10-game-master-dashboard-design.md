# Game Master Dashboard Design

## Goal

Add a game master area to The Last Reunion Dinner so a host can monitor both existing team slots, inspect a persistent event history, and prepare a new round without changing the single-server, shared-database deployment model.

## Agreed behavior

- The landing page offers Team One, Team Two, and Game Master login.
- Team One and Team Two remain the current independent investigation slots.
- Each team starts its own 30-minute timer when that team starts the investigation.
- The game master logs in with a password configured on the server.
- The dashboard shows live team progress, remaining time, status, and final accusations.
- A timestamped event log includes answer submissions, correctness, clue unlocks, final accusations, and new-round actions. Submitted answers and accusation values are included.
- Event history survives round resets.
- Starting a new round requires confirmation and resets both teams' progress, timers, submissions, and wrong-attempt penalties. Team timers remain stopped until their teams start.

## Current application

The app is a dependency-free Python HTTP server with a SQLite database and a single-page frontend in `public/app.js`. Two team rows store their progress and timer state. A game master password already protects the in-game reset endpoint, but there is no login session, dashboard, or event history. Team selection is currently part of the investigation landing screen.

## Proposed design

### Landing and navigation

Replace the direct team-selection flow with a landing page containing Team One and Team Two buttons plus a Game Master login button. Team buttons enter the existing team briefing and investigation. The game master button opens a password login form. A logged-in game master can return to the landing page or log out from the dashboard.

### Authentication and sessions

Read the game master password from `GAME_MASTER_PASSWORD` at server startup. If unset, the game master login is unavailable and reset actions are rejected. Compare submitted passwords with a constant-time comparison. On successful login, issue an opaque, cryptographically random session token in an HttpOnly, SameSite cookie with a bounded lifetime. Store only a hash of the token server-side, expire sessions, and provide logout. Dashboard, log, and round-control endpoints require a valid session. Configure the cookie's Secure attribute with a `SESSION_COOKIE_SECURE` setting: enable it for HTTPS hosting and disable it only for local HTTP development. Check the Origin header on authenticated state-changing requests to prevent cross-site request forgery.

No default password is provided. Hosting documentation will explain how to configure the password and that public hosting should use HTTPS.

### Dashboard

Add a game-master dashboard in the existing frontend. Poll authenticated server endpoints to show both teams' current state: started/not started, clues recovered, remaining time, active/ended state, wrong-attempt count, and final accusation if submitted. Keep the dashboard read-only for team progress. A separate Start New Round action opens a confirmation prompt, then performs a reset of both team rows. The action leaves both timers stopped and retains all event history.

### Event history

Add a SQLite event table with an auto-increment id, timestamp, round identifier, team id when applicable, event type, submitted value/payload, correctness when applicable, and a readable summary. Record investigation starts, answer attempts (including incorrect answers), clue unlocks, wrong final combinations and their deductions, final accusation submissions, and round starts/resets. Keep history across rounds and return it newest-first with a bounded page size. The dashboard can refresh the feed periodically and should avoid exposing it to unauthenticated team clients.

Create a round record or equivalent monotonically increasing round id so each event can be grouped. Initialize a first round for existing databases during migration. Reset runs in one database transaction: increment/start the round, clear both teams' progress, timers, submissions, and wrong-attempt counts, append the round event, then commit.

### Server API and data flow

Add login, logout, session-check, dashboard-state, event-history, and authenticated new-round actions to the current HTTP server. Centralize session validation and require it before returning dashboard data or mutating a round. Existing public team state and answer APIs remain separate; their successful and unsuccessful transitions append event rows in the same transaction as the team-state update so the log cannot disagree with game state.

Dashboard polling returns only the two current team summaries and a bounded event page. Team endpoints continue to return only the selected team's state and unlocked clues. The login endpoint returns a generic authentication error and never echoes the configured password.

### Persistence and migration

Extend `initialize()` to create event, round, and session tables and migrate existing team databases without discarding progress. Existing databases gain an initial round association. Session tokens are transient and may be invalidated on server restart; teams' progress and event history persist as before.

## Error handling and security

- Reject login when no password is configured and reject incorrect credentials without revealing which part failed.
- Use constant-time password comparison and cryptographically random session tokens; store only token hashes.
- Expire sessions and invalidate them on logout.
- Check same-origin requests for authenticated state changes.
- Require an authenticated session for dashboard data, logs, logout, and new-round actions.
- Require explicit confirmation in the UI before resetting both teams.
- Execute a round reset and its event insertion atomically.
- Validate event pagination inputs and cap result size.
- Set no-store cache headers on authenticated API responses.
- Do not log passwords, cookies, or session tokens.

## Verification

Extend the existing Python HTTP tests to cover login success/failure, session-required dashboard access, logout/expiry, dashboard summaries for both teams, event creation for valid and invalid answers and final submissions, event retention after reset, and reset confirmation/authentication behavior. Run the complete Python test suite and `node --check public/app.js`. Review the rendered landing, login, and dashboard flows for desktop and mobile layouts.

## Out of scope

- Multiple mystery titles or separate game databases; “Game 1” and “Game 2” mean the current Team One and Team Two slots.
- Game master accounts, usernames, password recovery, or role management.
- Starting both team timers simultaneously.
- Exporting logs or building analytics/leaderboards.
- Changing clue content, answer rules, or the current team's investigation flow beyond navigation.
