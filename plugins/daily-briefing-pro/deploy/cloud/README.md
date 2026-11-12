# Daily Briefing Pro Cloud Runtime

This Compose runtime carries the complete `daily-briefing-pro` plugin tree, including its five top-level skills, nested stock-analysis and market-board modules, scripts, templates, and reference material. `market-query` now has a portable Python entry point backed by `thsdk` and the Fuyao REST API, so it works on Linux without a Windows Lumi client. It runs as an on-demand CLI container; it publishes no network port or web service.

Stock and industry report delivery uses a separate, fail-closed cloud contract.
Fuyao REST supplies security lookup, sector directory/membership, sector
snapshots, news and quote fallback. The official iWencai OpenAPI supplies the
primary real-time quote, financials, valuation, peer metrics, holders,
fund-flow aggregates and industry fundamentals. It does not use a guest
`thsdk` account as the report's primary source. `FUYAO_API_KEY` is required;
`IWENCAI_API_KEY` is preferred but no longer a startup dependency. When
Wencai is absent or out of quota, company basics, product
mix, margin balance and daily net flow are filled from public Eastmoney
endpoints; reports label those sources and never invent a complete picture.
The official iWencai endpoint exposes only an aggregated daily buy/sell total
for large orders. Eastmoney fallback exposes daily net inflow, not ticks, so
the two modes are labelled `daily_aggregate` and `daily_net_flow`.

The image pins Python 3.12.8, Node 24.18.0, the direct Python dependencies observed in the local baseline environment, Chromium, FFmpeg, and the `hithink-finance` CLI. `PYTHONHASHSEED=2` and CRLF HTML output preserve the 2026-10-10 source report byte-for-byte. The default broadsheet removes the three remote Google Fonts links so an offline cloud host always renders immediately; the benchmark verifier passes `--remote-fonts` to reproduce the original local broadsheet byte-for-byte. `scripts/run_all.py` always builds and visually verifies the default broadsheet edition, and delivers that artifact as the report.

Chromium is installed under `/opt/playwright-browsers`, outside the persistent `/runtime/home` volume. Do not move it back under `$HOME`: an empty or reused home volume would hide the browser binary and break report verification.

The Dockerfile contains architecture-specific branches for both `linux/amd64`
and `linux/arm64`. AKShare is installed with `--no-deps` because its Linux
metadata pulls in `py-mini-racer`, which has no ARM64 wheel. The image
installs `py-mini-racer` on AMD64 and `akracer` on ARM64, then runs a
`MiniRacer` smoke test during the build. AKShare's other runtime dependencies
are pinned explicitly in `requirements-cloud.txt`. The last formally built
AMD64 image is `candidate9`, which predates the latest source-label and
integrity-gate corrections; the current working tree still needs a formal
candidate10 rebuild. The ARM64 formal image build and native Chromium visual
gate are also still unverified, so an ARM64 overlay image must not be
presented as a formal build.

Version 3.23.19 completes the portable market-query surface with sorting, watchlists, sector groups, one-shot subscriptions, and a read-only tool whitelist; cloud ranking now returns `prev_close` and HTML parity only normalizes the exact collection timestamp from each payload. Version 3.23.18 hardens the portable entry point with process-tree timeouts, vendor-name normalization (`万  科Ａ` → `万科A`), non-empty research/section boundaries, and a cloud sector snapshot. Version 3.23.17 bounds Codex semantic-summary batches, runs up to four batches concurrently, reuses cached report logic during compilation, uses the faster default reasoning level, and terminates the complete CLI process tree on timeout so a stuck child cannot consume the collector's whole time budget. Version 3.23.16 adds the official Hithink index fallback for industry and CSI 300 bars when AKShare trails the target session. Version 3.23.15 added the missing-only cloud baseline and the bundled rotation-model archive. Version 3.23.14 added the fail-fast runtime preflight, durable-data seed path, explicit writable rotation-model volume, and correct Compose secret targets. No version invents missing model data or downgrades source/cookie completeness gates.

The portable CLI also normalizes the vendor's premarket null sentinel
(`2147483648`) instead of exposing it as a price, and `market status --probe`
requires at least one real THS or Fuyao query to succeed. The stock collector
retries transient peer-query failures and falls back from the leaf industry to
its parent before allowing a report section to become empty.

## Prepare the cloud host

