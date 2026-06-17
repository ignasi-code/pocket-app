import json
import hashlib
import html as html_lib
import hmac
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Flask, Response, abort, jsonify, make_response, render_template, render_template_string, request, send_file

from office.shared.social.buffer_client import BufferApiError, create_post, get_account, get_channels, get_organizations


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
SHARED_CLOUDFLARE_ENV_PATH = Path.home() / ".config" / "codex-shared" / "cloudflare.env"
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
    extra_args = shlex.split(os.environ.get("POCKET_GEMINI_ARGS", ""))
    return ["-m", current_default_gemini_model(), *extra_args]


DEFAULT_GEMINI_MODEL = current_default_gemini_model()
GEMINI_COMMAND = os.environ.get("POCKET_GEMINI_COMMAND", "gemini")
GEMINI_ARGS = current_gemini_args()
GEMINI_WORKDIR = Path(os.environ.get("POCKET_GEMINI_WORKDIR", BASE_DIR)).expanduser()
GEMINI_TIMEOUT_SECONDS = int(os.environ.get("POCKET_GEMINI_TIMEOUT_SECONDS", "180"))
POCKET_ACCESS_TOKEN = clean_config_value(os.environ.get("POCKET_ACCESS_TOKEN"))
BUFFER_API_KEY = clean_config_value(os.environ.get("BUFFER_API_KEY"))
BUFFER_ORGANIZATION_ID = clean_config_value(os.environ.get("BUFFER_ORGANIZATION_ID"))
BUFFER_CHANNEL_ID = clean_config_value(os.environ.get("BUFFER_CHANNEL_ID"))
BUFFER_DEFAULT_MODE = clean_config_value(os.environ.get("BUFFER_DEFAULT_MODE")) or "addToQueue"
UPTIMEROBOT_STATUS_PAGE_URL = clean_config_value(os.environ.get("UPTIMEROBOT_STATUS_PAGE_URL"))
UPTIMEROBOT_BADGE_URL = clean_config_value(os.environ.get("UPTIMEROBOT_BADGE_URL"))
OPS_HMAC_SECRET = clean_config_value(os.environ.get("POCKET_OPS_HMAC_SECRET"))
OPS_SESSION_COOKIE = "pocket_ops_session"
DEFAULT_OPS_SESSION_SECONDS = 12 * 60 * 60
DEFAULT_OPS_HMAC_MAX_AGE_SECONDS = 5 * 60
MAX_PROMPT_LENGTH = int(os.environ.get("POCKET_MAX_PROMPT_LENGTH", "12000"))
TERMINAL_TIMEOUT_SECONDS = int(os.environ.get("POCKET_TERMINAL_TIMEOUT_SECONDS", "120"))
TERMINAL_MAX_COMMAND_LENGTH = int(os.environ.get("POCKET_TERMINAL_MAX_COMMAND_LENGTH", "20000"))
FAST_DEFAULT_DOWNLOAD_BYTES = int(os.environ.get("POCKET_FAST_DOWNLOAD_BYTES", str(16 * 1024 * 1024)))
FAST_DEFAULT_UPLOAD_BYTES = int(os.environ.get("POCKET_FAST_UPLOAD_BYTES", str(8 * 1024 * 1024)))
FAST_MAX_DOWNLOAD_BYTES = int(os.environ.get("POCKET_FAST_MAX_DOWNLOAD_BYTES", str(64 * 1024 * 1024)))
FAST_MAX_UPLOAD_BYTES = int(os.environ.get("POCKET_FAST_MAX_UPLOAD_BYTES", str(64 * 1024 * 1024)))
FAST_CHUNK_BYTES = bytes((index % 251 for index in range(64 * 1024)))
STORE_CATALOG_PATH = BASE_DIR / "pages" / "store" / "catalog.json"
STORE_DATA_DIR = BASE_DIR / "pages" / "store" / "data"
STORE_PLACEHOLDER_IMAGE = "https://placehold.co/900x1100/f8dd5f/1f1a15?text=Roxanne"
STORE_BASE_URL = os.environ.get("POCKET_STORE_BASE_URL", "https://roxanneassoulin.com").rstrip("/")
STORE_CURRENCY = os.environ.get("POCKET_STORE_CURRENCY", "usd").lower()
STORE_DISPLAY_CURRENCY = os.environ.get("POCKET_STORE_DISPLAY_CURRENCY", "eur").lower()
STORE_DISPLAY_EUR_RATE = float(os.environ.get("POCKET_STORE_DISPLAY_EUR_RATE", "0.875"))
STORE_COLLECTION_INITIAL_PRODUCT_LIMIT = 12
STORE_IMAGE_QUALITY = 60
STORE_HTML_BROWSER_CACHE_SECONDS = 300
STORE_HTML_EDGE_CACHE_SECONDS = 86400
STORE_DATA_BROWSER_CACHE_SECONDS = 3600
STORE_DATA_EDGE_CACHE_SECONDS = 86400
STORE_ASSET_CACHE_SECONDS = 31536000
STORE_CART_UPSELL_HANDLES = [
    "the-salt-pepper-cylinder-bracelet-stack",
    "the-pearl-branch-bracelet",
    "the-paprika-necklace-duo",
    "the-netted-stone-pendant",
]
PWA_DIR = BASE_DIR / "pages" / "pwa"
PWA_BROWSER_CACHE_SECONDS = 300
PWA_DATA_BROWSER_CACHE_SECONDS = 3600
STORE_SWATCH_COLORS = {
    "cloud": "#8ED1D1",
    "lemon": "#E3D43C",
    "sienna": "#C75530",
    "salt & pepper": "#1f1f1f",
}
SHOPIFY_LEGACY_IMAGE_SIZE_RE = re.compile(
    r"_(?:\d+x\d*|\d*x\d+|x\d+)(?:_crop_[^./@]+)?(?:@2x)?(?=\.(?:jpe?g|png|webp)$)",
    re.IGNORECASE,
)
RESTART_LOG_PATH = BASE_DIR / "pocket-restart.log"

app = Flask(__name__)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True


def truthy_env(name):
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def has_gemini_api_key():
    return bool(clean_config_value(os.environ.get("GEMINI_API_KEY")))


def has_buffer_api_key():
    return bool(clean_config_value(os.environ.get("BUFFER_API_KEY")))


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


def write_shared_cloudflare_env(updates):
    SHARED_CLOUDFLARE_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = SHARED_CLOUDFLARE_ENV_PATH.read_text(encoding="utf-8").splitlines() if SHARED_CLOUDFLARE_ENV_PATH.exists() else []
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

    SHARED_CLOUDFLARE_ENV_PATH.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")
    os.chmod(SHARED_CLOUDFLARE_ENV_PATH, 0o600)


def refresh_runtime_config(updates):
    global DEFAULT_GEMINI_MODEL, GEMINI_ARGS, POCKET_ACCESS_TOKEN, BUFFER_API_KEY, BUFFER_ORGANIZATION_ID, BUFFER_CHANNEL_ID, BUFFER_DEFAULT_MODE, UPTIMEROBOT_STATUS_PAGE_URL, UPTIMEROBOT_BADGE_URL, OPS_HMAC_SECRET
    for key, value in updates.items():
        os.environ[key] = value
    DEFAULT_GEMINI_MODEL = current_default_gemini_model()
    GEMINI_ARGS = current_gemini_args()
    POCKET_ACCESS_TOKEN = clean_config_value(os.environ.get("POCKET_ACCESS_TOKEN"))
    BUFFER_API_KEY = clean_config_value(os.environ.get("BUFFER_API_KEY"))
    BUFFER_ORGANIZATION_ID = clean_config_value(os.environ.get("BUFFER_ORGANIZATION_ID"))
    BUFFER_CHANNEL_ID = clean_config_value(os.environ.get("BUFFER_CHANNEL_ID"))
    BUFFER_DEFAULT_MODE = clean_config_value(os.environ.get("BUFFER_DEFAULT_MODE")) or "addToQueue"
    UPTIMEROBOT_STATUS_PAGE_URL = clean_config_value(os.environ.get("UPTIMEROBOT_STATUS_PAGE_URL"))
    UPTIMEROBOT_BADGE_URL = clean_config_value(os.environ.get("UPTIMEROBOT_BADGE_URL"))
    OPS_HMAC_SECRET = clean_config_value(os.environ.get("POCKET_OPS_HMAC_SECRET"))


def request_token():
    if request.is_json:
        data = request.get_json(silent=True) or {}
        return str(data.get("token") or request.headers.get("X-Pocket-Token") or "").strip()
    return str(request.form.get("token") or request.headers.get("X-Pocket-Token") or "").strip()


def access_denied():
    return bool(POCKET_ACCESS_TOKEN and request_token() != POCKET_ACCESS_TOKEN)


def current_ops_session_seconds():
    raw_value = clean_config_value(os.environ.get("POCKET_OPS_SESSION_SECONDS"))
    if not raw_value:
        return DEFAULT_OPS_SESSION_SECONDS
    try:
        seconds = int(raw_value)
    except ValueError:
        return DEFAULT_OPS_SESSION_SECONDS
    return max(60, min(seconds, 7 * 24 * 60 * 60))


