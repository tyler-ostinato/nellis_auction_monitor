# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python application that scrapes the Nellis Auction website (Delran, NJ warehouse) for listings matching configured keywords, then sends email notifications. It runs as a scheduled daemon (daily at a configured time) inside a Docker container or Kubernetes pod, routing traffic through NordVPN.

## Local Development

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Run (starts the scheduler loop — runs at configured time daily)
python -m app.main

# Run once immediately (set in config/config.yaml)
# scheduler.skipScheduleInDebug: true
python -m app.main
```

Set credentials in `.env` (copy from `.env.example`):
```
AUCTION_EMAIL_ADDRESS=your-email@gmail.com
AUCTION_EMAIL_PASSWORD=your-app-password
```

No test suite exists yet (`pytest tests/` is a placeholder).

## Kubernetes Deployment (primary target)

Uses a local `kind` cluster with a registry on port 5001. All `just` recipes use `kubectl --context kind-kind` by default.

```bash
just deploy    # build image, push to localhost:5001, kubectl apply k8s/
just secret    # create/update Secret from .env file
just logs      # stream pod logs
just restart   # rollout restart
just teardown  # delete all k8s resources
```

The Kubernetes deployment requires a separate `nordlynx` container (NordVPN) running in the cluster — the pod routes all traffic through `socks5://nordlynx.nordlynx.svc.cluster.local:1080` via `SOCKS5_PROXY_URL`.

## Docker Compose (alternative)

```bash
docker-compose build
docker-compose up -d
docker-compose logs -f auction-monitor
```

Docker Compose uses `network_mode: "container:nordlynx"` — the nordlynx container must be running first from its own compose file.

## Configuration

Config lives in two files mounted at `/app/config/` (read-only in containers):

- **`config/config.yaml`** — scraper settings, scheduler time/timezone, email SMTP, filters (star rating, min retail price), logging
- **`config/keywords.yaml`** — list of keyword strings matched (case-insensitive substring) against listing titles

In Kubernetes, both files are served from `k8s/configmap.yaml` — edit the ConfigMap, not the local files, for k8s deployments. After editing the ConfigMap, run `just deploy` to re-apply.

Key config fields:
- `scraper.locationCode` — must be `"phi"` for Delran/Philadelphia warehouse; without it, the server defaults to Las Vegas and returns 0 results
- `scraper.maxPages` — set to 200 in k8s ConfigMap (scrapes all available pages)
- `scheduler.skipScheduleInDebug` — set `true` to run one scrape immediately on startup (useful for testing)
- `filters.minEstimatedRetailPrice` — filters out cheap/low-value items

## Architecture

```
main.py → AuctionScheduler (APScheduler) → scrape_and_notify() [async]
                                                 ↓
                                          AuctionScraper (Playwright/Chromium)
                                                 ↓
                                          Rating + price filter
                                                 ↓
                                          KeywordMatcher (substring match)
                                                 ↓
                                          EmailNotifier (SMTP)
```

**Scraping strategy** (`scraper.py`): The Nellis Auction site is built with Remix. The scraper intercepts Remix data API responses (`?_data=` or `.data` suffix) to get clean JSON — this is the primary path. Falls back to evaluating `window.__remixRouter.state.loaderData` / `window.__remixContext.state.loaderData` from the browser JS context, then finally to HTML/script-tag JSON parsing. Pagination uses Nellis's `_p1=s%3A120%2Cn%3A{page_index}` query parameter (0-based, 120 items/page).

**No deduplication between runs**: `ListingTracker` (`tracker.py`) is defined but not wired into `scrape_and_notify()` in `main.py` — every run emails all matching listings regardless of prior runs. The `data/seen_listings.json` file exists but is not used in the current flow.

**APScheduler + asyncio**: The scheduler runs jobs in threads and cannot await coroutines directly. `main.py` wraps the async `scrape_and_notify()` in a sync `run_task()` that calls `asyncio.run()`.

## Listing Data Shape

Fields on each listing dict (from `_parse_remix_listings`):
- `id` — numeric listing ID (used in URLs, not `inventoryNumber`)
- `title`, `url`, `price` (current bid), `estimated_retail` (retail price)
- `rating` — integer 1–5 from `grade.rating` in API response
- `category`, `location`, `bid_count`, `is_closed`, `market_status`
- `matched_keywords` — added by `KeywordMatcher.find_matches()`