The commands below require Docker Engine with the Compose v2 plugin available to root (`sudo docker compose version`).

From this directory on the cloud host (the setup command needs permission to assign the runtime files and secrets to container UID 10001):

```sh
sudo sh ./init-secrets.sh

# Docker Engine 20.10 and newer: use BuildKit so --platform is honored.
# Replace amd64 with arm64 on an ARM host.
sudo env DOCKER_BUILDKIT=1 docker build \
  --platform linux/amd64 \
  --memory=1800m --memory-swap=1800m \
  --cpu-period=100000 --cpu-quota=100000 \
  -f Dockerfile -t daily-briefing-pro:3.23.19-cloud ../..
```

Without `DOCKER_BUILDKIT=1`, older Docker engines may silently use the host
architecture even when `--platform` is present. Verify the result before
starting Compose:

```sh
sudo docker image inspect daily-briefing-pro:3.23.19-cloud \
  --format '{{.Architecture}} {{.Os}}'
```

The output must match the host runtime (`amd64` on x86_64, `arm64` on
`aarch64`/`arm64`). The image includes architecture-specific AKShare glue:
`akracer` on ARM64 and `py-mini-racer` on AMD64.

The current verification state for this revision is:

| Architecture | Verification state |
| --- | --- |
| AMD64 | Last formal Dockerfile build is `daily-briefing-pro:3.23.19-cloud-amd64-candidate9`; current working tree needs a candidate10 rebuild |
| ARM64 | Formal build and native visual gate not yet verified for the current working tree |

The tag above is an internal verification tag, not a release tag. Build and
tag the image in your own registry before production use. Do not use an
overlay image as proof of an ARM64 build. Set `DAILY_BRIEFING_IMAGE` to the
image tag you actually built and verified:

```sh
sudo DAILY_BRIEFING_IMAGE=daily-briefing-pro:3.23.19-cloud \
  docker compose -f compose.yaml run --rm briefing python scripts/run_all.py
```

## Manual validation in GitHub Actions

`.github/workflows/cloud-port-validation.yml` provides a manual, reproducible
Linux validation path when no SSH build host is available. It runs the full
Python test suite, builds the formal AMD64 Dockerfile, then executes
`doctor --probe`, live market queries, and the stock/industry report gates
inside that image. Configure repository Actions secret `FUYAO_API_KEY`;
`IWENCAI_API_KEY` is optional. The workflow passes configured values as
environment variables and the container entrypoint keeps them out of image
layers. Evidence is uploaded as the `cloud-port-evidence` artifact. The
workflow is manual-only and does not publish an image or a release.

The secret files are created empty and are ignored by Git and Docker build context. Copy or enter the user's own API keys and platform cookie JSON files directly on the cloud host. The setup command assigns secrets and persistent runtime files to container UID 10001 with mode `0600`. Compose reads the host secret files before mounting them read-only into the container, so run `init-secrets.sh` and the Compose commands with `sudo` unless the deployment user already has Docker access and can read those files. Do not put secrets in the image, repository, command-line arguments, or logs. After copying a data snapshot into `runtime/data/`, or restoring model files under `runtime/models/`, rerun `sh ./init-secrets.sh` so container UID 10001 can update those persistent files.

Recognized secret files:

| File | Used for |
| --- | --- |
| `secrets/deepseek_api_key` | AI summaries |
| `secrets/openai_api_key` | AI summaries / transcription fallback |
| `secrets/siliconflow_api_key` | Douyin transcription |
| `secrets/groq_api_key` | Douyin transcription |
| `secrets/douyin_asr_api_key` | Generic OpenAI-compatible Douyin ASR; `DOUYIN_ASR_BASE_URL` and `DOUYIN_ASR_MODEL` must also be set |
| `secrets/ima_openapi_clientid`, `secrets/ima_openapi_apikey` | IMA research search |
| `secrets/hithink_finance_api_key` | Optional override for the official Tonghuashun finance data CLI |
| `secrets/fuyao_api_key` | Required for cloud stock/industry reports and Fuyao REST market queries (`FUYAO_API_KEY`); also used by the finance CLI when no separate key is supplied |
| `secrets/iwencai_api_key` | Optional official iWencai OpenAPI key (`IWENCAI_API_KEY`); missing/quota-exhausted runs use labelled Eastmoney and thsdk fallbacks |
| `secrets/ths_username`, `secrets/ths_password`, `secrets/ths_mac` | Optional fixed THS account for `thsdk`-only compatibility queries; not required by the cloud stock/industry report path |
| `secrets/tgb_cookies.json` | TGB authenticated pages |
| `secrets/douyin_cookies.json` | Douyin authenticated requests |
| `secrets/xueqiu_cookies.json` | Xueqiu browser context |
| `secrets/ths_selfstock.json` | Optional Tonghuashun watchlist input |

