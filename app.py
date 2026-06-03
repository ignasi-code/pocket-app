import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
PLACEHOLDER_VALUES = {
    "your-gemini-api-key-here",
    "change-this-before-exposing-the-server",
}


def clean_config_value(value):
    text = str(value or "").strip()
    if text in PLACEHOLDER_VALUES:
        return ""
    return text


def load_local_env():
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = clean_config_value(value.strip().strip('"').strip("'"))
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env()


def current_default_gemini_model():
    return clean_config_value(os.environ.get("POCKET_GEMINI_MODEL")) or "gemini-2.5-flash-lite"


def current_gemini_args():
    return shlex.split(os.environ.get("POCKET_GEMINI_ARGS", "")) or ["-m", current_default_gemini_model()]


DEFAULT_GEMINI_MODEL = current_default_gemini_model()
GEMINI_COMMAND = os.environ.get("POCKET_GEMINI_COMMAND", "gemini")
GEMINI_ARGS = current_gemini_args()
GEMINI_WORKDIR = Path(os.environ.get("POCKET_GEMINI_WORKDIR", BASE_DIR)).expanduser()
GEMINI_TIMEOUT_SECONDS = int(os.environ.get("POCKET_GEMINI_TIMEOUT_SECONDS", "180"))
POCKET_ACCESS_TOKEN = clean_config_value(os.environ.get("POCKET_ACCESS_TOKEN"))
MAX_PROMPT_LENGTH = int(os.environ.get("POCKET_MAX_PROMPT_LENGTH", "12000"))

app = Flask(__name__)


def truthy_env(name):
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def has_gemini_api_key():
    return bool(clean_config_value(os.environ.get("GEMINI_API_KEY")))


def setup_is_open():
    return truthy_env("POCKET_SETUP_ENABLED") or not has_gemini_api_key()


def quote_env_value(value):
    text = str(value or "")
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def write_env_updates(updates):
    existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    written = set()
    next_lines = []

    for raw_line in existing_lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            next_lines.append(raw_line)
            continue

        key, _value = line.split("=", 1)
        key = key.strip()
        if key in updates:
            next_lines.append(f"{key}={quote_env_value(updates[key])}")
            written.add(key)
        else:
            next_lines.append(raw_line)

    for key, value in updates.items():
        if key not in written:
            if next_lines and next_lines[-1].strip():
                next_lines.append("")
            next_lines.append(f"{key}={quote_env_value(value)}")

    ENV_PATH.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")
    os.chmod(ENV_PATH, 0o600)


def refresh_runtime_config(updates):
    global DEFAULT_GEMINI_MODEL, GEMINI_ARGS, POCKET_ACCESS_TOKEN
    for key, value in updates.items():
        os.environ[key] = value
    DEFAULT_GEMINI_MODEL = current_default_gemini_model()
    GEMINI_ARGS = current_gemini_args()
    POCKET_ACCESS_TOKEN = clean_config_value(os.environ.get("POCKET_ACCESS_TOKEN"))


def request_token():
    if request.is_json:
        data = request.get_json(silent=True) or {}
        return str(data.get("token") or request.headers.get("X-Pocket-Token") or "").strip()
    return str(request.form.get("token") or request.headers.get("X-Pocket-Token") or "").strip()


def access_denied():
    return bool(POCKET_ACCESS_TOKEN and request_token() != POCKET_ACCESS_TOKEN)


def restart_current_process():
    def delayed_restart():
        time.sleep(0.8)
        restart_argv = list(sys.argv)
        if restart_argv:
            command = Path(restart_argv[0])
            if not command.exists():
                restart_argv[0] = shutil.which(restart_argv[0]) or restart_argv[0]
        os.execv(sys.executable, [sys.executable, *restart_argv])

    threading.Thread(target=delayed_restart, daemon=True).start()


