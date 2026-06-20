const WAITLIST_PATH = "/api/maison-flou/waitlist";
const API_PREFIX = "/api/maison-flou";
const LAB_PATH_PREFIX = "/lab";
const OFFICE_HOST = "office.maisonflou.com";
const OFFICE_SESSION_COOKIE = "mf_office_session";
const OFFICE_SESSION_SECONDS = 60 * 60 * 24;
const MAX_BODY_BYTES = 16 * 1024;
const FROM_EMAIL = "Maison Flou <atelier@maisonflou.com>";
const REPLY_TO_EMAIL = "atelier@maisonflou.com";
const ATELIER_EMAIL = "atelier@maisonflou.com";
const DEFAULT_SCHEDULER_ENABLED = "false";
const DEFAULT_SCHEDULER_MODE = "publish";
const DEFAULT_POSTS_PER_DAY = "1";
const DEFAULT_PUBLISH_TIMES = "09:00";
const DEFAULT_OFFICE_TIMEZONE = "Europe/Madrid";
const DEFAULT_RECAP_ENABLED = "true";
const DEFAULT_RECAP_TIME = "18:00";
const DEFAULT_META_GRAPH_VERSION = "v25.0";
const DEFAULT_BUSINESS_ID = "maison-flou";
const DEFAULT_TLDR_MODEL = "gemini-2.5-flash-lite";
const DEFAULT_TEXT_MODEL = "gemini-2.5-flash-lite";
const DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image";
const DEFAULT_IMAGE_SIZE = 1080;
const DEFAULT_IMAGE_QUALITY = 88;
const IMAGE_PROMPT_TEMPLATE = `Act as the Creative Director for an elite, hyper-minimalist French fashion house called MAISON FLOU, inspired by Jacquemus, Loewe, and Coperni. Your sole task is to generate a single, highly detailed image description prompt in English for an AI image generator (Flux).

STRICT OUTPUT RULES:
1. Return ONLY the raw prompt text in English. No introductions, no explanations, no quotation marks.
2. The prompt must focus on one architectural luxury object.
3. Environment: Mediterranean backdrops, brutalist concrete ledges, sun-bleached stone, textured cream plaster walls, blinding summer sunlight, and razor-sharp shadows.
4. Camera/Aesthetic: High-end Vogue editorial photography, 35mm film grain, cinematic muted or overexposed tones.

Product mix guidance for this run:
{category_prompt}

Example of a valid output:
A sculptural matte ceramic vase with impossible fluid asymmetrical curves, resting on a brutalist raw concrete pedestal, blinding midday sunlight, razor sharp shadows, grainy 35mm texture.`;
const CAPTION_PROMPT_TEMPLATE = `Act as the Copywriter for MAISON FLOU. I will provide you with an image description. You must generate a short, cold, highly sophisticated Instagram caption for it.

STRICT OUTPUT RULES:
1. Return ONLY the caption text. No emojis, no hashtags.
2. Start the post with exactly: Objet d’étude {object_number}.
3. Write 2 short, poetic, philosophical lines about space, form, stillness, or structure based on the image description provided.
4. Conclude the caption with exactly these two phrases, keeping the double line breaks:
"Allocation for Collection 01 is strictly limited. Request registry access at our digital atelier.

maisonflou.com"

Image Description to process:
{image_prompt}`;
const OBJECT_CATEGORIES = [
  {
    id: "leather-objects",
    label: "Bags / clutches / leather objects",
    weight: 25,
    prompt: "bags, clutches, structured leather goods, folded leather objects, or small architectural leather forms",
  },
  {
    id: "draped-textiles",
    label: "Draped textiles / garment fragments",
    weight: 25,
    prompt: "draped luxury textiles, garment fragments, sculptural fabric forms, or folded couture textile objects",
  },
  {
    id: "wearable-accessories",
    label: "Eyewear / jewelry / hair objects / belts",
    weight: 18,
    prompt: "sculptural eyewear, stone jewelry forms, metal hair objects, architectural belts, or other wearable accessories",
  },
  {
    id: "footwear-forms",
    label: "Shoes / abstract footwear",
    weight: 12,
    prompt: "abstract footwear, sculptural shoes, sandal forms, or impossible shoe-like luxury objects",
  },
  {
    id: "vessels",
    label: "Perfume / glass / ceramic / vessel objects",
    weight: 12,
    prompt: "glass perfume vessels, geometric ceramic objects, impossible vases, or small craft vessels",
  },
  {
    id: "experimental-objects",
    label: "Experimental tech / impossible luxury objects",
    weight: 8,
    prompt: "experimental tech-luxury objects, impossible luxury instruments, conceptual closures, or non-obvious fashion objects",
  },
];
const ALLOWED_ORIGINS = new Set([
  "https://maisonflou.com",
  "https://www.maisonflou.com",
  "https://office.maisonflou.com",
  "https://maison-flou.pages.dev",
]);

function utcTimestamp() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  const allowOrigin = ALLOWED_ORIGINS.has(origin) ? origin : "https://maisonflou.com";
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, X-Pocket-Token",
    "Cache-Control": "no-store",
    "Vary": "Origin",
  };
}