def current_ops_hmac_max_age_seconds():
    raw_value = clean_config_value(os.environ.get("POCKET_OPS_HMAC_MAX_AGE_SECONDS"))
    if not raw_value:
        return DEFAULT_OPS_HMAC_MAX_AGE_SECONDS
    try:
        seconds = int(raw_value)
    except ValueError:
        return DEFAULT_OPS_HMAC_MAX_AGE_SECONDS
    return max(30, min(seconds, 60 * 60))


def current_ops_hmac_secret():
    return OPS_HMAC_SECRET or POCKET_ACCESS_TOKEN


def ops_hmac_message(method, path, timestamp, body):
    return b"\n".join([
        method.upper().encode("utf-8"),
        path.encode("utf-8"),
        str(timestamp).encode("utf-8"),
        body,
    ])


def normalize_hmac_signature(signature):
    text = str(signature or "").strip()
    if text.lower().startswith("sha256="):
        text = text.split("=", 1)[1]
    return text.lower()


def ops_hmac_authorized():
    secret = current_ops_hmac_secret()
    if not secret:
        return False

    timestamp = str(request.headers.get("X-Pocket-Ops-Timestamp") or "").strip()
    signature = normalize_hmac_signature(request.headers.get("X-Pocket-Ops-Signature"))
    if not timestamp or not signature:
        return False

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return False

    if abs(int(time.time()) - timestamp_int) > current_ops_hmac_max_age_seconds():
        return False

    body = request.get_data(cache=True) or b""
    message = ops_hmac_message(request.method, request.path, timestamp, body)
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def ops_hmac_request_present():
    return bool(request.headers.get("X-Pocket-Ops-Timestamp") or request.headers.get("X-Pocket-Ops-Signature"))


def sign_ops_session(expires_at):
    if not POCKET_ACCESS_TOKEN:
        return ""
    payload = str(expires_at).encode("utf-8")
    secret = POCKET_ACCESS_TOKEN.encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def create_ops_session_value():
    expires_at = int(time.time() + current_ops_session_seconds())
    return f"{expires_at}.{sign_ops_session(expires_at)}"


def ops_session_valid():
    value = request.cookies.get(OPS_SESSION_COOKIE, "")
    try:
        expires_text, signature = value.split(".", 1)
        expires_at = int(expires_text)
    except ValueError:
        return False
    if expires_at < int(time.time()):
        return False
    expected = sign_ops_session(expires_at)
    return bool(expected and hmac.compare_digest(signature, expected))


def ops_authorized():
    if ops_hmac_request_present():
        return (True, False, "") if ops_hmac_authorized() else (False, False, "Invalid ops signature.")
    if not POCKET_ACCESS_TOKEN and not current_ops_hmac_secret():
        return True, False, ""
    if ops_session_valid():
        return True, False, ""
    if request_token() == POCKET_ACCESS_TOKEN:
        return True, True, ""
    if request_token():
        return False, False, "Invalid Pocket access token."
    if current_ops_hmac_secret():
        return False, False, "Invalid ops signature."
    return False, False, "Invalid Pocket access token."


def ops_auth_label():
    if not POCKET_ACCESS_TOKEN:
        return "No Pocket access token is configured. Signed automation requests can use HMAC headers."
    if ops_session_valid():
        return "Ops is unlocked for this browser."
    return "Unlock once with your Pocket access token, or use signed HMAC headers for automation."


def run_git_pull():
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
    return {
        "elapsed": elapsed,
        "message": message,
        "ok": ok,
        "output": output,
        "returncode": result.returncode,
    }


def restart_command():
    configured = clean_config_value(os.environ.get("POCKET_RESTART_COMMAND"))
    if configured:
        return configured
    return " ".join([
        shlex.quote(sys.executable),
        shlex.quote(str(BASE_DIR / "run_pocket.py")),
    ])


def restart_current_process():
    command = restart_command()
    shell = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
    wrapper = " ".join([
        "cd",
        shlex.quote(str(BASE_DIR)),
        "&&",
        "sleep",
        "1",
        "&&",
        command,
        ">>",
        shlex.quote(str(RESTART_LOG_PATH)),
        "2>&1",
    ])

    subprocess.Popen(
        [shell, "-lc", wrapper],
        cwd=str(BASE_DIR),
        start_new_session=True,
    )

    def delayed_exit():
        time.sleep(0.6)
        os._exit(0)

    threading.Thread(target=delayed_exit, daemon=True).start()
    return command


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


def get_monitoring_info():
    return {
        "provider": "uptimerobot",
        "status_page_url": UPTIMEROBOT_STATUS_PAGE_URL,
        "badge_url": UPTIMEROBOT_BADGE_URL,
        "configured": bool(UPTIMEROBOT_STATUS_PAGE_URL or UPTIMEROBOT_BADGE_URL),
    }


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


def parse_price_cents(price):
    text = str(price or "0").strip().replace(",", "")
    try:
        return int(round(float(text) * 100))
    except ValueError:
        return 0


def format_price(cents):
    return f"{cents / 100:.2f}"


def format_display_price(cents):
    if cents % 100 == 0:
        return str(cents // 100)
    return format_price(cents)


def store_display_price_cents(cents):
    if STORE_DISPLAY_CURRENCY != "eur":
        return cents
    if cents <= 0:
        return 0
    converted_whole_units = int((cents / 100) * STORE_DISPLAY_EUR_RATE)
    return converted_whole_units * 100 + 95


def store_money_label(cents):
    display_cents = store_display_price_cents(cents)
    if STORE_DISPLAY_CURRENCY == "eur":
        whole = display_cents // 100
        remainder = display_cents % 100
        return f"\u20ac{whole},{remainder:02d}"
    return f"${format_display_price(display_cents)}"


def load_store_catalog():
    return json.loads(STORE_CATALOG_PATH.read_text(encoding="utf-8"))


def load_store_homepage():
    return json.loads((STORE_DATA_DIR / "homepage.json").read_text(encoding="utf-8"))


def load_store_merchandising():
    path = STORE_DATA_DIR / "merchandising.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def store_products():
    return load_store_catalog().get("products", [])


def store_product_by_handle(handle):
    return next((product for product in store_products() if product.get("handle") == handle), None)


def store_cart_upsell_products():
    products_by_handle = {product.get("handle"): product for product in store_products()}
    return [
        products_by_handle[handle]
        for handle in STORE_CART_UPSELL_HANDLES
        if handle in products_by_handle
    ]


def store_first_available_variant(product):
    variants = product.get("variants", [])
    return next((variant for variant in variants if variant.get("available") is not False), variants[0] if variants else {})


def store_product_image(product):
    variant = store_first_available_variant(product)
    featured = variant.get("featured_image") if isinstance(variant, dict) else None
    if featured and featured.get("src"):
        return featured["src"]
    images = product.get("images", [])
    return images[0].get("src") if images else STORE_PLACEHOLDER_IMAGE


def store_is_shopify_image(src):
    text = str(src or "")
    return "cdn.shopify.com/" in text or "/cdn/shop/" in text


def store_image_url(src, width=None, height=None, crop=None):
    text = str(src or STORE_PLACEHOLDER_IMAGE)
    if not store_is_shopify_image(text):
        return text

    parts = urlsplit(text)
    path = SHOPIFY_LEGACY_IMAGE_SIZE_RE.sub("", parts.path)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in {"width", "height", "crop", "quality"}
    ]
    if width or height:
        query.append(("quality", str(STORE_IMAGE_QUALITY)))
    if width:
        query.append(("width", str(int(width))))
    if height:
        query.append(("height", str(int(height))))
    if crop:
        query.append(("crop", str(crop)))
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def store_image_widths(widths):
    if isinstance(widths, str):
        values = widths.split(",")
    else:
        values = widths or []

    parsed = []
    for value in values:
        try:
            parsed.append(int(value))
        except (TypeError, ValueError):
            continue
    return sorted({width for width in parsed if width > 0})


def store_image_srcset(src, widths):
    if not store_is_shopify_image(src):
        return ""
    return ", ".join(
        f"{store_image_url(src, width=width)} {width}w"
        for width in store_image_widths(widths)
    )


def store_price_label(product):
    prices = [
        parse_price_cents(variant.get("price"))
        for variant in product.get("variants", [])
        if parse_price_cents(variant.get("price")) > 0
    ]
    if not prices:
        return "$0"
    low = min(prices)
    high = max(prices)
    if low == high:
        return store_money_label(low)
    separator = " \u2013 " if STORE_DISPLAY_CURRENCY == "eur" else " - "
    return f"{store_money_label(low)}{separator}{store_money_label(high)}"


def store_variant_price_label(variant):
    return store_money_label(parse_price_cents(variant.get("price")))


def store_primary_option_name(product):
    options = product.get("options") or []
    if options and isinstance(options[0], dict):
        return str(options[0].get("name") or "Variant").strip() or "Variant"
    if options and isinstance(options[0], str):
        return str(options[0]).strip() or "Variant"
    return "Variant"


def store_variant_image_src(product, variant):
    featured = variant.get("featured_image") if isinstance(variant, dict) else None
    if featured and featured.get("src"):
        return featured["src"]
    return store_product_image(product)