GPT_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pocket Server GPT</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #111416;
      --panel: #181d20;
      --panel-strong: #20272b;
      --line: #30383d;
      --text: #eef3f2;
      --muted: #a8b3b0;
      --accent: #70d3b4;
      --danger: #ff8e7a;
      --shadow: rgba(0, 0, 0, 0.32);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    main {
      width: min(980px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }

    header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 18px;
    }

    h1 {
      margin: 0;
      font-size: clamp(28px, 4vw, 44px);
      line-height: 1;
      font-weight: 760;
      letter-spacing: 0;
    }

    .meta {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      padding: 0 12px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }

    .dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--accent);
      box-shadow: 0 0 14px rgba(112, 211, 180, 0.6);
    }

    .composer {
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: 0 18px 50px var(--shadow);
    }

    textarea,
    input {
      width: 100%;
      border: 0;
      outline: 0;
      color: var(--text);
      background: transparent;
      font: inherit;
    }

    textarea {
      display: block;
      min-height: 210px;
      resize: vertical;
      padding: 18px;
      line-height: 1.5;
      font-size: 16px;
    }

    .composer-footer {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: center;
      border-top: 1px solid var(--line);
      padding: 12px;
      background: var(--panel-strong);
    }

    .token-wrap {
      display: none;
      border: 1px solid var(--line);
      background: var(--panel);
    }

    .token-wrap[data-visible="true"] {
      display: block;
    }

    input {
      height: 42px;
      padding: 0 12px;
      font-size: 14px;
    }

    button {
      min-width: 118px;
      height: 42px;
      border: 0;
      background: var(--accent);
      color: #07110e;
      font: inherit;
      font-weight: 720;
      cursor: pointer;
    }

    button:disabled {
      cursor: wait;
      opacity: 0.62;
    }

    .output {
      margin-top: 18px;
      border: 1px solid var(--line);
      background: var(--panel);
      min-height: 240px;
    }

    .output-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
    }

    pre {
      margin: 0;
      padding: 16px;
      min-height: 188px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--text);
      font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }

    .error {
      color: var(--danger);
    }

    @media (max-width: 680px) {
      main {
        width: min(100vw - 20px, 980px);
        padding-top: 18px;
      }

      header {
        display: block;
      }

      .status {
        margin-top: 14px;
        width: 100%;
        justify-content: center;
      }

      .composer-footer {
        grid-template-columns: 1fr;
      }

      button {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>GPT</h1>
        <p class="meta">Gemini CLI bridge running in {{ workdir }}</p>
      </div>
      <div class="status"><span class="dot"></span><span id="status">Ready</span></div>
    </header>

    <form class="composer" id="prompt-form">
      <textarea id="prompt" name="prompt" autocomplete="off" spellcheck="true"
        placeholder="Ask Gemini to inspect files, pull the latest repo, restart a service, or explain what it plans to do..."></textarea>
      <div class="composer-footer">
        <div class="token-wrap" data-visible="{{ 'true' if auth_required else 'false' }}">
          <input id="token" name="token" type="password" autocomplete="current-password" placeholder="Pocket access token">
        </div>
        <button id="send" type="submit">Send</button>
      </div>
    </form>

    <section class="output">
      <div class="output-head">
        <span>Gemini output</span>
        <span id="duration"></span>
      </div>
      <pre id="output">Waiting for a prompt.</pre>
    </section>
  </main>

  <script>
    const form = document.getElementById("prompt-form");
    const promptInput = document.getElementById("prompt");
    const tokenInput = document.getElementById("token");
    const sendButton = document.getElementById("send");
    const output = document.getElementById("output");
    const status = document.getElementById("status");
    const duration = document.getElementById("duration");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const prompt = promptInput.value.trim();
      if (!prompt) {
        output.textContent = "Write a prompt first.";
        output.classList.add("error");
        return;
      }

      output.textContent = "";
      output.classList.remove("error");
      duration.textContent = "";
      status.textContent = "Running";
      sendButton.disabled = true;

      const started = performance.now();
      try {
        const response = await fetch("/api/gpt", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt,
            token: tokenInput ? tokenInput.value : ""
          })
        });
        const data = await response.json();
        duration.textContent = data.elapsed_seconds ? `${data.elapsed_seconds}s` : "";

        if (!response.ok) {
          output.textContent = data.error || "Request failed.";
          output.classList.add("error");
          status.textContent = "Error";
          return;
        }

        output.textContent = data.output || "(Gemini returned no output.)";
        status.textContent = "Ready";
      } catch (error) {
        output.textContent = error.message || "Request failed.";
        output.classList.add("error");
        status.textContent = "Error";
        duration.textContent = `${Math.round((performance.now() - started) / 1000)}s`;
      } finally {
        sendButton.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


ACTION_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #101315;
      --panel: #191f22;
      --line: #333b40;
      --text: #eef3f2;
      --muted: #a9b3b0;
      --accent: #72d6b9;
      --danger: #ff927e;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    main {
      width: min(760px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 34px 0;
    }

    h1 {
      margin: 0 0 8px;
      font-size: 34px;
      line-height: 1.08;
      letter-spacing: 0;
    }

    p {
      margin: 0 0 18px;
      color: var(--muted);
      line-height: 1.5;
    }

    form,
    .panel {
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 18px;
    }

    label {
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin: 0 0 8px;
    }

    input {
      width: 100%;
      height: 46px;
      border: 1px solid var(--line);
      background: #111619;
      color: var(--text);
      padding: 0 12px;
      font: inherit;
      outline: 0;
      margin-bottom: 14px;
    }

    button,
    a.button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 0 18px;
      border: 0;
      background: var(--accent);
      color: #07110e;
      font: inherit;
      font-weight: 760;
      cursor: pointer;
      text-decoration: none;
    }

    pre {
      margin: 14px 0 0;
      white-space: pre-wrap;
      word-break: break-word;
      font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      color: var(--text);
    }

    .ok { color: var(--accent); }
    .bad { color: var(--danger); }
    code { color: var(--text); }
  </style>
