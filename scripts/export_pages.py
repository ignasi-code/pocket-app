from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as pocket  # noqa: E402


STORE_ASSET_ROUTES = [
    "/store/assets/store.js",
    "/store/assets/store.min.js",
    "/store/assets/store.css",
    "/store/assets/store.min.css",
    *[
        f"/store/assets/store.{scope}.min.css"
        for scope in sorted(pocket.STORE_CSS_SCOPES)
    ],
    *[
        f"/store/assets/fonts/{filename}"
        for filename in sorted(pocket.STORE_FONT_ASSETS)
    ],
]

STATIC_PAGE_ROUTES = {
    "/": "index.html",
    "/bp": "bp/index.html",
}


def clean_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)


def write_bytes(output_dir: Path, relative_path: str, data: bytes) -> Path:
    destination = output_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return destination


def write_text(output_dir: Path, relative_path: str, text: str) -> Path:
    destination = output_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination


def clean_index_path(route: str) -> str:
    clean = route.split("?", 1)[0].strip("/")
    if not clean:
        return "index.html"
    return f"{clean}/index.html"


def asset_path(route: str) -> str:
    return route.split("?", 1)[0].lstrip("/")


def fetch_route(client, route: str) -> bytes:
    response = client.get(route)
    try:
        if response.status_code != 200:
            raise RuntimeError(f"Export route {route} returned HTTP {response.status_code}.")
        return response.get_data()
    finally:
        response.close()


def export_route(client, output_dir: Path, route: str, relative_path: str) -> Path:
    return write_bytes(output_dir, relative_path, fetch_route(client, route))


def export_clean_html_route(client, output_dir: Path, route: str) -> Path:
    return export_route(client, output_dir, route, clean_index_path(route))


def store_collection_routes() -> list[str]:
    return [
        f"/store/collections/{handle}"
        for handle in sorted(pocket.store_collection_definitions())
    ]


def store_collection_fragment_routes() -> list[str]:
    return [
        f"/store/collections/{handle}/products-fragment?offset={pocket.STORE_COLLECTION_INITIAL_PRODUCT_LIMIT}"
        for handle in sorted(pocket.store_collection_definitions())
    ]


def store_product_routes() -> list[str]:
    handles = [
        str(product.get("handle") or "").strip()
        for product in pocket.store_products()
    ]
    return [
        f"/store/products/{handle}"
        for handle in sorted({handle for handle in handles if handle})
    ]


def export_cart_items_static_index(output_dir: Path) -> Path:
    payload = pocket.json.dumps(
        pocket.store_cart_index_payload(),
        separators=(",", ":"),
    )
    return write_text(output_dir, "store/cart-items.json", payload)


def headers_file() -> str:
    html_cache = "Cache-Control: public, max-age=300, stale-while-revalidate=3600, stale-if-error=86400"
    return "\n".join([
        "/",
        f"  {html_cache}",
        "",
        "/bp/*",
        f"  {html_cache}",
        "",
        "/store/",
        f"  {html_cache}",
        "",
        "/store/cart/*",
        f"  {html_cache}",
        "",
        "/store/products/*",
        f"  {html_cache}",
        "",
        "/store/collections/*",
        f"  {html_cache}",
        "",
        "/store/assets/*",
        "  Cache-Control: public, max-age=31536000, immutable",
        "",
        "/store/catalog.json",
        "  Cache-Control: public, max-age=3600, stale-while-revalidate=3600, stale-if-error=86400",
        "",
        "/store/cart-index.json",
        "  Cache-Control: public, max-age=3600, stale-while-revalidate=3600, stale-if-error=86400",
        "",
        "/store/cart-items.json",
        "  Cache-Control: public, max-age=3600, stale-while-revalidate=3600, stale-if-error=86400",
        "",
        "/store/collections/*/products-fragment",
        "  Cache-Control: public, max-age=3600, stale-while-revalidate=3600, stale-if-error=86400",
        "",
    ])


def build_dist(output_dir: Path | str = ROOT_DIR / "dist") -> set[Path]:
    output_path = Path(output_dir)
    clean_output_dir(output_path)
    written: set[Path] = set()

    with pocket.app.test_client() as client:
        for route, relative_path in STATIC_PAGE_ROUTES.items():
            written.add(export_route(client, output_path, route, relative_path))

        for route in [
            "/store",
            "/store/cart",
            *store_collection_routes(),
            *store_collection_fragment_routes(),
            *store_product_routes(),
            "/store/cart-upsells-fragment",
            "/store/cart-drawer-upsells-fragment",
        ]:
            written.add(export_clean_html_route(client, output_path, route))

        for route in [
            "/store/catalog.json",
            "/store/cart-index.json",
        ]:
            written.add(export_route(client, output_path, route, asset_path(route)))

        written.add(export_cart_items_static_index(output_path))

        for route in STORE_ASSET_ROUTES:
            written.add(export_route(client, output_path, route, asset_path(route)))

    written.add(write_text(output_path, "_headers", headers_file()))
    return written


def main() -> None:
    written = build_dist()
    print(f"Built dist with {len(written)} files.")


if __name__ == "__main__":
    main()