def store_pdp_sibling_products(product):
    variants = product.get("variants", [])
    option_name = store_primary_option_name(product).lower()
    if len(variants) != 1 or option_name != "color":
        return [product]

    siblings = [
        item for item in store_products()
        if item.get("title") == product.get("title")
        and item.get("product_type") == product.get("product_type")
        and item.get("vendor") == product.get("vendor")
        and len(item.get("variants", [])) == 1
        and store_primary_option_name(item).lower() == option_name
    ]
    if len(siblings) <= 1:
        return [product]
    return [product, *[item for item in siblings if item.get("handle") != product.get("handle")]]


def store_swatch_color(label):
    key = str(label or "").strip().lower()
    return STORE_SWATCH_COLORS.get(key, "")


def store_pdp_variant_options(product):
    selected_variant = store_first_available_variant(product)
    option_name = store_primary_option_name(product).lower()
    entries = []

    for source_product in store_pdp_sibling_products(product):
        for variant in source_product.get("variants", []):
            title = variant.get("option1") or variant.get("title") or "Default"
            entries.append({
                "variant": variant,
                "title": title,
                "price_label": store_variant_price_label(variant),
                "image_src": store_variant_image_src(source_product, variant),
                "url": "" if source_product.get("handle") == product.get("handle") else f"/store/products/{source_product.get('handle')}",
                "selected": str(variant.get("id")) == str(selected_variant.get("id")),
                "swatch": store_swatch_color(title) if option_name == "color" else "",
            })

    return entries


def store_pdp_gallery_images(product):
    images = list(product.get("images", []))
    if not images:
        return [{"src": STORE_PLACEHOLDER_IMAGE, "variant_ids": []}]

    variants = product.get("variants", [])
    option_name = store_primary_option_name(product).lower()
    if len(variants) == 1 and option_name == "color":
        lifestyle_images = [image for image in images if not image.get("variant_ids")]
        variant_images = [image for image in images if image.get("variant_ids")]
        if lifestyle_images and variant_images:
            return [*lifestyle_images, *variant_images]

    return images


def store_description_lines(product):
    text = str(product.get("body_html") or "")
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    for token in ["<p>", "</p>", '<meta charset="utf-8">', "<meta charset='utf-8'>"]:
        text = text.replace(token, "")
    text = html_lib.unescape(text).replace("\xa0", " ")
    lines = []
    for line in text.splitlines():
        clean = line.strip().strip("-").strip()
        if clean:
            lines.append(clean)
    return lines


def store_product_description_html(product):
    text = str(product.get("body_html") or "").strip()
    for token in ['<meta charset="utf-8">', "<meta charset='utf-8'>"]:
        text = text.replace(token, "")
    return text.replace("\xa0", " ")


def store_collection_definitions():
    extracted = load_store_merchandising().get("collections", {})
    return {
        "shop": {
            "title": "Shop All",
            "description": "A static-first catalog view generated from public Shopify JSON.",
            "matcher": lambda product: True,
        },
        "new-arrivals": {
            "title": "New Arrivals",
            "description": "Fresh pieces from the latest public catalog snapshot.",
            **extracted.get("new-arrivals", {}),
            "matcher": lambda product: True,
        },
        "the-summer-capsule": {
            "title": "The Summer Capsule",
            "description": "Bright cords, pearls, charms, and stacks for the seasonal story.",
            **extracted.get("the-summer-capsule", {}),
            "matcher": lambda product: True,
        },
        "best-sellers": {
            "title": "Best Sellers",
            "description": "A prototype bestseller edit using the strongest featured handles.",
            "handles": {
                "the-salt-pepper-cylinder-necklace-set",
                "the-salt-pepper-cylinder-bracelet-stack",
                "the-paprika-necklace-duo",
                "the-pearl-branch-bracelet",
                "the-salt-pepper-bracelet-duo",
                "the-salt-pepper-necklace-duo",
            },
        },
        "necklaces": {
            "title": "Necklaces",
            "description": "Necklaces filtered from product_type.",
            **extracted.get("necklaces", {}),
            "matcher": lambda product: product.get("product_type") == "Necklaces",
        },
        "bracelets": {
            "title": "Bracelets",
            "description": "Bracelets filtered from product_type.",
            "matcher": lambda product: product.get("product_type") == "Bracelets",
        },
        "earrings": {
            "title": "Earrings",
            "description": "Earrings filtered from product_type.",
            "matcher": lambda product: product.get("product_type") == "Earrings",
        },
        "the-cord-charms": {
            "title": "The Cord Charms",
            "description": "Cord and charm products inferred from tags and titles.",
            "matcher": lambda product: "cord" in " ".join(product.get("tags", [])).lower() or "charm" in product.get("title", "").lower(),
        },
        "custom": {
            "title": "Custom",
            "description": "Personalized cords and charms inferred from tags and titles.",
            "matcher": lambda product: "cord" in " ".join(product.get("tags", [])).lower() or "charm" in product.get("title", "").lower(),
        },
        "the-puffy-heart-club": {
            "title": "The Puffy Heart Club",
            "description": "Heart-led products inferred from tags and titles.",
            "matcher": lambda product: "heart" in " ".join(product.get("tags", [])).lower() or "heart" in product.get("title", "").lower(),
        },
        "pearls-1": {
            "title": "Pretty in Pearls",
            "description": "Pearl products inferred from tags and titles.",
            "matcher": lambda product: "pearl" in " ".join(product.get("tags", [])).lower() or "pearl" in product.get("title", "").lower(),
        },
    }


def store_collection_products(handle):
    definition = store_collection_definitions().get(handle)
    if not definition:
        return None, []
    products = store_products()
    if "handles" in definition:
        selected = [product for product in products if product.get("handle") in definition["handles"]]
    else:
        selected = [product for product in products if definition["matcher"](product)]
    ordered_handles = definition.get("ordered_handles") or []
    if ordered_handles:
        rank = {product_handle: index for index, product_handle in enumerate(ordered_handles)}
        selected.sort(key=lambda product: (rank.get(product.get("handle"), len(rank)), product.get("title", "")))
    return definition, selected


def store_collection_view_data(handle):
    collection, products = store_collection_products(handle)
    if not collection:
        return None
    products, search_query = store_apply_search_filter(products, request.args.get("q", ""))
    products, active_filters = store_apply_collection_filters(products, request.args)
    products = store_sort_collection_products(products, request.args.get("sort_by"))
    return {
        "collection": collection,
        "products": products,
        "active_filters": active_filters,
        "current_sort": request.args.get("sort_by", ""),
        "search_query": search_query,
    }


def store_collection_fragment_url(handle, offset):
    query = []
    for key, values in request.args.lists():
        if key == "offset":
            continue
        for value in values:
            query.append((key, value))
    query.append(("offset", str(int(offset))))
    return f"/store/collections/{handle}/products-fragment?{urlencode(query)}"


def store_product_price_values(product):
    values = []
    for variant in product.get("variants", []):
        try:
            values.append(float(variant.get("price") or 0))
        except (TypeError, ValueError):
            continue
    return values or [0]


def store_sort_collection_products(products, sort_by):
    sorted_products = list(products)
    if sort_by == "price-ascending":
        sorted_products.sort(key=lambda product: (min(store_product_price_values(product)), product.get("title", "")))
    elif sort_by == "price-descending":
        sorted_products.sort(key=lambda product: (max(store_product_price_values(product)), product.get("title", "")), reverse=True)
    return sorted_products


STORE_COLOR_ALIASES = {
    "black": {"black", "salt", "pepper"},
    "blue": {"blue", "cloud", "lapis"},
    "brown": {"brown", "buckwheat", "driftwood", "espresso", "natural"},
    "diamond": {"diamond", "cubic", "cz", "zirconia"},
    "gold": {"gold"},
    "green": {"green", "forest", "moss"},
    "lemon": {"lemon", "yellow"},
    "multi": {"multi", "rainbow", "duo", "stack", "assorted"},
    "orange": {"orange", "paprika", "sienna", "coral", "blood orange"},
    "pink": {"pink", "rose"},
    "rainbow": {"rainbow", "multi"},
    "red": {"red", "blood orange"},
    "white": {"white", "bone", "pearl", "coconut"},
    "yellow": {"yellow", "lemon"},
}


def store_product_search_text(product):
    values = [
        product.get("title", ""),
        product.get("handle", ""),
        product.get("product_type", ""),
        " ".join(product.get("tags", [])),
    ]
    values.extend(variant.get("title", "") for variant in product.get("variants", []))
    values.extend(image.get("src", "") for image in product.get("images", []))
    return " ".join(str(value) for value in values).lower()


def store_product_matches_color(product, color):
    needles = STORE_COLOR_ALIASES.get(str(color).lower(), {str(color).lower()})
    haystack = store_product_search_text(product)
    return any(needle in haystack for needle in needles)


def store_normalized_search_query(query):
    return " ".join(str(query or "").strip().lower().split())


def store_apply_search_filter(products, query):
    normalized_query = store_normalized_search_query(query)
    if not normalized_query:
        return list(products), ""
    terms = normalized_query.split()
    filtered = [
        product for product in products
        if all(term in store_product_search_text(product) for term in terms)
    ]
    return filtered, normalized_query


