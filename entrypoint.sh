#!/bin/bash
set -e

if [ -n "$TG_API_ID" ] && [ -n "$TG_API_HASH" ]; then
  echo "TG_API_ID/TG_API_HASH found — starting local Bot API server (20MB limit removed, up to 2000MB)..."
  mkdir -p /tmp/tg-bot-api
  telegram-bot-api --local --api-id="$TG_API_ID" --api-hash="$TG_API_HASH" \
    --http-port=8081 --dir=/tmp/tg-bot-api &
  # Give it a moment to come up before the bot tries to connect.
  sleep 3
else
  echo "No TG_API_ID/TG_API_HASH set — using Telegram's normal cloud API (20MB file limit applies)."
fi

exec python bot.py
