# The Last Reunion Dinner

A restaurant murder mystery for two teams, inspired by escape-room gameplay. This is an independent game, not an official Mystery Manila product.

## Run

Requires Python 3.12+; no packages or build step needed.

```sh
cd /workspace/mystery_cfa
python3 server.py --port 3000
```

Serve the same application URL to both groups, with one selecting Team One and the other selecting Team Two. Devices selecting the same team share progress and timer. Each team's 30-minute clock starts when it starts the investigation, includes the opening discussion, survives refreshes/server restarts, and is enforced by the server. Answers are checked on the server without exposing future question answers in the browser. Each team has one final submission. For coordinated starts, have both teams press Start at the host's signal.

Provide the source newsletter/articles to players separately. The website uses the five exact questions supplied by the organizer. The staged timeline is guidance; clues unlock sequentially when solved. The final deduction requires The Chef (or Chef), Poisoned Drink, and Jealousy, without case sensitivity.

## Media and sound

The three supplied MP4s are retained in `public/media`. The first is a Chef statement and is withheld until Clue 4 because it contains relationship spoilers. Clue 4 also includes the private-conversation clip and a still extracted from it. Clue 5 includes the waitress confession. Written evidence remains available if a video cannot play. The restaurant backdrop is a still from the supplied waitress video. The cast image shown in chat was not available as a downloadable file; this version uses the supplied video assets.

Optional original suspense ambience is generated locally with Web Audio. The requested YouTube music is available through a user-activated player and external link. Playback depends on internet access, YouTube availability and browser policies. No YouTube audio is downloaded. External fonts have local fallbacks.

## Validate

```sh
python3 -m unittest discover -s tests -v
node --check public/app.js
```

## Hosting and a new round

Both groups must reach the same Python server. Static-only hosting will not run the game API. The server binds to `0.0.0.0` by default. Use your hosting provider's HTTPS ingress for public play; the environment onboarding UI does not provide a playable web preview.

Progress is stored in the ignored `.runtime/game.sqlite3`. For a new round, stop the server and choose a fresh database path, preserving the previous round:

```sh
GAME_DB=.runtime/round-2.sqlite3 python3 server.py --port 3000
```

This is designed for a supervised event: the two slots are shared, not password protected. Anyone with the URL can select either team; assign one lead device per team. Media URLs are not access controlled. A production competition requiring private team accounts or protected evidence needs further authentication. There is no shared leaderboard or automatic winner declaration.
