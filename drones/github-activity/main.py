"""
github-activity drone
Fetches merged PRs, open PRs, open issues, and recent CI failures for all repos
in the SokratesAI GitHub org. Posts a Slack summary. Runs daily at 07:00 UTC.
No LLM. Pure automation.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, timezone
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
SLACK_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#digest")
GITHUB_ORG = os.environ.get("SLACK_ORG", "SokratesAI")

GH_API = "https://api.github.com"
HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
LOOKBACK_HOURS = 24


def gh_get(path: str, params: dict | None = None) -> list | dict | None:
    url = f"{GH_API}{path}"
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        log.error("GitHub API error %s: %s", url, e)
        return None
    except Exception as e:
        log.error("GitHub request failed %s: %s", url, e)
        return None


def get_repos() -> list[str]:
    data = gh_get(f"/orgs/{GITHUB_ORG}/repos", {"per_page": 100, "sort": "pushed"})
    if not data:
        return []
    return [r["name"] for r in data if not r.get("archived")]


def get_merged_prs(repo: str, since: datetime) -> list[dict]:
    data = gh_get(f"/repos/{GITHUB_ORG}/{repo}/pulls", {"state": "closed", "per_page": 50, "sort": "updated", "direction": "desc"})
    if not data:
        return []
    merged = []
    for pr in data:
        merged_at = pr.get("merged_at")
        if not merged_at:
            continue
        t = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
        if t >= since:
            merged.append({"title": pr["title"], "url": pr["html_url"], "user": pr["user"]["login"]})
    return merged


def get_open_prs(repo: str) -> list[dict]:
    data = gh_get(f"/repos/{GITHUB_ORG}/{repo}/pulls", {"state": "open", "per_page": 20})
    if not data:
        return []
    return [{"title": pr["title"], "url": pr["html_url"], "user": pr["user"]["login"]} for pr in data]


def get_open_issues(repo: str) -> int:
    data = gh_get(f"/repos/{GITHUB_ORG}/{repo}", )
    if not data:
        return 0
    return data.get("open_issues_count", 0)


def get_failed_runs(repo: str, since: datetime) -> list[dict]:
    data = gh_get(f"/repos/{GITHUB_ORG}/{repo}/actions/runs", {"status": "failure", "per_page": 5})
    if not data:
        return []
    failures = []
    for run in data.get("workflow_runs", []):
        t = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
        if t >= since:
            failures.append({"name": run["name"], "url": run["html_url"], "branch": run.get("head_branch", "?")})
    return failures


def fmt_list(items: list[dict], key: str, url_key: str = "url", limit: int = 5) -> str:
    if not items:
        return "_none_"
    lines = [f"• <{item[url_key]}|{item[key]}>" for item in items[:limit]]
    if len(items) > limit:
        lines.append(f"_...and {len(items) - limit} more_")
    return "\n".join(lines)


def main():
    log.info("github-activity starting for org %s", GITHUB_ORG)
    since = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

    repos = get_repos()
    if not repos:
        log.error("No repos found for org %s", GITHUB_ORG)
        sys.exit(1)
    log.info("Found %d repos", len(repos))

    all_merged: list[dict] = []
    all_open_prs: list[dict] = []
    total_open_issues = 0
    all_failures: list[dict] = []

    for repo in repos:
        all_merged += get_merged_prs(repo, since)
        all_open_prs += get_open_prs(repo)
        total_open_issues += get_open_issues(repo)
        all_failures += get_failed_runs(repo, since)

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"GitHub Activity — {GITHUB_ORG}", "emoji": True}},
        {"type": "divider"},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Merged PRs (last 24h)*\n{len(all_merged)}"},
            {"type": "mrkdwn", "text": f"*Open PRs*\n{len(all_open_prs)}"},
            {"type": "mrkdwn", "text": f"*Open Issues*\n{total_open_issues}"},
            {"type": "mrkdwn", "text": f"*CI Failures (last 24h)*\n{len(all_failures)}"},
        ]},
        {"type": "divider"},
    ]

    if all_merged:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Merged PRs*\n{fmt_list(all_merged, 'title')}"}})
        blocks.append({"type": "divider"})

    if all_open_prs:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Open PRs*\n{fmt_list(all_open_prs, 'title')}"}})
        blocks.append({"type": "divider"})

    if all_failures:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*CI Failures*\n{fmt_list(all_failures, 'name')}"}})
        blocks.append({"type": "divider"})

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"Scanned {len(repos)} repos | platform-drones/github-activity"}]})

    client = WebClient(token=SLACK_TOKEN)
    try:
        client.chat_postMessage(channel=SLACK_CHANNEL, text=f"GitHub Activity — {GITHUB_ORG}", blocks=blocks)
        log.info("Posted to %s", SLACK_CHANNEL)
    except SlackApiError as e:
        log.error("Slack post failed: %s", e.response["error"])
        sys.exit(1)


if __name__ == "__main__":
    main()
