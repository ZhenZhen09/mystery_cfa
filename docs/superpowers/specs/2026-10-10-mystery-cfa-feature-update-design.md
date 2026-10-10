# Mystery CFA Feature Update Design

## Goal

Update the existing two-team mystery game with the requested clue content, team-separated game-master activity logs, clear round resets with live team redirects, persistent final-answer display, and timer/victory presentation improvements.

## Constraints and decisions

- Keep the Python standard-library server, SQLite database, and current single-page frontend; add no runtime dependencies.
- A new round permanently removes Team One and Team Two event rows, resets their stored investigation state, and records a fresh round-start event. Old team activity is not archived.
- An open team briefing or investigation detects a changed round ID through the existing polling pattern and returns to the landing screen without a document reload.
- A wrong final accusation remains retryable after its penalty. The submitted values stay visible in disabled fields until the team deliberately chooses to enter another accusation.
- Honor `prefers-reduced-motion` for countdown and victory effects.

## Existing system

The dependency-free Python server stores two team rows, rounds, game-master sessions, and game events in SQLite. Team clients poll `/api/state` while investigating, and the game-master screen polls the dashboard and a shared event feed. The frontend is a single `public/app.js` file with styles in `public/style.css`. Team state currently stores the successful final submission but not the latest failed attempt. The new-round route resets team rows and preserves all events.

## Design

### Server state and round reset

Extend the team table migration with a nullable JSON `last_attempt` column. Every final accusation stores its submitted killer, weapon, and motive there in the same transaction as its event row and penalty/result update. `/api/state` returns the active `round_id` and latest final attempt. Add an optional validated `team` filter to the authenticated event endpoint so the dashboard can page each team's events independently.

When the game master starts a new round, perform one transaction that marks the prior round inactive, creates the next active round, deletes all team-associated event rows, clears both teams' start time, progress, successful submission, last attempt, completion time, and penalty count, then records the new round-start event. Keep non-team round-control events outside the team activity columns. This explicitly implements permanent deletion of old team logs.

### Team portal refresh behavior

Include `round_id` in every team state response. While a team is in its briefing or investigation, poll state and compare its round ID with the ID captured on entry. If it changes, stop audio, clear selected clue and local final-form state, show the landing page with a short “new round is ready” notice, and do not reload the document. Keep the existing independent timer-start behavior for each team.

### Game-master activity columns

Replace the shared event feed with two labeled, responsive columns: Team One Activity and Team Two Activity. Load and paginate each team's newest-first events independently, preserving the existing event details and correctness markers. Use two columns on wider screens and stack them on narrow screens.

### Clue media and briefing copy

- Remove the paragraph beginning “But old relationships, jealousy...” and the complete investigation timeline from the team briefing. Keep the first introductory paragraph, source-article guidance, and start/back actions.
- Copy the supplied Chief video to `public/media/chief.mp4`.
- Clue 2 displays the Waitress statement video and the existing Chef statement video (`intro.mp4`).
- Clue 5 displays the supplied Chief video in place of the previous Chef video. Keep the existing clue text and other evidence intact.

### Final accusation behavior

Accept `poison drink`, in addition to existing weapon aliases, using the existing case-insensitive normalization. After submitting a combination, show all three submitted values in disabled controls. A wrong combination exposes a clear retry action; choosing it clears and re-enables the fields while retaining the previous attempt in the server log. A completed case keeps the final submitted values visible in disabled controls on the result screen.

### Timer suspense and victory

Update a page-level suspense value from remaining time so timer text and selected page accents transition smoothly from the current gold/neutral palette toward orange and then red. Add a restrained pulse only in the critical time range. On a correct solve, show an animated “YOU WON!” line above “You Uncovered the Truth,” with a lightweight CSS confetti celebration. Use CSS only and disable nonessential motion when the user requests reduced motion.

## Error handling and data safety

- If state polling fails, keep the current game screen and its existing connection warning; redirect only after a valid response reports a different round ID.
- Validate the optional team event filter as 1 or 2 and continue requiring game-master authentication.
- Keep reset, event deletion, team clearing, and creation of the next round atomic.
- Escape event and accusation values before rendering them.
- Serve the copied video as a static asset; preserve the existing media controls and pause background audio when evidence video starts.

## Verification

- Extend `tests/test_game.py` for the new answer alias, latest-attempt persistence, filtered event paging, permanent deletion of team logs on reset, round ID responses, and cleared team state.
- Run the full Python unit suite and `node --check public/app.js`.
- Manually verify the two responsive activity columns, clue 2/5 videos, briefing content, locked final values and retry action, timer color changes, reduced-motion behavior, victory confetti, and a second browser team's live redirect after a new round.

## Out of scope

- Adding accounts, a second game database, external animation libraries, or an archive browser for deleted team events.
- Changing the question answers, clue sequence, wrong-answer penalty duration, or independent team timers.
