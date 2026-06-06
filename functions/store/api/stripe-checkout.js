const JSON_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Type": "application/json",
};

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: JSON_HEADERS,
  });
}

function parsePriceCents(price) {
  const value = Number.parseFloat(String(price || "0").replaceAll(",", ""));
  if (!Number.isFinite(value) || value <= 0) return 0;
  return Math.round(value * 100);
}

function parseCartItem(item) {
  if (!item || typeof item !== "object") {
    throw new Error("Each cart item must be an object.");
  }
  const id = Number.parseInt(item.id, 10);
  const qty = Number.parseInt(item.qty, 10);
  if (!Number.isFinite(id) || !Number.isFinite(qty)) {
    throw new Error("Cart items require numeric id and qty.");
  }
  if (qty < 1 || qty > 99) {
    throw new Error("Cart item quantity must be between 1 and 99.");
  }
  return { id, qty };
}

async function loadCatalog(env, request) {
  const catalogUrl = new URL("/store/catalog.json", request.url);
  const response = await env.ASSETS.fetch(new Request(catalogUrl.toString(), { method: "GET" }));
  if (!response.ok) {
    throw new Error(`Store catalog is unavailable: ${response.status}`);
  }
  return response.json();
}

function productImage(product, variant) {
  return variant?.featured_image?.src || product?.images?.[0]?.src || "";
}

function verifyCartItems(cartItems, catalog) {
  if (!Array.isArray(cartItems)) {
    throw new Error("cartItems must be an array.");
  }
  if (!cartItems.length) {
    throw new Error("Cart is empty.");
  }
  if (cartItems.length > 100) {
    throw new Error("Cart has too many lines.");
  }

  const variants = new Map();
  for (const product of catalog.products || []) {
    for (const variant of product.variants || []) {
      variants.set(Number(variant.id), { product, variant });
    }
  }

  return cartItems.map(rawItem => {
    const item = parseCartItem(rawItem);
    const catalogItem = variants.get(item.id);
    if (!catalogItem) {
      throw new Error(`Unknown variant id: ${item.id}`);
    }
    const { product, variant } = catalogItem;
    if (variant.available === false) {
      throw new Error(`Variant is unavailable: ${item.id}`);
    }
    const unitAmount = parsePriceCents(variant.price);
    if (unitAmount <= 0) {
      throw new Error(`Variant has invalid price: ${item.id}`);
    }
    return {
      id: item.id,
      qty: item.qty,
      title: product.title || "Untitled product",
      variantTitle: variant.title || "",
      unitAmount,
      image: productImage(product, variant),
    };
  });
}

function checkoutUrls(env, request) {
  const origin = new URL(request.url).origin;
  return {
    success: env.STRIPE_SUCCESS_URL || `${origin}/store/cart?stripe=success`,
    cancel: env.STRIPE_CANCEL_URL || `${origin}/store/cart?stripe=cancel`,
  };
}

function stripeSessionParams(items, env, request) {
  const urls = checkoutUrls(env, request);
  const currency = String(env.STRIPE_CURRENCY || "usd").toLowerCase();
  const params = new URLSearchParams();
  params.set("mode", "payment");
  params.set("success_url", urls.success);
  params.set("cancel_url", urls.cancel);
  params.set("metadata[source]", "pocket-store-fallback");

  items.forEach((item, index) => {
    const prefix = `line_items[${index}]`;
    const name = item.variantTitle && item.variantTitle !== "Default Title"
      ? `${item.title} - ${item.variantTitle}`
      : item.title;
    params.set(`${prefix}[quantity]`, String(item.qty));
    params.set(`${prefix}[price_data][currency]`, currency);
    // First line-item amount shape: line_items[0][price_data][unit_amount]
    params.set(`${prefix}[price_data][unit_amount]`, String(item.unitAmount));
    params.set(`${prefix}[price_data][product_data][name]`, name);
    params.set(`${prefix}[price_data][product_data][metadata][variant_id]`, String(item.id));
    if (String(item.image || "").startsWith("https://")) {
      params.set(`${prefix}[price_data][product_data][images][0]`, item.image);
    }
  });
  return params;
}

export async function onRequestGet({ request }) {
  const url = new URL(request.url);
  if (url.searchParams.get("check") === "1") {
    return json({ ok: true, receiver: "cloudflare-pages-stripe-checkout" });
  }
  return json({ ok: false, error: "not_found" }, 404);
}

export async function onRequestPost({ request, env }) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON body." }, 400);
  }

  let items;
  try {
    const catalog = await loadCatalog(env, request);
    items = verifyCartItems(body.cartItems, catalog);
  } catch (error) {
    return json({ error: error.message || "Cart verification failed." }, 400);
  }

  if (!env.STRIPE_SECRET_KEY) {
    return json({ error: "Stripe fallback is not configured." }, 503);
  }

  const stripeResponse = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.STRIPE_SECRET_KEY}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: stripeSessionParams(items, env, request),
  });
  const payload = await stripeResponse.json().catch(() => ({}));

  if (!stripeResponse.ok || !payload.url) {
    return json({
      error: "Stripe checkout failed.",
      status: stripeResponse.status,
      detail: payload?.error?.message || "",
    }, 502);
  }

  return json({ mode: "stripe", url: payload.url });
}
