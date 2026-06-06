const NO_STORE_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Type": "application/json",
};

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: NO_STORE_HEADERS,
  });
}

export async function onRequestGet({ request }) {
  const url = new URL(request.url);
  if (url.searchParams.get("check") === "1") {
    return json({ ok: true, receiver: "cloudflare-pages-pulse" });
  }
  return json({ ok: false, error: "not_found" }, 404);
}

export async function onRequestPost({ request }) {
  const length = Number(request.headers.get("content-length") || 0);
  if (length > 16 * 1024) {
    return json({ ok: false, error: "payload_too_large" }, 413);
  }

  try {
    if (request.headers.get("content-type")?.includes("application/json")) {
      await request.json();
    } else {
      await request.text();
    }
  } catch {
    return json({ ok: false, error: "invalid_payload" }, 400);
  }

  return new Response(null, {
    status: 204,
    headers: {
      "Cache-Control": "no-store",
    },
  });
}
