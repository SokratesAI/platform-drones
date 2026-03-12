"""
cncf-watcher drone
Fetches the CNCF landscape JSON, diffs against a local snapshot, and posts
new/promoted projects to Slack. Runs weekly on Mondays at 09:00 UTC.
No LLM. Pure automation.
"""

import os
import sys
import json
import logging
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SLACK_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#digest")
SNAPSHOT_PATH = "/data/cncf-snapshot.json"
LANDSCAPE_URL = "https://landscape.cncf.io/data/exports/landscape.json"


def fetch_landscape() -> dict[str, str]:
    """Returns {project_name: maturity} for all CNCF projects."""
    log.info("Fetching CNCF landscape from %s", LANDSCAPE_URL)
    try:
        r = requests.get(LANDSCAPE_URL, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error("Failed to fetch landscape: %s", e)
        return {}

    projects: dict[str, str] = {}
    for category in data.get("landscape", []):
        for subcategory in category.get("subcategories", []):
            for item in subcategory.get("items", []):
                name = item.get("name", "")
                maturity = item.get("project", "")  # sandbox / incubating / graduated / ""
                if name and maturity:
                    projects[name] = maturity
    log.info("Fetched %d CNCF projects", len(projects))
    return projects


def load_snapshot() -> dict[str, str] | None:
    if not os.path.exists(SNAPSHOT_PATH):
        return None
    try:
        with open(SNAPSHOT_PATH) as f:
            return json.load(f)
    except Exception as e:
        log.error("Failed to load snapshot: %s", e)
        return None


def save_snapshot(projects: dict[str, str]):
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(projects, f, indent=2)
    log.info("Snapshot saved to %s", SNAPSHOT_PATH)


MATURITY_ORDER = {"sandbox": 1, "incubating": 2, "graduated": 3}


def diff(old: dict[str, str], new: dict[str, str]) -> tuple[list[str], list[tuple[str, str, str]]]:
    new_projects = [name for name in new if name not in old]
    promoted = []
    for name, new_maturity in new.items():
        old_maturity = old.get(name)
        if old_maturity and old_maturity != new_maturity:
            if MATURITY_ORDER.get(new_maturity, 0) > MATURITY_ORDER.get(old_maturity, 0):
                promoted.append((name, old_maturity, new_maturity))
    return new_projects, promoted


def build_blocks(new_projects: list[str], promoted: list[tuple], total: int) -> list[dict]:
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "CNCF Landscape Weekly Update", "emoji": True}},
        {"type": "divider"},
    ]

    if new_projects:
        names = "\n".join(f"• {n}" for n in sorted(new_projects))
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*New projects ({len(new_projects)})*\n{names}"}})
        blocks.append({"type": "divider"})

    if promoted:
        lines = "\n".join(f"• *{name}*: {old} → {new}" for name, old, new in sorted(promoted))
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Maturity promotions ({len(promoted)})*\n{lines}"}})
        blocks.append({"type": "divider"})

    if not new_projects and not promoted:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "_No changes this week._"}})

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"Tracking {total} CNCF projects | platform-drones/cncf-watcher"}]})
    return blocks


def main():
    log.info("cncf-watcher starting")
    current = fetch_landscape()
    if not current:
        log.error("Empty landscape fetch — aborting")
        sys.exit(1)

    snapshot = load_snapshot()
    save_snapshot(current)

    client = WebClient(token=SLACK_TOKEN)

    if snapshot is None:
        log.info("First run — posting baseline")
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "CNCF Landscape — Baseline Captured", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"Tracking *{len(current)} projects*. Future runs will diff against this baseline."}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "platform-drones/cncf-watcher"}]},
        ]
    else:
        new_projects, promoted = diff(snapshot, current)
        log.info("Diff: %d new, %d promoted", len(new_projects), len(promoted))
        blocks = build_blocks(new_projects, promoted, len(current))

    try:
        client.chat_postMessage(channel=SLACK_CHANNEL, text="CNCF Landscape Update", blocks=blocks)
        log.info("Posted to %s", SLACK_CHANNEL)
    except SlackApiError as e:
        log.error("Slack post failed: %s", e.response["error"])
        sys.exit(1)


if __name__ == "__main__":
    main()