def store_apply_collection_filters(products, args):
    categories = [value for value in args.getlist("filter.p.product_type[]") if value]
    colors = [value for value in args.getlist("filter.p.m.roxanne-assoulin.filter_color[]") if value]
    category_keys = {category.lower() for category in categories}
    color_keys = {color.lower() for color in colors}
    filtered = list(products)
    if categories:
        filtered = [product for product in filtered if str(product.get("product_type", "")).lower() in category_keys]
    if colors:
        filtered = [product for product in filtered if any(store_product_matches_color(product, color) for color in colors)]
    return filtered, {
        "categories": categories,
        "colors": colors,
        "category_keys": category_keys,
        "color_keys": color_keys,
    }


def store_query_url(**updates):
    params = request.args.to_dict(flat=False)
    for key, value in updates.items():
        if value is None or value == "":
            params.pop(key, None)
        elif isinstance(value, (list, tuple)):
            params[key] = [str(item) for item in value]
        else:
            params[key] = [str(value)]

    pairs = []
    for key, values in params.items():
        pairs.extend((key, value) for value in values)
    query = urlencode(pairs)
    return f"?{query}" if query else "?"


def store_template_context(**kwargs):
    store_css_scope = kwargs.pop("store_css_scope", None)
    merchandising = load_store_merchandising()
    context = {
        "collections": store_collection_definitions(),
        "merchandising": merchandising,
        "product_image": store_product_image,
        "image_url": store_image_url,
        "image_srcset": store_image_srcset,
        "price_label": store_price_label,
        "variant_price_label": store_variant_price_label,
        "description_lines": store_description_lines,
        "description_html": store_product_description_html,
        "first_variant": store_first_available_variant,
        "pdp_gallery_images": store_pdp_gallery_images,
        "pdp_option_label": store_primary_option_name,
        "pdp_variant_options": store_pdp_variant_options,
        "product_merchandising": lambda handle: merchandising.get("product_pages", {}).get(handle, {}),
        "placeholder_image": STORE_PLACEHOLDER_IMAGE,
        "search_query": request.args.get("q", "").strip(),
        "store_query_url": store_query_url,
        "store_base_url": STORE_BASE_URL,
        "store_display_currency": STORE_DISPLAY_CURRENCY,
        "store_display_eur_rate": STORE_DISPLAY_EUR_RATE,
        "cart_upsells": store_cart_upsell_products(),
        "store_css_asset": store_css_asset_url(store_css_scope),
    }
    context.update(kwargs)
    return context


def minify_store_html(html):
    return re.sub(r">\s+<", "><", html.strip())


def apply_cache_headers(response, browser_max_age, edge_max_age=None, immutable=False):
    browser_directives = ["public", f"max-age={browser_max_age}"]
    edge_directives = ["public", f"max-age={edge_max_age if edge_max_age is not None else browser_max_age}"]
    if immutable:
        browser_directives.append("immutable")
        edge_directives.append("immutable")
    else:
        browser_directives.extend(["stale-while-revalidate=3600", "stale-if-error=86400"])
    edge_directives.extend(["stale-while-revalidate=604800", "stale-if-error=604800"])
    edge_value = ", ".join(edge_directives)

    response.headers["Cache-Control"] = ", ".join(browser_directives)
    response.headers["CDN-Cache-Control"] = edge_value
    response.headers["Cloudflare-CDN-Cache-Control"] = edge_value
    return response


def apply_no_store_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers.pop("CDN-Cache-Control", None)
    response.headers.pop("Cloudflare-CDN-Cache-Control", None)
    return response


def store_json_response(payload, status=200, no_store=False):
    response = jsonify(payload)
    if no_store:
        apply_no_store_headers(response)
    return response, status


def render_store_template(template_name, **context):
    response = Response(minify_store_html(render_template(template_name, **context)), mimetype="text/html")
    return apply_cache_headers(
        response,
        STORE_HTML_BROWSER_CACHE_SECONDS,
        STORE_HTML_EDGE_CACHE_SECONDS,
    )


def render_static_pwa_file(path, mimetype, browser_max_age, edge_max_age=None, immutable=False):
    response = send_file(path, mimetype=mimetype, max_age=browser_max_age)
    return apply_cache_headers(response, browser_max_age, edge_max_age, immutable=immutable)


def store_variant_lookup():
    lookup = {}
    for product in load_store_catalog().get("products", []):
        for variant in product.get("variants", []):
            try:
                variant_id = int(variant.get("id"))
            except (TypeError, ValueError):
                continue
            lookup[variant_id] = {
                "product": product,
                "variant": variant,
            }
    return lookup


def store_compact_image(image):
    if isinstance(image, dict) and image.get("src"):
        return {"src": image["src"]}
    return None


def store_cart_index_payload():
    products = []
    for product in load_store_catalog().get("products", []):
        products.append(store_compact_cart_product(product))
    return {"products": products}


def store_compact_cart_product(product):
    images = [
        compact_image
        for compact_image in [store_compact_image((product.get("images") or [{}])[0])]
        if compact_image
    ]
    variants = []
    for variant in product.get("variants", []):
        compact_variant = {
            "id": variant.get("id"),
            "title": variant.get("title"),
            "price": variant.get("price"),
            "position": variant.get("position"),
        }
        compact_featured_image = store_compact_image(variant.get("featured_image"))
        if compact_featured_image:
            compact_variant["featured_image"] = compact_featured_image
        variants.append(compact_variant)
    return {
        "title": product.get("title"),
        "handle": product.get("handle"),
        "images": images,
        "variants": variants,
    }


def store_cart_items_payload(raw_ids):
    requested_ids = {
        int(item)
        for item in re.findall(r"\d+", raw_ids or "")
    }
    products = []
    if not requested_ids:
        return {"products": products}
    for product in load_store_catalog().get("products", []):
        variant_ids = {
            int(variant.get("id"))
            for variant in product.get("variants", [])
            if str(variant.get("id") or "").isdigit()
        }
        if requested_ids & variant_ids:
            products.append(store_compact_cart_product(product))
    return {"products": products}


def parse_cart_item(raw_item):
    if not isinstance(raw_item, dict):
        raise ValueError("Each cart item must be an object.")
    try:
        variant_id = int(raw_item.get("id"))
        quantity = int(raw_item.get("qty"))
    except (TypeError, ValueError):
        raise ValueError("Cart items require numeric id and qty.")
    if quantity < 1 or quantity > 99:
        raise ValueError("Cart item quantity must be between 1 and 99.")
    return variant_id, quantity


def store_verified_checkout_items(cart_items):
    if not isinstance(cart_items, list):
        raise ValueError("cartItems must be an array.")
    if not cart_items:
        raise ValueError("Cart is empty.")
    if len(cart_items) > 100:
        raise ValueError("Cart has too many lines.")

    variants = store_variant_lookup()
    verified_items = []
    subtotal_cents = 0
    permalink_parts = []

    for raw_item in cart_items:
        variant_id, quantity = parse_cart_item(raw_item)
        catalog_item = variants.get(variant_id)
        if not catalog_item:
            raise ValueError(f"Unknown variant id: {variant_id}")

        product = catalog_item["product"]
        variant = catalog_item["variant"]
        if variant.get("available") is False:
            raise ValueError(f"Variant is unavailable: {variant_id}")

        unit_amount_cents = parse_price_cents(variant.get("price"))
        if unit_amount_cents <= 0:
            raise ValueError(f"Variant has invalid price: {variant_id}")

        line_total_cents = unit_amount_cents * quantity
        subtotal_cents += line_total_cents
        permalink_parts.append(f"{variant_id}:{quantity}")
        verified_items.append({
            "id": variant_id,
            "title": product.get("title", "Untitled product"),
            "variant_title": variant.get("title") or "",
            "qty": quantity,
            "unit_amount_cents": unit_amount_cents,
            "unit_amount": format_price(unit_amount_cents),
            "line_total_cents": line_total_cents,
            "line_total": format_price(line_total_cents),
            "image": store_product_image(product),
        })

    return verified_items, subtotal_cents, permalink_parts


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
        {% if output %}
          <pre>{{ output }}</pre>
        {% endif %}
      </form>
    {% endif %}
  </main>