The container passes API keys from read-only Compose secrets to the child process environment. A single Fuyao key can serve both the REST market query and the official `hithink-finance` CLI; an explicitly populated `secrets/hithink_finance_api_key` still takes precedence. Wencai uses its own `secrets/iwencai_api_key`; it is not interchangeable with the Fuyao key and is not a startup requirement. Cookie files are mounted read-only. The runtime data, reports, and user cache live under `runtime/` and persist across runs.

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
sudo docker compose -f compose.yaml run --rm briefing \
  python scripts/runtime_preflight.py --date 2026-10-19 --json

sudo docker compose -f compose.yaml run --rm briefing \
  python scripts/run_all.py --date 2026-10-19 --preflight-only
```

The report checks Python dependencies, FFmpeg/Node, `hithink-finance` authentication and calendar access, AI-summary API credentials, the configured Douyin cloud ASR key, TGB/Douyin/Xueqiu cookies, sentiment-panel depth and dates, static rosters, node/rotation history, the rotation model inputs, and writable directories. It reports only credential source/status, never secret values. `run_all.py` writes the same report to `/runtime/data/preflight.json` and stops before collection when any blocker exists. A `--resume` run also validates every dated module and the daily quote before compilation starts.

Compose sets `DOUYIN_TRANSCRIPT_PROVIDER=auto`. A generic ASR is used only
when all of `DOUYIN_ASR_BASE_URL`, `DOUYIN_ASR_API_KEY` and
`DOUYIN_ASR_MODEL` are set. It is tried before Groq/OpenAI/SiliconFlow. There
is no local model fallback: the image contains no Whisper weights, torch,
CTranslate2 or faster-whisper. Preflight fails when no cloud ASR credential is
configured, and the scheduled-briefing gate refuses to start without one. The
text AI Relay is never treated as an audio endpoint. A missing key cannot
bypass the real-transcription requirement or allow title-only substitutes.

## Verify the reference report

Copy the complete `2026-10-10数据` snapshot into `verification/2026-10-10-data/`, the source `2026-10-10简报.html`, and its final `2026-10-10简报-报刊版.html` reference into `verification/`. The verifier copies the snapshot into an ephemeral container directory, so it does not seed live runtime state. Then run:

```sh
sudo docker compose -f compose.yaml run --rm briefing \
  sh /opt/daily-briefing-pro/deploy/cloud/verify-baseline.sh \
  2026-10-10 /verification/2026-10-10简报.html
```

The script checks the source-report SHA256, rebuilds it from the snapshot, renders the broadsheet edition, checks the stylesheet fingerprint, and requires SHA256 plus byte-for-byte `cmp` equality for both reports.

Run the bundled regression suite with:

```sh
sudo docker compose -f compose.yaml run --rm briefing \
  python -m unittest discover -s tests -v
```

## Run plugin functions

```sh
# Full daily briefing (live sources; requires the relevant keys/cookies above)
# The run creates and verifies the newspaper-style final report automatically.
sudo docker compose -f compose.yaml run --rm briefing python scripts/run_all.py

# A requested report date
sudo docker compose -f compose.yaml run --rm briefing python scripts/run_all.py --date 2026-10-10

# Standalone news, research, blogger, and market-data entry points
sudo docker compose -f compose.yaml run --rm briefing python scripts/news_screener.py health
sudo docker compose -f compose.yaml run --rm briefing node scripts/yanbao/run.mjs --date 2026-10-10
sudo docker compose -f compose.yaml run --rm briefing python scripts/fetch_sentiment_survey.py --date 2026-10-10

# Stock / industry reports: collect, build, and gate in one command
sudo docker compose -f compose.yaml run --rm briefing python /opt/daily-briefing-pro/cloud_cli.py stock-report 600519
sudo docker compose -f compose.yaml run --rm briefing python /opt/daily-briefing-pro/cloud_cli.py industry-report 白酒

