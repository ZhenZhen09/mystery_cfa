# Firebase-ready Mystery CFA design

## Goal

Prepare the existing two-team Mystery CFA game for deployment through Firebase Hosting, Cloud Run, and Cloud Firestore while preserving its current interface and local/Render SQLite workflow. The deployed game must keep team state, game-master sessions, access codes, login throttling, round state, and activity logs across Cloud Run restarts and instances.

## Current application

- `server.py` is a dependency-free Python HTTP server that serves `public/` and implements all `/api/*` routes.
- SQLite is accessed directly throughout the HTTP handlers. The current SQL transaction boundaries protect coupled state changes and event writes.
- `public/app.js` uses same-origin `fetch` calls and polls team state and the game-master dashboard; it does not require a persistent socket.
- The local game and Render deployment use SQLite. A Firebase deployment cannot rely on a Cloud Run container's local filesystem for durable state.

## Selected architecture

Use Firebase Hosting for the existing static website and media, route `/api/**` to a Python container on Cloud Run, and use Firestore as the durable store for the Cloud Run backend. Hosting and the backend share the public origin, so the current same-origin API calls and secure session cookies remain applicable. The Cloud Run service will use Application Default Credentials through its attached Google service identity; no service-account JSON key is committed or embedded in the app.

The Python backend will select its persistence implementation through configuration. SQLite remains the default for local development and Render. Firestore is selected explicitly in the Cloud Run configuration. Both implementations must expose the same game operations and response shapes so the browser interface remains unchanged.

## Firestore records and operations

- Keep a singleton game metadata document for the active round and a monotonic event sequence.
- Store each team's current round state in a team document, including timer timestamps, clue progress, last attempt, final submission, and wrong-attempt count.
- Store team access-code hash/salt/iteration metadata and the currently revealable code in a team-code document; store game-master and team session token hashes with expiration timestamps in separate session collections.
- Store login throttling state under a team/client key.
- Store activity events in a collection ordered by their monotonic numeric ID, preserving the existing API event shape and pagination behavior.
- Use Firestore transactions for state transitions that also create events: team start, clue answer, final accusation, access-code replacement, and new round. Keep authorization checks on the server.
- Delete team activity log records in bounded Firestore batches. A new round clears team progress, answers, results, penalties, and team activity events while retaining access codes, matching current behavior.
- Build team state and dashboard payloads from Firestore documents using the existing `state()` rules, including server-derived timer remaining, answer acceptance, result reveal, and automatic portal reset when the round ID changes.

## Deployment files and configuration

- Add a container definition for the existing Python server, binding to `0.0.0.0` and the `PORT` supplied by Cloud Run.
- Add the minimal Python runtime dependency for Firestore/Firebase Admin SDK.
- Add Firebase Hosting configuration to serve `public/` and rewrite `/api/**` to the named Cloud Run service and selected region. The service name and Firebase project ID are documented deployment inputs, not credentials.
- Document Firebase project setup, Firestore creation, Cloud Run service identity/IAM, Hosting rewrite target, required secrets/environment variables, and deploy order.
- Do not add Firebase client SDKs or expose Firestore to browsers. All game reads and writes continue through authenticated Python API routes.
- Do not remove Render configuration or change its SQLite behavior.

## Data migration

The first Firebase deployment will start with an empty Firestore game state. Existing SQLite files are not uploaded automatically. If preserving an in-progress or historical local game becomes necessary, that will be a separate explicit migration step; the implementation must not silently copy or delete local databases.

## Security and operational behavior

- Store only hashed session tokens and PBKDF2 team-code hashes for authentication. The revealable team code remains protected behind the game-master session, as in the current feature.
- Keep the game-master password in Cloud Run secrets/environment configuration, not in source or Firebase Hosting assets.
- Enforce HTTPS secure cookies in the hosted configuration. The API remains same-origin under Firebase Hosting rewrites.
- Ensure concurrent requests cannot both consume the same clue state or lose wrong-attempt penalties; Firestore transaction conflicts must retry safely without duplicating events.
- Keep static media behavior and existing clue video/audio paths unchanged.

## Verification criteria

- Existing SQLite test suite continues to pass without requiring Firebase credentials.
- Firestore implementation is exercised against the Firestore emulator for login, code replacement/revocation, answer progression, final-answer penalties, event pagination/deletion, new-round reset, and concurrent state updates.
- Verify Cloud Run startup honors `PORT`, serves health checks, and has no dependency on writable local storage.
- Verify Firebase Hosting serves `/`, static media, and the existing same-origin `/api/*` routes through the Cloud Run rewrite.
- Verify Render/local startup still uses SQLite when Firestore mode is not selected.

## Alternatives considered

1. **Firebase Hosting + Cloud Run + Firestore (selected):** Keeps the current Python backend and same-origin website while giving the game durable shared state.
2. **Cloud Run serves both UI and API + Firestore:** Slightly fewer Firebase configuration files, but does not use Firebase Hosting's static CDN and hosting workflow.
3. **Vercel Python Functions + Firestore:** Requires reshaping the long-lived HTTP server into function handlers and still requires an external persistent store; it is less aligned with the current app.

## Out of scope

- Rewriting the game backend in JavaScript/TypeScript or Firebase Functions.
- Migrating current SQLite data automatically.
- Changing UI, game rules, answer validation, team authentication, or media assets.
- Making Firestore directly accessible from browser code.