</body>
</html>
"""


OPS_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pocket Ops</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #101315;
      --panel: #191f22;
      --line: #333b40;
      --text: #eef3f2;
      --muted: #a9b3b0;
      --accent: #72d6b9;
      --accent-2: #9fc4e0;
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
      width: min(820px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 34px 0;
    }

    h1 {
      margin: 0 0 8px;
      font-size: 34px;
      line-height: 1.08;
      letter-spacing: 0;
    }

    h2 {
      margin: 0 0 12px;
      font-size: 18px;
      letter-spacing: 0;
    }

    p {
      margin: 0 0 18px;
      color: var(--muted);
      line-height: 1.5;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }

    .unlock-form,
    .panel {
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 18px;
      margin-top: 14px;
    }

    .actions-form {
      margin: 0;
      padding: 0;
      border: 0;
      background: transparent;
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

    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 48px;
      width: 100%;
      padding: 0 18px;
      border: 0;
      background: var(--accent);
      color: #07110e;
      font: inherit;
      font-weight: 760;
      cursor: pointer;
    }

    .secondary { background: var(--accent-2); }

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

    @media (max-width: 620px) {
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <h1>Pocket Ops</h1>
    <p>{{ auth_label }}</p>

    {% if result %}
      <section class="panel">
        <p class="{{ 'ok' if ok else 'bad' }}">{{ result }}</p>
        {% if output %}
          <pre>{{ output }}</pre>
        {% endif %}
      </section>
    {% endif %}

    {% if needs_unlock %}
      <form class="unlock-form" method="post" action="/ops">
        <h2>Unlock</h2>
        <label for="token">Pocket access token</label>
        <input id="token" name="token" type="password" autocomplete="current-password" required>
        <button type="submit" name="action" value="unlock">Unlock ops</button>
      </form>
    {% else %}
      <section class="panel">
        <h2>Actions</h2>
        <form class="actions-form grid" method="post" action="/ops">
          <button type="submit" name="action" value="pull">Pull</button>
          <button class="secondary" type="submit" name="action" value="restart">Restart</button>
          <button type="submit" name="action" value="pull_restart">Pull then restart</button>
        </form>
      </section>
    {% endif %}

    <section class="panel">
      <h2>Notes</h2>
      <p>Unattended ops requests must be signed with <code>X-Pocket-Ops-Timestamp</code> and <code>X-Pocket-Ops-Signature</code>. The signature signs <code>POST</code>, <code>/ops</code>, the timestamp, and the exact request body.</p>
      <p>Restart command: <code>{{ restart_command }}</code></p>
    </section>
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
          <label for="buffer_api_key">Buffer API key</label>
          <input id="buffer_api_key" name="buffer_api_key" type="password" autocomplete="off" placeholder="Leave blank to keep existing key">
        </div>
        <div class="field">
          <label for="buffer_organization_id">Buffer organization ID</label>
          <input id="buffer_organization_id" name="buffer_organization_id" type="text" value="{{ buffer_organization_id }}" autocomplete="off" placeholder="Optional until you list channels">
        </div>
        <div class="field">
          <label for="buffer_channel_id">Buffer channel ID</label>
          <input id="buffer_channel_id" name="buffer_channel_id" type="text" value="{{ buffer_channel_id }}" autocomplete="off" placeholder="Optional until you post">
        </div>
        <div class="field">
          <label for="uptimerobot_status_page_url">UptimeRobot status page URL</label>
          <input id="uptimerobot_status_page_url" name="uptimerobot_status_page_url" type="url" value="{{ uptimerobot_status_page_url }}" autocomplete="off" placeholder="https://stats.uptimerobot.com/...">
        </div>
        <div class="field">
          <label for="uptimerobot_badge_url">UptimeRobot badge URL</label>
          <input id="uptimerobot_badge_url" name="uptimerobot_badge_url" type="url" value="{{ uptimerobot_badge_url }}" autocomplete="off" placeholder="Optional badge image URL">
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


@app.route("/bp")
@app.route("/bp/")
def bp_home():
    return send_file(BASE_DIR / "pages" / "bp" / "index.html")


@app.route("/pwa")
@app.route("/pwa/")
def pwa_home():
    return render_static_pwa_file(PWA_DIR / "index.html", "text/html", PWA_BROWSER_CACHE_SECONDS)


@app.route("/pwa/app.css")
def pwa_app_css():
    return render_static_pwa_file(PWA_DIR / "app.css", "text/css", PWA_BROWSER_CACHE_SECONDS)


@app.route("/pwa/app.js")
def pwa_app_js():
    return render_static_pwa_file(PWA_DIR / "app.js", "text/javascript", PWA_BROWSER_CACHE_SECONDS)


@app.route("/pwa/manifest.webmanifest")
def pwa_manifest():
    return render_static_pwa_file(PWA_DIR / "manifest.webmanifest", "application/manifest+json", PWA_BROWSER_CACHE_SECONDS)


@app.route("/pwa/service-worker.js")
def pwa_service_worker():
    response = render_static_pwa_file(PWA_DIR / "service-worker.js", "text/javascript", 0)
    response.headers["Cache-Control"] = "no-store"
    response.headers.pop("CDN-Cache-Control", None)
    response.headers.pop("Cloudflare-CDN-Cache-Control", None)
    return response


@app.route("/pwa/offline.html")
def pwa_offline():
    return render_static_pwa_file(PWA_DIR / "offline.html", "text/html", PWA_BROWSER_CACHE_SECONDS)


@app.route("/pwa/catalog.json")
def pwa_catalog():
    response = send_file(STORE_CATALOG_PATH, mimetype="application/json", max_age=PWA_DATA_BROWSER_CACHE_SECONDS)
    return apply_cache_headers(response, PWA_DATA_BROWSER_CACHE_SECONDS, STORE_DATA_EDGE_CACHE_SECONDS)


@app.route("/pwa/cart-index.json")
def pwa_cart_index():
    payload = jsonify(store_cart_index_payload())
    return apply_cache_headers(payload, PWA_DATA_BROWSER_CACHE_SECONDS, STORE_DATA_EDGE_CACHE_SECONDS)


@app.route("/pwa/icons/<path:filename>")
def pwa_icon(filename):
    return render_static_pwa_file(PWA_DIR / "icons" / filename, "image/svg+xml", STORE_ASSET_CACHE_SECONDS, immutable=True)


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


@app.route("/methodiq")
@app.route("/methodiq/")
def methodiq_index():
    return send_file(BASE_DIR / "pages" / "methodiq" / "index.html")


@app.route("/methodiq/home")
def methodiq_home():
    return send_file(BASE_DIR / "pages" / "methodiq" / "home.html")


@app.route("/methodiq/category")
def methodiq_category():
    return send_file(BASE_DIR / "pages" / "methodiq" / "category.html")


@app.route("/methodiq/dapinaq")
def methodiq_dapinaq():
    return send_file(BASE_DIR / "pages" / "methodiq" / "dapinaq.html")


@app.route("/methodiq/clarixa")
def methodiq_clarixa():
    return send_file(BASE_DIR / "pages" / "methodiq" / "clarixa.html")


@app.route("/store")
@app.route("/store/")
def store_page():
    products_by_handle = {product.get("handle"): product for product in store_products()}
    return render_store_template(
        "store/home.html",
        **store_template_context(
            homepage=load_store_homepage(),
            products_by_handle=products_by_handle,
            store_css_scope="home",
        ),
    )


@app.route("/store/collections/<handle>")
def store_collection_page(handle):
    view_data = store_collection_view_data(handle)
    if not view_data:
        abort(404)
    return render_store_template(
        "store/collection.html",
        **store_template_context(
            handle=handle,
            **view_data,
            collection_initial_product_limit=STORE_COLLECTION_INITIAL_PRODUCT_LIMIT,
            collection_deferred_url=store_collection_fragment_url(
                handle,
                STORE_COLLECTION_INITIAL_PRODUCT_LIMIT,
            ),
            store_css_scope="collection",
        ),
    )


@app.route("/store/collections/<handle>/products-fragment")
def store_collection_products_fragment(handle):
    view_data = store_collection_view_data(handle)
    if not view_data:
        abort(404)
    try:
        offset = max(0, int(request.args.get("offset", STORE_COLLECTION_INITIAL_PRODUCT_LIMIT)))
    except (TypeError, ValueError):
        offset = STORE_COLLECTION_INITIAL_PRODUCT_LIMIT
    html = minify_store_html(render_template(
        "store/_collection_products_fragment.html",
        **store_template_context(
            products=view_data["products"][offset:],
        ),
    ))
    response = Response(html, mimetype="text/html")
    return apply_cache_headers(
        response,
        STORE_DATA_BROWSER_CACHE_SECONDS,
        STORE_DATA_EDGE_CACHE_SECONDS,
    )


@app.route("/store/products/<handle>")
def store_product_page(handle):
    product = store_product_by_handle(handle)
    if not product:
        abort(404)
    related = [
        item for item in store_products()
        if item.get("handle") != handle and item.get("product_type") == product.get("product_type")
    ][:4]
    return render_store_template(
        "store/product.html",
        **store_template_context(
            product=product,
            related=related,
            store_css_scope="product",
        ),
    )


@app.route("/store/cart")
def store_cart_page():
    return render_store_template(
        "store/cart.html",
        **store_template_context(store_css_scope="cart"),
    )


@app.route("/store/cart-upsells-fragment")
def store_cart_upsells_fragment():
    html = minify_store_html(render_template(
        "store/_cart_page_upsells.html",
        **store_template_context(cart_upsells=store_cart_upsell_products()),
    ))
    response = Response(html, mimetype="text/html")
    return apply_cache_headers(
        response,
        STORE_DATA_BROWSER_CACHE_SECONDS,
        STORE_DATA_EDGE_CACHE_SECONDS,
    )


@app.route("/store/cart-drawer-upsells-fragment")
def store_cart_drawer_upsells_fragment():
    html = minify_store_html(render_template(
        "store/_cart_drawer_upsells.html",
        **store_template_context(cart_upsells=store_cart_upsell_products()),
    ))
    response = Response(html, mimetype="text/html")
    return apply_cache_headers(
        response,
        STORE_DATA_BROWSER_CACHE_SECONDS,
        STORE_DATA_EDGE_CACHE_SECONDS,
    )


@app.route("/store/assets/store.js")
def store_asset_js():
    response = send_file(
        BASE_DIR / "pages" / "store" / "store.js",
        mimetype="text/javascript",
        max_age=STORE_ASSET_CACHE_SECONDS,
    )
    return apply_cache_headers(
        response,
        STORE_ASSET_CACHE_SECONDS,
        STORE_ASSET_CACHE_SECONDS,
        immutable=True,
    )


def minify_store_js(js):
    return "\n".join(
        line.strip()
        for line in js.splitlines()
        if line.strip()
    )


@app.route("/store/assets/store.min.js")
def store_asset_min_js():
    js = (BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")
    response = Response(minify_store_js(js), mimetype="text/javascript")
    return apply_cache_headers(
        response,
        STORE_ASSET_CACHE_SECONDS,
        STORE_ASSET_CACHE_SECONDS,
        immutable=True,
    )


@app.route("/store/assets/store.css")
def store_asset_css():
    response = send_file(
        BASE_DIR / "pages" / "store" / "store.css",
        mimetype="text/css",
        max_age=STORE_ASSET_CACHE_SECONDS,
    )
    return apply_cache_headers(
        response,
        STORE_ASSET_CACHE_SECONDS,
        STORE_ASSET_CACHE_SECONDS,
        immutable=True,
    )


STORE_FONT_ASSETS = {
    "SupremeLLWeb-Regular-store-latin.woff2",
    "SupremeLLWeb-Medium-store-latin.woff2",
    "SupremeLLWeb-Regular-store-tight.woff2",
    "SupremeLLWeb-Medium-store-tight.woff2",
}

STORE_FULL_CSS_ASSET = "/store/assets/store.min.css?v=20260605-cart-cls"
STORE_SCOPED_CSS_VERSION = "20260606-stripe-fallback"
STORE_CSS_SCOPES = {"home", "collection", "product", "cart"}

STORE_SCOPED_CSS_EXCLUDE_PREFIXES = {
    "home": {
        "collection", "collection-filter", "collection-grid", "collection-hero", "pagination",
        "pdp", "product-info", "product-page", "product-details", "product-buy", "product-qty",
        "product-short", "product-motto", "product-detail", "details-list", "option-selector",
        "gallery", "product-gallery", "cart-page", "cart-upsell",
    },
    "collection": {
        "hero", "hero-copy", "hero-cta", "product-module", "double-image", "split-banner",
        "split-tile", "category-module", "category-list", "info-module", "pdp", "product-info",
        "product-page", "product-details", "product-buy", "product-qty", "product-short",
        "product-motto", "product-detail", "details-list", "option-selector", "gallery",
        "product-gallery", "cart-page", "cart-upsell",
    },
    "product": {
        "hero", "hero-copy", "hero-cta", "product-module", "double-image", "split-banner",
        "split-tile", "category-module", "category-list", "info-module", "collection",
        "collection-filter", "collection-grid", "collection-hero", "pagination", "cart-page",
        "cart-upsell",
    },
    "cart": {
        "hero", "hero-copy", "hero-cta", "product-module", "double-image", "split-banner",
        "split-tile", "category-module", "category-list", "info-module", "collection",
        "collection-filter", "collection-grid", "collection-hero", "pagination", "pdp",
        "product-info", "product-page", "product-details", "product-buy", "product-qty",
        "product-short", "product-motto", "product-detail", "details-list", "option-selector",
        "gallery", "product-gallery",
    },
}

STORE_SCOPED_CSS_KEEP_PREFIXES = (
    "cart-drawer", "product-tile", "product-card", "quickshop", "search-drawer", "menu-drawer",
    "drawer", "footer", "shipping-promo", "site-header", "brand", "store-search", "cart-link",
    "button", "price", "grid", "empty-state", "plain-button",
)

STORE_CSS_CLASS_RE = re.compile(r"\.([A-Za-z0-9_-]+)")


def store_css_asset_url(scope=None):
    if scope in STORE_CSS_SCOPES:
        return f"/store/assets/store.{scope}.min.css?v={STORE_SCOPED_CSS_VERSION}"
    return STORE_FULL_CSS_ASSET


@app.route("/store/assets/fonts/<path:filename>")
def store_asset_font(filename):
    if filename not in STORE_FONT_ASSETS:
        abort(404)
    response = send_file(
        BASE_DIR / "pages" / "store" / "fonts" / filename,
        mimetype="font/woff2",
        max_age=STORE_ASSET_CACHE_SECONDS,
    )
    return apply_cache_headers(
        response,
        STORE_ASSET_CACHE_SECONDS,
        STORE_ASSET_CACHE_SECONDS,
        immutable=True,
    )


def minify_store_css(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,>+~])\s*", r"\1", css)
    css = css.replace(";}", "}")
    return css.strip()


def iter_store_css_blocks(css):
    index = 0
    length = len(css)
    while index < length:
        while index < length and css[index].isspace():
            index += 1
        if index >= length:
            break
        prelude_start = index
        while index < length and css[index] != "{":
            index += 1
        if index >= length:
            break
        prelude = css[prelude_start:index].strip()
        index += 1
        body_start = index
        depth = 1
        while index < length and depth:
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
            index += 1
        yield prelude, css[body_start:index - 1]


def split_store_css_selectors(prelude):
    return [selector.strip() for selector in prelude.split(",") if selector.strip()]


def store_css_class_is_excluded(class_name, scope):
    if any(class_name.startswith(prefix) for prefix in STORE_SCOPED_CSS_KEEP_PREFIXES):
        return False
    return any(
        class_name == prefix
        or class_name.startswith(prefix + "-")
        or class_name.startswith(prefix + "__")
        for prefix in STORE_SCOPED_CSS_EXCLUDE_PREFIXES.get(scope, set())
    )


def store_css_selector_matches_scope(selector, scope):
    class_names = STORE_CSS_CLASS_RE.findall(selector)
    if not class_names:
        return True
    return not any(store_css_class_is_excluded(class_name, scope) for class_name in class_names)


def filter_store_css_for_scope(css, scope):
    if scope not in STORE_CSS_SCOPES:
        return css

    blocks = []
    for prelude, body in iter_store_css_blocks(css):
        if prelude.startswith("@font-face"):
            blocks.append(f"{prelude}{{{body}}}")
        elif prelude.startswith("@media"):
            filtered_body = filter_store_css_for_scope(body, scope).strip()
            if filtered_body:
                blocks.append(f"{prelude}{{{filtered_body}}}")
        elif prelude.startswith("@"):
            blocks.append(f"{prelude}{{{body}}}")
        else:
            selectors = [
                selector
                for selector in split_store_css_selectors(prelude)
                if store_css_selector_matches_scope(selector, scope)
            ]
            if selectors:
                blocks.append(f"{', '.join(selectors)}{{{body}}}")
    return "\n".join(blocks)


@app.route("/store/assets/store.min.css")
def store_asset_min_css():
    css = (BASE_DIR / "pages" / "store" / "store.css").read_text(encoding="utf-8")
    response = Response(minify_store_css(css), mimetype="text/css")
    return apply_cache_headers(
        response,
        STORE_ASSET_CACHE_SECONDS,
        STORE_ASSET_CACHE_SECONDS,
        immutable=True,
    )


@app.route("/store/assets/store.<scope>.min.css")
def store_asset_scoped_min_css(scope):
    if scope not in STORE_CSS_SCOPES:
        abort(404)
    css = (BASE_DIR / "pages" / "store" / "store.css").read_text(encoding="utf-8")
    scoped_css = filter_store_css_for_scope(css, scope)
    response = Response(minify_store_css(scoped_css), mimetype="text/css")
    return apply_cache_headers(
        response,
        STORE_ASSET_CACHE_SECONDS,
        STORE_ASSET_CACHE_SECONDS,
        immutable=True,
    )


@app.route("/store/catalog.json")
def store_catalog():
    response = send_file(STORE_CATALOG_PATH, mimetype="application/json", max_age=STORE_DATA_BROWSER_CACHE_SECONDS)
    return apply_cache_headers(
        response,
        STORE_DATA_BROWSER_CACHE_SECONDS,
        STORE_DATA_EDGE_CACHE_SECONDS,
    )


@app.route("/store/cart-index.json")
def store_cart_index():
    response = Response(
        json.dumps(store_cart_index_payload(), separators=(",", ":")),
        mimetype="application/json",
    )
    return apply_cache_headers(
        response,
        STORE_DATA_BROWSER_CACHE_SECONDS,
        STORE_DATA_EDGE_CACHE_SECONDS,
    )


@app.route("/store/cart-items.json")
def store_cart_items():
    response = Response(
        json.dumps(
            store_cart_items_payload(request.args.get("ids", "")),
            separators=(",", ":"),
        ),
        mimetype="application/json",
    )
    return apply_cache_headers(
        response,
        STORE_DATA_BROWSER_CACHE_SECONDS,
        STORE_DATA_EDGE_CACHE_SECONDS,
    )


@app.route("/store/api/checkout", methods=["POST"])
def store_mock_checkout():
    data = request.get_json(silent=True) or {}
    cart_items = data.get("cartItems")

    try:
        verified_items, subtotal_cents, permalink_parts = store_verified_checkout_items(cart_items)
    except OSError as exc:
        return store_json_response({"error": f"Store catalog is unavailable: {exc}"}, 500, no_store=True)
    except json.JSONDecodeError as exc:
        return store_json_response({"error": f"Store catalog is invalid: {exc}"}, 500, no_store=True)
    except ValueError as exc:
        return store_json_response({"error": str(exc)}, 400, no_store=True)

    return store_json_response({
        "mode": "mock",
        "currency": STORE_CURRENCY,
        "item_count": sum(item["qty"] for item in verified_items),
        "subtotal_cents": subtotal_cents,
        "subtotal": format_price(subtotal_cents),
        "line_items": verified_items,
        "shopify_cart_url": f"{STORE_BASE_URL}/cart/{','.join(permalink_parts)}",
    }, no_store=True)


def stripe_checkout_urls():
    root = request.url_root.rstrip("/")
    return (
        clean_config_value(os.environ.get("STRIPE_SUCCESS_URL")) or f"{root}/store/cart?stripe=success",
        clean_config_value(os.environ.get("STRIPE_CANCEL_URL")) or f"{root}/store/cart?stripe=cancel",
    )


def stripe_checkout_form_params(verified_items):
    success_url, cancel_url = stripe_checkout_urls()
    params = [
        ("mode", "payment"),
        ("success_url", success_url),
        ("cancel_url", cancel_url),
        ("metadata[source]", "pocket-store-fallback"),
    ]
    currency = clean_config_value(os.environ.get("STRIPE_CURRENCY")) or STORE_CURRENCY
    for index, item in enumerate(verified_items):
        prefix = f"line_items[{index}]"
        name = item["title"]
        if item.get("variant_title") and item["variant_title"] != "Default Title":
            name = f"{name} - {item['variant_title']}"
        params.extend([
            (f"{prefix}[quantity]", str(item["qty"])),
            (f"{prefix}[price_data][currency]", currency.lower()),
            (f"{prefix}[price_data][unit_amount]", str(item["unit_amount_cents"])),
            (f"{prefix}[price_data][product_data][name]", name),
            (f"{prefix}[price_data][product_data][metadata][variant_id]", str(item["id"])),
        ])
        if str(item.get("image") or "").startswith("https://"):
            params.append((f"{prefix}[price_data][product_data][images][0]", item["image"]))
    return params


@app.route("/store/api/stripe-checkout", methods=["POST"])
def store_stripe_checkout():
    data = request.get_json(silent=True) or {}
    cart_items = data.get("cartItems")

    try:
        verified_items, _subtotal_cents, _permalink_parts = store_verified_checkout_items(cart_items)
    except OSError as exc:
        return store_json_response({"error": f"Store catalog is unavailable: {exc}"}, 500, no_store=True)
    except json.JSONDecodeError as exc:
        return store_json_response({"error": f"Store catalog is invalid: {exc}"}, 500, no_store=True)
    except ValueError as exc:
        return store_json_response({"error": str(exc)}, 400, no_store=True)

    stripe_secret = clean_config_value(os.environ.get("STRIPE_SECRET_KEY"))
    if not stripe_secret:
        return store_json_response({"error": "Stripe fallback is not configured."}, 503, no_store=True)

    body = urlencode(stripe_checkout_form_params(verified_items)).encode("utf-8")
    stripe_request = UrlRequest(
        "https://api.stripe.com/v1/checkout/sessions",
        data=body,
        headers={
            "Authorization": f"Bearer {stripe_secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urlopen(stripe_request, timeout=20) as stripe_response:
            payload = json.loads(stripe_response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return store_json_response({
            "error": "Stripe checkout failed.",
            "status": exc.code,
            "detail": detail[:1000],
        }, 502, no_store=True)
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return store_json_response({"error": f"Stripe checkout failed: {exc}"}, 502, no_store=True)

    if not payload.get("url"):
        return store_json_response({"error": "Stripe checkout did not return a hosted URL."}, 502, no_store=True)

    return store_json_response({"mode": "stripe", "url": payload["url"]}, no_store=True)


@app.route("/store/pulse", methods=["GET", "POST"])
def store_pulse():
    if request.method == "GET":
        if request.args.get("check") == "1":
            return store_json_response({"ok": True, "receiver": "flask-store-pulse"}, no_store=True)
        return store_json_response({"ok": False, "error": "not_found"}, 404, no_store=True)

    if request.content_length and request.content_length > 16 * 1024:
        return store_json_response({"ok": False, "error": "payload_too_large"}, 413, no_store=True)

    request.get_json(silent=True)
    response = Response(status=204)
    return apply_no_store_headers(response)


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "pocket-office",
        "runtime": "termux",
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
        "monitoring": get_monitoring_info(),
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
            buffer_organization_id=BUFFER_ORGANIZATION_ID,
            buffer_channel_id=BUFFER_CHANNEL_ID,
            uptimerobot_status_page_url=UPTIMEROBOT_STATUS_PAGE_URL,
            uptimerobot_badge_url=UPTIMEROBOT_BADGE_URL,
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
            buffer_organization_id=BUFFER_ORGANIZATION_ID,
            buffer_channel_id=BUFFER_CHANNEL_ID,
            uptimerobot_status_page_url=UPTIMEROBOT_STATUS_PAGE_URL,
            uptimerobot_badge_url=UPTIMEROBOT_BADGE_URL,
            api_key_required=not has_gemini_api_key(),
        ), 401

    gemini_api_key = clean_config_value(request.form.get("gemini_api_key"))
    pocket_access_token = clean_config_value(request.form.get("pocket_access_token"))
    gemini_model = clean_config_value(request.form.get("gemini_model")) or DEFAULT_GEMINI_MODEL
    gemini_args = clean_config_value(request.form.get("gemini_args"))
    buffer_api_key = clean_config_value(request.form.get("buffer_api_key"))
    buffer_organization_id = clean_config_value(request.form.get("buffer_organization_id"))
    buffer_channel_id = clean_config_value(request.form.get("buffer_channel_id"))
    uptimerobot_status_page_url = clean_config_value(request.form.get("uptimerobot_status_page_url"))
    uptimerobot_badge_url = clean_config_value(request.form.get("uptimerobot_badge_url"))

    if not gemini_api_key and not has_gemini_api_key():
        return render_template_string(
            SETUP_PAGE,
            locked=False,
            saved=False,
            error="Gemini API key is required.",
            default_model=gemini_model,
            gemini_args=gemini_args,
            buffer_organization_id=buffer_organization_id,
            buffer_channel_id=buffer_channel_id,
            uptimerobot_status_page_url=uptimerobot_status_page_url,
            uptimerobot_badge_url=uptimerobot_badge_url,
            api_key_required=True,
        ), 400

    updates = {
        "POCKET_GEMINI_MODEL": gemini_model,
        "POCKET_GEMINI_ARGS": gemini_args,
        "BUFFER_ORGANIZATION_ID": buffer_organization_id,
        "BUFFER_CHANNEL_ID": buffer_channel_id,
        "BUFFER_DEFAULT_MODE": BUFFER_DEFAULT_MODE,
        "UPTIMEROBOT_STATUS_PAGE_URL": uptimerobot_status_page_url,
        "UPTIMEROBOT_BADGE_URL": uptimerobot_badge_url,
    }
    if gemini_api_key:
        updates["GEMINI_API_KEY"] = gemini_api_key
    if pocket_access_token:
        updates["POCKET_ACCESS_TOKEN"] = pocket_access_token
    if buffer_api_key:
        updates["BUFFER_API_KEY"] = buffer_api_key

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
            buffer_organization_id=buffer_organization_id,
            buffer_channel_id=buffer_channel_id,
            uptimerobot_status_page_url=uptimerobot_status_page_url,
            uptimerobot_badge_url=uptimerobot_badge_url,
            api_key_required=not has_gemini_api_key(),
        ), 500

    return render_template_string(
        SETUP_PAGE,
        locked=False,
        saved=True,
        error="",
        default_model=gemini_model,
        gemini_args=gemini_args,
        buffer_organization_id=buffer_organization_id,
        buffer_channel_id=buffer_channel_id,
        uptimerobot_status_page_url=uptimerobot_status_page_url,
        uptimerobot_badge_url=uptimerobot_badge_url,
        api_key_required=not has_gemini_api_key(),
    )


@app.route("/api/buffer/status")
def buffer_status():
    if access_denied():
        return jsonify({"error": "Invalid Pocket access token."}), 401
    if not BUFFER_API_KEY:
        return jsonify({"configured": False, "error": "BUFFER_API_KEY is not configured."}), 400
    try:
        account = get_account(BUFFER_API_KEY)
    except BufferApiError as exc:
        return jsonify({"configured": True, "error": str(exc)}), 502
    return jsonify({
        "configured": True,
        "account": account,
        "organization_id": BUFFER_ORGANIZATION_ID,
        "channel_id": BUFFER_CHANNEL_ID,
        "default_mode": BUFFER_DEFAULT_MODE,
    })


@app.route("/api/buffer/organizations")
def buffer_organizations():
    if access_denied():
        return jsonify({"error": "Invalid Pocket access token."}), 401
    if not BUFFER_API_KEY:
        return jsonify({"error": "BUFFER_API_KEY is not configured."}), 400
    try:
        organizations = get_organizations(BUFFER_API_KEY)
    except BufferApiError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"organizations": organizations})


@app.route("/api/buffer/channels")
def buffer_channels():
    if access_denied():
        return jsonify({"error": "Invalid Pocket access token."}), 401
    if not BUFFER_API_KEY:
        return jsonify({"error": "BUFFER_API_KEY is not configured."}), 400
    organization_id = clean_config_value(request.args.get("organization_id")) or BUFFER_ORGANIZATION_ID
    try:
        channels = get_channels(BUFFER_API_KEY, organization_id)
    except BufferApiError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"organization_id": organization_id, "channels": channels})


@app.route("/api/buffer/post", methods=["POST"])
def buffer_post():
    if access_denied():
        return jsonify({"error": "Invalid Pocket access token."}), 401
    if not BUFFER_API_KEY:
        return jsonify({"error": "BUFFER_API_KEY is not configured."}), 400

    data = request.get_json(silent=True) or {}
    text = clean_config_value(data.get("text"))
    image_url = clean_config_value(data.get("image_url"))
    channel_id = clean_config_value(data.get("channel_id")) or BUFFER_CHANNEL_ID
    mode = clean_config_value(data.get("mode")) or BUFFER_DEFAULT_MODE
    scheduling_type = clean_config_value(data.get("scheduling_type")) or "automatic"

    try:
        result = create_post(
            BUFFER_API_KEY,
            channel_id=channel_id,
            text=text,
            image_url=image_url,
            mode=mode,
            scheduling_type=scheduling_type,
        )
    except BufferApiError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"result": result})


CF_HELPER_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cloudflare Env Helper</title>
  <style>
    :root { color-scheme: dark; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
    body { margin: 0; padding: 24px; background: #05070a; color: #e8f0ff; }
    main { max-width: 920px; margin: 0 auto; background: #10171d; border: 1px solid #203040; border-radius: 16px; padding: 20px; }
    h1 { margin: 0 0 8px; color: #72f1b8; }
    p, li { color: #8ea4bf; line-height: 1.5; }
    label { display: block; margin: 16px 0 8px; font-weight: 700; }
    input, textarea { width: 100%; box-sizing: border-box; border-radius: 10px; border: 1px solid #203040; background: #0b1117; color: #e8f0ff; padding: 12px; font: inherit; }
    textarea { min-height: 160px; resize: vertical; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 16px; }
    button { border: 1px solid #203040; background: #15212c; color: #e8f0ff; padding: 10px 14px; border-radius: 999px; cursor: pointer; font: inherit; }
    .ok { color: #72f1b8; }
    .err { color: #ff8a8a; }
    code { color: #72f1b8; }
  </style>
</head>
<body>
  <main>
    <h1>Cloudflare Env Helper</h1>
    <p>Local-only helper. It writes to <code>~/.config/codex-shared/cloudflare.env</code> on this machine.</p>
    {% if saved %}<p class="ok">Saved.</p>{% endif %}
    {% if error %}<p class="err">{{ error }}</p>{% endif %}
    <form method="post">
      <label for="account">Account ID</label>
      <input id="account" name="account_id" value="{{ account_id }}" autocomplete="off" spellcheck="false" placeholder="Cloudflare account ID">

      <label for="token">API Token</label>
      <textarea id="token" name="api_token" autocomplete="off" spellcheck="false" placeholder="Paste Cloudflare API token here">{{ api_token }}</textarea>

      <label for="zone">Zone ID (optional)</label>
      <input id="zone" name="zone_id" value="{{ zone_id }}" autocomplete="off" spellcheck="false" placeholder="Cloudflare zone ID">

      <div class="row">
        <button type="submit">Save .env.cloudflare</button>
      </div>
    </form>
    <p>After saving, tell Codex done and I’ll purge the cache.</p>
  </main>
</body>
</html>
"""


