# The Last Reunion Dinner

A restaurant murder mystery for two teams, inspired by escape-room gameplay. This is an independent game, not an official Mystery Manila product.

## Run

Requires Python 3.12+; no packages or build step needed.

```sh
cd /workspace/mystery_cfa
python3 server.py --port 3000
```

Serve the same application URL to both groups, with one selecting Team One and the other selecting Team Two. After selection, the URL identifies that team's portal (`?team=1` or `?team=2`), so refreshing reopens the same team's briefing or saved investigation. Devices selecting the same team share progress and timer. Each team's 30-minute clock starts when it starts the investigation, includes the opening discussion, survives refreshes/server restarts, and is enforced by the server. Answers are checked on the server without exposing future question answers in the browser. Each team may retry an incorrect final combination; each incorrect attempt deducts three minutes. For coordinated starts, have both teams press Start at the host's signal.

Provide the source newsletter/articles to players separately. The website uses the five exact questions supplied by the organizer. The staged timeline is guidance; clues unlock sequentially when solved. The final deduction accepts The Chef, Chef, or Sam; Poisoned Drink, Drink, or Wine; and Jealousy, without case sensitivity.

## Media and sound

The supplied MP4s are retained in `public/media`. Clue 2 includes the Waitress and Chef statements. Clue 4 includes the private-conversation clip and a still extracted from it. Clue 5 includes the Chief's statement. Written evidence remains available if a video cannot play. The restaurant backdrop is a still from the supplied waitress video. The cast image shown in chat was not available as a downloadable file; this version uses the supplied video assets.

Optional original suspense ambience is generated locally with Web Audio. The requested YouTube music is available through a user-activated player and external link. Playback depends on internet access, YouTube availability and browser policies. No YouTube audio is downloaded. External fonts have local fallbacks.

## Validate

```sh
python3 -m unittest discover -s tests -v
node --check public/app.js
```

## Hosting and a new round

Both groups must reach the same Python server. Static-only hosting will not run the game API. The server binds to `0.0.0.0` by default. Use your hosting provider's HTTPS ingress for public play; the environment onboarding UI does not provide a playable web preview.

Progress and activity events are stored in `.runtime/game.sqlite3`. The game master logs in from the landing page and can start a new round from the dashboard. Starting a new round permanently clears both teams' activity events, progress, saved answers and results, penalties, and timers. The default game master password is `game`; you can override it with `GAME_MASTER_PASSWORD` when starting the server:

```sh
GAME_MASTER_PASSWORD='choose-a-private-password' SESSION_COOKIE_SECURE=1 python3 server.py --port 3000
```

On PowerShell, configure the settings for the current terminal before launching:

```powershell
$env:GAME_MASTER_PASSWORD = 'choose-a-private-password'
$env:SESSION_COOKIE_SECURE = '1'
python server.py --port 3000
```

Open the game link and choose **Game master login**. The password form appears whenever you open game-master access. The dashboard shows both teams, their independent timers, progress, final accusations, separate timestamped activity logs, and the **Team access codes** section. Create a strong, different code for each team (at least 8 characters) and share each code only with that team. The dashboard shows whether a code is set but never shows its saved value. Replacing a code immediately signs that team out without changing its game progress. Players select their team and enter the code before the game loads. Ten incorrect attempts from one client for one team within 15 minutes trigger a five-minute lockout. Team sessions last eight hours and survive a server restart. Each team must use its own browser profile or device: tabs in the same browser profile share cookies, so entering both team codes in one profile gives that profile access to both teams. **Delete log** in a team column permanently clears only that team's events; its progress, answers, results, and timer remain unchanged. **Start new round** clears both teams after confirmation but keeps the team codes. Any authenticated team portal already open returns to the landing page automatically when a new round starts. Each team's timer starts when that team enters the investigation.

For local HTTP development only, set `SESSION_COOKIE_SECURE=0` so the browser will send the login cookie. Hosted use must run over HTTPS with `SESSION_COOKIE_SECURE=1`. Game master sessions expire after eight hours and are cleared when the server restarts. For security, set a private `GAME_MASTER_PASSWORD` when hosting publicly.

To preserve a copy of an earlier round, stop the server and back up its database before starting a new round. Alternatively, use a fresh database path for a separate event:

```sh
GAME_DB=.runtime/round-2.sqlite3 python3 server.py --port 3000
```

This is designed for a supervised event. Team codes prevent casual outsiders from joining and stop a Team One session from being used to act as Team Two. They remain shared secrets: a player can share their team's code or use an already authenticated device. Use strong, distinct codes and give them to teams privately; use HTTPS for hosted play. Game master access is password protected. Media URLs are not access controlled. There is no shared leaderboard or automatic winner declaration.
