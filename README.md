# platform-drones

Hardcoded automation drones for the SokratesAI platform. No LLM — pure scheduled automation.

## Drones

| Drone | Schedule | Purpose |
|-------|----------|---------|
| `daily-digest` | 08:00 UTC daily | Posts top HN stories, Kubernetes blog, and CNCF blog links to Slack |
| `cncf-watcher` | 09:00 UTC Monday | Diffs CNCF landscape for new/promoted projects, posts to Slack |
| `github-activity` | 07:00 UTC daily | Reports merged PRs, open PRs, open issues, CI failures for the SokratesAI org |

## Architecture

- Each drone is a standalone Python container
- No inter-drone communication
- All config via environment variables
- All output via Slack Block Kit messages
- Deployed as Kubernetes CronJobs in the `drones` namespace

## Secrets required

### `slack-credentials` (K8s secret, namespace `drones`)
- `bot-token` — Slack bot OAuth token with `chat:write` scope

### `github-credentials` (K8s secret, namespace `drones`)
- `token` — GitHub personal access token or fine-grained token with `repo` read access

## Local development

```bash
cd drones/<drone-name>
pip install -r requirements.txt
SLACK_BOT_TOKEN=xoxb-... python main.py
```

## Build

Images are built and pushed to `ghcr.io/sokratesai/platform-drones/<drone-name>:latest` via GitHub Actions on every push to `main` that touches `drones/**`.

## Deploy

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
```
