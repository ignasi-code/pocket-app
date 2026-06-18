const WAITLIST_PATH = "/api/maison-flou/waitlist";
const ORIGIN_URL = "__MAISON_FLOU_WAITLIST_ORIGIN_URL__";
const MAX_BODY_BYTES = 16 * 1024;
const ALLOWED_ORIGINS = new Set([
  "https://maisonflou.com",
  "https://www.maisonflou.com",
  "https://maison-flou.pages.dev",
]);

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  const allowOrigin = ALLOWED_ORIGINS.has(origin) ? origin : "https://maisonflou.com";
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Accept",
    "Cache-Control": "no-store",
    "Vary": "Origin",
  };
}

function jsonResponse(request, payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      ...corsHeaders(request),
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}

function cleanText(value, limit = 160) {
  return String(value || "")
    .replace(/[\x00-\x1f\x7f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, limit)
    .trim();
}

function normalizeEmail(value) {
  const email = cleanText(value, 254).toLowerCase();
  if (!email) return "";
  return /^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,24}$/.test(email) ? email : "";
}

async function readPayload(request) {
  const contentType = request.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    const payload = await request.json();
    return payload && typeof payload === "object" ? payload : {};
  }
  if (contentType.includes("application/x-www-form-urlencoded")) {
    return Object.fromEntries(new URLSearchParams(await request.text()).entries());
  }
  if (contentType.includes("multipart/form-data")) {
    return Object.fromEntries((await request.formData()).entries());
  }
  return {};
}

async function handleWaitlist(request) {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders(request) });
  }
  if (request.method !== "POST") {
    return jsonResponse(request, { ok: false, error: "method_not_allowed" }, 405);
  }

  const contentLength = Number(request.headers.get("Content-Length") || "0");
  if (contentLength > MAX_BODY_BYTES) {
    return jsonResponse(request, { ok: false, error: "payload_too_large" }, 413);
  }

  let payload;
  try {
    payload = await readPayload(request);
  } catch {
    return jsonResponse(request, { ok: false, error: "invalid_payload" }, 400);
  }

  if (cleanText(payload.website, 80) || cleanText(payload.url, 80) || cleanText(payload.company, 80)) {
    return jsonResponse(request, { ok: true, status: "received" });
  }

  const email = normalizeEmail(payload.email);
  if (!email) {
    return jsonResponse(request, { ok: false, error: "valid_email_required" }, 400);
  }

  const originPayload = {
    email,
    instagram: cleanText(payload.instagram, 80).replace(/^@+/, ""),
    source: cleanText(payload.source, 120) || "maisonflou.com",
  };

  let originResponse;
  try {
    originResponse = await fetch(ORIGIN_URL, {
      method: "POST",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Maison-Flou-Edge": "cloudflare-worker",
      },
      body: JSON.stringify(originPayload),
    });
  } catch {
    return jsonResponse(request, { ok: false, error: "origin_unavailable" }, 502);
  }

  const body = await originResponse.text();
  return new Response(body || "{}", {
    status: originResponse.status,
    headers: {
      ...corsHeaders(request),
      "Content-Type": originResponse.headers.get("Content-Type") || "application/json; charset=utf-8",
    },
  });
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname !== WAITLIST_PATH) {
      return jsonResponse(request, { ok: false, error: "not_found" }, 404);
    }
    return handleWaitlist(request);
  },
};
