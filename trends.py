"""
Optional: trend inspiration lookup.

This is intentionally a stub, not a working feature, because real trend data
(currently popular TikTok/YouTube sounds, formats, hashtags) requires a paid
third-party search or trends API — there's no free, reliable, ToS-safe way to
scrape that live. Wire in a provider you actually have a key for, e.g.:

  - https://serper.dev            (Google search API, has a free tier)
  - https://www.tikapi.io          (TikTok data API, paid)
  - YouTube Data API v3            (free quota, official, for YouTube only)

This function is NOT called anywhere in bot.py yet. To use it, add an
/trends command handler in bot.py that calls this and messages the result
back to the user. It only returns text ideas/descriptions — it never
downloads or reproduces anyone else's video content.
"""

import os
import requests  # add "requests" to requirements.txt if you wire this up


def search_trend_ideas(topic: str) -> str:
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        return (
            "Trend lookup isn't configured yet. Get a free API key from "
            "https://serper.dev, set SERPER_API_KEY as an environment variable "
            "on Render, and this will start returning real results."
        )

    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": f"trending {topic} TikTok format 2026"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    snippets = [r.get("snippet", "") for r in data.get("organic", [])[:5] if r.get("snippet")]
    if not snippets:
        return "No results found for that topic."
    return "Current trend chatter I found:\n\n" + "\n\n".join(f"• {s}" for s in snippets)
