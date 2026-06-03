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
POCKET_HOST=0.0.0.0 POCKET_PORT=5052 flask --app app run --host 0.0.0.0 --port 5052
```

Then open `/setup` in a browser to paste your Gemini API key and save `.env`.

Control pages:

- `/`: BODY POWER landing page.
- `/stats`: Dashboard for battery, storage, RAM, and system info.
- `/fast`: Pocket Fast speed test for the Termux tunnel.
- `/gpt`: Gemini CLI prompt bridge.
- `/terminal`: Token-protected browser terminal for pasted shell commands.
- `/setup`: Save local `.env` config from the browser.
- `/pull`: Run `git pull origin master`.
- `/restart`: Restart the current Pocket Server process.

The `/gpt` page sends prompts to the local Gemini CLI with:

```bash
gemini -m gemini-2.5-flash-lite -p "<prompt>"
```

## Configuration

- `GEMINI_API_KEY`: Gemini API key from Google AI Studio. Used by Gemini CLI.
- `POCKET_GEMINI_MODEL`: Gemini model for the bridge. Default: `gemini-2.5-flash-lite`.
- `POCKET_GEMINI_COMMAND`: Gemini executable name or path. Default: `gemini`.
- `POCKET_GEMINI_ARGS`: Extra Gemini CLI arguments, split like shell args. Overrides `POCKET_GEMINI_MODEL` when set.
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

Do not expose this app publicly without setting `POCKET_ACCESS_TOKEN`.

To let Gemini CLI auto-approve tool calls from `/gpt`, set `POCKET_GEMINI_ARGS` to:

```bash
--yolo
```