@app.route("/cloudflare", methods=["GET", "POST"])
def cloudflare_env_helper():
    if request.method == "GET":
        return render_template_string(
            CF_HELPER_PAGE,
            saved=False,
            error="",
            account_id="",
            api_token="",
            zone_id="",
        )

    account_id = clean_config_value(request.form.get("account_id"))
    api_token = clean_config_value(request.form.get("api_token"))
    zone_id = clean_config_value(request.form.get("zone_id"))

    if not account_id or not api_token:
        return render_template_string(
            CF_HELPER_PAGE,
            saved=False,
            error="Account ID and API token are required.",
            account_id=account_id,
            api_token=api_token,
            zone_id=zone_id,
        ), 400

    write_shared_cloudflare_env({
        "CLOUDFLARE_ACCOUNT_ID": account_id,
        "CLOUDFLARE_API_TOKEN": api_token,
        "CLOUDFLARE_ZONE_ID": zone_id,
    })

    return render_template_string(
        CF_HELPER_PAGE,
        saved=True,
        error="",
        account_id=account_id,
        api_token=api_token,
        zone_id=zone_id,
    )


def render_ops_page(result="", output="", ok=False, status=200, set_session=False, unlocked=False):
    needs_unlock = bool(
        POCKET_ACCESS_TOKEN
        and not ops_session_valid()
        and not unlocked
    )
    response = make_response(render_template_string(
        OPS_PAGE,
        auth_label=ops_auth_label() if not unlocked else "Ops is unlocked for this browser.",
        needs_unlock=needs_unlock,
        result=result,
        output=output,
        ok=ok,
        restart_command=restart_command(),
    ), status)
    if set_session:
        response.set_cookie(
            OPS_SESSION_COOKIE,
            create_ops_session_value(),
            max_age=current_ops_session_seconds(),
            httponly=True,
            secure=request.is_secure,
            samesite="Lax",
        )
    return response


