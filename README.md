# Pocket Server

Small Flask app for controlling a local machine from a browser.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
POCKET_PORT=5052 flask --app app run --host 127.0.0.1 --port 5052
```

Open:

```text
http://127.0.0.1:5052/gpt
```

## Run on Termux

```bash
pkg install python -y
python -m pip install -r requirements.txt
POCKET_HOST=0.0.0.0 POCKET_PORT=5052 python run_pocket.py
```

Then open `/setup` in a browser to paste your Gemini API key and save `.env`.

Current Termux tunnel:

```text
https://changes-sic-dans-directive.trycloudflare.com/
```

Control pages:

- `/`: Pocket Arkanoid HTML5 game.
- `/bp`: BODY POWER landing page.
- `/stats`: Dashboard for battery, storage, RAM, and system info.
- `/fast`: Pocket Fast speed test for the Termux tunnel.
- `/gpt`: Gemini CLI prompt bridge.
- `/store`: Public static-first Shopify storefront prototype with home, collection, product, cart, and mock checkout.
- `/terminal`: Token-protected browser terminal for pasted shell commands.
- `/setup`: Save local `.env` config from the browser.
- `/office/maison-flou`: legacy Termux office status. Prefer Cloudflare `/lab`.
- `/ops`: Unlock once in the browser, or use signed HMAC requests, then run pull, restart, or pull then restart.
- `/pull`: Run `git pull origin master`.
- `/restart`: Start a fresh Pocket Server process in the background, then stop the old one.

The `/gpt` page sends prompts to the local Gemini CLI with:

```bash
gemini -m gemini-2.5-flash-lite -p "<prompt>"
```

## Configuration

- `GEMINI_API_KEY`: Gemini API key from Google AI Studio. Used by Gemini CLI.
- `POCKET_GEMINI_MODEL`: Gemini model for the bridge. Default: `gemini-2.5-flash-lite`.
- `POCKET_GEMINI_COMMAND`: Gemini executable name or path. Default: `gemini`.
- `POCKET_GEMINI_ARGS`: Extra Gemini CLI arguments appended after `-m POCKET_GEMINI_MODEL`, split like shell args.
- `POCKET_GEMINI_WORKDIR`: Directory where Gemini runs. Default: this repo.
- `POCKET_GEMINI_TIMEOUT_SECONDS`: Request timeout. Default: `180`.
- `POCKET_ACCESS_TOKEN`: Token required by `/terminal` and `/api/terminal`; optional token required by `/api/gpt`, `/fast/api/download`, and `/fast/api/upload`.
- `POCKET_PUBLIC_BASE_URL`: Public Termux base URL when Cloudflare needs the phone as a processing origin.
- `POCKET_CONTENT_PUBLISH_URL`: Optional explicit Termux URL for Cloudflare to request image/caption generation.
- `POCKET_MAX_PROMPT_LENGTH`: Prompt character limit. Default: `12000`.
- `POCKET_TERMINAL_SHELL`: Shell used by `/terminal`. Default: detected `bash`, detected `sh`, then `/bin/sh`.
- `POCKET_TERMINAL_TIMEOUT_SECONDS`: Browser terminal command timeout. Default: `120`.
- `POCKET_TERMINAL_MAX_COMMAND_LENGTH`: Browser terminal command character limit. Default: `20000`.
- `POCKET_FAST_DOWNLOAD_BYTES`: Default server-to-browser test size. Default: `16777216`.
- `POCKET_FAST_UPLOAD_BYTES`: Default browser-to-server test size. Default: `8388608`.
- `POCKET_FAST_MAX_DOWNLOAD_BYTES`: Maximum server-to-browser test size. Default: `67108864`.
- `POCKET_FAST_MAX_UPLOAD_BYTES`: Maximum browser-to-server test size. Default: `67108864`.
- `POCKET_STORE_BASE_URL`: Shopify store base URL used to generate mock cart permalinks. Default: `https://roxanneassoulin.com`.
- `POCKET_STORE_CURRENCY`: Currency label for the mock checkout response. Default: `usd`.
- `POCKET_TUNNEL_URL`: Public tunnel URL for the Termux server. Current value: `https://changes-sic-dans-directive.trycloudflare.com/`.
- `POCKET_RESTART_COMMAND`: Optional command used by `/restart`. Default runs `python run_pocket.py`.
- `POCKET_OPS_SESSION_SECONDS`: How long `/ops` stays unlocked in one browser after a valid token. Default: `43200`.
- `POCKET_OPS_HMAC_SECRET`: Optional dedicated secret for signed `/ops` automation requests. If unset, `/ops` uses `POCKET_ACCESS_TOKEN` for HMAC signing.
- `POCKET_OPS_HMAC_MAX_AGE_SECONDS`: Maximum accepted signed `/ops` timestamp age. Default: `300`.
- `CLOUDFLARE_D1_DATABASE`: Maison Flou D1 database name. Default: `maison_flou`.
- `CLOUDFLARE_WORKER_CRON`: Worker cron trigger. Default: `0 9 * * *` UTC.
- `CLOUDFLARE_WORKER_ROUTES`: Comma-separated Worker routes. Default includes `maisonflou.com/api/maison-flou/*` and `maisonflou.com/lab*`.
- `LAB_ACCESS_TOKEN`: Optional dedicated `/lab` token. If unset, `POCKET_ACCESS_TOKEN` is used.
- `LAB_TRUST_CF_ACCESS`: Set to `1` only after Cloudflare Access protects `/lab`.
- `BUFFER_MAISON_FLOU_CHANNEL_ID`: Maison Flou Buffer channel override for the Cloudflare Worker.
- `RESEND_API_KEY`: Resend send-only API key used by the Worker and local tests.

