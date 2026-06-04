import json
import html as html_lib
import os
import platform
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, render_template_string, request, send_file


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
    extra_args = shlex.split(os.environ.get("POCKET_GEMINI_ARGS", ""))
    return ["-m", current_default_gemini_model(), *extra_args]


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
STORE_CATALOG_PATH = BASE_DIR / "pages" / "store" / "catalog.json"
STORE_DATA_DIR = BASE_DIR / "pages" / "store" / "data"
STORE_PLACEHOLDER_IMAGE = "https://placehold.co/900x1100/f8dd5f/1f1a15?text=Roxanne"
STORE_BASE_URL = os.environ.get("POCKET_STORE_BASE_URL", "https://roxanneassoulin.com").rstrip("/")
STORE_CURRENCY = os.environ.get("POCKET_STORE_CURRENCY", "usd").lower()
STORE_SWATCH_COLORS = {
    "cloud": "#8ED1D1",
    "lemon": "#E3D43C",
    "sienna": "#C75530",
    "salt & pepper": "#1f1f1f",
}
RESTART_LOG_PATH = BASE_DIR / "pocket-restart.log"

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
        return f"${format_display_price(low)}"
    return f"${format_display_price(low)} - ${format_display_price(high)}"


def store_variant_price_label(variant):
    return f"${format_display_price(parse_price_cents(variant.get('price')))}"


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
    "green": {"green", "forest", "moss"},
    "pink": {"pink", "rose"},
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


def store_apply_collection_filters(products, args):
    categories = [value for value in args.getlist("filter.p.product_type[]") if value]
    colors = [value for value in args.getlist("filter.p.m.roxanne-assoulin.filter_color[]") if value]
    filtered = list(products)
    if categories:
        category_set = {category.lower() for category in categories}
        filtered = [product for product in filtered if str(product.get("product_type", "")).lower() in category_set]
    if colors:
        filtered = [product for product in filtered if any(store_product_matches_color(product, color) for color in colors)]
    return filtered, {"categories": categories, "colors": colors}


def store_template_context(**kwargs):
    merchandising = load_store_merchandising()
    context = {
        "collections": store_collection_definitions(),
        "merchandising": merchandising,
        "product_image": store_product_image,
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
    }
    context.update(kwargs)
    return context


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


@app.route("/store")
@app.route("/store/")
def store_page():
    products_by_handle = {product.get("handle"): product for product in store_products()}
    return render_template(
        "store/home.html",
        **store_template_context(
            homepage=load_store_homepage(),
            products_by_handle=products_by_handle,
        ),
    )


@app.route("/store/collections/<handle>")
def store_collection_page(handle):
    collection, products = store_collection_products(handle)
    if not collection:
        abort(404)
    products, active_filters = store_apply_collection_filters(products, request.args)
    products = store_sort_collection_products(products, request.args.get("sort_by"))
    return render_template(
        "store/collection.html",
        **store_template_context(
            handle=handle,
            collection=collection,
            products=products,
            active_filters=active_filters,
            current_sort=request.args.get("sort_by", ""),
        ),
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
    return render_template(
        "store/product.html",
        **store_template_context(
            product=product,
            related=related,
        ),
    )


@app.route("/store/cart")
def store_cart_page():
    return render_template(
        "store/cart.html",
        **store_template_context(),
    )


@app.route("/store/assets/store.js")
def store_asset_js():
    return send_file(BASE_DIR / "pages" / "store" / "store.js", mimetype="text/javascript")


@app.route("/store/catalog.json")
def store_catalog():
    return send_file(STORE_CATALOG_PATH, mimetype="application/json")


@app.route("/store/api/checkout", methods=["POST"])
def store_mock_checkout():
    data = request.get_json(silent=True) or {}
    cart_items = data.get("cartItems")

    if not isinstance(cart_items, list):
        return jsonify({"error": "cartItems must be an array."}), 400
    if not cart_items:
        return jsonify({"error": "Cart is empty."}), 400
    if len(cart_items) > 100:
        return jsonify({"error": "Cart has too many lines."}), 400

    try:
        variants = store_variant_lookup()
    except OSError as exc:
        return jsonify({"error": f"Store catalog is unavailable: {exc}"}), 500
    except json.JSONDecodeError as exc:
        return jsonify({"error": f"Store catalog is invalid: {exc}"}), 500

    verified_items = []
    subtotal_cents = 0
    permalink_parts = []

    try:
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
            })
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "mode": "mock",
        "currency": STORE_CURRENCY,
        "item_count": sum(item["qty"] for item in verified_items),
        "subtotal_cents": subtotal_cents,
        "subtotal": format_price(subtotal_cents),
        "line_items": verified_items,
        "shopify_cart_url": f"{STORE_BASE_URL}/cart/{','.join(permalink_parts)}",
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
