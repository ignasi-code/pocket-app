import os
import shlex
import subprocess
import time
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template_string, request


BASE_DIR = Path(__file__).resolve().parent
GEMINI_COMMAND = os.environ.get("POCKET_GEMINI_COMMAND", "gemini")
GEMINI_ARGS = shlex.split(os.environ.get("POCKET_GEMINI_ARGS", ""))
GEMINI_WORKDIR = Path(os.environ.get("POCKET_GEMINI_WORKDIR", BASE_DIR)).expanduser()
GEMINI_TIMEOUT_SECONDS = int(os.environ.get("POCKET_GEMINI_TIMEOUT_SECONDS", "180"))
POCKET_ACCESS_TOKEN = os.environ.get("POCKET_ACCESS_TOKEN", "").strip()
MAX_PROMPT_LENGTH = int(os.environ.get("POCKET_MAX_PROMPT_LENGTH", "12000"))

app = Flask(__name__)


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


@app.route("/")
def home():
    return redirect("/gpt")


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
    token = str(data.get("token") or request.headers.get("X-Pocket-Token") or "").strip()

    if POCKET_ACCESS_TOKEN and token != POCKET_ACCESS_TOKEN:
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
