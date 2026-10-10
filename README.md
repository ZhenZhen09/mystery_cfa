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

## Deploy with Render and Firestore (free tier)

This is the recommended deployment for the current Render setup. One Render web service serves both the website and its `/api/*` endpoints from the same origin; Firestore stores all hosted game state. The app does not use Render's local filesystem for persistent game data. Local runs continue to use SQLite unless `DATA_BACKEND=firestore` is set.

Render free web services can sleep after 15 minutes without requests. The first request after sleep may take about a minute to wake. Free instances have an ephemeral filesystem and can restart, so do not use SQLite for the hosted service. Firestore preserves game state through these restarts. Review current Render and Firebase usage/billing in their dashboards.

### 1. Confirm Firebase project and Firestore

1. In [Firebase Console](https://console.firebase.google.com/), open project **cfamystery** (Project ID `cfamystery`).
2. Open **Build → Firestore Database**. Create a database in **Native mode** if one does not already exist. The existing database location can be retained; this Render deployment does not require Cloud Run to be in the same region.

### 2. Create a service account key for Render

Render is outside Google Cloud, so the Python Firestore client needs a credential file. Create a dedicated service account in Google Cloud Console:

1. Open **IAM & Admin → Service Accounts** in project `cfamystery` and choose **Create service account**.
2. Name it `render-firestore-runtime`.
3. Grant it the **Cloud Datastore User** role (`roles/datastore.user`) so it can read and write the game documents.
4. Open that service account, choose **Keys → Add key → Create new key → JSON**, and download the JSON key. Keep it private. Do not upload it to GitHub, put it in `public/`, or paste it into a normal environment variable. If Google Cloud blocks service-account key creation through an organization policy, use a Google-hosted runtime such as Cloud Run instead.

### 3. Create the Render web service

1. Push the project to GitHub, including `render.yaml`, `requirements.txt`, `server.py`, `firestore_store.py`, `game_rules.py`, and `public/`.
2. In Render, choose **New → Blueprint**, connect `ZhenZhen09/mystery_cfa`, and select branch `main`.
3. Review the Blueprint service `cfamystery` and create it on the **Free** plan. Enter a private value when Render asks for `GAME_MASTER_PASSWORD`.
4. In the new Render service, open **Environment → Secret Files → Add Secret File**. Set the filename to `firebase-service-account.json` and upload/paste the contents of the JSON key. Save it. The service configuration points `GOOGLE_APPLICATION_CREDENTIALS` to `/etc/secrets/firebase-service-account.json`.
5. Confirm these environment settings are present: `DATA_BACKEND=firestore`, `GOOGLE_CLOUD_PROJECT=cfamystery`, `GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/firebase-service-account.json`, and `SESSION_COOKIE_SECURE=1`. `GAME_MASTER_PASSWORD` must also be set as a secret environment variable.
6. Save changes and wait for Render to finish deploying. The build command is `pip install -r requirements.txt`; the start command uses Render's assigned `$PORT`; the health check is `/healthz`.

### 4. Check the service and configure the game

1. Open the Render service's `onrender.com` URL with `/healthz` appended. It should return `ok: true` and `backend: firestore`.
2. Open the service URL without `/healthz`, log in to Game Master, and set separate access codes for Team 1 and Team 2.
3. Have each team open the Render URL on a separate device or browser profile and enter its own code. Start a round and check the Game Master activity dashboard.

Render's Firebase Admin setup uses Application Default Credentials, which reads the file path in `GOOGLE_APPLICATION_CREDENTIALS`. The browser never receives this service-account key and never connects directly to Firestore. Revoke the key in Google Cloud IAM if it is ever exposed.

## Alternative: Firebase Hosting, Cloud Run, and Firestore

This separate deployment uses Firebase Hosting for the website, Cloud Run for the Python API, and Firestore for game data. It starts with a fresh game; local `.runtime/game.sqlite3` data is not uploaded. Use this path only if you want the app hosted on Firebase/Cloud Run instead of the Render URL. Its `/api/**` rewrite is not used by the Render deployment.

The commands below use the Singapore region `asia-southeast1`. Keep Firestore and Cloud Run in the same region. Firestore's database location cannot be changed after creation.

### 1. Create the Firebase project and Firestore database

1. Open the [Firebase Console](https://console.firebase.google.com/) and create a project. Save its **Project ID**; this is different from the display name.
2. In Firebase Console, choose **Build → Firestore Database → Create database**. Choose **Native mode** and location **asia-southeast1 (Singapore)**.
3. Link a Google Cloud billing account to the project. Cloud Run requires billing to be enabled; usage may fall within Google's no-cost allowances, but charges can apply for compute, network traffic, builds, and other services.
4. Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) and [Firebase CLI](https://firebase.google.com/docs/cli). In PowerShell:

   ```powershell
   npm install -g firebase-tools
   gcloud init
   firebase login
   ```

5. Set the project ID for the commands in this guide:

   ```powershell
   $projectId = 'YOUR_FIREBASE_PROJECT_ID'
   gcloud config set project $projectId
   ```

### 2. Enable the Google Cloud services

In the same PowerShell window, run:

```powershell
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com firestore.googleapis.com --project $projectId
```

### 3. Give Cloud Run a Firestore service identity

Create a service identity for the game backend and grant it access to Firestore:

```powershell
$runtimeAccount = "cfamystery-runtime@$projectId.iam.gserviceaccount.com"
gcloud iam service-accounts create cfamystery-runtime --display-name "Mystery CFA Cloud Run service" --project $projectId
gcloud projects add-iam-policy-binding $projectId --member "serviceAccount:$runtimeAccount" --role roles/datastore.user
```

The app uses Cloud Run's attached identity. **Do not create or download a service-account JSON key.**

### 4. Store the Game Master password as a secret

In [Google Cloud Secret Manager](https://console.cloud.google.com/security/secret-manager), select your project and create a secret named `game-master-password`. Enter a strong password that is different from the local default `game`.

Allow the Cloud Run service identity to read this secret:

```powershell
gcloud secrets add-iam-policy-binding game-master-password --member "serviceAccount:$runtimeAccount" --role roles/secretmanager.secretAccessor --project $projectId
```

### 5. Deploy the Python API to Cloud Run

In PowerShell, change to the repository root (the folder containing `server.py`, `Dockerfile`, and `firebase.json`), then deploy:

```powershell
gcloud run deploy cfamystery-api `
  --source . `
  --region asia-southeast1 `
  --project $projectId `
  --service-account $runtimeAccount `
  --allow-unauthenticated `
  --port 8080 `
  --set-env-vars "DATA_BACKEND=firestore,GOOGLE_CLOUD_PROJECT=$projectId,SESSION_COOKIE_SECURE=1" `
  --set-secrets "GAME_MASTER_PASSWORD=game-master-password:latest"
```

Unauthenticated Cloud Run invocation is needed so Firebase Hosting can forward team and game-master login requests. The game API still checks team access codes, game-master password, and authenticated session cookies.

When the deployment finishes, verify the Cloud Run service is healthy. The URL is shown by `gcloud run deploy`; you can also retrieve it with:

```powershell
$serviceUrl = gcloud run services describe cfamystery-api --region asia-southeast1 --project $projectId --format="value(status.url)"
Invoke-RestMethod "$serviceUrl/healthz"
```

The response should include `ok: true` and `backend: firestore`.

### 6. Select your Firebase project for Hosting

From the repository root, run:

```powershell
firebase use --add
```

Select the project created in Step 1 and use the alias `default`. This creates `.firebaserc` for your local checkout. The checked-in `firebase.json` already points Hosting at `public/`, rewrites `/api/**` to Cloud Run service `cfamystery-api` in `asia-southeast1`, and includes the Firestore index definition. If you deploy Cloud Run to another region or use a different service name, update the matching rewrite in `firebase.json` first.

Deploy the Firestore index and Hosting site:

```powershell
firebase deploy --only firestore:indexes,hosting
```

Firebase prints the Hosting URL, usually `https://YOUR_PROJECT_ID.web.app`. The Cloud Run service must exist before deploying the Hosting rewrite.

### 7. Configure and try the game

1. Open the Firebase Hosting URL and choose **Game master login**.
2. Sign in using the password stored in Secret Manager.
3. Open **Team access codes**, set a different code for each team, and share each code privately.
4. Open the Hosting URL in separate browser profiles/devices for Team One and Team Two. Enter the matching team code.
5. Start each team's investigation. The game-master dashboard should show progress, timers, and activity logs as the teams play.
6. Start a new round from the dashboard to confirm the teams reset and their portals return to team selection.

The website's static assets and media are public URLs as they are in the current app. Team codes protect access to game APIs; they do not restrict direct access to the clue media files.

The browser never connects directly to Firestore. The Python service uses its Cloud Run identity and Firebase Admin server credentials, which bypass Firestore Security Rules; do not add open database rules or put service credentials in `public/`.

This is designed for a supervised event. Team codes prevent casual outsiders from joining and stop a Team One session from being used to act as Team Two. They remain shared secrets: a player can share their team's code or use an already authenticated device. Use strong, distinct codes and give them to teams privately; use HTTPS for hosted play. Game master access is password protected. Media URLs are not access controlled. There is no shared leaderboard or automatic winner declaration.
