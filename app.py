import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template_string, request, send_file


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
TERMINAL_TIMEOUT_SECONDS = int(os.environ.get("POCKET_TERMINAL_TIMEOUT_SECONDS", "120"))
TERMINAL_MAX_COMMAND_LENGTH = int(os.environ.get("POCKET_TERMINAL_MAX_COMMAND_LENGTH", "20000"))
FAST_DEFAULT_DOWNLOAD_BYTES = int(os.environ.get("POCKET_FAST_DOWNLOAD_BYTES", str(16 * 1024 * 1024)))
FAST_DEFAULT_UPLOAD_BYTES = int(os.environ.get("POCKET_FAST_UPLOAD_BYTES", str(8 * 1024 * 1024)))
FAST_MAX_DOWNLOAD_BYTES = int(os.environ.get("POCKET_FAST_MAX_DOWNLOAD_BYTES", str(64 * 1024 * 1024)))
FAST_MAX_UPLOAD_BYTES = int(os.environ.get("POCKET_FAST_MAX_UPLOAD_BYTES", str(64 * 1024 * 1024)))
FAST_CHUNK_BYTES = bytes((index % 251 for index in range(64 * 1024)))

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


def get_ram_info():
    info = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    value = int(parts[1])
                    info[key] = value
        return {
            "total": info.get("MemTotal", 0),
            "available": info.get("MemAvailable", info.get("MemFree", 0) + info.get("Buffers", 0) + info.get("Cached", 0)),
        }
    except Exception:
        return None


def get_storage_info():
    try:
        usage = shutil.disk_usage("/")
        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
        }
    except Exception:
        return None