</head>
<body>
  <main>
    <h1>{{ heading }}</h1>
    <p>{{ description }}</p>

    {% if result %}
      <section class="panel">
        <p class="{{ 'ok' if ok else 'bad' }}">{{ result }}</p>
        {% if output %}
          <pre>{{ output }}</pre>
        {% endif %}
        {% if next_href %}
          <p><a class="button" href="{{ next_href }}">{{ next_label }}</a></p>
        {% endif %}
      </section>
    {% else %}
      <form method="post" action="{{ action }}">
        {% if auth_required %}
          <label for="token">Pocket access token</label>
          <input id="token" name="token" type="password" autocomplete="current-password" required>
        {% endif %}
        <button type="submit">{{ button }}</button>
      </form>
    {% endif %}
  </main>
</body>
</html>
"""


SETUP_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pocket Server Setup</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #101315;
      --panel: #191f22;
      --line: #333b40;
      --text: #eef3f2;
      --muted: #a9b3b0;
      --accent: #72d6b9;
      --danger: #ff927e;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    main {
      width: min(720px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 34px 0;
    }

    h1 {
      margin: 0 0 8px;
      font-size: 34px;
      line-height: 1.08;
      letter-spacing: 0;
    }

    p {
      margin: 0 0 18px;
      color: var(--muted);
      line-height: 1.5;
    }

    form,
    .panel {
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 18px;
    }

    label {
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin: 0 0 8px;
    }

    input {
      width: 100%;
      height: 46px;
      border: 1px solid var(--line);
      background: #111619;
      color: var(--text);
      padding: 0 12px;
      font: inherit;
      outline: 0;
    }

    .field {
      margin-bottom: 14px;
    }

    button {
      height: 44px;
      padding: 0 18px;
      border: 0;
      background: var(--accent);
      color: #07110e;
      font: inherit;
      font-weight: 760;
      cursor: pointer;
    }

    .ok { color: var(--accent); }
    .bad { color: var(--danger); }
    code { color: var(--text); }
  </style>
</head>
<body>
  <main>
    <h1>Pocket Setup</h1>
    <p>Save local Termux configuration without typing secrets in the terminal. This writes <code>.env</code> with private file permissions.</p>

    {% if saved %}
      <section class="panel">
        <p class="ok">Configuration saved.</p>
        <p>Open <code>/gpt</code> to use the Gemini bridge.</p>
      </section>
    {% else %}
      {% if locked %}
        <p>Setup is protected because a Gemini API key is already configured. Enter the Pocket access token to update settings.</p>
      {% endif %}
      {% if error %}
        <p class="bad">{{ error }}</p>
      {% endif %}
      <form method="post" action="/setup">
        {% if locked %}
          <div class="field">
            <label for="setup_token">Current Pocket access token</label>
            <input id="setup_token" name="token" type="password" autocomplete="current-password" required>
          </div>
        {% endif %}
        <div class="field">
          <label for="gemini_api_key">Gemini API key</label>
          <input id="gemini_api_key" name="gemini_api_key" type="password" autocomplete="off" {% if api_key_required %}required{% endif %} placeholder="{{ 'Leave blank to keep existing key' if not api_key_required else '' }}">
        </div>
        <div class="field">
          <label for="pocket_access_token">{{ 'New Pocket access token' if locked else 'Pocket access token' }}</label>
          <input id="pocket_access_token" name="pocket_access_token" type="password" autocomplete="off" placeholder="{{ 'Leave blank to keep existing token' if locked else 'Recommended before using this beyond localhost' }}">
        </div>
        <div class="field">
          <label for="gemini_model">Gemini model</label>
          <input id="gemini_model" name="gemini_model" type="text" value="{{ default_model }}" autocomplete="off">
        </div>
        <div class="field">
          <label for="gemini_args">Gemini extra args</label>
          <input id="gemini_args" name="gemini_args" type="text" value="{{ gemini_args }}" autocomplete="off" placeholder="Example: --yolo">
        </div>
        <button type="submit">Save Configuration</button>
      </form>
    {% endif %}
  </main>
</body>
</html>
"""


