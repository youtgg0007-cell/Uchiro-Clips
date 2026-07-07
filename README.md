# Uchiro Clips — Telegram Bot

Send it a video, it auto-cuts highlight clips (real ffmpeg audio-loudness +
scene-cut analysis, not a browser hack), exports for TikTok/YouTube/Square,
mixes in music you upload, and tags highlights — no watermark, ever.

**What this bot does NOT do, on purpose:** download other people's
TikTok/YouTube videos, strip their watermarks, or auto-follow accounts. That's
a copyright/ToS issue no matter what interface wraps it, so it's intentionally
left out.

## Deploy on Render (free)

1. Push this folder to a new GitHub repo (`bot.py`, `requirements.txt`,
   `Dockerfile`, `entrypoint.sh`, `README.md`).
2. Go to [render.com](https://render.com) → New → Web Service → connect your repo.
3. Environment: **Docker** (Render will detect the Dockerfile automatically).
4. Instance type: **Free**.
5. Add environment variable:
   - `BOT_TOKEN` = the token you got from @BotFather
   (Render automatically provides `RENDER_EXTERNAL_URL` and `PORT`.)
6. Deploy. First deploy takes a few minutes (installing ffmpeg + Python deps).
7. Once it's live, message your bot on Telegram with `/start`.

## Supporting long/large videos (important for teams)

By default, Telegram's bots can only download files up to **20MB** — this is
a Telegram platform limit, not a bug in this code, and it will hit long videos
constantly. To remove it (up to 2000MB), run Telegram's official local Bot API
server alongside the bot. This repo already has it wired up — you just need
two more environment variables:

1. Go to https://my.telegram.org/apps and log in with your own phone number
   (this is free, one-time, and standard practice for this — it's not tied to
   your bot account, just used to register an "app" for the API server).
2. Create an app, copy the **api_id** and **api_hash** it gives you.
3. In Render, add two more environment variables:
   - `TG_API_ID` = your api_id
   - `TG_API_HASH` = your api_hash
4. Redeploy. The logs should show "Using local Bot API server — file size
   limit raised to 2000MB."

Without these two variables, the bot still works fine, just capped at 20MB
per video (Telegram's default).

**Heads up on free-tier limits with large videos:** Render's free instance has
512MB RAM and shared CPU. A 2000MB video will take real time and memory to
download, analyze, and re-encode with ffmpeg — it may be slow, and very large
files could still fail or time out on the free tier. If your team is
regularly working with long/large videos, budget for Render's paid Starter
tier ($7/mo, more RAM/CPU) once this is more than a test.

## Free tier reality check (so there are no surprises)

- **It sleeps after ~15 minutes of no traffic**, and the next message takes
  30–60 seconds to wake it up. That's normal for Render's free tier — the bot
  isn't broken, it's just cold-starting.
- **512MB RAM** on the free instance. Fine for short clips (a few minutes of
  video); very large/long files may fail or run slowly. If this becomes a real
  product for your team, Render's $7/mo Starter plan removes the sleep and
  gives more headroom — worth it once you have real users.
- Every video is processed one at a time, in a temp folder, and deleted after
  the clips are sent back — nothing is stored long-term.

## Adding music matching, trends, more presets, etc.

`bot.py` is a straightforward starting point, not a finished product — it's
built to be extended. `trends.py` has a stub for trend-inspiration lookups
(needs your own API key, see the comments in that file). If you want help
adding features (better highlight scoring, batch export, a web dashboard for
your team, etc.), just ask.
