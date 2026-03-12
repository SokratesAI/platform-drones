"""
daglig-prompelyd drone
Fetches a random fart sound from Freesound.org and posts it to Slack daily at 09:00 Oslo time.
No LLM. Pure automation. 💨
"""

import os
import sys
import random
import logging
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SLACK_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#daglige-prompelyder")
FREESOUND_API_KEY = os.environ["FREESOUND_API_KEY"]

FREESOUND_SEARCH_URL = (
    "https://freesound.org/apiv2/search/text/"
    "?query=fart&token={token}&fields=id,name,url,previews,description"
    "&page_size=50&filter=duration:[0.5 TO 8]&sort=random"
)

NORWEGIAN_INTROS = [
    "Dagens prompelyd er her! 🎺",
    "God morgen! Hør på denne perlen 💨",
    "Klar for en ny dag? Start med dette! 🌅",
    "Dagens musikalske innslag er servert 🎵",
    "En klassiker for en ny dag 🏆",
    "Dette er hva du har ventet på 👑",
    "Morgenens høydepunkt 🌟",
    "Kunstnerisk uttrykk, tidlig på dagen 🎨",
    "Musikk til sjelen 🎶",
    "Ingen dag er komplett uten dette 🌈",
]


def fetch_fart_sound() -> dict | None:
    url = FREESOUND_SEARCH_URL.format(token=FREESOUND_API_KEY)
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            log.error("No results from Freesound API")
            return None
        sound = random.choice(results)
        return {
            "name": sound.get("name", "Ukjent lyd"),
            "url": sound.get("url", ""),
            "preview_mp3": sound.get("previews", {}).get("preview-lq-mp3", ""),
        }
    except Exception as e:
        log.error("Freesound fetch failed: %s", e)
        return None


def build_blocks(sound: dict) -> list[dict]:
    intro = random.choice(NORWEGIAN_INTROS)
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "💨 Dagens Prompelyd", "emoji": True},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{intro}\n\n*{sound['name']}*"},
        },
    ]

    links = []
    if sound["url"]:
        links.append(f"<{sound['url']}|Åpne på Freesound.org>")
    if sound["preview_mp3"]:
        links.append(f"<{sound['preview_mp3']}|Last ned MP3-forhåndsvisning>")

    if links:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": " · ".join(links)},
        })

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "Posted by platform-drones/daglig-prompelyd · Powered by Freesound.org"}],
    })
    return blocks


def main():
    log.info("daglig-prompelyd starting")
    sound = fetch_fart_sound()

    if sound:
        blocks = build_blocks(sound)
        fallback_text = f"Dagens Prompelyd: {sound['name']} {sound['url']}"
    else:
        log.warning("Could not fetch sound, posting fallback message")
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "💨 Dagens Prompelyd", "emoji": True},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "Beklager, Freesound.org svarte ikke i dag. Prøv igjen i morgen! 🙏"},
            },
        ]
        fallback_text = "Dagens Prompelyd — ikke tilgjengelig i dag"

    client = WebClient(token=SLACK_TOKEN)
    try:
        client.chat_postMessage(
            channel=SLACK_CHANNEL,
            text=fallback_text,
            blocks=blocks,
        )
        log.info("Posted to %s", SLACK_CHANNEL)
    except SlackApiError as e:
        log.error("Slack post failed: %s", e.response["error"])
        sys.exit(1)


if __name__ == "__main__":
    main()
