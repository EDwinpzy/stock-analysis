# Daily Briefing Pro Cloud Runtime

This Compose runtime carries the complete `daily-briefing-pro` plugin tree, including its five top-level skills, nested stock-analysis and market-board modules, scripts, templates, and reference material. `market-query` is bundled for source completeness but depends on a Windows Lumi client, so it is not a cloud data source. It runs as an on-demand CLI container; it publishes no network port or web service.

The image pins Python 3.12.8, Node 24.18.0, the direct Python dependencies observed in the local baseline environment, Chromium, FFmpeg, and the `hithink-finance` CLI. `PYTHONHASHSEED=2` and CRLF HTML output preserve both the 2026-10-10 source report and its final broadsheet edition byte-for-byte. `scripts/run_all.py` always builds and visually verifies the broadsheet edition, and delivers that artifact as the report.

Version 3.23.14 adds a fail-fast runtime preflight, a durable-data seed path, an explicit writable rotation-model volume, and correct Compose secret targets. It does not invent missing model data or downgrade source/cookie completeness gates.

## Prepare the cloud host

From this directory on the cloud host (the setup command needs permission to assign the runtime files to container UID 10001):

```sh
sh ./init-secrets.sh
docker build \
  --memory=1800m --memory-swap=1800m \
  --cpu-period=100000 --cpu-quota=100000 \
  -f Dockerfile -t daily-briefing-pro:3.23.14-cloud ../..
```

The secret files are created empty and are ignored by Git and Docker build context. Copy or enter the user's own API keys and platform cookie JSON files directly on the cloud host. The setup command assigns them to container UID 10001 with mode `0600`. Do not put secrets in the image, repository, command-line arguments, or logs. After copying a data snapshot into `runtime/data/`, or restoring model files under `runtime/models/`, rerun `sh ./init-secrets.sh` so container UID 10001 can update those persistent files.

Recognized secret files:

| File | Used for |
| --- | --- |
| `secrets/deepseek_api_key` | AI summaries |
| `secrets/openai_api_key` | AI summaries / transcription fallback |
| `secrets/siliconflow_api_key` | Douyin transcription |
| `secrets/groq_api_key` | Douyin transcription |
| `secrets/ima_openapi_clientid`, `secrets/ima_openapi_apikey` | IMA research search |
| `secrets/hithink_finance_api_key` | Official Tonghuashun finance data CLI |
| `secrets/tgb_cookies.json` | TGB authenticated pages |
| `secrets/douyin_cookies.json` | Douyin authenticated requests |
| `secrets/xueqiu_cookies.json` | Xueqiu browser context |
| `secrets/ths_selfstock.json` | Optional Tonghuashun watchlist input |

The container passes API keys from read-only Compose secrets to the child process environment. Cookie files are mounted read-only. The runtime data, reports, and user cache live under `runtime/` and persist across runs.

The Compose file explicitly maps cookie secrets to `/run/secrets/*.json`; do not remove those `target:` entries. A secret named `tgb_cookies` otherwise appears at `/run/secrets/tgb_cookies` while the collector reads `/run/secrets/tgb_cookies.json`.

## Seed durable local history

A clean cloud volume does not inherit the Windows runtime at `~/.codex/daily-briefing-pro/data`. Compose sets `DAILY_BRIEFING_CLOUD=1`. Missing durable files are seeded automatically from the installed package's `data/` baseline, using the same allowlist as local migration: sentiment panel/history, node-cycle and rotation history, AI summary caches, transcript cache, and stock caches. Existing cloud files always win, and the seeder never copies `*_today.json`, cookies, login state, `.env`, or delivery snapshots. This is why a clean task starts with usable history instead of an empty panel.

To copy a newer Windows snapshot into an existing cloud volume, or to refresh files that already exist, use the explicit seed utility:

Preview first, then apply:

```powershell
pwsh -NoProfile -File .\seed-data.ps1
pwsh -NoProfile -File .\seed-data.ps1 -Apply -RefreshExisting
```

The default source is `$HOME\.codex\daily-briefing-pro\data`; the default destination is `deploy/cloud/runtime/data`. Replaced files are backed up beside the target. The same allowlist controls both paths, so installation snapshots cannot overwrite live cloud history.

`-RefreshExisting` still protects a newer destination by comparing file timestamps. If the files crossed machines in a way that makes timestamps unreliable, inspect the preview and use `-Force` to replace differing files; every replaced file is backed up beside the target.

The script resolves its own directory at runtime, so it works with both PowerShell 7 (`pwsh`) and Windows PowerShell 5.1.

## Install the rotation model