def get_battery_info():
    try:
        result = subprocess.run(
            ["termux-battery-status"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {"error": "termux-battery-status failed"}
    except FileNotFoundError:
        return {"error": "termux-api not installed"}
    except Exception as e:
        return {"error": str(e)}


def get_system_info():
    try:
        uptime_str = "Unknown"
        try:
            with open("/proc/uptime", "r") as f:
                uptime_seconds = float(f.readline().split()[0])
                hours = int(uptime_seconds // 3600)
                minutes = int((uptime_seconds % 3600) // 60)
                seconds = int(uptime_seconds % 60)
                uptime_str = f"{hours}h {minutes}m {seconds}s"
        except Exception:
            pass

        return {
            "platform": platform.platform(),
            "uptime": uptime_str,
            "load": os.getloadavg() if hasattr(os, "getloadavg") else [0, 0, 0],
        }
    except Exception:
        return None


def parse_positive_int(value, default, maximum):
    try:
        number = int(str(value or "").strip())
    except ValueError:
        number = default
    return max(1, min(number, maximum))


def stream_test_bytes(total_bytes):
    remaining = total_bytes
    while remaining:
        chunk_size = min(remaining, len(FAST_CHUNK_BYTES))
        yield FAST_CHUNK_BYTES[:chunk_size]
        remaining -= chunk_size


def terminal_shell_command():
    shell = (
        os.environ.get("POCKET_TERMINAL_SHELL")
        or shutil.which("bash")
        or shutil.which("sh")
        or "/bin/sh"
    )
    return [shell, "-lc"]


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

    nav {
      margin-top: 12px;
      display: flex;
      gap: 16px;
    }

    nav a {
      color: var(--muted);
      text-decoration: none;
      font-size: 13px;
      font-weight: 600;
      transition: color 0.2s;
    }

    nav a:hover {
      color: var(--accent);
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

    .output-tools {
      display: inline-flex;
      align-items: center;
      gap: 10px;
    }

    .raw-toggle {
      min-width: 0;
      height: 28px;
      padding: 0 10px;
      border: 1px solid var(--line);
      background: transparent;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }

    .raw-toggle[data-active="true"] {
      color: var(--accent);
      border-color: var(--accent);
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

    .raw-panel {
      display: none;
      border-top: 1px solid var(--line);
      background: #0a0d0e;
    }

    .raw-panel[data-visible="true"] {
      display: block;
    }

    .raw-panel pre {
      min-height: 120px;
      max-height: 320px;
      color: var(--muted);
    }

    .typing::after {
      content: "|";
      color: var(--accent);
      animation: blink 0.85s step-end infinite;
    }

    @keyframes blink {
      50% { opacity: 0; }
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
        <nav>
          <a href="/stats">STATS</a>
          <a href="/fast">FAST</a>
          <a href="/setup">SETUP</a>
        </nav>
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
        <div class="output-tools">
          <span id="duration"></span>
          <button class="raw-toggle" id="raw-toggle" type="button" data-active="false">Raw</button>
        </div>
      </div>
      <pre id="output">Waiting for a prompt.</pre>
      <div class="raw-panel" id="raw-panel" data-visible="false">
        <pre id="raw-output">No response yet.</pre>
      </div>
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
    const rawToggle = document.getElementById("raw-toggle");
    const rawPanel = document.getElementById("raw-panel");
    const rawOutput = document.getElementById("raw-output");
    let typingTimer = 0;
    let typingRun = 0;

    rawToggle.addEventListener("click", () => {
      const visible = rawPanel.dataset.visible !== "true";
      rawPanel.dataset.visible = visible ? "true" : "false";
      rawToggle.dataset.active = visible ? "true" : "false";
    });

    function stopTyping() {
      typingRun += 1;
      if (typingTimer) {
        window.clearTimeout(typingTimer);
        typingTimer = 0;
      }
      output.classList.remove("typing");
    }

    function parseJsonResponse(text) {
      try {
        return JSON.parse(text);
      } catch (_error) {
        return {
          error: "Response was not JSON. Open Raw to inspect the HTTP response.",
          output: text
        };
      }
    }

    function setRawResponse(details) {
      const lines = [
        `HTTP ${details.status} ${details.statusText || ""}`.trim(),
        `Content-Type: ${details.contentType || "(missing)"}`,
        "",
        details.body || "(empty body)"
      ];
      rawOutput.textContent = lines.join("\\n");
    }

    async function typeOutput(text) {
      const fullText = text || "(Gemini returned no output.)";
      const runId = typingRun + 1;
      typingRun = runId;
      output.textContent = "";
      output.classList.add("typing");

      const charsPerTick = Math.max(2, Math.ceil(fullText.length / 180));
      const tickMs = 12;
      let index = 0;

      return new Promise((resolve) => {
        function tick() {
          if (runId !== typingRun) {
            resolve();
            return;
          }

          index = Math.min(index + charsPerTick, fullText.length);
          output.textContent = fullText.slice(0, index);
          output.scrollTop = output.scrollHeight;

          if (index >= fullText.length) {
            output.classList.remove("typing");
            typingTimer = 0;
            resolve();
            return;
          }

          typingTimer = window.setTimeout(tick, tickMs);
        }

        tick();
      });
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const prompt = promptInput.value.trim();
      if (!prompt) {
        stopTyping();
        output.textContent = "Write a prompt first.";
        output.classList.add("error");
        return;
      }

      stopTyping();
      output.textContent = "";
      output.classList.remove("error");
      duration.textContent = "";
      rawOutput.textContent = "Waiting for response.";
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
        const responseText = await response.text();
        setRawResponse({
          status: response.status,
          statusText: response.statusText,
          contentType: response.headers.get("Content-Type"),
          body: responseText
        });
        const data = parseJsonResponse(responseText);
        duration.textContent = data.elapsed_seconds ? `${data.elapsed_seconds}s` : "";

        if (!response.ok) {
          output.textContent = data.error || "Request failed.";
          output.classList.add("error");
          status.textContent = "Error";
          return;
        }

        status.textContent = "Typing";
        await typeOutput(data.output || "(Gemini returned no output.)");
        status.textContent = "Ready";
      } catch (error) {
        stopTyping();
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


TERMINAL_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pocket Terminal</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0f1214;
      --panel: #171c1f;
      --panel-strong: #20262a;
      --line: #333b40;
      --text: #edf3f1;
      --muted: #a7b2ae;
      --accent: #73d8ba;
      --danger: #ff927e;
      --shadow: rgba(0, 0, 0, 0.34);
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
      gap: 18px;
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
      min-height: 34px;
      padding: 8px 12px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }

    .terminal {
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
      font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }

    textarea {
      display: block;
      min-height: 260px;
      resize: vertical;
      padding: 18px;
    }

    .footer {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: center;
      border-top: 1px solid var(--line);
      padding: 12px;
      background: var(--panel-strong);
    }

    .token-wrap {
      border: 1px solid var(--line);
      background: var(--panel);
    }

    input {
      height: 42px;
      padding: 0 12px;
    }

    button {
      min-width: 118px;
      height: 42px;
      border: 0;
      background: var(--accent);
      color: #07110e;
      font: inherit;
      font-weight: 760;
      cursor: pointer;
    }

    button:disabled {
      cursor: wait;
      opacity: 0.62;
    }

    .output {
      margin-top: 18px;
      border: 1px solid var(--line);
      background: #080b0c;
    }

    .output-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 14px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
    }

    pre {
      margin: 0;
      min-height: 240px;
      max-height: 58vh;
      overflow: auto;
      padding: 16px;
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--text);
      font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }

    .bad { color: var(--danger); }

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
      }

      .footer {
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
        <h1>Pocket Terminal</h1>
        <p class="meta">Paste shell commands and run them on this server in {{ workdir }}.</p>
      </div>
      <div class="status" id="status">Ready</div>
    </header>

    <form class="terminal" id="terminal-form">
      <textarea id="command" spellcheck="false" autocomplete="off" placeholder="cd ~/pocket-app
curl -i -X POST http://127.0.0.1:5052/api/gpt \\
  -H 'Content-Type: application/json' \\
  -d '{&quot;prompt&quot;:&quot;say hello&quot;,&quot;token&quot;:&quot;YOUR_POCKET_TOKEN&quot;}'"></textarea>
      <div class="footer">
        <div class="token-wrap">
          <input id="token" type="password" autocomplete="current-password" placeholder="Pocket access token" required>
        </div>
        <button id="run" type="submit">Run</button>
      </div>
    </form>

    <section class="output">
      <div class="output-head">
        <span>Output</span>
        <span id="duration"></span>
      </div>
      <pre id="output">Waiting for a command.</pre>
    </section>
  </main>

  <script>
    const form = document.getElementById("terminal-form");
    const commandInput = document.getElementById("command");
    const tokenInput = document.getElementById("token");
    const runButton = document.getElementById("run");
    const output = document.getElementById("output");
    const status = document.getElementById("status");
    const duration = document.getElementById("duration");

    tokenInput.value = sessionStorage.getItem("pocket-terminal-token") || "";
    tokenInput.addEventListener("input", () => {
      sessionStorage.setItem("pocket-terminal-token", tokenInput.value.trim());
    });

    function formatTerminalResult(data) {
      const lines = [];
      if (data.error) {
        lines.push(data.error);
      }
      if (Number.isInteger(data.returncode)) {
        lines.push(`Exit ${data.returncode}`);
      }
      if (data.output) {
        if (lines.length) {
          lines.push("");
        }
        lines.push(data.output);
      }
      return lines.join("\\n") || "Command failed.";
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const command = commandInput.value.trim();
      if (!command) {
        output.textContent = "Paste a command first.";
        output.classList.add("bad");
        return;
      }

      output.textContent = "";
      output.classList.remove("bad");
      duration.textContent = "";
      status.textContent = "Running";
      runButton.disabled = true;

      const started = performance.now();
      try {
        const response = await fetch("/api/terminal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            command,
            token: tokenInput.value
          })
        });
        const text = await response.text();
        let data = {};
        try {
          data = JSON.parse(text);
        } catch (_error) {
          data = { error: `HTTP ${response.status} returned non-JSON:\\n${text}` };
        }

        duration.textContent = data.elapsed_seconds ? `${data.elapsed_seconds}s` : "";
        if (!response.ok) {
          output.textContent = formatTerminalResult(data);
          output.classList.add("bad");
          status.textContent = Number.isInteger(data.returncode) ? `Exit ${data.returncode}` : "Error";
          return;
        }

        output.textContent = data.output || "(Command returned no output.)";
        status.textContent = `Exit ${data.returncode}`;
      } catch (error) {
        output.textContent = error.message || "Command failed.";
        output.classList.add("bad");
        status.textContent = "Error";
        duration.textContent = `${Math.round((performance.now() - started) / 1000)}s`;
      } finally {
        runButton.disabled = false;
      }
    });
  </script>
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
    return send_file(BASE_DIR / "pages" / "index.html")


@app.route("/terminal")
def terminal_page():
    return render_template_string(
        TERMINAL_PAGE,
        workdir=str(BASE_DIR),
    )


@app.route("/api/terminal", methods=["POST"])
def run_terminal_command():
    data = request.get_json(silent=True) or {}
    command = str(data.get("command") or "").strip()

    if not POCKET_ACCESS_TOKEN:
        return jsonify({
            "error": "Set POCKET_ACCESS_TOKEN before using /terminal.",
        }), 403

    if access_denied():
        return jsonify({"error": "Invalid Pocket access token."}), 401

    if not command:
        return jsonify({"error": "Command is required."}), 400

    if len(command) > TERMINAL_MAX_COMMAND_LENGTH:
        return jsonify({
            "error": f"Command is too long. Limit is {TERMINAL_MAX_COMMAND_LENGTH} characters.",
        }), 400

    started = time.time()
    try:
        result = subprocess.run(
            [*terminal_shell_command(), command],
            cwd=str(BASE_DIR),
            text=True,
            capture_output=True,
            timeout=TERMINAL_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return jsonify({
            "error": "Terminal shell not found. Set POCKET_TERMINAL_SHELL.",
        }), 500
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part).strip()
        return jsonify({
            "error": f"Command timed out after {TERMINAL_TIMEOUT_SECONDS} seconds.",
            "output": output,
            "elapsed_seconds": round(time.time() - started, 2),
        }), 504

    output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    return jsonify({
        "output": output,
        "returncode": result.returncode,
        "elapsed_seconds": round(time.time() - started, 2),
    }), 200 if result.returncode == 0 else 502


@app.route("/fast")
@app.route("/fast/")
def fast_page():
    return send_file(BASE_DIR / "pages" / "fast" / "index.html")


@app.route("/fast/api/download")
def fast_download():
    if access_denied():
        return jsonify({"error": "Invalid Pocket access token."}), 401

    total_bytes = parse_positive_int(
        request.args.get("bytes"),
        FAST_DEFAULT_DOWNLOAD_BYTES,
        FAST_MAX_DOWNLOAD_BYTES,
    )
    response = Response(
        stream_test_bytes(total_bytes),
        content_type="application/octet-stream",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Length"] = str(total_bytes)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/fast/api/upload", methods=["POST"])
def fast_upload():
    if access_denied():
        return jsonify({"error": "Invalid Pocket access token."}), 401

    if request.content_length and request.content_length > FAST_MAX_UPLOAD_BYTES:
        return jsonify({
            "error": f"Upload is too large. Limit is {FAST_MAX_UPLOAD_BYTES} bytes.",
        }), 413

    started = time.time()
    total_bytes = 0
    while True:
        chunk = request.stream.read(64 * 1024)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > FAST_MAX_UPLOAD_BYTES:
            return jsonify({
                "error": f"Upload is too large. Limit is {FAST_MAX_UPLOAD_BYTES} bytes.",
            }), 413

    return jsonify({
        "bytes": total_bytes,
        "elapsed_seconds": round(time.time() - started, 4),
    })


@app.route("/stats")
@app.route("/stats/")
def stats_page():
    return send_file(BASE_DIR / "pages" / "stats" / "index.html")


@app.route("/api/stats")
def api_stats():
    return jsonify({
        "battery": get_battery_info(),
        "ram": get_ram_info(),
        "storage": get_storage_info(),
        "system": get_system_info(),
    })


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