@app.route("/")
def home():
    return "Hello, World!"


@app.route("/setup", methods=["GET", "POST"])
def setup_page():
    locked = not setup_is_open()
    if request.method == "GET":
        return render_template_string(
            SETUP_PAGE,
            locked=locked,
            saved=False,
            error="",
            default_model=DEFAULT_GEMINI_MODEL,
            gemini_args=os.environ.get("POCKET_GEMINI_ARGS", ""),
            api_key_required=not has_gemini_api_key(),
        )

    if locked and access_denied():
        return render_template_string(
            SETUP_PAGE,
            locked=locked,
            saved=False,
            error="Invalid Pocket access token.",
            default_model=DEFAULT_GEMINI_MODEL,
            gemini_args=os.environ.get("POCKET_GEMINI_ARGS", ""),
            api_key_required=not has_gemini_api_key(),
        ), 401

    gemini_api_key = clean_config_value(request.form.get("gemini_api_key"))
    pocket_access_token = clean_config_value(request.form.get("pocket_access_token"))
    gemini_model = clean_config_value(request.form.get("gemini_model")) or DEFAULT_GEMINI_MODEL
    gemini_args = clean_config_value(request.form.get("gemini_args"))

    if not gemini_api_key and not has_gemini_api_key():
        return render_template_string(
            SETUP_PAGE,
            locked=False,
            saved=False,
            error="Gemini API key is required.",
            default_model=gemini_model,
            gemini_args=gemini_args,
            api_key_required=True,
        ), 400

    updates = {
        "POCKET_GEMINI_MODEL": gemini_model,
        "POCKET_GEMINI_ARGS": gemini_args,
    }
    if gemini_api_key:
        updates["GEMINI_API_KEY"] = gemini_api_key
    if pocket_access_token:
        updates["POCKET_ACCESS_TOKEN"] = pocket_access_token

    try:
        write_env_updates(updates)
        refresh_runtime_config(updates)
    except OSError as exc:
        return render_template_string(
            SETUP_PAGE,
            locked=False,
            saved=False,
            error=f"Could not save .env: {exc}",
            default_model=gemini_model,
            gemini_args=gemini_args,
            api_key_required=not has_gemini_api_key(),
        ), 500

    return render_template_string(
        SETUP_PAGE,
        locked=False,
        saved=True,
        error="",
        default_model=gemini_model,
        gemini_args=gemini_args,
        api_key_required=not has_gemini_api_key(),
    )