The skill ships a self-contained rotation model archive at
`skills/daily-briefing-pro/data/cloud-baseline/models/sw_rotation_model.zip`.
`cloud_bootstrap.py` extracts it once into a writable versioned directory
(`~/.codex/daily-briefing-pro/models/sw_rotation_model-<sha>`) when no explicit
model is present, so a clean cloud task can score without a manual upload.
The archive includes `RECONSTRUCTED.md`: the original model directory was not
in the marketplace package and was lost locally, so this is a functional
rebuild with the original config and 38-feature contract. On the saved
2026-10-19 snapshot it reproduces 8/15 T+5 names with a 0.50 score-rank
correlation; the near-window T+5 RankIC is 0.0638. It is not a byte-for-byte
copy of the lost model, but every local and cloud run now uses the same
archive and inputs, so their scores are reproducible.

To use a refreshed or custom model, place it in either:

- `plugins/daily-briefing-pro/models/sw_rotation_model/` before building the image; the entrypoint copies it once into the writable `/runtime/models` volume, or
- `deploy/cloud/runtime/models/sw_rotation_model/` directly on the cloud host.

Required entries include `run.py`, `config.json`, and the model's original `data/` files. A cached `rotation_today.json` is display output only and cannot be used to recompute ranks. An explicitly configured model always wins over the bundled archive. If neither exists, preflight blocks the full run with an actionable error.

After copying model files directly into `runtime/models/`, run `sh ./init-secrets.sh` once to align their ownership with container UID 10001.

## Run preflight

Run the structured check before collecting data:

```sh
docker compose -f compose.yaml run --rm --no-build briefing \
  python scripts/runtime_preflight.py --date 2026-10-19 --json

docker compose -f compose.yaml run --rm --no-build briefing \
  python scripts/run_all.py --date 2026-10-19 --preflight-only
```

The report checks Python dependencies, FFmpeg/Node, `hithink-finance` authentication and calendar access, AI-summary credentials or Codex login, the configured Douyin transcription path (local Whisper or API key), TGB/Douyin/Xueqiu cookies, sentiment-panel depth and dates, static rosters, node/rotation history, the rotation model inputs, and writable directories. It reports only credential source/status, never secret values. `run_all.py` writes the same report to `/runtime/data/preflight.json` and stops before collection when any blocker exists. A `--resume` run also validates every dated module and the daily quote before compilation starts.

Compose sets `DOUYIN_TRANSCRIPT_PROVIDER=auto`: a configured Groq/OpenAI/SiliconFlow key is tried first, then the container falls back to local Whisper. Because the container is limited to 1.5 CPU and 2GB memory, preflight warns when no transcription API key is available. The warning does not bypass the real-transcription requirement or allow title-only substitutes.

The image bakes the `small` Whisper checkpoint into `/opt/whisper-cache`; the
entrypoint copies it into the named runtime home on first start. This removes
the build-time-only download gap that previously made the first cloud video
transcription fail or take many minutes.

## Verify the reference report

Copy the complete `2026-10-10数据` snapshot into `verification/2026-10-10-data/`, the source `2026-10-10简报.html`, and its final `2026-10-10简报-报刊版.html` reference into `verification/`. The verifier copies the snapshot into an ephemeral container directory, so it does not seed live runtime state. Then run:

```sh
docker compose -f compose.yaml run --rm --no-build briefing \
  sh /opt/daily-briefing-pro/deploy/cloud/verify-baseline.sh \
  2026-10-10 /verification/2026-10-10简报.html
```

The script checks the source-report SHA256, rebuilds it from the snapshot, renders the broadsheet edition, checks the stylesheet fingerprint, and requires SHA256 plus byte-for-byte `cmp` equality for both reports.

Run the bundled regression suite with:

```sh
docker compose -f compose.yaml run --rm --no-build briefing \
  python -m unittest discover -s tests -v
```

## Run plugin functions

```sh
# Full daily briefing (live sources; requires the relevant keys/cookies above)
# The run creates and verifies the newspaper-style final report automatically.
docker compose -f compose.yaml run --rm --no-build briefing python scripts/run_all.py

# A requested report date
docker compose -f compose.yaml run --rm --no-build briefing python scripts/run_all.py --date 2026-10-10

# Standalone news, research, blogger, and market-data entry points
docker compose -f compose.yaml run --rm --no-build briefing python scripts/news_screener.py health
docker compose -f compose.yaml run --rm --no-build briefing node scripts/yanbao/run.mjs --date 2026-10-10
docker compose -f compose.yaml run --rm --no-build briefing python scripts/fetch_sentiment_survey.py --date 2026-10-10

# Stock analysis, market board, industry analysis, and emotion panel
docker compose -f compose.yaml run --rm --no-build briefing python ../stock-analysis/scripts/fetch_stock_data.py 600519
docker compose -f compose.yaml run --rm --no-build briefing python modules/stock-market-board/scripts/fetch_data.py 600519
docker compose -f compose.yaml run --rm --no-build briefing python ../stock-emotion-panel/scripts/fetch_panel.py --help
```

The installed skill documents remain in `/opt/daily-briefing-pro/skills/`. Workflows that require an LLM to interpret fetched data continue to be orchestrated by the cloud agent; this container supplies their Python, Node, browser, and data-source runtime.