function jsonResponse(request, payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      ...corsHeaders(request),
      ...extraHeaders,
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

function boolSetting(value) {
  return ["1", "true", "yes", "on", "enabled"].includes(String(value || "").trim().toLowerCase());
}

function parseJsonObject(value) {
  try {
    const parsed = JSON.parse(String(value || "{}"));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function htmlResponse(html, status = 200) {
  return new Response(html, {
    status,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

function unauthorizedResponse(request) {
  return jsonResponse(request, { ok: false, error: "unauthorized" }, 401);
}

function requestToken(request) {
  const url = new URL(request.url);
  const authorization = request.headers.get("Authorization") || "";
  const bearer = authorization.match(/^Bearer\s+(.+)$/i);
  return cleanText(
    request.headers.get("X-Pocket-Token")
      || (bearer && bearer[1])
      || url.searchParams.get("token")
      || "",
    500
  );
}

function labAccessEmail(request) {
  return cleanText(request.headers.get("Cf-Access-Authenticated-User-Email"), 254).toLowerCase();
}

function allowedOperatorEmails(env) {
  return String(env.OFFICE_ALLOWED_EMAILS || env.LAB_ALLOWED_EMAILS || "")
    .split(",")
    .map((item) => normalizeEmail(item))
    .filter(Boolean);
}

function tokenAccessAllowed(request, env) {
  const token = requestToken(request);
  const expectedToken = cleanText(env.LAB_ACCESS_TOKEN || env.POCKET_ACCESS_TOKEN, 500);
  if (expectedToken && token === expectedToken) return true;

  const host = new URL(request.url).hostname.toLowerCase();
  if (boolSetting(env.LAB_TRUST_CF_ACCESS) && host === OFFICE_HOST) {
    const email = labAccessEmail(request);
    const allowedEmails = allowedOperatorEmails(env);
    if (email && (!allowedEmails.length || allowedEmails.includes(email))) return true;
  }

  return false;
}

function cookieValue(request, name) {
  const cookie = request.headers.get("Cookie") || "";
  for (const part of cookie.split(";")) {
    const [rawKey, ...rest] = part.trim().split("=");
    if (rawKey === name) return rest.join("=");
  }
  return "";
}

function base64UrlEncodeBytes(value) {
  return bytesToBase64(value).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64UrlEncodeText(value) {
  return base64UrlEncodeBytes(new TextEncoder().encode(String(value || "")));
}

function base64UrlDecodeText(value) {
  const text = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
  const padded = text.padEnd(Math.ceil(text.length / 4) * 4, "=");
  return new TextDecoder().decode(base64ToBytes(padded));
}

function sessionSecret(env) {
  return cleanText(env.OFFICE_SESSION_SECRET || env.LAB_ACCESS_TOKEN || env.POCKET_ACCESS_TOKEN, 500);
}

async function hmacSignature(env, value) {
  const secret = sessionSecret(env);
  if (!secret) return "";
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return base64UrlEncodeBytes(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value)));
}

async function signedSessionCookie(env, email) {
  if (!sessionSecret(env)) throw new Error("session_secret_missing");
  const now = Math.floor(Date.now() / 1000);
  const payload = base64UrlEncodeText(JSON.stringify({
    email,
    iat: now,
    exp: now + OFFICE_SESSION_SECONDS,
  }));
  const signature = await hmacSignature(env, payload);
  return `${OFFICE_SESSION_COOKIE}=${payload}.${signature}; Path=/; Max-Age=${OFFICE_SESSION_SECONDS}; HttpOnly; Secure; SameSite=Lax`;
}

async function officeSessionEmail(request, env) {
  const value = cookieValue(request, OFFICE_SESSION_COOKIE);
  const [payload, signature] = value.split(".");
  if (!payload || !signature || !sessionSecret(env)) return "";
  const expected = await hmacSignature(env, payload);
  if (signature !== expected) return "";
  try {
    const data = JSON.parse(base64UrlDecodeText(payload));
    if (!data || Number(data.exp) < Math.floor(Date.now() / 1000)) return "";
    const email = normalizeEmail(data.email);
    return allowedOperatorEmails(env).includes(email) ? email : "";
  } catch {
    return "";
  }
}

async function labAccessAllowed(request, env) {
  if (tokenAccessAllowed(request, env)) return true;
  return Boolean(await officeSessionEmail(request, env));
}

function maskEmail(email) {
  const text = cleanText(email, 254);
  const [name, domain] = text.split("@");
  if (!name || !domain) return text ? "hidden" : "";
  if (name.length <= 2) return `${name[0] || "*"}***@${domain}`;
  return `${name[0]}${"*".repeat(Math.min(5, Math.max(3, name.length - 2)))}${name[name.length - 1]}@${domain}`;
}

function normalizeEmail(value) {
  const email = cleanText(value, 254).toLowerCase();
  if (!email) return "";
  return /^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,24}$/.test(email) ? email : "";
}

function hex(buffer) {
  return [...new Uint8Array(buffer)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function sha256(value) {
  return hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
}

async function sha256Bytes(bytes) {
  return hex(await crypto.subtle.digest("SHA-256", bytes));
}

function bytesToBase64(bytes) {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < view.length; index += chunkSize) {
    binary += String.fromCharCode(...view.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function base64ToBytes(value) {
  const binary = atob(String(value || ""));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function imageExtension(mimeType) {
  const text = String(mimeType || "").toLowerCase();
  if (text.includes("jpeg") || text.includes("jpg")) return "jpg";
  if (text.includes("webp")) return "webp";
  return "png";
}

function imageDimensions(bytes) {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  if (
    view.length >= 24
    && view[0] === 0x89
    && view[1] === 0x50
    && view[2] === 0x4E
    && view[3] === 0x47
  ) {
    return {
      width: (view[16] << 24) | (view[17] << 16) | (view[18] << 8) | view[19],
      height: (view[20] << 24) | (view[21] << 16) | (view[22] << 8) | view[23],
    };
  }

  if (view.length > 12 && view[0] === 0xFF && view[1] === 0xD8) {
    let index = 2;
    while (index + 9 < view.length) {
      if (view[index] !== 0xFF) {
        index += 1;
        continue;
      }
      const marker = view[index + 1];
      index += 2;
      if (marker === 0xD8 || marker === 0xD9) continue;
      if (index + 2 > view.length) break;
      const segmentLength = (view[index] << 8) | view[index + 1];
      if (segmentLength < 2) break;
      if ([0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF].includes(marker) && index + 7 < view.length) {
        return {
          height: (view[index + 3] << 8) | view[index + 4],
          width: (view[index + 5] << 8) | view[index + 6],
        };
      }
      index += segmentLength;
    }
  }
  return { width: 0, height: 0 };
}

function stripJpegMetadata(bytes) {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  if (view.length < 4 || view[0] !== 0xFF || view[1] !== 0xD8) return view;
  const chunks = [view.slice(0, 2)];
  let index = 2;
  while (index + 4 <= view.length) {
    if (view[index] !== 0xFF) {
      chunks.push(view.slice(index));
      break;
    }
    const marker = view[index + 1];
    if (marker === 0xDA) {
      chunks.push(view.slice(index));
      break;
    }
    if (marker === 0xD9) {
      chunks.push(view.slice(index, index + 2));
      break;
    }
    const segmentLength = (view[index + 2] << 8) | view[index + 3];
    if (segmentLength < 2 || index + 2 + segmentLength > view.length) {
      chunks.push(view.slice(index));
      break;
    }
    const shouldStrip = (marker >= 0xE0 && marker <= 0xEF) || marker === 0xFE;
    if (!shouldStrip) chunks.push(view.slice(index, index + 2 + segmentLength));
    index += 2 + segmentLength;
  }
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const output = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.length;
  }
  return output.length >= 4 ? output : view;
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

async function appendOfficeEvent(env, eventType, subject, message, status = "ok", metadata = {}) {
  const timestamp = utcTimestamp();
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO office_events (
      id, timestamp, business_id, event_type, status, subject, message, metadata
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    id,
    timestamp,
    "maison-flou",
    eventType,
    status,
    subject,
    message,
    JSON.stringify(metadata)
  ).run();
  return id;
}

async function getContentSetting(env, key, fallback = "") {
  const row = await env.DB.prepare(
    "SELECT value FROM content_settings WHERE key = ? LIMIT 1"
  ).bind(key).first();
  return cleanText(row && row.value, 500) || fallback;
}

async function setContentSetting(env, key, value) {
  await env.DB.prepare(
    `INSERT INTO content_settings (key, value, updated_at)
     VALUES (?, ?, ?)
     ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`
  ).bind(key, String(value || ""), utcTimestamp()).run();
}

function schedulerEnabled(value) {
  return ["1", "true", "yes", "on", "enabled"].includes(String(value || "").trim().toLowerCase());
}

function clampNumber(value, min, max, fallback) {
  const number = Number.parseInt(String(value || ""), 10);
  if (!Number.isFinite(number)) return fallback;
  return Math.max(min, Math.min(max, number));
}

function normalizeTime(value) {
  const match = String(value || "").trim().match(/^([01]?\d|2[0-3]):([0-5]\d)$/);
  if (!match) return "";
  return `${match[1].padStart(2, "0")}:${match[2]}`;
}

function parseTimeList(value, fallback = DEFAULT_PUBLISH_TIMES) {
  const times = String(value || "")
    .split(/[,\n]+/)
    .map(normalizeTime)
    .filter(Boolean);
  const unique = [...new Set(times)].sort();
  return unique.length ? unique : parseTimeList(fallback, "09:00");
}

function timeMinutes(value) {
  const time = normalizeTime(value);
  if (!time) return -1;
  const [hour, minute] = time.split(":").map(Number);
  return hour * 60 + minute;
}

function safeTimeZone(value) {
  const timeZone = cleanText(value, 80) || DEFAULT_OFFICE_TIMEZONE;
  try {
    new Intl.DateTimeFormat("en-CA", { timeZone }).format(new Date());
    return timeZone;
  } catch {
    return DEFAULT_OFFICE_TIMEZONE;
  }
}

function normalizeMetaAdAccountId(value) {
  const text = cleanText(value, 80).replace(/^act_+/i, "");
  return text ? `act_${text.replace(/[^0-9]/g, "")}` : "";
}

function normalizeMetaId(value) {
  return cleanText(value, 80).replace(/[^0-9]/g, "");
}

async function readMetaSettings(env) {
  const settings = await readContentSettings(env);
  return {
    ad_account_id: normalizeMetaAdAccountId(settings.meta_ad_account_id?.value),
    campaign_id: normalizeMetaId(settings.meta_campaign_id?.value),
    adset_id: normalizeMetaId(settings.meta_adset_id?.value),
    page_id: normalizeMetaId(settings.meta_page_id?.value),
    instagram_user_id: normalizeMetaId(settings.meta_instagram_user_id?.value),
    token_configured: Boolean(cleanText(env.META_ACCESS_TOKEN, 2000)),
    graph_version: cleanText(env.META_GRAPH_VERSION, 20) || DEFAULT_META_GRAPH_VERSION,
  };
}

function missingMetaConfig(config) {
  const missing = [];
  if (!config.token_configured) missing.push("META_ACCESS_TOKEN");
  if (!config.ad_account_id) missing.push("meta_ad_account_id");
  if (!config.campaign_id) missing.push("meta_campaign_id");
  if (!config.adset_id) missing.push("meta_adset_id");
  if (!config.page_id) missing.push("meta_page_id");
  if (!config.instagram_user_id) missing.push("meta_instagram_user_id");
  return missing;
}

function metaGraphUrl(env, path, params = {}) {
  const version = cleanText(env.META_GRAPH_VERSION, 20) || DEFAULT_META_GRAPH_VERSION;
  const url = new URL(`https://graph.facebook.com/${version}/${path.replace(/^\/+/, "")}`);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  return url;
}

async function metaGraphRequest(env, path, { method = "GET", params = {}, body = {} } = {}) {
  const token = cleanText(env.META_ACCESS_TOKEN, 3000);
  if (!token) throw new Error("META_ACCESS_TOKEN is not configured.");
  const headers = {
    "Authorization": `Bearer ${token}`,
    "Accept": "application/json",
    "User-Agent": "maison-flou-worker/0.1 (+https://maisonflou.com)",
  };
  const options = { method, headers };
  const url = metaGraphUrl(env, path, params);
  if (method !== "GET") {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    const form = new URLSearchParams();
    for (const [key, value] of Object.entries(body)) {
      if (value !== undefined && value !== null && value !== "") form.set(key, String(value));
    }
    options.body = form;
  }
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.error) {
    const error = payload.error || payload;
    throw new Error(`Meta ${method} ${path} HTTP ${response.status}: ${JSON.stringify(error).slice(0, 700)}`);
  }
  return payload;
}

function officeClock(date = new Date(), timeZone = DEFAULT_OFFICE_TIMEZONE) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: safeTimeZone(timeZone),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = Object.fromEntries(formatter.formatToParts(date).map((part) => [part.type, part.value]));
  const hour = parts.hour === "24" ? "00" : parts.hour;
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${hour}:${parts.minute}`,
    minutes: Number(hour) * 60 + Number(parts.minute),
    timeZone: safeTimeZone(timeZone),
  };
}

function isDueNow(clock, slot, windowMinutes = 20) {
  const slotMinutes = timeMinutes(slot);
  if (slotMinutes < 0) return false;
  const delta = clock.minutes - slotMinutes;
  return delta >= 0 && delta < windowMinutes;
}

function schedulerKey(kind, date, slot = "") {
  return `scheduler_${kind}_${date}${slot ? `_${slot.replace(":", "")}` : ""}`;
}

async function getSettingBoolean(env, key, fallback = "false") {
  return schedulerEnabled(await getContentSetting(env, key, fallback));
}

async function markSchedulerDone(env, kind, date, slot, value = "done") {
  await setContentSetting(env, schedulerKey(kind, date, slot), value);
}

async function schedulerAlreadyDone(env, kind, date, slot = "") {
  return Boolean(await getContentSetting(env, schedulerKey(kind, date, slot), ""));
}

async function appendOfficeEventOncePerDay(env, date, eventType, subject, message, status = "info", metadata = {}) {
  const key = schedulerKey(eventType.replace(/[^a-z0-9]+/gi, "_").toLowerCase(), date);
  if (await getContentSetting(env, key, "")) return false;
  await appendOfficeEvent(env, eventType, subject, message, status, metadata);
  await setContentSetting(env, key, utcTimestamp());
  return true;
}

async function logContentRun(env, data) {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO content_runs (
      id, timestamp, status, trigger, object_number, image_url, caption, buffer_post_id, metadata
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    id,
    utcTimestamp(),
    cleanText(data.status, 40) || "logged",
    cleanText(data.trigger, 80),
    cleanText(data.object_number, 12),
    cleanText(data.image_url, 500),
    String(data.caption || "").slice(0, 5000),
    cleanText(data.buffer_post_id, 120),
    JSON.stringify(data.metadata || {})
  ).run();
  return id;
}

async function readOfficeEvents(env, limit = 50) {
  const rows = await env.DB.prepare(
    `SELECT id, timestamp, business_id, event_type, status, subject, message, metadata
     FROM office_events
     WHERE business_id = ?
     ORDER BY timestamp DESC
     LIMIT ?`
  ).bind(DEFAULT_BUSINESS_ID, Math.max(1, Math.min(Number(limit) || 50, 250))).all();
  return (rows.results || []).map((row) => ({
    ...row,
    metadata: parseJsonObject(row.metadata),
  }));
}

async function readWaitlistLeads(env, { limit = 50, reveal = false } = {}) {
  const rows = await env.DB.prepare(
    `SELECT id, timestamp, email, email_hash, instagram, source,
            confirmation_status, confirmation_sent_at, notification_status, notification_sent_at
     FROM waitlist_leads
     ORDER BY timestamp DESC
     LIMIT ?`
  ).bind(Math.max(1, Math.min(Number(limit) || 50, 250))).all();
  return (rows.results || []).map((row) => ({
    ...row,
    email: reveal ? cleanText(row.email, 254) : maskEmail(row.email),
    email_revealed: Boolean(reveal),
  }));
}

async function countWaitlistLeads(env) {
  const row = await env.DB.prepare("SELECT COUNT(*) AS count FROM waitlist_leads").first();
  return Number(row && row.count) || 0;
}

async function readContentRuns(env, limit = 50) {
  const rows = await env.DB.prepare(
    `SELECT id, timestamp, status, trigger, object_number, image_url, caption, buffer_post_id, metadata
     FROM content_runs
     ORDER BY timestamp DESC
     LIMIT ?`
  ).bind(Math.max(1, Math.min(Number(limit) || 50, 250))).all();
  return (rows.results || []).map((row) => ({
    ...row,
    metadata: parseJsonObject(row.metadata),
  }));
}

async function countContentRunsForDay(env, day, status) {
  const row = await env.DB.prepare(
    `SELECT COUNT(*) AS count
     FROM content_runs
     WHERE substr(timestamp, 1, 10) = ?
       AND status = ?`
  ).bind(cleanText(day, 20), cleanText(status, 40)).first();
  return Number(row && row.count) || 0;
}

async function readTechnologyChanges(env, limit = 50) {
  try {
    const rows = await env.DB.prepare(
      `SELECT id, timestamp, source, title, details, metadata
       FROM technology_changes
       ORDER BY timestamp DESC
       LIMIT ?`
    ).bind(Math.max(1, Math.min(Number(limit) || 50, 250))).all();
    return (rows.results || []).map((row) => ({
      ...row,
      metadata: parseJsonObject(row.metadata),
    }));
  } catch {
    return [];
  }
}

async function readMetaAdSyncRows(env, limit = 50) {
  try {
    const rows = await env.DB.prepare(
      `SELECT id, timestamp, business_id, content_run_id, object_number,
              instagram_media_id, instagram_permalink, ad_account_id, campaign_id,
              adset_id, creative_id, ad_id, status, metadata
       FROM meta_ad_sync
       WHERE business_id = ?
       ORDER BY timestamp DESC
       LIMIT ?`
    ).bind(DEFAULT_BUSINESS_ID, Math.max(1, Math.min(Number(limit) || 50, 250))).all();
    return (rows.results || []).map((row) => ({
      ...row,
      metadata: parseJsonObject(row.metadata),
    }));
  } catch {
    return [];
  }
}

async function readMetaAdSyncIndex(env) {
  const rows = await readMetaAdSyncRows(env, 250);
  return {
    byRunId: new Map(rows.map((row) => [row.content_run_id, row])),
    byMediaId: new Map(rows.filter((row) => row.instagram_media_id).map((row) => [row.instagram_media_id, row])),
  };
}

async function writeMetaAdSync(env, data) {
  const id = cleanText(data.id, 80) || crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO meta_ad_sync (
      id, timestamp, business_id, content_run_id, object_number, instagram_media_id,
      instagram_permalink, ad_account_id, campaign_id, adset_id, creative_id, ad_id,
      status, metadata
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(content_run_id) DO UPDATE SET
      timestamp = excluded.timestamp,
      object_number = excluded.object_number,
      instagram_media_id = excluded.instagram_media_id,
      instagram_permalink = excluded.instagram_permalink,
      ad_account_id = excluded.ad_account_id,
      campaign_id = excluded.campaign_id,
      adset_id = excluded.adset_id,
      creative_id = excluded.creative_id,
      ad_id = excluded.ad_id,
      status = excluded.status,
      metadata = excluded.metadata`
  ).bind(
    id,
    utcTimestamp(),
    DEFAULT_BUSINESS_ID,
    cleanText(data.content_run_id, 120),
    cleanText(data.object_number, 20),
    cleanText(data.instagram_media_id, 120),
    cleanText(data.instagram_permalink, 500),
    cleanText(data.ad_account_id, 80),
    cleanText(data.campaign_id, 80),
    cleanText(data.adset_id, 80),
    cleanText(data.creative_id, 80),
    cleanText(data.ad_id, 80),
    cleanText(data.status, 40),
    JSON.stringify(data.metadata || {})
  ).run();
  return id;
}

async function readContentSettings(env) {
  const rows = await env.DB.prepare(
    "SELECT key, value, updated_at FROM content_settings ORDER BY key"
  ).all();
  return Object.fromEntries((rows.results || []).map((row) => [row.key, {
    value: row.value,
    updated_at: row.updated_at,
  }]));
}

function eventDay(event) {
  return cleanText(event.timestamp, 32).slice(0, 10);
}

function officeEventCounts(events) {
  const counts = {
    generated: 0,
    drafted: 0,
    published: 0,
    emails: 0,
    replies: 0,
    leads: 0,
    lead_events: 0,
    sales: 0,
    needs_review: 0,
    failed: 0,
  };
  for (const event of events) {
    const eventType = cleanText(event.event_type, 100);
    const status = cleanText(event.status, 40);
    if (["content.generated", "image.generated", "caption.generated"].includes(eventType)) counts.generated += 1;
    if (["content.drafted", "buffer.drafted", "social.drafted"].includes(eventType)) counts.drafted += 1;
    if (["content.published", "buffer.published", "social.published"].includes(eventType)) counts.published += 1;
    if (eventType.startsWith("email.")) counts.emails += 1;
    if (["email.replied", "email.reply.sent"].includes(eventType)) counts.replies += 1;
    if (eventType.startsWith("lead.")) {
      counts.lead_events += 1;
      counts.leads += 1;
    }
    if (eventType.startsWith("sale.") || eventType.startsWith("order.")) counts.sales += 1;
    if (status === "needs_review" || eventType.endsWith(".needs_review")) counts.needs_review += 1;
    if (["error", "failed"].includes(status) || eventType.endsWith(".failed")) counts.failed += 1;
  }
  return counts;
}

async function buildOfficeStatus(env, day = "") {
  const selectedDay = cleanText(day, 20) || utcTimestamp().slice(0, 10);
  const events = await readOfficeEvents(env, 250);
  const dayEvents = events.filter((event) => eventDay(event) === selectedDay);
  const latestEvents = dayEvents.slice(0, 12);
  const counts = officeEventCounts(dayEvents);
  const waitlistLeadCount = await countWaitlistLeads(env);
  const settings = await readContentSettings(env);
  const postsPerDay = clampNumber(settings.content_posts_per_day?.value || DEFAULT_POSTS_PER_DAY, 1, 6, 1);
  const publishTimes = parseTimeList(settings.content_publish_times?.value || DEFAULT_PUBLISH_TIMES).slice(0, postsPerDay);
  const timezone = safeTimeZone(settings.office_timezone?.value || DEFAULT_OFFICE_TIMEZONE);
  const runs = await readContentRuns(env, 250);
  const dayPublishedRuns = runs.filter((run) => eventDay(run) === selectedDay && cleanText(run.status, 40) === "published");
  const metaSyncRows = await readMetaAdSyncRows(env, 250);
  counts.leads = waitlistLeadCount;
  counts.instagram_posts = dayPublishedRuns.length;
  counts.meta_ads = metaSyncRows.filter((row) => cleanText(row.status, 40) === "created_paused").length;
  const status = counts.failed
    ? "Attention needed"
    : counts.needs_review
      ? "Needs review"
      : dayEvents.length
        ? "Running normally"
        : "No activity logged today";
  const lastEvent = latestEvents[0] || null;
  return {
    business_id: DEFAULT_BUSINESS_ID,
    day: selectedDay,
    status,
    event_count: dayEvents.length,
    last_action: lastEvent ? lastEvent.timestamp : "",
    last_action_label: lastEvent ? (lastEvent.subject || lastEvent.event_type || "") : "",
    counts,
    stats: {
      waitlist_leads: waitlistLeadCount,
      instagram_posts_today: dayPublishedRuns.length,
      instagram_posts_target: postsPerDay,
      publish_times: publishTimes,
      office_timezone: timezone,
      recap_enabled: (settings.recap_enabled?.value || DEFAULT_RECAP_ENABLED) === "true",
      recap_email: settings.recap_email?.value || ATELIER_EMAIL,
      recap_time: settings.recap_time?.value || DEFAULT_RECAP_TIME,
      meta_ads_synced: counts.meta_ads,
      meta_token_configured: Boolean(cleanText(env.META_ACCESS_TOKEN, 2000)),
    },
    latest_events: latestEvents,
  };
}

async function sha256ShortJson(value) {
  return (await sha256(JSON.stringify(value, (_key, item) => {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      return Object.keys(item).sort().reduce((sorted, key) => {
        sorted[key] = item[key];
        return sorted;
      }, {});
    }
    return item;
  }))).slice(0, 16);
}

async function officeTldrSignature(summary) {
  const latest = (summary.latest_events || [])[0] || {};
  return sha256ShortJson({
    day: summary.day,
    event_count: summary.event_count,
    latest_id: latest.id || "",
    counts: summary.counts || {},
    stats: summary.stats || {},
  });
}

function fallbackOfficeTldr(summary) {
  const counts = summary.counts || {};
  if (!summary.event_count) return "No office activity has been logged today.";
  if (counts.failed) return `${counts.failed} issue needs attention. Review the latest office actions before the next run.`;
  const parts = [];
  if (counts.published) parts.push(`published ${counts.published}`);
  if (counts.generated) parts.push(`generated ${counts.generated}`);
  if (counts.leads) parts.push(`captured ${counts.leads} lead${counts.leads === 1 ? "" : "s"}`);
  if (counts.replies) parts.push(`sent ${counts.replies} repl${counts.replies === 1 ? "y" : "ies"}`);
  return parts.length ? `Today the office ${parts.join(", ")}.` : "The office logged activity today with no urgent action required.";
}

function buildTldrPrompt(summary) {
  return [
    "Write one calm mobile dashboard TLDR for this autonomous office activity.",
    "Maximum 28 words. No bullets. No intro. Mention blockers only if present.",
    "",
    JSON.stringify({
      business_id: summary.business_id,
      day: summary.day,
      status: summary.status,
      counts: summary.counts,
      latest_events: (summary.latest_events || []).slice(0, 8).map((event) => ({
        time: event.timestamp,
        event_type: event.event_type,
        status: event.status,
        subject: event.subject,
        message: event.message,
      })),
    }),
  ].join("\n");
}

async function runGeminiTldr(env, summary) {
  const key = cleanText(env.GEMINI_API_KEY, 500);
  if (!key) return "";
  const model = cleanText(env.GEMINI_TLDR_MODEL, 80) || DEFAULT_TLDR_MODEL;
  const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(key)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
      "User-Agent": "maison-flou-worker/0.1 (+https://maisonflou.com)",
    },
    body: JSON.stringify({
      contents: [{ parts: [{ text: buildTldrPrompt(summary) }] }],
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`Gemini HTTP ${response.status}`);
  return cleanText((((payload.candidates || [])[0] || {}).content || {}).parts?.[0]?.text, 240);
}

async function readTldrCache(env, businessId) {
  const row = await env.DB.prepare(
    "SELECT business_id, signature, text, source, generated_at, updated_at FROM office_tldr_cache WHERE business_id = ? LIMIT 1"
  ).bind(businessId).first();
  return row || null;
}

async function writeTldrCache(env, data) {
  await env.DB.prepare(
    `INSERT INTO office_tldr_cache (business_id, signature, text, source, generated_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(business_id) DO UPDATE SET
       signature = excluded.signature,
       text = excluded.text,
       source = excluded.source,
       generated_at = excluded.generated_at,
       updated_at = excluded.updated_at`
  ).bind(
    data.business_id,
    data.signature,
    data.text,
    data.source,
    data.generated_at,
    utcTimestamp()
  ).run();
}

async function generateOfficeTldr(env, summary, refresh = false) {
  const signature = await officeTldrSignature(summary);
  const cached = await readTldrCache(env, DEFAULT_BUSINESS_ID);
  if (!refresh && cached && cached.signature === signature && cached.text) {
    return { ...cached, cached: true };
  }
  const fallback = fallbackOfficeTldr(summary);
  let text = fallback;
  let source = "fallback";
  let error = "";
  try {
    const aiText = await runGeminiTldr(env, summary);
    if (aiText) {
      text = aiText;
      source = "gemini";
    }
  } catch (exc) {
    error = String(exc).slice(0, 500);
  }
  const result = {
    business_id: DEFAULT_BUSINESS_ID,
    signature,
    text,
    source,
    generated_at: utcTimestamp(),
    cached: false,
    ...(error ? { error } : {}),
  };
  await writeTldrCache(env, result);
  return result;
}

function previousIsoDate(dateText) {
  const date = new Date(`${cleanText(dateText, 20)}T12:00:00Z`);
  if (Number.isNaN(date.getTime())) return utcTimestamp().slice(0, 10);
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function eventReportPreview(event) {
  const metadata = event.metadata || {};
  return {
    time: event.timestamp,
    type: event.event_type,
    status: event.status,
    subject: event.subject,
    message: event.message,
    object_number: metadata.object_number || "",
    category: (metadata.category || {}).label || (metadata.object_category || {}).label || metadata.category || "",
    runtime: metadata.runtime || "",
    trigger: metadata.trigger || "",
    error: metadata.error ? String(metadata.error).slice(0, 240) : "",
  };
}

function contentRunReportPreview(run) {
  const metadata = run.metadata || {};
  return {
    time: run.timestamp,
    status: run.status,
    trigger: run.trigger,
    object_number: run.object_number,
    buffer_post_id: run.buffer_post_id,
    category: (metadata.category || {}).label || (metadata.object_category || {}).label || metadata.category || "",
    image_method: (metadata.image_file || {}).method || "",
    caption_first_line: String(run.caption || "").split("\n")[0],
  };
}

function technologyChangePreview(change) {
  const metadata = change.metadata || {};
  return {
    time: change.timestamp,
    source: change.source,
    title: change.title,
    short_hash: metadata.short_hash || change.id.slice(0, 7),
  };
}

async function buildRecapContext(env, previousSummary, currentSummary) {
  const reportDays = new Set([previousSummary.day, currentSummary.day].filter(Boolean));
  const technologyChanges = (await readTechnologyChanges(env, 80))
    .filter((change) => !reportDays.size || reportDays.has(eventDay(change)))
    .slice(0, 50)
    .map(technologyChangePreview);
  const recentPosts = (await readContentRuns(env, 50))
    .filter((run) => !reportDays.size || reportDays.has(eventDay(run)))
    .slice(0, 24)
    .map(contentRunReportPreview);

  return {
    generated_at: utcTimestamp(),
    business: "Maison Flou",
    period: {
      prior_day: previousSummary.day,
      current_day_so_far: currentSummary.day,
    },
    final_state: {
      office_auth: "Worker-owned Google login on office.maisonflou.com. Cloudflare Access was tried earlier but is not the active office gate.",
      cloudflare_access_enabled: false,
      instagram_pacing: Number((currentSummary.stats || {}).instagram_posts_today || 0) > Number((currentSummary.stats || {}).instagram_posts_target || 0)
        ? "above_target"
        : "at_or_below_target",
    },
    technology_changes_newest_first: technologyChanges,
    prior_day_office: {
      day: previousSummary.day,
      status: previousSummary.status,
      event_count: previousSummary.event_count,
      counts: previousSummary.counts,
      stats: previousSummary.stats,
      latest_events_newest_first: (previousSummary.latest_events || []).slice(0, 18).map(eventReportPreview),
    },
    current_day_office: {
      day: currentSummary.day,
      status: currentSummary.status,
      event_count: currentSummary.event_count,
      counts: currentSummary.counts,
      stats: currentSummary.stats,
      latest_events_newest_first: (currentSummary.latest_events || []).slice(0, 18).map(eventReportPreview),
    },
    recent_social_posts_newest_first: recentPosts,
    interpretation_notes: [
      "Technology work should be summarized as implemented backend/frontend/infrastructure capabilities, not as a raw commit list.",
      "Current state beats history: if older changes were superseded by newer changes, summarize the final state.",
      "Do not say Cloudflare Access is the current office protection. The current office auth is Worker-owned Google login.",
      "If instagram_posts_today is greater than instagram_posts_target, say publishing is above target, not aligned with target.",
      "Events and changes are newest-first. Prefer newer events when deciding current state.",
      "Social work should cover generated/published objects, Buffer/Instagram posting, categories, and failures or anomalies.",
      "Business work should cover waitlist leads, email confirmations, domain/email infrastructure, and next commercial actions.",
      "Mention risks only when actionable. Do not inflate small issues.",
    ],
  };
}

function buildRecapFallback(previousSummary, currentSummary, context = {}) {
  const previousCounts = previousSummary.counts || {};
  const currentCounts = currentSummary.counts || {};
  const techCount = (context.technology_changes_newest_first || []).length;
  return [
    `Maison Flou office recap for ${previousSummary.day}.`,
    "",
    `Technology: ${techCount} implementation change${techCount === 1 ? "" : "s"} recorded for the reporting window.`,
    `Previous day: ${previousCounts.instagram_posts || previousCounts.published || 0} Instagram post(s), ${previousCounts.lead_events || 0} lead event(s), ${previousCounts.failed || 0} failed action(s).`,
    `Current day so far: ${currentCounts.instagram_posts || currentCounts.published || 0} Instagram post(s), ${currentCounts.lead_events || 0} lead event(s), ${currentCounts.failed || 0} failed action(s).`,
    "",
    currentCounts.failed || previousCounts.failed
      ? "Action required: review failed events in the office dashboard."
      : "No urgent action is currently required.",
  ].join("\n");
}

function buildRecapPrompt(context) {
  return [
    "You are the Chief of Staff for MAISON FLOU, a tiny autonomous luxury-fashion office.",
    "Write a daily office status report for the founder.",
    "",
    "Purpose:",
    "- Explain what the office actually changed, built, published, or learned.",
    "- Separate technology, social/content, and business/commercial activity.",
    "- Make it useful for someone who wants to know what happened without reading git commits or raw logs.",
    "",
    "Output rules:",
    "- Return only the report body.",
    "- No markdown tables. No emojis. No hype.",
    "- Be concise but specific.",
    "- Use these sections in this order:",
    "  1. TL;DR",
    "  2. Technology / Infrastructure",
    "  3. Social / Content",
    "  4. Business / Leads / Email",
    "  5. Issues / Risks",
    "  6. Next Best Actions",
    "- In Technology / Infrastructure, translate implementation history into plain operational outcomes. Do not list hashes unless a rollback reference is needed.",
    "- Current state beats history: if older changes were superseded by newer changes, summarize the final state and mention the prior attempt only if useful.",
    "- In Social / Content, mention object numbers, volume, automation status, and notable categories if present.",
    "- In Business / Leads / Email, mention waitlist lead count, email/Resend readiness, domain/email status if inferable, and commercial readiness.",
    "- In Issues / Risks, separate resolved issues from open risks.",
    "- In Next Best Actions, give 3 to 5 practical actions.",
    "- If evidence is missing, say what should be logged next time instead of inventing.",
    "",
    "DATA:",
    JSON.stringify(context),
  ].join("\n");
}

async function generateRecapText(env, previousSummary, currentSummary, context) {
  try {
    const text = cleanAiOutput(await runGeminiText(env, buildRecapPrompt(context), env.GEMINI_TLDR_MODEL || env.MAISON_FLOU_GEMINI_MODEL || DEFAULT_TEXT_MODEL), 5000);
    return text || buildRecapFallback(previousSummary, currentSummary, context);
  } catch {
    return buildRecapFallback(previousSummary, currentSummary, context);
  }
}

function recapEmailBody(text, previousSummary, currentSummary) {
  const escaped = escapeHtml(text).replace(/\n/g, "<br>");
  const html = `
<!doctype html>
<html>
  <body style="margin:0;background:#f4f1ea;color:#161513;font-family:Georgia,'Times New Roman',serif;">
    <div style="max-width:620px;margin:0 auto;padding:40px 24px;">
      <div style="font-size:13px;letter-spacing:.22em;text-transform:uppercase;margin-bottom:34px;">MAISON FLOU OFFICE</div>
      <h1 style="font-size:30px;line-height:1.05;font-weight:400;margin:0 0 20px;">Daily status report.</h1>
      <p style="font:15px/1.7 Arial,sans-serif;color:#5f594f;margin:0 0 28px;">${escaped}</p>
      <p style="font:12px/1.7 Arial,sans-serif;letter-spacing:.12em;text-transform:uppercase;margin:0;color:#5f594f;">Previous day ${escapeHtml(previousSummary.day)} · Current day ${escapeHtml(currentSummary.day)}</p>
    </div>
  </body>
</html>`.trim();
  return { html, text };
}

async function sendDailyRecap(env, recipient, previousSummary, currentSummary, context = null) {
  const reportContext = context || await buildRecapContext(env, previousSummary, currentSummary);
  const text = await generateRecapText(env, previousSummary, currentSummary, reportContext);
  const subject = `MAISON FLOU office recap — ${previousSummary.day}`;
  const result = await sendResendEmail(
    env,
    recipient,
    subject,
    recapEmailBody(text, previousSummary, currentSummary)
  );
  return { ...result, subject, text };
}

function gqlString(value) {
  return JSON.stringify(String(value || ""));
}

function cleanAiOutput(value, limit = 6000) {
  return String(value || "")
    .replace(/^```[a-zA-Z0-9_-]*\s*/, "")
    .replace(/```$/, "")
    .trim()
    .replace(/^["“”]+|["“”]+$/g, "")
    .trim()
    .slice(0, limit)
    .trim();
}

function siteBaseUrl(env, request) {
  if (request) {
    const url = new URL(request.url);
    return `${url.protocol}//${url.host}`;
  }
  return cleanText(env.SITE_BASE_URL, 300) || "https://maisonflou.com";
}

function mediaUrl(env, id, request) {
  const base = cleanText(env.PUBLIC_MEDIA_BASE_URL || env.SITE_BASE_URL, 300) || "https://maisonflou.com";
  return `${base.replace(/\/+$/, "")}${API_PREFIX}/media/${encodeURIComponent(id)}`;
}

function categoryPublic(category) {
  return {
    id: category.id,
    label: category.label,
    weight: category.weight,
  };
}

async function selectObjectCategory(env) {
  const rows = await env.DB.prepare(
    `SELECT metadata FROM content_runs
     WHERE metadata != ''
     ORDER BY timestamp DESC
     LIMIT 80`
  ).all();
  const counts = Object.fromEntries(OBJECT_CATEGORIES.map((category) => [category.id, 0]));
  for (const row of rows.results || []) {
    const metadata = parseJsonObject(row.metadata);
    const categoryId = cleanText(((metadata.category || {}).id) || metadata.category_id, 80);
    if (Object.prototype.hasOwnProperty.call(counts, categoryId)) counts[categoryId] += 1;
  }
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  const weighted = OBJECT_CATEGORIES.map((category) => {
    const targetShare = category.weight / OBJECT_CATEGORIES.reduce((sum, item) => sum + item.weight, 0);
    const actualShare = total ? counts[category.id] / total : 0;
    const deficit = Math.max(0.05, targetShare - actualShare + targetShare);
    return { category, score: category.weight * deficit };
  });
  const scoreTotal = weighted.reduce((sum, item) => sum + item.score, 0);
  let draw = Math.random() * scoreTotal;
  for (const item of weighted) {
    draw -= item.score;
    if (draw <= 0) return item.category;
  }
  return weighted[0].category;
}

async function nextObjectNumber(env) {
  const configured = Number(await getContentSetting(env, "object_sequence", "0")) || 0;
  const rows = await env.DB.prepare(
    "SELECT object_number FROM content_runs WHERE object_number != ''"
  ).all();
  const maxSeen = (rows.results || []).reduce((max, row) => {
    const value = Number.parseInt(cleanText(row.object_number, 20), 10);
    return Number.isFinite(value) ? Math.max(max, value) : max;
  }, 12);
  const next = Math.max(configured, maxSeen, 12) + 1;
  return String(next).padStart(3, "0");
}

function buildImagePromptWithCategory(category) {
  return IMAGE_PROMPT_TEMPLATE.replace("{category_prompt}", category.prompt);
}

function buildCaptionPrompt(imagePrompt, objectNumber) {
  return CAPTION_PROMPT_TEMPLATE
    .replaceAll("{image_prompt}", imagePrompt)
    .replaceAll("{object_number}", objectNumber);
}

function enforceCaptionContract(value, objectNumber) {
  const start = `Objet d’étude ${objectNumber}.`;
  const close = "Allocation for Collection 01 is strictly limited. Request registry access at our digital atelier.\n\nmaisonflou.com";
  let text = cleanAiOutput(value, 5000);
  if (!text.startsWith(start)) text = `${start}\n\n${text}`.trim();
  if (!text.includes(close)) text = `${text.replace(/\s+$/, "")}\n\n${close}`.trim();
  return text;
}

function geminiImagePrompt(imagePrompt) {
  return `${imagePrompt}\n\nCreate one square 1:1 Instagram editorial product image. No text, no logo, no watermark, no frame, no collage.`;
}

async function runGeminiText(env, prompt, model = "") {
  const key = cleanText(env.GEMINI_API_KEY, 500);
  if (!key) throw new Error("GEMINI_API_KEY is not configured.");
  const selectedModel = cleanText(model || env.MAISON_FLOU_GEMINI_MODEL || env.GEMINI_TLDR_MODEL, 100) || DEFAULT_TEXT_MODEL;
  const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${selectedModel}:generateContent?key=${encodeURIComponent(key)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
      "User-Agent": "maison-flou-worker/0.1 (+https://maisonflou.com)",
    },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`Gemini text HTTP ${response.status}: ${JSON.stringify(payload).slice(0, 500)}`);
  const parts = (((payload.candidates || [])[0] || {}).content || {}).parts || [];
  const text = parts.map((part) => part.text || "").join("\n").trim();
  return cleanAiOutput(text);
}

async function runGeminiImage(env, imagePrompt) {
  const key = cleanText(env.GEMINI_API_KEY, 500);
  if (!key) throw new Error("GEMINI_API_KEY is not configured.");
  const selectedModel = cleanText(env.MAISON_FLOU_IMAGE_MODEL, 100) || DEFAULT_IMAGE_MODEL;
  const response = await fetch(`https://generativelanguage.googleapis.com/v1/models/${selectedModel}:generateContent`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
      "x-goog-api-key": key,
      "User-Agent": "maison-flou-worker/0.1 (+https://maisonflou.com)",
    },
    body: JSON.stringify({
      contents: [{ parts: [{ text: geminiImagePrompt(imagePrompt) }] }],
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`Gemini image HTTP ${response.status}: ${JSON.stringify(payload).slice(0, 500)}`);
  const parts = (((payload.candidates || [])[0] || {}).content || {}).parts || [];
  for (const part of parts) {
    const inlineData = part.inlineData || part.inline_data;
    if (!inlineData || !inlineData.data) continue;
    const mimeType = cleanText(inlineData.mimeType || inlineData.mime_type || "image/png", 80);
    const bytes = base64ToBytes(inlineData.data);
    const dimensions = imageDimensions(bytes);
    return {
      bytes,
      bytes_base64: inlineData.data,
      mime_type: mimeType,
      width: dimensions.width,
      height: dimensions.height,
      model: selectedModel,
      digest: (await sha256Bytes(bytes)).slice(0, 12),
    };
  }
  throw new Error("Gemini image API did not return image bytes.");
}

async function storeContentImage(env, data) {
  const id = data.id || crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO content_images (
      id, timestamp, object_number, kind, mime_type, bytes_base64, width, height, metadata
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
      timestamp = excluded.timestamp,
      object_number = excluded.object_number,
      kind = excluded.kind,
      mime_type = excluded.mime_type,
      bytes_base64 = excluded.bytes_base64,
      width = excluded.width,
      height = excluded.height,
      metadata = excluded.metadata`
  ).bind(
    id,
    utcTimestamp(),
    cleanText(data.object_number, 20),
    cleanText(data.kind, 40) || "image",
    cleanText(data.mime_type, 80) || "application/octet-stream",
    data.bytes_base64,
    Number(data.width) || 0,
    Number(data.height) || 0,
    JSON.stringify(data.metadata || {})
  ).run();
  return { ...data, id };
}

async function readContentImage(env, id) {
  return env.DB.prepare(
    "SELECT id, timestamp, object_number, kind, mime_type, bytes_base64, width, height, metadata FROM content_images WHERE id = ? LIMIT 1"
  ).bind(cleanText(id, 120)).first();
}

async function transformImageAtEdge(env, request, imageInfo) {
  const raw = await storeContentImage(env, {
    object_number: imageInfo.object_number,
    kind: "raw",
    mime_type: imageInfo.mime_type,
    bytes_base64: imageInfo.bytes_base64,
    width: imageInfo.width,
    height: imageInfo.height,
    metadata: imageInfo.metadata,
  });
  const rawUrl = mediaUrl(env, raw.id, request);
  try {
    const response = await fetch(rawUrl, {
      headers: {
        "Accept": "image/avif,image/webp,image/jpeg,image/png,image/*,*/*;q=0.8",
        "User-Agent": "maison-flou-worker/0.1 (+https://maisonflou.com)",
      },
      cf: {
        image: {
          width: DEFAULT_IMAGE_SIZE,
          height: DEFAULT_IMAGE_SIZE,
          fit: "cover",
          format: "jpeg",
          quality: DEFAULT_IMAGE_QUALITY,
        },
      },
    });
    if (!response.ok) throw new Error(`image_transform_http_${response.status}`);
    const contentType = cleanText(response.headers.get("Content-Type"), 80) || "image/jpeg";
    if (!contentType.toLowerCase().startsWith("image/")) {
      throw new Error(`image_transform_non_image_${contentType}`);
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length < 64) throw new Error("image_transform_empty_body");
    const dimensions = imageDimensions(bytes);
    const digest = (await sha256Bytes(bytes)).slice(0, 12);
    const processed = await storeContentImage(env, {
      object_number: imageInfo.object_number,
      kind: "square",
      mime_type: contentType.includes("jpeg") ? "image/jpeg" : contentType,
      bytes_base64: bytesToBase64(bytes),
      width: dimensions.width || DEFAULT_IMAGE_SIZE,
      height: dimensions.height || DEFAULT_IMAGE_SIZE,
      metadata: {
        ...imageInfo.metadata,
        raw_id: raw.id,
        method: "cloudflare_image_transform_cover_reencode",
        digest,
      },
    });
    return {
      id: processed.id,
      url: mediaUrl(env, processed.id, request),
      raw_id: raw.id,
      raw_url: rawUrl,
      mime_type: processed.mime_type,
      width: processed.width,
      height: processed.height,
      method: "cloudflare_image_transform_cover_reencode",
      digest,
    };
  } catch (error) {
    if (String(raw.mime_type || "").toLowerCase().includes("jpeg")) {
      const strippedBytes = stripJpegMetadata(base64ToBytes(raw.bytes_base64));
      const dimensions = imageDimensions(strippedBytes);
      const digest = (await sha256Bytes(strippedBytes)).slice(0, 12);
      const stripped = await storeContentImage(env, {
        object_number: imageInfo.object_number,
        kind: "metadata-stripped",
        mime_type: "image/jpeg",
        bytes_base64: bytesToBase64(strippedBytes),
        width: dimensions.width || raw.width,
        height: dimensions.height || raw.height,
        metadata: {
          ...imageInfo.metadata,
          raw_id: raw.id,
          method: "jpeg_metadata_strip_fallback",
          transform_error: String(error).slice(0, 300),
          digest,
        },
      });
      return {
        id: stripped.id,
        url: mediaUrl(env, stripped.id, request),
        raw_id: raw.id,
        raw_url: rawUrl,
        mime_type: stripped.mime_type,
        width: stripped.width,
        height: stripped.height,
        method: "jpeg_metadata_strip_fallback",
        transform_error: String(error).slice(0, 300),
        digest,
      };
    }
    return {
      id: raw.id,
      url: rawUrl,
      raw_id: raw.id,
      raw_url: rawUrl,
      mime_type: raw.mime_type,
      width: raw.width,
      height: raw.height,
      method: "edge_raw_fallback",
      transform_error: String(error).slice(0, 300),
    };
  }
}

async function generateCloudflareContent(env, { request, imagePrompt = "", objectNumber = "", trigger = "cloudflare-lab" } = {}) {
  const category = await selectObjectCategory(env);
  const object_number = cleanText(objectNumber, 20) || await nextObjectNumber(env);
  const prompt = cleanAiOutput(imagePrompt)
    || await runGeminiText(env, buildImagePromptWithCategory(category));
  if (!prompt) throw new Error("Image prompt generation returned empty output.");
  const caption = enforceCaptionContract(
    await runGeminiText(env, buildCaptionPrompt(prompt, object_number)),
    object_number
  );
  const generatedImage = await runGeminiImage(env, prompt);
  const processed = await transformImageAtEdge(env, request, {
    ...generatedImage,
    object_number,
    metadata: {
      category: categoryPublic(category),
      trigger,
      image_prompt: prompt,
      model: generatedImage.model,
      digest: generatedImage.digest,
    },
  });
  await appendOfficeEvent(
    env,
    "content.generated",
    `Objet ${object_number}`,
    "Cloudflare generated and processed a Maison Flou image.",
    "ok",
    {
      object_number,
      category: categoryPublic(category),
      image_url: processed.url,
      image_source: "gemini_cloudflare",
      processing_method: processed.method,
      runtime: "cloudflare_worker",
    }
  );
  return {
    business_id: DEFAULT_BUSINESS_ID,
    object_number,
    object_category: categoryPublic(category),
    image_prompt: prompt,
    caption,
    image_url: processed.url,
    image_source: processed.method === "cloudflare_image_transform_cover_reencode"
      ? "gemini_cloudflare_square"
      : processed.method === "jpeg_metadata_strip_fallback"
        ? "gemini_cloudflare_metadata_stripped"
        : "gemini_cloudflare_raw",
    image_width: processed.width || DEFAULT_IMAGE_SIZE,
    image_height: processed.height || DEFAULT_IMAGE_SIZE,
    image_model: generatedImage.model,
    image_file: {
      id: processed.id,
      raw_id: processed.raw_id,
      mime_type: processed.mime_type,
      width: processed.width,
      height: processed.height,
      method: processed.method,
      transform_error: processed.transform_error || "",
    },
  };
}

async function bufferGraphql(env, query) {
  const apiKey = cleanText(env.BUFFER_API_KEY, 500);
  if (!apiKey) throw new Error("BUFFER_API_KEY is not configured.");
  const response = await fetch("https://api.buffer.com", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "Accept": "application/json",
      "User-Agent": "maison-flou-worker/0.1 (+https://maisonflou.com)",
    },
    body: JSON.stringify({ query }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.errors) {
    throw new Error(`Buffer HTTP ${response.status}: ${JSON.stringify(payload.errors || payload).slice(0, 500)}`);
  }
  return payload.data || payload;
}

async function createBufferPost(env, data) {
  const channelId = cleanText(data.channel_id || env.BUFFER_CHANNEL_ID, 160);
  if (!channelId) throw new Error("BUFFER_CHANNEL_ID is not configured.");
  const text = String(data.caption || data.text || "").trim();
  if (!text) throw new Error("Buffer caption is empty.");
  const imageUrl = cleanText(data.image_url, 800);
  const mode = cleanText(data.mode, 40) || "shareNow";
  const saveToDraft = data.save_to_draft ? "saveToDraft: true" : "";
  const assets = imageUrl
    ? `assets: [{ image: { url: ${gqlString(imageUrl)} metadata: { altText: "Maison Flou image study" dimensions: { width: 1080 height: 1080 } } } }]`
    : "";
  const query = `
    mutation CreatePost {
      createPost(input: {
        text: ${gqlString(text)}
        channelId: ${gqlString(channelId)}
        schedulingType: automatic
        mode: ${mode}
        ${saveToDraft}
        metadata: { instagram: { type: post, shouldShareToFeed: false } }
        ${assets}
      }) {
        ... on PostActionSuccess { post { id text assets { id mimeType } } }
        ... on MutationError { message }
      }
    }
  `;
  const result = (await bufferGraphql(env, query)).createPost;
  if (result && result.message && !result.post) throw new Error(result.message);
  return result || {};
}

async function runContentPublish(env, { request, trigger = "cloudflare-lab", mode = "shareNow", saveToDraft = false, imagePrompt = "", objectNumber = "" } = {}) {
  const generated = await generateCloudflareContent(env, {
    request,
    trigger,
    imagePrompt,
    objectNumber,
  });
  const buffer = await createBufferPost(env, {
    caption: generated.caption,
    image_url: generated.image_url,
    mode,
    save_to_draft: saveToDraft,
  });
  const bufferPostId = ((buffer.post || {}).id) || "";
  await logContentRun(env, {
    status: saveToDraft ? "drafted" : "published",
    trigger,
    object_number: generated.object_number || "",
    image_url: generated.image_url || "",
    caption: generated.caption || "",
    buffer_post_id: bufferPostId,
    metadata: {
      source: generated.image_source || "",
      category: generated.object_category || {},
      buffer,
      image_file: generated.image_file || {},
    },
  });
  await setContentSetting(env, "object_sequence", String(Number.parseInt(generated.object_number, 10) || 0));
  await appendOfficeEvent(
    env,
    saveToDraft ? "content.drafted" : "content.published",
    `Objet ${generated.object_number || ""}`.trim(),
    saveToDraft ? "Cloudflare created a Buffer draft." : "Cloudflare published a Buffer post.",
    "ok",
    { buffer_post_id: bufferPostId, trigger, runtime: "cloudflare_worker" }
  );
  return {
    ok: true,
    status: saveToDraft ? "drafted" : "published",
    trigger,
    object_number: generated.object_number || "",
    image_url: generated.image_url || "",
    caption: generated.caption || "",
    image_source: generated.image_source || "",
    image_file: generated.image_file || {},
    buffer,
  };
}

function objectNumberFromText(value) {
  const match = String(value || "").match(/Objet\s+d[’'](?:e|é)tude\s+(\d{1,4})/i);
  return match ? match[1].padStart(3, "0") : "";
}

function instagramMediaObjectNumber(media) {
  return objectNumberFromText(media.caption || "");
}

function matchInstagramMediaForRun(run, mediaItems) {
  const objectNumber = cleanText(run.object_number, 12) || objectNumberFromText(run.caption);
  if (!objectNumber) return null;
  return mediaItems.find((media) => instagramMediaObjectNumber(media) === objectNumber) || null;
}

async function fetchInstagramMedia(env, config, limit = 50) {
  const payload = await metaGraphRequest(env, `${config.instagram_user_id}/media`, {
    params: {
      fields: "id,caption,permalink,timestamp,media_type",
      limit: Math.max(1, Math.min(Number(limit) || 50, 100)),
    },
  });
  return payload.data || [];
}

async function createMetaAdFromInstagramMedia(env, config, run, media) {
  const objectNumber = cleanText(run.object_number, 12) || instagramMediaObjectNumber(media);
  const name = `Maison Flou Objet ${objectNumber || media.id}`;
  const creative = await metaGraphRequest(env, `${config.ad_account_id}/adcreatives`, {
    method: "POST",
    body: {
      name,
      object_id: config.page_id,
      instagram_user_id: config.instagram_user_id,
      source_instagram_media_id: media.id,
    },
  });
  const ad = await metaGraphRequest(env, `${config.ad_account_id}/ads`, {
    method: "POST",
    body: {
      name,
      adset_id: config.adset_id,
      creative: JSON.stringify({ creative_id: creative.id }),
      status: "PAUSED",
    },
  });
  return {
    creative_id: cleanText(creative.id, 80),
    ad_id: cleanText(ad.id, 80),
  };
}

async function validateMetaAccess(env, config) {
  const missing = missingMetaConfig(config);
  if (missing.length) return { ok: false, missing, checks: {} };
  const checks = {};
  try {
    checks.me = await metaGraphRequest(env, "me", { params: { fields: "id,name" } });
    checks.ad_account = await metaGraphRequest(env, config.ad_account_id, { params: { fields: "id,name,account_status" } });
    checks.campaign = await metaGraphRequest(env, config.campaign_id, { params: { fields: "id,name,status,objective" } });
    checks.adset = await metaGraphRequest(env, config.adset_id, { params: { fields: "id,name,status,campaign_id" } });
    checks.page = await metaGraphRequest(env, config.page_id, { params: { fields: "id,name" } });
    checks.instagram = await metaGraphRequest(env, config.instagram_user_id, { params: { fields: "id,username" } });
    return { ok: true, missing: [], checks };
  } catch (error) {
    return { ok: false, missing: [], checks, error: String(error).slice(0, 700) };
  }
}

async function syncMetaAds(env, { dryRun = false, limit = 25 } = {}) {
  const config = await readMetaSettings(env);
  const missing = missingMetaConfig(config);
  if (missing.length) {
    return { ok: false, error: "missing_meta_config", missing, config };
  }
  const mediaItems = await fetchInstagramMedia(env, config, 50);
  const syncIndex = await readMetaAdSyncIndex(env);
  const runs = (await readContentRuns(env, 100))
    .filter((run) => cleanText(run.status, 40) === "published")
    .filter((run) => cleanText(run.object_number, 12))
    .slice(0, Math.max(1, Math.min(Number(limit) || 25, 50)));
  const results = [];

  for (const run of runs) {
    const existing = syncIndex.byRunId.get(run.id);
    if (existing && existing.ad_id) {
      results.push({ object_number: run.object_number, status: "already_synced", ad_id: existing.ad_id });
      continue;
    }
    const media = matchInstagramMediaForRun(run, mediaItems);
    if (!media) {
      results.push({ object_number: run.object_number, status: "no_instagram_match" });
      continue;
    }
    const existingMedia = syncIndex.byMediaId.get(media.id);
    if (existingMedia && existingMedia.ad_id) {
      results.push({ object_number: run.object_number, status: "already_synced", ad_id: existingMedia.ad_id });
      continue;
    }
    if (dryRun) {
      results.push({
        object_number: run.object_number,
        status: "would_create",
        instagram_media_id: media.id,
        instagram_permalink: media.permalink || "",
      });
      continue;
    }
    try {
      const created = await createMetaAdFromInstagramMedia(env, config, run, media);
      await writeMetaAdSync(env, {
        content_run_id: run.id,
        object_number: run.object_number,
        instagram_media_id: media.id,
        instagram_permalink: media.permalink || "",
        ad_account_id: config.ad_account_id,
        campaign_id: config.campaign_id,
        adset_id: config.adset_id,
        creative_id: created.creative_id,
        ad_id: created.ad_id,
        status: "created_paused",
        metadata: {
          media_timestamp: media.timestamp || "",
          media_type: media.media_type || "",
          content_trigger: run.trigger || "",
        },
      });
      await appendOfficeEvent(
        env,
        "meta.ad.created",
        `Meta ad Objet ${run.object_number}`,
        "Created a paused Meta ad from an existing Instagram post.",
        "ok",
        { object_number: run.object_number, ad_id: created.ad_id, creative_id: created.creative_id, instagram_media_id: media.id, runtime: "cloudflare_worker" }
      );
      results.push({ object_number: run.object_number, status: "created_paused", ad_id: created.ad_id, creative_id: created.creative_id });
    } catch (error) {
      await writeMetaAdSync(env, {
        content_run_id: run.id,
        object_number: run.object_number,
        instagram_media_id: media.id,
        instagram_permalink: media.permalink || "",
        ad_account_id: config.ad_account_id,
        campaign_id: config.campaign_id,
        adset_id: config.adset_id,
        status: "failed",
        metadata: { error: String(error).slice(0, 700) },
      });
      results.push({ object_number: run.object_number, status: "failed", error: String(error).slice(0, 500) });
    }
  }

  const created = results.filter((item) => item.status === "created_paused").length;
  const matched = results.filter((item) => ["created_paused", "would_create", "already_synced"].includes(item.status)).length;
  return {
    ok: true,
    dry_run: dryRun,
    config: { ...config, token_configured: Boolean(config.token_configured) },
    media_seen: mediaItems.length,
    content_runs_seen: runs.length,
    matched,
    created,
    results,
  };
}

async function maybeRunContentSchedule(controller, env, clock) {
  const enabled = await getSettingBoolean(env, "content_scheduler_enabled", DEFAULT_SCHEDULER_ENABLED);
  if (!enabled) {
    await appendOfficeEventOncePerDay(
      env,
      clock.date,
      "content.scheduler.idle",
      "Content scheduler idle",
      "Cron is active, but autonomous publishing is disabled.",
      "info",
      { cron: controller.cron || "", runtime: "cloudflare_worker" }
    );
    return { published: 0, skipped: "disabled" };
  }

  if (!cleanText(env.GEMINI_API_KEY, 500) || !cleanText(env.BUFFER_API_KEY, 500) || !cleanText(env.BUFFER_CHANNEL_ID, 160)) {
    await appendOfficeEventOncePerDay(
      env,
      clock.date,
      "content.scheduler.needs_review",
      "Content scheduler missing secrets",
      "Autonomous publishing is enabled, but Gemini or Buffer configuration is missing.",
      "needs_review",
      { cron: controller.cron || "", runtime: "cloudflare_worker" }
    );
    return { published: 0, skipped: "missing_secrets" };
  }

  const postsPerDay = clampNumber(await getContentSetting(env, "content_posts_per_day", DEFAULT_POSTS_PER_DAY), 1, 6, 1);
  const publishTimes = parseTimeList(await getContentSetting(env, "content_publish_times", DEFAULT_PUBLISH_TIMES));
  const mode = await getContentSetting(env, "content_scheduler_mode", DEFAULT_SCHEDULER_MODE);
  const targetStatus = mode === "draft" ? "drafted" : "published";
  let published = 0;

  for (const slot of publishTimes) {
    if (!isDueNow(clock, slot)) continue;
    if (await schedulerAlreadyDone(env, "content", clock.date, slot)) continue;
    const alreadyDoneToday = await countContentRunsForDay(env, clock.date, targetStatus);
    const remaining = Math.max(0, postsPerDay - alreadyDoneToday);
    if (!remaining) {
      await markSchedulerDone(env, "content", clock.date, slot, "target_met");
      continue;
    }
    const objectNumbers = [];
    let failed = false;
    for (let index = 0; index < remaining; index += 1) {
      try {
        const result = await runContentPublish(env, {
          trigger: "cloudflare-cron",
          mode: mode === "draft" ? "addToQueue" : "shareNow",
          saveToDraft: mode === "draft",
        });
        objectNumbers.push(result.object_number || "done");
        published += 1;
      } catch (error) {
        failed = true;
        await logContentRun(env, {
          status: "failed",
          trigger: "cloudflare-cron",
          metadata: { cron: controller.cron || "", slot, batch_index: index + 1, error: String(error).slice(0, 500) },
        });
        await appendOfficeEvent(
          env,
          "content.scheduler.failed",
          "Content scheduler failed",
          "The scheduled publishing request failed.",
          "failed",
          { cron: controller.cron || "", slot, batch_index: index + 1, error: String(error).slice(0, 500), runtime: "cloudflare_worker" }
        );
        break;
      }
    }
    if (!failed) await markSchedulerDone(env, "content", clock.date, slot, objectNumbers.join(",") || "done");
  }

  return { published, publish_times: publishTimes, posts_per_day: postsPerDay };
}

async function maybeSendRecapSchedule(controller, env, clock) {
  const enabled = await getSettingBoolean(env, "recap_enabled", DEFAULT_RECAP_ENABLED);
  if (!enabled) return { sent: false, skipped: "disabled" };
  const recipient = normalizeEmail(await getContentSetting(env, "recap_email", ATELIER_EMAIL));
  if (!recipient) {
    await appendOfficeEventOncePerDay(
      env,
      clock.date,
      "recap.scheduler.needs_review",
      "Recap recipient missing",
      "Daily recap is enabled, but no valid recipient email is configured.",
      "needs_review",
      { cron: controller.cron || "", runtime: "cloudflare_worker" }
    );
    return { sent: false, skipped: "missing_recipient" };
  }
  const recapTime = normalizeTime(await getContentSetting(env, "recap_time", DEFAULT_RECAP_TIME)) || DEFAULT_RECAP_TIME;
  if (!isDueNow(clock, recapTime)) return { sent: false, skipped: "not_due" };
  if (await schedulerAlreadyDone(env, "recap", clock.date, recapTime)) return { sent: false, skipped: "already_sent" };

  const currentSummary = await buildOfficeStatus(env, clock.date);
  const previousSummary = await buildOfficeStatus(env, previousIsoDate(clock.date));
  try {
    const result = await sendDailyRecap(env, recipient, previousSummary, currentSummary);
    await markSchedulerDone(env, "recap", clock.date, recapTime, result.id || "sent");
    await appendOfficeEvent(
      env,
      "recap.sent",
      "Daily recap sent",
      "The Maison Flou daily office recap was sent.",
      "ok",
      { recipient_hash: (await sha256(recipient)).slice(0, 16), resend_id: result.id || "", cron: controller.cron || "", runtime: "cloudflare_worker" }
    );
    return { sent: true, resend_id: result.id || "" };
  } catch (error) {
    await appendOfficeEvent(
      env,
      "recap.failed",
      "Daily recap failed",
      "The Maison Flou daily office recap could not be sent.",
      "failed",
      { error: String(error).slice(0, 500), cron: controller.cron || "", runtime: "cloudflare_worker" }
    );
    return { sent: false, error: String(error).slice(0, 500) };
  }
}

async function handleScheduled(controller, env) {
  if (!env.DB) return;
  await setContentSetting(env, "scheduler_last_seen_at", utcTimestamp());
  await setContentSetting(env, "scheduler_last_cron", controller.cron || "");
  const timezone = await getContentSetting(env, "office_timezone", DEFAULT_OFFICE_TIMEZONE);
  const clock = officeClock(new Date(), timezone);
  await setContentSetting(env, "scheduler_last_local_date", clock.date);
  await setContentSetting(env, "scheduler_last_local_time", clock.time);
  await maybeSendRecapSchedule(controller, env, clock);
  await maybeRunContentSchedule(controller, env, clock);
}

function confirmationEmail() {
  const html = `
<!doctype html>
<html>
  <body style="margin:0;background:#f4f1ea;color:#161513;font-family:Georgia,'Times New Roman',serif;">
    <div style="max-width:560px;margin:0 auto;padding:42px 24px;">
      <div style="font-size:13px;letter-spacing:.22em;text-transform:uppercase;margin-bottom:46px;">MAISON FLOU</div>
      <h1 style="font-size:30px;line-height:1.05;font-weight:400;margin:0 0 22px;">Registry request received.</h1>
      <p style="font:15px/1.7 Arial,sans-serif;color:#5f594f;margin:0 0 22px;">Your request for Collection 01 has entered the atelier register.</p>
      <p style="font:15px/1.7 Arial,sans-serif;color:#5f594f;margin:0 0 34px;">Allocation remains strictly limited. Further access will be issued from the atelier when available.</p>
      <p style="font:12px/1.6 Arial,sans-serif;letter-spacing:.12em;text-transform:uppercase;margin:0;">maisonflou.com</p>
    </div>
  </body>
</html>`.trim();
  const text = [
    "MAISON FLOU",
    "",
    "Registry request received.",
    "",
    "Your request for Collection 01 has entered the atelier register.",
    "",
    "Allocation remains strictly limited. Further access will be issued from the atelier when available.",
    "",
    "maisonflou.com",
  ].join("\n");
  return { html, text };
}

function notificationEmail(entry) {
  const instagram = entry.instagram || "not provided";
  const source = entry.source || "maisonflou.com";
  return {
    html: [
      "<p>New Maison Flou registry request.</p>",
      `<p>Email: ${escapeHtml(entry.email)}<br>Instagram: ${escapeHtml(instagram)}<br>Source: ${escapeHtml(source)}</p>`,
    ].join(""),
    text: [
      "New Maison Flou registry request.",
      "",
      `Email: ${entry.email}`,
      `Instagram: ${instagram}`,
      `Source: ${source}`,
    ].join("\n"),
  };
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  })[char]);
}

async function sendResendEmail(env, to, subject, body) {
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
      "Accept": "application/json",
      "User-Agent": "maison-flou-worker/0.1 (+https://maisonflou.com)",
    },
    body: JSON.stringify({
      from: FROM_EMAIL,
      to: [to],
      reply_to: REPLY_TO_EMAIL,
      subject,
      html: body.html,
      text: body.text,
    }),
  });
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }
  if (!response.ok) {
    throw new Error(`Resend HTTP ${response.status}: ${text.slice(0, 500)}`);
  }
  return payload;
}

async function sendConfirmation(env, entry) {
  return sendResendEmail(
    env,
    entry.email,
    "MAISON FLOU registry request received",
    confirmationEmail()
  );
}

async function sendNotification(env, entry) {
  return sendResendEmail(
    env,
    ATELIER_EMAIL,
    "New Maison Flou registry request",
    notificationEmail(entry)
  );
}

async function handleWaitlist(request, env) {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders(request) });
  }
  if (request.method !== "POST") {
    return jsonResponse(request, { ok: false, error: "method_not_allowed" }, 405);
  }
  if (!env.DB) {
    return jsonResponse(request, { ok: false, error: "database_unavailable" }, 503);
  }
  if (!env.RESEND_API_KEY) {
    return jsonResponse(request, { ok: false, error: "email_unavailable" }, 503);
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

  const emailHash = (await sha256(email)).slice(0, 16);
  const timestamp = utcTimestamp();
  const entry = {
    email,
    emailHash,
    instagram: cleanText(payload.instagram, 80).replace(/^@+/, ""),
    source: cleanText(payload.source, 120) || "maisonflou.com",
    userAgent: cleanText(request.headers.get("User-Agent"), 220),
    remoteAddrHash: (await sha256(cleanText(request.headers.get("CF-Connecting-IP"), 120))).slice(0, 16),
  };

  const existing = await env.DB.prepare(
    "SELECT id, confirmation_status FROM waitlist_leads WHERE email_hash = ? LIMIT 1"
  ).bind(emailHash).first();
  if (existing) {
    if (existing.confirmation_status !== "sent") {
      try {
        const retry = await sendConfirmation(env, entry);
        await env.DB.prepare(
          "UPDATE waitlist_leads SET confirmation_status = ?, confirmation_sent_at = ?, resend_id = ? WHERE id = ?"
        ).bind("sent", utcTimestamp(), retry.id || "", existing.id).run();
        await appendOfficeEvent(
          env,
          "lead.waitlist.confirmation_retried",
          "Registry confirmation retried",
          "A pending Maison Flou confirmation email was resent.",
          "ok",
          { email_hash: emailHash, resend_id: retry.id || "", runtime: "cloudflare_worker" }
        );
      } catch (error) {
        await appendOfficeEvent(
          env,
          "lead.waitlist.email_failed",
          "Registry confirmation failed",
          "A repeated Maison Flou request still could not receive a confirmation email.",
          "needs_review",
          { email_hash: emailHash, error: String(error).slice(0, 500), runtime: "cloudflare_worker" }
        );
        return jsonResponse(request, { ok: false, error: "email_unavailable" }, 502);
      }
    }
    await appendOfficeEvent(
      env,
      "lead.waitlist.duplicate",
      "Registry request duplicate",
      "A repeated Maison Flou registry request was received.",
      "info",
      { email_hash: emailHash, source: entry.source, runtime: "cloudflare_worker" }
    );
    return jsonResponse(request, { ok: true, status: "already_registered" });
  }

  const leadId = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO waitlist_leads (
      id, timestamp, email, email_hash, instagram, source, user_agent, remote_addr_hash,
      confirmation_status, notification_status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    leadId,
    timestamp,
    entry.email,
    entry.emailHash,
    entry.instagram,
    entry.source,
    entry.userAgent,
    entry.remoteAddrHash,
    "pending",
    "pending"
  ).run();

  let confirmation;
  try {
    confirmation = await sendConfirmation(env, entry);
    await env.DB.prepare(
      "UPDATE waitlist_leads SET confirmation_status = ?, confirmation_sent_at = ?, resend_id = ? WHERE id = ?"
    ).bind("sent", utcTimestamp(), confirmation.id || "", leadId).run();
  } catch (error) {
    await env.DB.prepare(
      "UPDATE waitlist_leads SET confirmation_status = ? WHERE id = ?"
    ).bind("failed", leadId).run();
    await appendOfficeEvent(
      env,
      "lead.waitlist.email_failed",
      "Registry confirmation failed",
      "A Maison Flou registry request was stored, but confirmation email failed.",
      "needs_review",
      { email_hash: emailHash, error: String(error).slice(0, 500), runtime: "cloudflare_worker" }
    );
    return jsonResponse(request, { ok: false, error: "email_unavailable" }, 502);
  }

  await appendOfficeEvent(
    env,
    "lead.waitlist.captured",
    "Registry request captured",
    "A Maison Flou registry request was stored in D1 and confirmation email was sent.",
    "ok",
    {
      email_hash: emailHash,
      has_instagram: Boolean(entry.instagram),
      source: entry.source,
      resend_id: confirmation.id || "",
      runtime: "cloudflare_worker",
    }
  );

  try {
    await sendNotification(env, entry);
    await env.DB.prepare(
      "UPDATE waitlist_leads SET notification_status = ?, notification_sent_at = ? WHERE id = ?"
    ).bind("sent", utcTimestamp(), leadId).run();
  } catch (error) {
    await env.DB.prepare(
      "UPDATE waitlist_leads SET notification_status = ? WHERE id = ?"
    ).bind("failed", leadId).run();
    await appendOfficeEvent(
      env,
      "lead.waitlist.notify_failed",
      "Registry notification failed",
      "Confirmation was sent, but the atelier notification failed.",
      "needs_review",
      { email_hash: emailHash, error: String(error).slice(0, 500), runtime: "cloudflare_worker" }
    );
  }

  return jsonResponse(request, { ok: true, status: "registered" });
}

function redirectResponse(location, headers = {}) {
  return new Response(null, {
    status: 302,
    headers: {
      Location: location,
      "Cache-Control": "no-store",
      ...headers,
    },
  });
}

function renderOfficeLogin(env, message = "") {
  const clientId = cleanText(env.GOOGLE_OAUTH_CLIENT_ID, 180);
  const setupMessage = clientId ? "" : "Google sign-in is not configured yet.";
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Maison Flou Office</title>
  <script src="https://accounts.google.com/gsi/client" async defer></script>
  <style>
    :root { color-scheme: light; --bg:#f5f1e8; --ink:#15130f; --muted:#6f675b; --line:#d8cec0; --card:#fffaf0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; display:grid; place-items:center; padding:22px; background:var(--bg); color:var(--ink); }
    main { width:min(100%, 420px); }
    h1 { margin:0 0 10px; font-family:Georgia, "Times New Roman", serif; font-weight:400; font-size:42px; line-height:.92; }
    p { margin:0; color:var(--muted); line-height:1.5; }
    .panel { margin-top:22px; border:1px solid var(--line); border-radius:8px; background:var(--card); padding:18px; }
    .label { margin:0 0 12px; font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
    .message { margin-top:12px; min-height:20px; font-size:14px; color:var(--muted); }
    .footer { margin-top:18px; font-size:12px; letter-spacing:.12em; text-transform:uppercase; }
  </style>
</head>
<body>
  <main>
    <h1>Maison Flou<br>Office</h1>
    <p>Private atelier access.</p>
    <div class="panel">
      <p class="label">Operator login</p>
      ${clientId ? `<div id="g_id_onload" data-client_id="${escapeHtml(clientId)}" data-callback="handleCredential" data-auto_prompt="false"></div>
      <div class="g_id_signin" data-type="standard" data-theme="outline" data-size="large" data-text="signin_with" data-shape="rectangular" data-logo_alignment="left"></div>` : ""}
      <p class="message" id="message">${escapeHtml(message || setupMessage)}</p>
    </div>
    <p class="footer">MAISON FLOU OFFICE</p>
  </main>
  <script>
    async function handleCredential(response) {
      const message = document.getElementById("message");
      message.textContent = "Authorizing...";
      try {
        const result = await fetch("/auth/google", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ credential: response.credential })
        });
        const data = await result.json();
        if (!result.ok || !data.ok) throw new Error(data.error || "Access denied");
        location.href = "/";
      } catch (error) {
        message.textContent = error.message || "Access denied";
      }
    }
  </script>
</body>
</html>`;
}

async function verifyGoogleCredential(env, credential) {
  const clientId = cleanText(env.GOOGLE_OAUTH_CLIENT_ID, 180);
  if (!clientId) throw new Error("google_client_missing");
  const token = String(credential || "").trim();
  if (!token || token.length > 4096) throw new Error("credential_missing");

  const response = await fetch(`https://oauth2.googleapis.com/tokeninfo?id_token=${encodeURIComponent(token)}`, {
    headers: { Accept: "application/json" },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error("google_token_invalid");
  if (payload.aud !== clientId) throw new Error("google_audience_invalid");
  if (!["accounts.google.com", "https://accounts.google.com"].includes(payload.iss)) {
    throw new Error("google_issuer_invalid");
  }
  if (Number(payload.exp || 0) < Math.floor(Date.now() / 1000)) throw new Error("google_token_expired");
  if (!(payload.email_verified === true || payload.email_verified === "true")) {
    throw new Error("google_email_unverified");
  }

  const email = normalizeEmail(payload.email);
  const allowedEmails = allowedOperatorEmails(env);
  if (!email || !allowedEmails.includes(email)) throw new Error("email_not_allowed");
  return {
    email,
    name: cleanText(payload.name, 120),
    picture: cleanText(payload.picture, 500),
  };
}

async function handleOfficeGoogleAuth(request, env) {
  if (request.method !== "POST") {
    return jsonResponse(request, { ok: false, error: "method_not_allowed" }, 405);
  }
  const payload = await readPayload(request).catch(() => ({}));
  try {
    const operator = await verifyGoogleCredential(env, payload.credential);
    try {
      await appendOfficeEvent(
        env,
        "office.login",
        "Office login",
        "A Maison Flou operator signed in to the office.",
        "ok",
        { email_hash: (await sha256(operator.email)).slice(0, 16), runtime: "cloudflare_worker" }
      );
    } catch {}
    return jsonResponse(request, { ok: true, email: operator.email }, 200, {
      "Set-Cookie": await signedSessionCookie(env, operator.email),
    });
  } catch (error) {
    try {
      await appendOfficeEvent(
        env,
        "office.login.denied",
        "Office login denied",
        "A Maison Flou office login attempt was rejected.",
        "needs_review",
        { error: String(error.message || error).slice(0, 120), runtime: "cloudflare_worker" }
      );
    } catch {}
    return jsonResponse(request, { ok: false, error: String(error.message || error).slice(0, 120) }, 401);
  }
}

function handleOfficeLogout() {
  return redirectResponse("/login", {
    "Set-Cookie": `${OFFICE_SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax`,
  });
}

async function handleOfficeSession(request, env) {
  const email = await officeSessionEmail(request, env);
  if (email) return jsonResponse(request, { ok: true, email, auth: "google" });
  if (tokenAccessAllowed(request, env)) return jsonResponse(request, { ok: true, email: "", auth: "token" });
  return unauthorizedResponse(request);
}

async function handleHealth(request, env) {
  const checks = {
    worker: true,
    database: false,
    resend_configured: Boolean(cleanText(env.RESEND_API_KEY, 500)),
    gemini_configured: Boolean(cleanText(env.GEMINI_API_KEY, 500)),
    buffer_configured: Boolean(cleanText(env.BUFFER_API_KEY, 500) && cleanText(env.BUFFER_CHANNEL_ID, 160)),
    meta_token_configured: Boolean(cleanText(env.META_ACCESS_TOKEN, 2000)),
  };
  try {
    if (env.DB) {
      await env.DB.prepare("SELECT 1 AS ok").first();
      checks.database = true;
    }
  } catch {}
  return jsonResponse(request, {
    ok: checks.worker && checks.database,
    business_id: DEFAULT_BUSINESS_ID,
    timestamp: utcTimestamp(),
    checks,
  }, checks.worker && checks.database ? 200 : 503);
}

function renderLabDashboard() {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Maison Flou Lab</title>
  <style>
    :root { color-scheme: light; --bg:#f5f1e8; --ink:#15130f; --muted:#6f675b; --line:#d8cec0; --card:#fffaf0; --ok:#1f7a4b; --warn:#9a6a00; --bad:#a33; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); }
    main { width:min(100%, 980px); margin:0 auto; padding:18px 14px 46px; }
    header { display:flex; justify-content:space-between; align-items:flex-start; gap:14px; margin-bottom:16px; }
    .header-actions { display:grid; gap:8px; justify-items:end; }
    h1 { margin:0; font-family: Georgia, "Times New Roman", serif; font-size:30px; line-height:.95; font-weight:400; }
    .subtle, .label, span { color:var(--muted); }
    .label { margin:0 0 8px; font-size:11px; letter-spacing:.14em; text-transform:uppercase; }
    section { border-top:1px solid var(--line); padding:16px 0; }
    .card { border:1px solid var(--line); background:var(--card); padding:12px; border-radius:8px; }
    .grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
    .metric strong { display:block; font-size:24px; line-height:1; }
    .metric span { font-size:12px; }
    .status { display:flex; align-items:center; gap:8px; font-size:18px; }
    .dot { width:10px; height:10px; border-radius:99px; background:var(--ok); flex:0 0 auto; }
    .dot.warn { background:var(--warn); }
    .dot.bad { background:var(--bad); }
    .toolbar { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
    input, select, button { min-height:42px; border:1px solid var(--ink); border-radius:6px; background:transparent; color:var(--ink); padding:0 11px; font:inherit; }
    input { width:100%; }
    button { background:var(--ink); color:var(--card); cursor:pointer; }
    button.secondary { background:transparent; color:var(--ink); }
    button:disabled { opacity:.55; cursor:wait; }
    .list { display:grid; gap:8px; }
    .row { display:flex; justify-content:space-between; gap:10px; align-items:center; border:1px solid var(--line); background:rgba(255,250,240,.6); border-radius:8px; padding:10px; min-width:0; }
    .row strong, .row span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .row strong { font-size:14px; }
    .row span { font-size:12px; margin-top:2px; }
    .tldr { font-family: Georgia, "Times New Roman", serif; font-size:20px; line-height:1.25; }
    .auth { display:none; }
    .auth.visible { display:block; }
    a { color:inherit; }
    @media (min-width:720px) { main { padding-top:30px; } .grid { grid-template-columns:repeat(4,minmax(0,1fr)); } h1 { font-size:40px; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Maison Flou<br>Lab</h1>
        <div class="subtle" id="day">Cloudflare office</div>
        <div class="subtle" id="operator"></div>
      </div>
      <div class="header-actions">
        <div class="card" id="event-count">0 events</div>
        <button class="secondary" id="logout">Logout</button>
      </div>
    </header>

    <section class="auth" id="auth">
      <p class="label">Access token</p>
      <input id="token" type="password" placeholder="Pocket token" autocomplete="current-password">
      <div class="toolbar"><button id="unlock">Unlock</button></div>
    </section>

    <section>
      <p class="label">AI TLDR</p>
      <div class="card tldr" id="tldr">Loading office summary...</div>
      <div class="toolbar">
        <button class="secondary" id="refresh-tldr">Refresh TLDR</button>
        <span id="tldr-source"></span>
      </div>
    </section>

    <section>
      <p class="label">Status</p>
      <div class="status"><span class="dot" id="status-dot"></span><span id="status">Loading</span></div>
      <div class="subtle" id="last-action"></div>
      <div class="grid" id="metrics" style="margin-top:12px"></div>
    </section>

    <section>
      <p class="label">Instagram Scheduler</p>
      <div class="card">
        <label class="label" for="scheduler-enabled">Scheduler</label>
        <select id="scheduler-enabled"><option value="false">Disabled</option><option value="true">Enabled</option></select>
        <label class="label" for="scheduler-mode" style="margin-top:10px">Mode</label>
        <select id="scheduler-mode"><option value="publish">Publish now</option><option value="draft">Draft</option></select>
        <label class="label" for="posts-per-day" style="margin-top:10px">Instagram images per day</label>
        <input id="posts-per-day" type="number" min="1" max="6" step="1">
        <label class="label" for="publish-times" style="margin-top:10px">Publish times</label>
        <input id="publish-times" type="text" inputmode="numeric" placeholder="09:00, 18:00">
        <div class="toolbar">
          <button id="save-scheduler-settings">Save scheduler</button>
          <button id="publish-now">Publish now</button>
        </div>
        <div class="subtle" id="scheduler-result"></div>
      </div>
    </section>

    <section>
      <p class="label">Daily Report</p>
      <div class="card">
        <label class="label" for="office-timezone">Office timezone</label>
        <input id="office-timezone" type="text" placeholder="Europe/Madrid">
        <label class="label" for="recap-enabled" style="margin-top:10px">Daily recap</label>
        <select id="recap-enabled"><option value="false">Disabled</option><option value="true">Enabled</option></select>
        <label class="label" for="recap-email" style="margin-top:10px">Recap email</label>
        <input id="recap-email" type="email" autocomplete="email" placeholder="atelier@maisonflou.com">
        <label class="label" for="recap-time" style="margin-top:10px">Recap time</label>
        <input id="recap-time" type="time">
        <div class="toolbar">
          <button id="save-report-settings">Save report</button>
          <button id="send-report-now">Send now</button>
        </div>
        <div class="subtle" id="report-result"></div>
      </div>
    </section>

    <section>
      <p class="label">Meta Ads</p>
      <div class="card">
        <label class="label" for="meta-ad-account-id">Ad account ID</label>
        <input id="meta-ad-account-id" type="text" placeholder="act_123456789">
        <label class="label" for="meta-campaign-id" style="margin-top:10px">Campaign ID</label>
        <input id="meta-campaign-id" type="text" inputmode="numeric" placeholder="123456789">
        <label class="label" for="meta-adset-id" style="margin-top:10px">Ad set ID</label>
        <input id="meta-adset-id" type="text" inputmode="numeric" placeholder="123456789">
        <label class="label" for="meta-page-id" style="margin-top:10px">Facebook Page ID</label>
        <input id="meta-page-id" type="text" inputmode="numeric" placeholder="123456789">
        <label class="label" for="meta-instagram-user-id" style="margin-top:10px">Instagram user ID</label>
        <input id="meta-instagram-user-id" type="text" inputmode="numeric" placeholder="17841400000000000">
        <div class="toolbar">
          <button id="save-meta-settings">Save ads</button>
          <button class="secondary" id="check-meta-access">Check access</button>
          <button id="sync-meta-ads">Sync IG ads</button>
        </div>
        <div class="subtle" id="meta-result"></div>
      </div>
    </section>

    <section>
      <p class="label">Waitlist</p>
      <div class="list" id="waitlist"></div>
      <div class="toolbar"><button class="secondary" id="reveal-leads">Reveal emails</button></div>
    </section>

    <section>
      <p class="label">Content Ledger</p>
      <div class="list" id="posts"></div>
    </section>

    <section>
      <p class="label">Latest Actions</p>
      <div class="list" id="actions"></div>
    </section>
  </main>
  <script>
    const key = "maison-flou-lab-token";
    const auth = document.getElementById("auth");
    const tokenInput = document.getElementById("token");
    tokenInput.value = localStorage.getItem(key) || "";
    function token() { return localStorage.getItem(key) || tokenInput.value || ""; }
    function headers(extra = {}) { return { ...extra, ...(token() ? {"X-Pocket-Token": token()} : {}) }; }
    function html(value) { return String(value || "").replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c])); }
    function time(value) { return value ? String(value).slice(11,16) : ""; }
    async function api(path, options = {}) {
      const response = await fetch(path, { ...options, headers: headers(options.headers || {}) });
      const data = await response.json();
      if (response.status === 401) auth.classList.add("visible");
      if (!response.ok) throw new Error(data.error || "Request failed");
      auth.classList.remove("visible");
      return data;
    }
    function renderMetrics(counts) {
      const rows = [["IG Today", counts.instagram_posts], ["Meta Ads", counts.meta_ads], ["Generated", counts.generated], ["Published", counts.published], ["Review", counts.needs_review], ["Leads", counts.leads], ["Emails", counts.emails], ["Failed", counts.failed]];
      document.getElementById("metrics").innerHTML = rows.map(([label, value]) => \`<div class="card metric"><strong>\${Number(value || 0)}</strong><span>\${label}</span></div>\`).join("");
    }
    function renderRows(id, rows, empty, map) {
      const target = document.getElementById(id);
      target.innerHTML = rows.length ? rows.map(map).join("") : \`<div class="row"><div><strong>\${empty}</strong><span>No records to show.</span></div></div>\`;
    }
    async function loadStatus() {
      const data = await api("/api/maison-flou/office/status");
      document.getElementById("day").textContent = data.day || "Today";
      document.getElementById("event-count").textContent = \`\${data.event_count || 0} events\`;
      document.getElementById("status").textContent = data.status || "Unknown";
      const stats = data.stats || {};
      document.getElementById("last-action").textContent = data.last_action_label ? \`Last action: \${data.last_action_label} · IG \${stats.instagram_posts_today || 0}/\${stats.instagram_posts_target || 0}\` : \`IG \${stats.instagram_posts_today || 0}/\${stats.instagram_posts_target || 0}\`;
      const dot = document.getElementById("status-dot");
      dot.className = "dot" + ((data.counts || {}).failed ? " bad" : ((data.counts || {}).needs_review ? " warn" : ""));
      renderMetrics(data.counts || {});
      renderRows("actions", data.latest_events || [], "No actions logged", event => \`<div class="row"><div><strong>\${html(event.subject || event.event_type)}</strong><span>\${html(time(event.timestamp))} · \${html(event.message || event.status)}</span></div></div>\`);
    }
    async function loadTldr(refresh = false) {
      const data = await api(\`/api/maison-flou/office/tldr\${refresh ? "?refresh=1" : ""}\`);
      document.getElementById("tldr").textContent = data.text || "No summary available.";
      document.getElementById("tldr-source").textContent = data.source ? \`\${data.source}\${data.cached ? " · cached" : ""}\` : "";
    }
    async function loadSettings() {
      const data = await api("/api/maison-flou/settings");
      const settings = data.settings || {};
      document.getElementById("scheduler-enabled").value = (settings.content_scheduler_enabled || {}).value === "true" ? "true" : "false";
      document.getElementById("scheduler-mode").value = (settings.content_scheduler_mode || {}).value || "publish";
      document.getElementById("posts-per-day").value = (settings.content_posts_per_day || {}).value || "1";
      document.getElementById("publish-times").value = (settings.content_publish_times || {}).value || "09:00";
      document.getElementById("office-timezone").value = (settings.office_timezone || {}).value || "Europe/Madrid";
      document.getElementById("recap-enabled").value = (settings.recap_enabled || {}).value === "true" ? "true" : "false";
      document.getElementById("recap-email").value = (settings.recap_email || {}).value || "atelier@maisonflou.com";
      document.getElementById("recap-time").value = (settings.recap_time || {}).value || "18:00";
      document.getElementById("meta-ad-account-id").value = (settings.meta_ad_account_id || {}).value || "";
      document.getElementById("meta-campaign-id").value = (settings.meta_campaign_id || {}).value || "";
      document.getElementById("meta-adset-id").value = (settings.meta_adset_id || {}).value || "";
      document.getElementById("meta-page-id").value = (settings.meta_page_id || {}).value || "";
      document.getElementById("meta-instagram-user-id").value = (settings.meta_instagram_user_id || {}).value || "";
    }
    async function loadSession() {
      try {
        const data = await api("/api/maison-flou/office/session");
        document.getElementById("operator").textContent = data.email || data.auth || "";
      } catch {}
    }
    async function loadLeads(reveal = false) {
      const data = await api(\`/api/maison-flou/waitlist/leads\${reveal ? "?reveal=1" : ""}\`);
      renderRows("waitlist", data.leads || [], "No leads yet", lead => \`<div class="row"><div><strong>\${html(lead.email || lead.email_hash)}</strong><span>\${html(time(lead.timestamp))} · \${html(lead.instagram ? "@" + lead.instagram : "no instagram")} · email \${html(lead.confirmation_status)}</span></div></div>\`);
    }
    async function loadPosts() {
      const data = await api("/api/maison-flou/posts");
      renderRows("posts", data.posts || [], "No posts yet", post => \`<div class="row"><div><strong>Objet \${html(post.object_number)}</strong><span>\${html(post.status)} · \${html(time(post.timestamp))} · \${html(post.trigger)}</span></div>\${post.image_url ? \`<a href="\${html(post.image_url)}" target="_blank" rel="noopener">Image</a>\` : ""}</div>\`);
    }
    document.getElementById("unlock").addEventListener("click", () => { localStorage.setItem(key, tokenInput.value); boot(); });
    document.getElementById("logout").addEventListener("click", () => { localStorage.removeItem(key); location.href = "/logout"; });
    document.getElementById("refresh-tldr").addEventListener("click", () => loadTldr(true));
    document.getElementById("reveal-leads").addEventListener("click", () => loadLeads(true));
    document.getElementById("save-scheduler-settings").addEventListener("click", async () => {
      const result = document.getElementById("scheduler-result");
      result.textContent = "Saving...";
      await api("/api/maison-flou/settings", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
        content_scheduler_enabled: document.getElementById("scheduler-enabled").value,
        content_scheduler_mode: document.getElementById("scheduler-mode").value,
        content_posts_per_day: document.getElementById("posts-per-day").value,
        content_publish_times: document.getElementById("publish-times").value
      }) });
      result.textContent = "Scheduler saved.";
      await Promise.all([loadSettings(), loadStatus()]);
    });
    document.getElementById("save-report-settings").addEventListener("click", async () => {
      const result = document.getElementById("report-result");
      result.textContent = "Saving...";
      await api("/api/maison-flou/settings", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
        office_timezone: document.getElementById("office-timezone").value,
        recap_enabled: document.getElementById("recap-enabled").value,
        recap_email: document.getElementById("recap-email").value,
        recap_time: document.getElementById("recap-time").value
      }) });
      result.textContent = "Report settings saved.";
      await Promise.all([loadSettings(), loadStatus(), loadTldr(true)]);
    });
    document.getElementById("publish-now").addEventListener("click", async event => {
      const result = document.getElementById("scheduler-result");
      event.target.disabled = true;
      result.textContent = "Publishing...";
      try {
        const data = await api("/api/maison-flou/content/publish", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ mode:"shareNow" }) });
        result.textContent = \`Published Objet \${data.object_number || ""}.\`;
        await Promise.all([loadStatus(), loadPosts(), loadTldr(true)]);
      } catch (error) {
        result.textContent = error.message;
      } finally {
        event.target.disabled = false;
      }
    });
    document.getElementById("send-report-now").addEventListener("click", async event => {
      const result = document.getElementById("report-result");
      event.target.disabled = true;
      result.textContent = "Sending report...";
      try {
        const data = await api("/api/maison-flou/report/send", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
          recap_email: document.getElementById("recap-email").value,
          office_timezone: document.getElementById("office-timezone").value
        }) });
        result.textContent = \`Report sent to \${data.recipient || "recipient"}.\`;
        await Promise.all([loadStatus(), loadTldr(true)]);
      } catch (error) {
        result.textContent = error.message;
      } finally {
        event.target.disabled = false;
      }
    });
    document.getElementById("save-meta-settings").addEventListener("click", async () => {
      const result = document.getElementById("meta-result");
      result.textContent = "Saving...";
      await api("/api/maison-flou/settings", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
        meta_ad_account_id: document.getElementById("meta-ad-account-id").value,
        meta_campaign_id: document.getElementById("meta-campaign-id").value,
        meta_adset_id: document.getElementById("meta-adset-id").value,
        meta_page_id: document.getElementById("meta-page-id").value,
        meta_instagram_user_id: document.getElementById("meta-instagram-user-id").value
      }) });
      result.textContent = "Meta ad settings saved.";
      await Promise.all([loadSettings(), loadStatus()]);
    });
    document.getElementById("check-meta-access").addEventListener("click", async event => {
      const result = document.getElementById("meta-result");
      event.target.disabled = true;
      result.textContent = "Checking Meta access...";
      try {
        const data = await api("/api/maison-flou/meta/status?check=1");
        const validation = data.validation || {};
        result.textContent = validation.ok
          ? "Meta access ok."
          : \`Meta needs review: \${(validation.missing || data.missing || []).join(", ") || validation.error || "check failed"}\`;
      } catch (error) {
        result.textContent = error.message;
      } finally {
        event.target.disabled = false;
      }
    });
    document.getElementById("sync-meta-ads").addEventListener("click", async event => {
      const result = document.getElementById("meta-result");
      event.target.disabled = true;
      result.textContent = "Syncing Instagram ads...";
      try {
        const data = await api("/api/maison-flou/meta/sync-ads", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ limit:25 }) });
        result.textContent = \`Meta sync complete: \${data.created || 0} created, \${data.matched || 0} matched.\`;
        await Promise.all([loadStatus(), loadTldr(true)]);
      } catch (error) {
        result.textContent = error.message;
      } finally {
        event.target.disabled = false;
      }
    });
    async function boot() {
      await Promise.all([loadSession(), loadStatus(), loadTldr(false), loadSettings(), loadLeads(false), loadPosts()]);
    }
    boot().catch(error => {
      document.getElementById("status").textContent = error.message;
      auth.classList.add("visible");
    });
  </script>
</body>
</html>`;
}

async function handleOfficeStatus(request, env) {
  if (!(await labAccessAllowed(request, env))) return unauthorizedResponse(request);
  const url = new URL(request.url);
  const day = url.searchParams.get("day") || officeClock(new Date(), await getContentSetting(env, "office_timezone", DEFAULT_OFFICE_TIMEZONE)).date;
  return jsonResponse(request, await buildOfficeStatus(env, day));
}

async function handleOfficeTldr(request, env) {
  if (!(await labAccessAllowed(request, env))) return unauthorizedResponse(request);
  const url = new URL(request.url);
  const payload = request.method === "POST" ? await readPayload(request).catch(() => ({})) : {};
  const refresh = boolSetting(url.searchParams.get("refresh") || payload.refresh);
  const day = url.searchParams.get("day") || payload.day || officeClock(new Date(), await getContentSetting(env, "office_timezone", DEFAULT_OFFICE_TIMEZONE)).date;
  const summary = await buildOfficeStatus(env, day);
  return jsonResponse(request, await generateOfficeTldr(env, summary, refresh));
}

async function handleLeads(request, env) {
  if (!(await labAccessAllowed(request, env))) return unauthorizedResponse(request);
  const url = new URL(request.url);
  const reveal = url.searchParams.get("reveal") === "1";
  const limit = Number(url.searchParams.get("limit") || "50");
  return jsonResponse(request, {
    business_id: DEFAULT_BUSINESS_ID,
    masked: !reveal,
    leads: await readWaitlistLeads(env, { limit, reveal }),
  });
}

async function handlePosts(request, env) {
  if (!(await labAccessAllowed(request, env))) return unauthorizedResponse(request);
  const url = new URL(request.url);
  return jsonResponse(request, {
    business_id: DEFAULT_BUSINESS_ID,
    posts: await readContentRuns(env, Number(url.searchParams.get("limit") || "50")),
  });
}

async function handleMedia(request, env, id) {
  const image = await readContentImage(env, id);
  if (!image || !image.bytes_base64) {
    return new Response("not found", {
      status: 404,
      headers: { "Cache-Control": "no-store" },
    });
  }
  const bytes = base64ToBytes(image.bytes_base64);
  return new Response(bytes, {
    headers: {
      "Content-Type": cleanText(image.mime_type, 80) || "application/octet-stream",
      "Cache-Control": "public, max-age=31536000, immutable",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

async function handleSettings(request, env) {
  if (!(await labAccessAllowed(request, env))) return unauthorizedResponse(request);
  if (request.method === "GET") {
    return jsonResponse(request, { business_id: DEFAULT_BUSINESS_ID, settings: await readContentSettings(env) });
  }
  if (request.method !== "POST") {
    return jsonResponse(request, { ok: false, error: "method_not_allowed" }, 405);
  }
  const payload = await readPayload(request).catch(() => ({}));
  const allowed = {};
  if (Object.prototype.hasOwnProperty.call(payload, "content_scheduler_enabled")) {
    allowed.content_scheduler_enabled = boolSetting(payload.content_scheduler_enabled) ? "true" : "false";
  }
  if (Object.prototype.hasOwnProperty.call(payload, "content_scheduler_mode")) {
    allowed.content_scheduler_mode = cleanText(payload.content_scheduler_mode, 20) === "draft" ? "draft" : "publish";
  }
  if (Object.prototype.hasOwnProperty.call(payload, "content_posts_per_day")) {
    allowed.content_posts_per_day = String(clampNumber(payload.content_posts_per_day, 1, 6, 1));
  }
  if (Object.prototype.hasOwnProperty.call(payload, "content_publish_times")) {
    allowed.content_publish_times = parseTimeList(payload.content_publish_times, DEFAULT_PUBLISH_TIMES).slice(0, 6).join(",");
  }
  if (Object.prototype.hasOwnProperty.call(payload, "office_timezone")) {
    allowed.office_timezone = safeTimeZone(payload.office_timezone || DEFAULT_OFFICE_TIMEZONE);
  }
  if (Object.prototype.hasOwnProperty.call(payload, "recap_enabled")) {
    allowed.recap_enabled = boolSetting(payload.recap_enabled) ? "true" : "false";
  }
  if (Object.prototype.hasOwnProperty.call(payload, "recap_email")) {
    allowed.recap_email = normalizeEmail(payload.recap_email) || ATELIER_EMAIL;
  }
  if (Object.prototype.hasOwnProperty.call(payload, "recap_time")) {
    allowed.recap_time = normalizeTime(payload.recap_time) || DEFAULT_RECAP_TIME;
  }
  if (Object.prototype.hasOwnProperty.call(payload, "meta_ad_account_id")) {
    allowed.meta_ad_account_id = normalizeMetaAdAccountId(payload.meta_ad_account_id);
  }
  if (Object.prototype.hasOwnProperty.call(payload, "meta_campaign_id")) {
    allowed.meta_campaign_id = normalizeMetaId(payload.meta_campaign_id);
  }
  if (Object.prototype.hasOwnProperty.call(payload, "meta_adset_id")) {
    allowed.meta_adset_id = normalizeMetaId(payload.meta_adset_id);
  }
  if (Object.prototype.hasOwnProperty.call(payload, "meta_page_id")) {
    allowed.meta_page_id = normalizeMetaId(payload.meta_page_id);
  }
  if (Object.prototype.hasOwnProperty.call(payload, "meta_instagram_user_id")) {
    allowed.meta_instagram_user_id = normalizeMetaId(payload.meta_instagram_user_id);
  }
  if (!Object.keys(allowed).length) {
    return jsonResponse(request, { ok: true, settings: await readContentSettings(env), updated: [] });
  }
  for (const [key, value] of Object.entries(allowed)) {
    await setContentSetting(env, key, value);
  }
  await appendOfficeEvent(
    env,
    "settings.updated",
    "Lab settings updated",
    "Cloudflare lab settings were updated.",
    "info",
    { keys: Object.keys(allowed), runtime: "cloudflare_worker" }
  );
  return jsonResponse(request, { ok: true, settings: await readContentSettings(env) });
}

async function handleReportSend(request, env) {
  if (!(await labAccessAllowed(request, env))) return unauthorizedResponse(request);
  if (request.method !== "POST") {
    return jsonResponse(request, { ok: false, error: "method_not_allowed" }, 405);
  }
  const payload = await readPayload(request).catch(() => ({}));
  const recipient = normalizeEmail(payload.recap_email) || normalizeEmail(await getContentSetting(env, "recap_email", ATELIER_EMAIL));
  if (!recipient) {
    return jsonResponse(request, { ok: false, error: "missing_recipient" }, 400);
  }
  const timezone = safeTimeZone(payload.office_timezone || await getContentSetting(env, "office_timezone", DEFAULT_OFFICE_TIMEZONE));
  const clock = officeClock(new Date(), timezone);
  const currentSummary = await buildOfficeStatus(env, clock.date);
  const previousSummary = await buildOfficeStatus(env, previousIsoDate(clock.date));
  if (boolSetting(payload.dry_run)) {
    const context = await buildRecapContext(env, previousSummary, currentSummary);
    const text = await generateRecapText(env, previousSummary, currentSummary, context);
    return jsonResponse(request, {
      ok: true,
      dry_run: true,
      recipient,
      subject: `MAISON FLOU office recap — ${previousSummary.day}`,
      preview: cleanText(text, 1200),
    });
  }
  try {
    const result = await sendDailyRecap(env, recipient, previousSummary, currentSummary);
    await appendOfficeEvent(
      env,
      "recap.sent.manual",
      "Daily report sent manually",
      "The Maison Flou daily office report was sent on demand.",
      "ok",
      { recipient_hash: (await sha256(recipient)).slice(0, 16), resend_id: result.id || "", runtime: "cloudflare_worker" }
    );
    return jsonResponse(request, {
      ok: true,
      recipient,
      resend_id: result.id || "",
      subject: result.subject || "",
      preview: cleanText(result.text, 600),
    });
  } catch (error) {
    await appendOfficeEvent(
      env,
      "recap.failed",
      "Daily report failed",
      "The Maison Flou daily office report could not be sent on demand.",
      "failed",
      { error: String(error).slice(0, 500), runtime: "cloudflare_worker" }
    );
    return jsonResponse(request, { ok: false, error: String(error).slice(0, 500) }, 502);
  }
}

async function handleMetaStatus(request, env) {
  if (!(await labAccessAllowed(request, env))) return unauthorizedResponse(request);
  const config = await readMetaSettings(env);
  const syncRows = await readMetaAdSyncRows(env, 50);
  const url = new URL(request.url);
  const check = url.searchParams.get("check") === "1";
  const validation = check ? await validateMetaAccess(env, config) : null;
  return jsonResponse(request, {
    ok: true,
    config,
    missing: missingMetaConfig(config),
    sync_count: syncRows.filter((row) => cleanText(row.status, 40) === "created_paused").length,
    recent_syncs: syncRows.slice(0, 12),
    ...(validation ? { validation } : {}),
  });
}

async function handleMetaSyncAds(request, env) {
  if (!(await labAccessAllowed(request, env))) return unauthorizedResponse(request);
  if (request.method !== "POST") {
    return jsonResponse(request, { ok: false, error: "method_not_allowed" }, 405);
  }
  const payload = await readPayload(request).catch(() => ({}));
  try {
    const result = await syncMetaAds(env, {
      dryRun: boolSetting(payload.dry_run),
      limit: clampNumber(payload.limit, 1, 50, 25),
    });
    await appendOfficeEvent(
      env,
      "meta.sync.completed",
      "Meta ads sync completed",
      result.ok
        ? `Meta sync checked ${result.content_runs_seen || 0} content run(s) and created ${result.created || 0} paused ad(s).`
        : "Meta sync could not run because configuration is incomplete.",
      result.ok ? "ok" : "needs_review",
      { created: result.created || 0, matched: result.matched || 0, missing: result.missing || [], dry_run: Boolean(result.dry_run), runtime: "cloudflare_worker" }
    );
    return jsonResponse(request, result, result.ok ? 200 : 400);
  } catch (error) {
    await appendOfficeEvent(
      env,
      "meta.sync.failed",
      "Meta ads sync failed",
      "The Meta ads sync could not complete.",
      "failed",
      { error: String(error).slice(0, 700), runtime: "cloudflare_worker" }
    );
    return jsonResponse(request, { ok: false, error: String(error).slice(0, 700) }, 502);
  }
}

async function handleContentPublish(request, env) {
  if (!(await labAccessAllowed(request, env))) return unauthorizedResponse(request);
  if (request.method !== "POST") {
    return jsonResponse(request, { ok: false, error: "method_not_allowed" }, 405);
  }
  const payload = await readPayload(request).catch(() => ({}));
  try {
    const result = await runContentPublish(env, {
      request,
      trigger: "cloudflare-lab",
      mode: cleanText(payload.mode, 40) || "shareNow",
      saveToDraft: boolSetting(payload.save_to_draft),
      imagePrompt: payload.image_prompt || "",
      objectNumber: payload.object_number || "",
    });
    return jsonResponse(request, result);
  } catch (error) {
    await appendOfficeEvent(
      env,
      "content.publish.failed",
      "Cloudflare publish failed",
      "The Cloudflare lab could not complete a Buffer publish.",
      "failed",
      { error: String(error).slice(0, 500), runtime: "cloudflare_worker" }
    );
    return jsonResponse(request, { ok: false, error: String(error).slice(0, 500) }, 502);
  }
}

async function handleRequest(request, env) {
  const url = new URL(request.url);
  const isOfficeHost = url.hostname.toLowerCase() === OFFICE_HOST;
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders(request) });
  }
  if (isOfficeHost && url.pathname === "/login") {
    if (await labAccessAllowed(request, env)) return redirectResponse("/");
    return htmlResponse(renderOfficeLogin(env));
  }
  if (isOfficeHost && url.pathname === "/auth/google") return handleOfficeGoogleAuth(request, env);
  if (isOfficeHost && url.pathname === "/logout") return handleOfficeLogout();
  if (url.pathname === "/health" || url.pathname === `${API_PREFIX}/health`) return handleHealth(request, env);
  if (url.pathname === WAITLIST_PATH) return handleWaitlist(request, env);
  if (
    url.pathname === LAB_PATH_PREFIX
    || url.pathname === `${LAB_PATH_PREFIX}/`
    || url.pathname === `${LAB_PATH_PREFIX}/maison-flou`
    || (isOfficeHost && ["/", "/office", "/office/", "/office/maison-flou"].includes(url.pathname))
  ) {
    if (!(await labAccessAllowed(request, env))) {
      return isOfficeHost ? htmlResponse(renderOfficeLogin(env)) : htmlResponse(renderLabDashboard(), 401);
    }
    return htmlResponse(renderLabDashboard());
  }
  if (url.pathname === `${API_PREFIX}/office/status`) return handleOfficeStatus(request, env);
  if (url.pathname === `${API_PREFIX}/office/tldr`) return handleOfficeTldr(request, env);
  if (url.pathname === `${API_PREFIX}/office/session`) return handleOfficeSession(request, env);
  if (url.pathname === `${API_PREFIX}/waitlist/leads`) return handleLeads(request, env);
  if (url.pathname === `${API_PREFIX}/posts`) return handlePosts(request, env);
  if (url.pathname.startsWith(`${API_PREFIX}/media/`)) {
    return handleMedia(request, env, decodeURIComponent(url.pathname.slice(`${API_PREFIX}/media/`.length)));
  }
  if (url.pathname === `${API_PREFIX}/settings`) return handleSettings(request, env);
  if (url.pathname === `${API_PREFIX}/report/send`) return handleReportSend(request, env);
  if (url.pathname === `${API_PREFIX}/meta/status`) return handleMetaStatus(request, env);
  if (url.pathname === `${API_PREFIX}/meta/sync-ads`) return handleMetaSyncAds(request, env);
  if (url.pathname === `${API_PREFIX}/content/publish`) return handleContentPublish(request, env);
  return jsonResponse(request, { ok: false, error: "not_found" }, 404);
}

export default {
  async fetch(request, env) {
    return handleRequest(request, env);
  },
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(handleScheduled(controller, env));
  },
};
