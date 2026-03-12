"""
daily-digest drone
Fetches top AI + Kubernetes stories from HackerNews, Kubernetes blog, and CNCF blog.
Posts a single Slack digest message at 08:00 UTC daily.
No LLM. Pure automation.
"""

import os
import sys
import logging
import requests
import feedparser
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SLACK_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#digest")

HN_AI_URL = "http://hn.algolia.com/api/v1/search?tags=story&query=AI&hitsPerPage=5"
HN_K8S_URL = "http://hn.algolia.com/api/v1/search?tags=story&query=kubernetes&hitsPerPage=5"
K8S_BLOG_URL = "https://kubernetes.io/feed.xml"
CNCF_BLOG_URL = "https://www.cncf.io/feed/"


def fetch_hn(url: str, label: str) -> list[dict]:
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        hits = r.json().get("hits", [])
        return [{"title": h.get("title", "No title"), "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"} for h in hits[:5]]
    except Exception as e:
        log.error("HN fetch failed (%s): %s", label, e)
        return []


def fetch_rss(url: str, label: str, limit: int = 5) -> list[dict]:
    try:
        feed = feedparser.parse(url)
        entries = feed.entries[:limit]
        return [{"title": e.get("title", "No title"), "url": e.get("link", "")} for e in entries]
    except Exception as e:
        log.error("RSS fetch failed (%s): %s", label, e)
        return []


def section_block(title: str, items: list[dict]) -> list[dict]:
    if not items:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*\n_No items fetched._"}}]

    lines = "\n".join(f"• <{item['url']}|{item['title']}>" for item in items)
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*\n{lines}"}},
        {"type": "divider"},
    ]


def build_blocks(hn_ai, hn_k8s, k8s_blog, cncf_blog) -> list[dict]:
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Daily Digest", "emoji": True},
        },
        {"type": "divider"},
    ]
    blocks += section_block("HackerNews — AI", hn_ai)
    blocks += section_block("HackerNews — Kubernetes", hn_k8s)
    blocks += section_block("Kubernetes Blog", k8s_blog)
    blocks += section_block("CNCF Blog", cncf_blog)
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "Posted by platform-drones/daily-digest"}],
    })
    return blocks


def main():
    log.info("daily-digest starting")
    hn_ai = fetch_hn(HN_AI_URL, "AI")
    hn_k8s = fetch_hn(HN_K8S_URL, "kubernetes")
    k8s_blog = fetch_rss(K8S_BLOG_URL, "kubernetes-blog")
    cncf_blog = fetch_rss(CNCF_BLOG_URL, "cncf-blog")

    blocks = build_blocks(hn_ai, hn_k8s, k8s_blog, cncf_blog)

    client = WebClient(token=SLACK_TOKEN)
    try:
        client.chat_postMessage(
            channel=SLACK_CHANNEL,
            text="Daily Digest",
            blocks=blocks,
        )
        log.info("Posted digest to %s", SLACK_CHANNEL)
    except SlackApiError as e:
        log.error("Slack post failed: %s", e.response["error"])
        sys.exit(1)


if __name__ == "__main__":
    main()