@app.route("/pull", methods=["GET", "POST"])
def pull_page():
    if request.method == "GET":
        return render_template_string(
            ACTION_PAGE,
            title="Pocket Pull",
            heading="Pull",
            description="Fetch and merge the latest code from origin/master.",
            action="/pull",
            button="Pull from Git",
            auth_required=bool(POCKET_ACCESS_TOKEN),
            result="",
            output="",
            ok=False,
        )

    if access_denied():
        return render_template_string(
            ACTION_PAGE,
            title="Pocket Pull",
            heading="Pull",
            description="Fetch and merge the latest code from origin/master.",
            action="/pull",
            button="Pull from Git",
            auth_required=bool(POCKET_ACCESS_TOKEN),
            result="Invalid Pocket access token.",
            output="",
            ok=False,
        ), 401

    started = time.time()
    result = subprocess.run(
        ["git", "pull", "origin", "master"],
        cwd=str(BASE_DIR),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    elapsed = round(time.time() - started, 2)
    ok = result.returncode == 0
    message = f"Pull completed in {elapsed}s." if ok else f"Pull failed with code {result.returncode}."

    return render_template_string(
        ACTION_PAGE,
        title="Pocket Pull",
        heading="Pull",
        description="Fetch and merge the latest code from origin/master.",
        action="/pull",
        button="Pull from Git",
        auth_required=bool(POCKET_ACCESS_TOKEN),
        result=message,
        output=output,
        ok=ok,
        next_href="/restart" if ok else "",
        next_label="Restart Server",
    ), 200 if ok else 502


@app.route("/restart", methods=["GET", "POST"])
def restart_page():
    if request.method == "GET":
        return render_template_string(
            ACTION_PAGE,
            title="Pocket Restart",
            heading="Restart",
            description="Restart the current Pocket Server process with the same command.",
            action="/restart",
            button="Restart Server",
            auth_required=bool(POCKET_ACCESS_TOKEN),
            result="",
            output="",
            ok=False,
        )

    if access_denied():
        return render_template_string(
            ACTION_PAGE,
            title="Pocket Restart",
            heading="Restart",
            description="Restart the current Pocket Server process with the same command.",
            action="/restart",
            button="Restart Server",
            auth_required=bool(POCKET_ACCESS_TOKEN),
            result="Invalid Pocket access token.",
            output="",
            ok=False,
        ), 401

    restart_current_process()
    return render_template_string(
        ACTION_PAGE,
        title="Pocket Restart",
        heading="Restart",
        description="Restart the current Pocket Server process with the same command.",
        action="/restart",
        button="Restart Server",
        auth_required=bool(POCKET_ACCESS_TOKEN),
        result="Restart requested. Wait a moment, then reload the page.",
        output="",
        ok=True,
    )


@app.route("/gpt")
def gpt_page():
    return render_template_string(
        GPT_PAGE,
        auth_required=bool(POCKET_ACCESS_TOKEN),
        workdir=str(GEMINI_WORKDIR),
    )


@app.route("/api/gpt", methods=["POST"])
def run_gemini_prompt():
    data = request.get_json(silent=True) or {}
    prompt = str(data.get("prompt") or "").strip()

    if access_denied():
        return jsonify({"error": "Invalid Pocket access token."}), 401

    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400

    if len(prompt) > MAX_PROMPT_LENGTH:
        return jsonify({"error": f"Prompt is too long. Limit is {MAX_PROMPT_LENGTH} characters."}), 400

    if not GEMINI_WORKDIR.exists():
        return jsonify({"error": f"Gemini workdir does not exist: {GEMINI_WORKDIR}"}), 500

    command = [GEMINI_COMMAND, *GEMINI_ARGS, "-p", prompt]
    started = time.time()
    try:
        result = subprocess.run(
            command,
            cwd=str(GEMINI_WORKDIR),
            text=True,
            capture_output=True,
            timeout=GEMINI_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return jsonify({
            "error": f"Gemini CLI not found: {GEMINI_COMMAND}",
            "hint": "Install Gemini CLI on the server or set POCKET_GEMINI_COMMAND.",
        }), 500
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part).strip()
        return jsonify({
            "error": f"Gemini timed out after {GEMINI_TIMEOUT_SECONDS} seconds.",
            "output": output,
            "elapsed_seconds": round(time.time() - started, 2),
        }), 504

    output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    response = {
        "output": output,
        "returncode": result.returncode,
        "elapsed_seconds": round(time.time() - started, 2),
    }

    if result.returncode != 0:
        response["error"] = f"Gemini exited with code {result.returncode}."
        return jsonify(response), 502

    return jsonify(response)


if __name__ == "__main__":
    host = os.environ.get("POCKET_HOST", "127.0.0.1")
    port = int(os.environ.get("POCKET_PORT", "5052"))
    app.run(host=host, port=port, debug=True)