# Raw collectors and the other on-demand pages
sudo docker compose -f compose.yaml run --rm briefing python /opt/daily-briefing-pro/cloud_cli.py stock 600519
sudo docker compose -f compose.yaml run --rm briefing python /opt/daily-briefing-pro/cloud_cli.py industry 白酒 --limit 15
sudo docker compose -f compose.yaml run --rm briefing python modules/stock-market-board/scripts/fetch_data.py 600519
sudo docker compose -f compose.yaml run --rm briefing python ../stock-emotion-panel/scripts/fetch_panel.py --help
```

`stock-report` and `industry-report` are the delivery entry points. They invoke the portable collector, build the HTML, and run the same section/table/source-fact gate used locally. A non-zero exit means the report must not be delivered. The collector JSON and report are written below the mounted `/runtime` directories; `work/` and local runtime snapshots are intentionally excluded from Git.

The cloud report path is deliberately deterministic: `stock-report` and
`industry-report` force `--source cloud`. When the official iWencai channel is
available it supplies financial and valuation fields; when its key or quota is
unavailable, the collector falls back to Eastmoney/Tencent and labels the
source instead of inventing a value. Quotes, sector membership, news and
holder snapshots use Fuyao REST or the documented fallback. The builder rejects
missing sections and empty tables, and the verifier rejects `暂无`,
`UNSOURCED` and `NaN` placeholders in required data. Use `doctor --probe`
before the first live run to verify the configured channels.

## Portable command boundary

`cloud_cli.py market` exposes the queries that have a real cloud contract. It
does not silently substitute a local-only feature with a different metric.

| Capability | Portable action | Cloud runtime | Boundary |
| --- | --- | --- | --- |
| Environment check | `doctor`, `market status` | `thsdk` and/or Fuyao key | Reports credential presence only |
| Security/realtime/day K | `search`, `realtime`, `candle` | Fuyao REST and `thsdk` | Fuyao K-line is daily only |
| Sector lookup | `blocks`, `sector` | Fuyao REST and `thsdk` | Constituents and index identity are preserved |
| Stock news | `news` | Fuyao REST and `thsdk` | Source/category columns are retained |
| Reference lookup | `catalog`, `fields`, `cloud-get`, `datahub-get` | Bundled references and REST | No guessed endpoint or field IDs |
| Intraday/tick | `trend`, `tick` | `thsdk` only | Fuyao public REST has no equivalent endpoint |
| Capital flow | `capital-flow` | `thsdk` only | Fuyao marks the flow endpoint `client-only` |
| Ranking | `sort` | `thsdk` block members plus realtime; Fuyao market/index fallback | Common market scopes and `.TI` sectors have a direct REST path; other numeric block IDs use `thsdk` |
| First-push subscription | `subscribe` | One-shot realtime/candle snapshot; `thsdk` for trend/tick | It returns the equivalent first snapshot and does not keep a persistent stream |
| Watchlist/groups | `watchlist`, `sectors` | `THS_SELFSTOCK_PATH` or `/run/secrets/ths_selfstock.json` | No login-state import; a missing file is reported instead of invented |
| Read-only calls | `call` | Allowlisted portable tools | `wencai_query` uses `IWENCAI_API_KEY` for all 21 skills; without it only the `hithink-market-query` skill can fall back to `thsdk` |
| Data/report parity | `parity` | Local and cloud JSON/HTML inputs | Ignores collection timestamps and runtime paths, not business values |

The portable CLI never invents a replacement for a local-only result. If a
required capability is unavailable, it returns a non-zero exit code and a JSON
error such as `unsupported_cloud` or `missing_api_key`.

`sort` supports the same `block`, `sortField`, `sortOrder`, `offset`, `count`
and `excludeBlocks` fields as the desktop tool. With `thsdk`, arbitrary numeric
block IDs are resolved through the Tonghuashun block tree. With pure Fuyao REST,
use `14` (沪深A股), `21` (沪市), `27` (深市), `50854` (全部含北交所), or a
`.TI` sector such as `881273.TI`. `subscribe` is deliberately one-shot: it
performs the requested realtime, candle, trend or tick fetch, returns the first
equivalent snapshot, and exits. This matches the desktop operation's
"first event then unsubscribe" lifecycle without claiming a persistent stream.

For watchlist parity, mount a genuine Tonghuashun self-stock export at
`secrets/ths_selfstock.json`. The portable reader supports the old list format
and both remote-client pipe formats. If the file is absent, `watchlist` returns
an explicit `unavailable` result with zero securities.

## Timeouts and process cleanup

The portable entry point applies a process-level timeout to every child
command and terminates the complete process tree on expiry, including
descendants that inherited stdout/stderr pipes. A timeout returns exit code
`124` instead of hanging the scheduler.

| Variable | Default | Scope |
| --- | ---: | --- |
| `DAILY_BRIEFING_PREFLIGHT_TIMEOUT` | 120 s | `stock --preflight`, `industry --preflight` |
| `DAILY_BRIEFING_COLLECT_TIMEOUT` | 300 s | market queries and report collectors |
| `DAILY_BRIEFING_BUILD_TIMEOUT` | 120 s | deterministic HTML builder |
| `DAILY_BRIEFING_PROBE_TIMEOUT` | 120 s | `doctor --probe` checks |
| `DAILY_BRIEFING_RUN_TIMEOUT` | 3600 s | complete `briefing` pipeline |

The collector also retries empty industry/concept directory responses a
bounded number of times and restores the `thsdk` connection context before
querying. Fuyao requests retry network errors, HTTP 429 and 5xx responses a
limited number of times; auth failures, redirects and business errors are not
blindly retried.

The broadsheet HTML uses system font fallbacks and makes no Google Fonts request, so the visual gate does not block on external font downloads. The image installs `fonts-noto-cjk` for Linux rendering; Windows/macOS use their native CJK font fallbacks.

The unified entry point also exposes market queries and report gates:

```sh
# Environment and both data channels. Guest THS accounts are for smoke tests;
# use secrets/ths_username, secrets/ths_password and secrets/ths_mac for a fixed
# THS account, and secrets/fuyao_api_key (or FUYAO_API_KEY) for the REST fallback.
sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py doctor --probe

sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py market realtime 600519 --mode cloud

sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py market candle 600519 --mode ths --count 20

sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py market trend 600519 --mode ths

sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py market tick 600519 --count 20 --mode ths

sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py market news 600519 --mode ths

sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py market fields --data-type tick --query 最新价

sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py market sort --block 14 --count 20

sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py market watchlist

sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py market subscribe --api SubscribeRealtime --target 600519

# Stock / industry reports must pass the same data and HTML gates before delivery.
sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py verify /runtime/reports/stock.html \
  --type stock --data-json /runtime/data/stock-analysis/_fetch_result_600519.json

sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py verify /runtime/reports/industry.html \
  --type industry --data-json /runtime/data/industry-analysis/_industry_白酒.json

sudo docker compose -f compose.yaml run --rm briefing \
  python /opt/daily-briefing-pro/cloud_cli.py parity \
  --data-local /verification/local-stock.json \
  --data-cloud /verification/cloud-stock.json \
  --html-local /verification/local-stock.html \
  --html-cloud /verification/cloud-stock.html
```

The Fuyao REST contract uses `600519.SH`; `thsdk` uses `USHA600519`. The CLI accepts either and keeps `vendor_thscode` in its output. Cloud K-lines are daily only; `trend` and `tick` are available through `thsdk` (`--mode ths` or `auto`) but the public Fuyao REST channel has no corresponding endpoint. `capital-flow` is `ths`-only because the public Fuyao endpoint is marked `client-only`; the CLI fails explicitly instead of substituting another metric. For stock/industry report schedulers, set `DAILY_BRIEFING_DATA_DIR`, `BRIEFING_OUTPUT_DIR`, `FUYAO_API_KEY` and `IWENCAI_API_KEY`; THS account variables are only needed for the `thsdk` compatibility channel.

The installed skill documents remain in `/opt/daily-briefing-pro/skills/`.
`briefing --scheduled` runs the complete daily pipeline in the container. The
OpenAI-compatible Relay is used only for textual semantic summaries; it is not
an audio transcription endpoint. Cloud mode also disables the local Codex CLI
summary fallback. Audio must come from one of these real paths:

- a native Douyin subtitle, when the video actually exposes one;
- an explicitly configured OpenAI-compatible audio ASR, Groq, OpenAI, or
  SiliconFlow endpoint.

The pipeline never treats a title, hashtags, or a replay fixture as a
transcript. If no real audio transcript is available, the run is reported as
incomplete or fails its gate rather than producing a substitute briefing.