## Maison Flou office loop

Maison Flou now uses Cloudflare for the public and office hot paths:

```text
maisonflou.com waitlist form
  -> Cloudflare Worker
  -> D1 waitlist_leads + office_events
  -> Resend confirmation + atelier notification

maisonflou.com/lab
  -> Cloudflare Worker
  -> D1 office_events + content_runs + content_settings + office_tldr_cache
  -> Buffer API for publishing
  -> Termux only when image/caption processing is needed
```

The private Cloudflare lab dashboard is:

```text
https://maisonflou.com/lab
```

It is token-gated by the Worker now and should also be protected with
Cloudflare Access. Generated social content still uses Termux as the processing
origin while image re-encode/crop relies on local tooling, but Buffer publishing
and the content ledger are now Cloudflare-owned. The legacy Termux processing
endpoint is:

```text
POST /api/maison-flou/content/publish
```

Cloudflare calls it with Buffer disabled, receives image/caption payloads, then
publishes through the Worker and records the run in D1.

Deploy the Worker/D1 schema/cron with:

```bash
node scripts/deploy_cloudflare_worker_direct.mjs
```

The Worker has a `scheduled()` handler and a daily cron. Its D1 setting
`content_scheduler_enabled` defaults to `false`, so cron ticks are logged but do
not publish until explicitly enabled.

For Cloudflare Worker Git builds, use `workers/maison-flou-api/wrangler.toml`
as the deploy root/config and set the same secrets in the Cloudflare dashboard.

## Store prototype

The `/store` prototype uses local snapshots at `pages/store/catalog.json` and `pages/store/data/homepage.json`. The catalog was captured from:

```text
https://roxanneassoulin.com/products.json
```

The browser owns cart state in `localStorage`. The mock checkout endpoint verifies variant IDs and prices against the server-side catalog before returning totals and a Shopify cart permalink. Prototype routes:

```text
/store
/store/collections/<handle>
/store/products/<handle>
/store/cart
/store/api/checkout
```

## Commandments

The working rules for clone and storefront decisions live in [`docs/commandments.md`](docs/commandments.md). The most important one for this repo is browser-first inspection before architecture decisions.

## Cloudflare Pages static export

The public static shell can be exported for Cloudflare Pages with:

```bash
.venv/bin/python scripts/export_pages.py
```

This writes a generated `dist/` folder with `/`, `/bp`, store pages, store assets, catalog JSON, cart JSON, fragments, and a Pages `_headers` file. Configure Cloudflare Pages with:

```text
Build command: python3 -m pip install -r requirements.txt && python3 scripts/export_pages.py
Build output directory: dist
Production branch: master
```

Project architecture notes: [docs/edge-first-architecture.md](/data/data/com.termux/files/home/pocket-app/docs/edge-first-architecture.md)

Do not expose this app publicly without setting `POCKET_ACCESS_TOKEN`. Unattended `/ops` automation should use HMAC headers instead of open mode. The HMAC message is:

```text
METHOD
PATH
TIMESTAMP
BODY
```

Example for `action=pull_restart`:

```bash
BODY='action=pull_restart'
TS="$(date +%s)"
SIG="$(BODY="$BODY" TS="$TS" python - <<'PY'
import hashlib, hmac, os
secret = os.environ["POCKET_OPS_HMAC_SECRET"].encode()
message = b"\n".join([
    b"POST",
    b"/ops",
    os.environ["TS"].encode(),
    os.environ["BODY"].encode(),
])
print(hmac.new(secret, message, hashlib.sha256).hexdigest())
PY
)"

curl -X POST "$POCKET_TUNNEL_URL/ops" \
  -H "X-Pocket-Ops-Timestamp: $TS" \
  -H "X-Pocket-Ops-Signature: sha256=$SIG" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "$BODY"
```

To let Gemini CLI auto-approve tool calls from `/gpt`, set `POCKET_GEMINI_ARGS` to:

```bash
--yolo
```
