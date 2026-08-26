# VC Music Userbot — GitHub Actions Edition

A Telegram voice-chat music bot built with Pyrogram, Py-TgCalls, MongoDB Atlas, and Redis — designed to run on **GitHub Actions** as its hosting platform, using a self-chaining workflow pattern to work around the 6-hour job runtime limit.

## ⚠️ Read this first: what "GitHub Actions hosting" actually means here

GitHub Actions jobs are hard-killed at 6 hours. There is no way around that ceiling — so this project **chains** workflow runs together instead:

1. The bot monitors its own elapsed runtime.
2. ~15 minutes before the 6h limit, it snapshots all active voice chats and queues to Redis, then triggers a fresh workflow run via the GitHub API.
3. The new run loads that snapshot and rejoins/resumes automatically.
4. A separate **watchdog** workflow checks every 10 minutes that a run is actually alive, and recovers if the chain ever breaks.

**Important:** rejoining a voice chat from a new process means a few seconds of audio interruption on every handoff — there's no way to hand off a live audio socket between two separate container processes. This gets you the closest realistic version of "24/7 on Actions," not literally gapless audio.

## What this bot can actually play

This bot plays:
- **Direct audio URLs** (any publicly reachable audio file/stream you have the right to play)
- **Local files** you've added to the music library

It does **not** include YouTube, SoundCloud, JioSaavn, Apple Music, or Deezer audio extraction — those require bypassing each platform's access controls, which isn't something this project implements. Spotify is integrated for **metadata only** (search, track info, recommendations) via Spotify's official Web API — Spotify doesn't offer third-party streaming access either, so search results need to be paired with a direct URL/local file to actually play.

Want more sources? The audio system is a plugin interface (`app/services/audio_source_base.py`) — drop in your own resolver and register it in `app/services/source_registry.py` without touching anything else.

## Project Structure

```
app/
  core/         # config, logging
  db/           # MongoDB models, repositories, Redis client
  services/     # queue engine, voice player, assistant pool,
                # workflow chainer, audio sources, recommendations
  bot/handlers/ # Pyrogram command handlers
  dashboard/    # FastAPI backend + React frontend
.github/workflows/
  runner.yml      # the bot itself, self-chaining
  watchdog.yml    # recovery if chaining fails
  ci.yml          # tests + lint
  backup.yml      # scheduled MongoDB backup
  security-scan.yml
docker/         # Dockerfile + compose (for local dev / non-Actions hosting)
k8s/            # Kubernetes manifests (alternative deployment target)
scripts/        # session string generator, backup script
tests/          # pytest unit tests
```

## Dashboard features

The web dashboard (`app/dashboard/`) gives you live visibility into the bot:

- **Overview** — active voice chat count, songs played (24h), total groups/users, 7-day active-user trend
- **Active Voice Chats** — which chats are streaming right now and which assistant is handling each
- **Connected Groups** — every group the bot has been used in, join date, current status, and a drill-down into that group's full play history (song, artist, time, who requested it)
- **Assistants** — health of each assistant account: online/offline, active call count, error count, last heartbeat
- **Top Tracks** — most-played tracks across all groups
- **Live Logs** — real-time log stream (WebSocket) with level filtering, backed by a capped Redis list so it works across the dashboard's separate process
- **Broadcast** — send a message to all groups, all users, or both, from the web UI (queues a job picked up by the running bot process) — also available as a DM-only `/broadcast` bot command

Login is via one-time code: DM the bot `/dashboardlogin`, then enter your Telegram user ID + the code on the login screen. Only the configured `OWNER_ID`/`SUDO_USERS` can log in.

## Setup

### 1. Get Telegram credentials
- API ID/hash: https://my.telegram.org
- Bot token: message [@BotFather](https://t.me/BotFather)
- Assistant session string(s): `python scripts/generate_session.py` (run locally, not in CI)

### 2. Get a MongoDB Atlas cluster and a Redis instance
Any managed free tier works for testing (MongoDB Atlas free tier, Upstash/Redis Cloud free tier).

### 3. (Optional) Spotify metadata
Create an app at https://developer.spotify.com/dashboard for `SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET`.

### 4. Configure secrets
Copy `.env.example` to `.env` for local testing. For GitHub Actions, add the same values as **repository secrets** (Settings → Secrets and variables → Actions). You'll also need a **Personal Access Token** with `repo` scope saved as `CHAIN_PAT` — the default `GITHUB_TOKEN` cannot trigger `repository_dispatch` events.

### 5. Push to GitHub
The workflows in `.github/workflows/` activate automatically once secrets are configured. `runner.yml` starts on its cron schedule, on manual dispatch, or via the chain.

## Running locally (recommended for development)

```bash
pip install -r requirements.txt --break-system-packages
cp .env.example .env   # fill in real values
python -m app.main
```

## Running the dashboard

```bash
# backend
uvicorn app.dashboard.backend.main:app --reload

# frontend
cd app/dashboard/frontend
npm install
npm run dev
```

Log in by DMing the bot `/dashboardlogin` to get a one-time code.

## Docker / Kubernetes (better long-term hosting options)

If you later move off Actions-as-host (recommended for production), the included `docker/` and `k8s/` configs deploy the exact same codebase to a persistent host with zero audio-gap restarts. GitHub Actions (`ci.yml`-style) then becomes pure CI/CD: test → build image → deploy — its intended role.

## Testing

```bash
pytest tests/ -v
```
