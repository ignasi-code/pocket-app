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

Control pages:

- `/`: BODY POWER landing page.
- `/stats`: Dashboard for battery, storage, RAM, and system info.
- `/fast`: Pocket Fast speed test for the Termux tunnel.
- `/gpt`: Gemini CLI prompt bridge.
- `/store`: Public static-first Shopify storefront prototype with home, collection, product, cart, and mock checkout.
- `/terminal`: Token-protected browser terminal for pasted shell commands.
- `/setup`: Save local `.env` config from the browser.
- `/ops`: Unlock once, then run pull, restart, or pull then restart from one page.
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
- `POCKET_RESTART_COMMAND`: Optional command used by `/restart`. Default runs `python run_pocket.py`.
- `POCKET_OPS_SESSION_SECONDS`: How long `/ops` stays unlocked in one browser after a valid token. Default: `43200`.
- `POCKET_OPS_OPEN`: Set to `1` only when you intentionally want `/ops` pull/restart actions to work without a token through the public tunnel.

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

Do not expose this app publicly without setting `POCKET_ACCESS_TOKEN`. Leave `POCKET_OPS_OPEN` unset or `0` unless you are deliberately allowing unattended tunnel operations for a short window.

To let Gemini CLI auto-approve tool calls from `/gpt`, set `POCKET_GEMINI_ARGS` to:

```bash
--yolo
```
