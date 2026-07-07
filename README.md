# Uchiro Clips — Telegram Bot

Send it a video, it auto-cuts highlight clips (real ffmpeg audio-loudness +
scene-cut analysis, not a browser hack), exports for TikTok/YouTube/Square,
mixes in music you upload, and tags highlights — no watermark, ever.

**What this bot does NOT do, on purpose:** download other people's
TikTok/YouTube videos, strip their watermarks, or auto-follow accounts. That's
a copyright/ToS issue no matter what interface wraps it, so it's intentionally
left out.

## Deploy on Render (free)

1. Push this folder to a new GitHub repo (just these 4 files: `bot.py`,
   `requirements.txt`, `Dockerfile`, `README.md`).
2. Go to [render.com](https://render.com) → New → Web Service → connect your repo.
3. Environment: **Docker** (Render will detect the Dockerfile automatically).
4. Instance type: **Free**.
5. Add one environment variable:
   - `BOT_TOKEN` = the token you got from @BotFather
   (Render automatically provides `RENDER_EXTERNAL_URL` and `PORT` — the bot
   uses those automatically, you don't need to set them.)
6. Deploy. First deploy takes a few minutes (installing ffmpeg + Python deps).
7. Once it's live, message your bot on Telegram with `/start`.

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
