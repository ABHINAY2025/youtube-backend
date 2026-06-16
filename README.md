---
title: devX Video Downloader
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# devX · Video Downloader

Paste a link → pick a quality → download. React frontend + Flask/yt-dlp
backend, MongoDB for accounts and download limits. Built to deploy as a
**Hugging Face Docker Space**.

> For personal & authorized use only. Respect YouTube's Terms of Service
> and copyright law.

## Features

- Paste a link, see title/thumbnail/qualities, download in the chosen quality
- ffmpeg-merged HD (1080p+) and MP3 audio extraction
- Animated devX-branded UI with a live download progress bar
- **Access tiers**
  - **Anonymous:** 2 free downloads per browser/device
  - **Registered (public):** 2 downloads per day
  - **Admin:** unlimited

## Architecture

```
frontend/   React (Vite) — built to static files
backend/    Flask API + yt-dlp + MongoDB; also serves the built frontend
Dockerfile  multi-stage: build React, then run Flask via gunicorn on :7860
```

State lives in **MongoDB Atlas** (collections `ytdl_users`, `ytdl_usage`),
so the Space's ephemeral disk is only used for in-flight downloads.

## Environment variables (set as HF Space *Secrets*)

| Key | Required | Default | Notes |
|-----|----------|---------|-------|
| `MONGO_URI` | ✅ | — | MongoDB Atlas connection string |
| `JWT_SECRET` | ✅ | — | long random string |
| `ADMIN_USERNAME` | | `admin` | seeded on first boot |
| `ADMIN_PASSWORD` | | `admin123` | **change this** |
| `ANON_LIMIT` | | `2` | free downloads per device |
| `USER_DAILY_LIMIT` | | `2` | per registered account/day |
| `YTDLP_PROXY` | | — | residential proxy (see scaling) |
| `YTDLP_COOKIES` | | — | path to cookies.txt |

## Deploy to Hugging Face Spaces

1. Create a new **Space** → SDK: **Docker**.
2. Push this repo to the Space (git remote), or upload the files.
3. In **Settings → Variables and secrets**, add `MONGO_URI` and `JWT_SECRET`
   (and override `ADMIN_PASSWORD`).
4. The Space builds the Dockerfile and serves on port 7860 automatically.

Default admin login: `admin` / `admin123` — **change the password.**

## Run locally

Backend:
```bash
cd backend
python -m venv venv && source venv/Scripts/activate   # Windows
pip install -r requirements.txt
cp .env.example .env   # fill in MONGO_URI + JWT_SECRET
python app.py          # http://localhost:7860
```

Frontend (dev, hot reload, proxies /api to :7860):
```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Production build served by Flask:
```bash
cd frontend && npm run build
cp -r dist ../backend/static_frontend
```

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
```

Covers the core access rules: anonymous capped at 2 then blocked, admin unlimited.

## ⚠️ Will YouTube block this with more users?

**Yes — this is the main operational risk.** Every download goes out
through the Space's single datacenter IP, which YouTube rate-limits and
flags aggressively (`HTTP 429`, "Sign in to confirm you're not a bot").
It works fine for personal/low traffic; for a public service you'll need:

1. **Rotating residential proxies** — set `YTDLP_PROXY`. This is the real
   fix and the main cost behind any subscription model.
2. **Rotating disposable Google-account cookies** — set `YTDLP_COOKIES`.
3. A **download queue + per-user rate limits** (the tier system here is
   the first step).

Keep yt-dlp current — `pip install -U yt-dlp` — as YouTube changes often.