@app.route("/ops", methods=["GET", "POST"])
def ops_page():
    if request.method == "GET":
        return render_ops_page()

    request.get_data(cache=True)
    action = str(request.form.get("action") or "unlock").strip()
    authorized, set_session, failure_message = ops_authorized()
    if not authorized:
        return render_ops_page(
            result=failure_message or "Invalid ops authorization.",
            output="",
            ok=False,
            status=401,
        )

    if action == "unlock":
        return render_ops_page(
            result="Ops unlocked. You can pull, restart, or pull then restart without typing the token again.",
            output="",
            ok=True,
            set_session=set_session,
            unlocked=True,
        )

    if action in {"enable_open", "disable_open"}:
        return render_ops_page(
            result="Open mode has been replaced by HMAC signed ops requests.",
            output="",
            ok=False,
            status=410,
            set_session=set_session,
            unlocked=set_session,
        )

    if action == "pull":
        pull = run_git_pull()
        return render_ops_page(
            result=pull["message"],
            output=pull["output"],
            ok=pull["ok"],
            status=200 if pull["ok"] else 502,
            set_session=set_session,
            unlocked=set_session,
        )

    if action == "restart":
        command = restart_current_process()
        return render_ops_page(
            result="Restart requested. Wait a moment, then reload the page.",
            output=f"Command: {command}\nLog: {RESTART_LOG_PATH}",
            ok=True,
            set_session=set_session,
            unlocked=set_session,
        )

    if action == "pull_restart":
        pull = run_git_pull()
        if not pull["ok"]:
            return render_ops_page(
                result=pull["message"],
                output=pull["output"],
                ok=False,
                status=502,
                set_session=set_session,
                unlocked=set_session,
            )
        command = restart_current_process()
        output = "\n\n".join(part for part in [
            pull["output"],
            f"Restart command: {command}\nLog: {RESTART_LOG_PATH}",
        ] if part)
        return render_ops_page(
            result=f"{pull['message']} Restart requested. Wait a moment, then reload the page.",
            output=output,
            ok=True,
            set_session=set_session,
            unlocked=set_session,
        )

    return render_ops_page(
        result=f"Unknown ops action: {action}",
        output="",
        ok=False,
        status=400,
        set_session=set_session,
        unlocked=set_session,
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

    pull = run_git_pull()

    return render_template_string(
        ACTION_PAGE,
        title="Pocket Pull",
        heading="Pull",
        description="Fetch and merge the latest code from origin/master.",
        action="/pull",
        button="Pull from Git",
        auth_required=bool(POCKET_ACCESS_TOKEN),
        result=pull["message"],
        output=pull["output"],
        ok=pull["ok"],
        next_href="/restart" if pull["ok"] else "",
        next_label="Restart Server",
    ), 200 if pull["ok"] else 502


@app.route("/restart", methods=["GET", "POST"])
def restart_page():
    if request.method == "GET":
        return render_template_string(
            ACTION_PAGE,
            title="Pocket Restart",
            heading="Restart",
            description="Start a fresh Pocket Server process in the background, then stop the old one.",
            action="/restart",
            button="Restart Server",
            auth_required=bool(POCKET_ACCESS_TOKEN),
            result="",
            output=f"Command: {restart_command()}\nLog: {RESTART_LOG_PATH}",
            ok=False,
        )

    if access_denied():
        return render_template_string(
            ACTION_PAGE,
            title="Pocket Restart",
            heading="Restart",
            description="Start a fresh Pocket Server process in the background, then stop the old one.",
            action="/restart",
            button="Restart Server",
            auth_required=bool(POCKET_ACCESS_TOKEN),
            result="Invalid Pocket access token.",
            output="",
            ok=False,
        ), 401

    command = restart_current_process()
    return render_template_string(
        ACTION_PAGE,
        title="Pocket Restart",
        heading="Restart",
        description="Start a fresh Pocket Server process in the background, then stop the old one.",
        action="/restart",
        button="Restart Server",
        auth_required=bool(POCKET_ACCESS_TOKEN),
        result="Restart requested. Wait a moment, then reload the page.",
        output=f"Command: {command}\nLog: {RESTART_LOG_PATH}",
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
