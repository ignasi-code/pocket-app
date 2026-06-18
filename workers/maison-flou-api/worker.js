const WAITLIST_PATH = "/api/maison-flou/waitlist";
const API_PREFIX = "/api/maison-flou";
const LAB_PATH_PREFIX = "/lab";
const MAX_BODY_BYTES = 16 * 1024;
const FROM_EMAIL = "Maison Flou <atelier@maisonflou.com>";
const REPLY_TO_EMAIL = "atelier@maisonflou.com";
const ATELIER_EMAIL = "atelier@maisonflou.com";
const DEFAULT_SCHEDULER_ENABLED = "false";
const DEFAULT_SCHEDULER_MODE = "publish";
const DEFAULT_BUSINESS_ID = "maison-flou";
const DEFAULT_TLDR_MODEL = "gemini-1.5-flash";
const ALLOWED_ORIGINS = new Set([
  "https://maisonflou.com",
  "https://www.maisonflou.com",
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

function labAccessAllowed(request, env) {
  const token = requestToken(request);
  const expectedToken = cleanText(env.LAB_ACCESS_TOKEN || env.POCKET_ACCESS_TOKEN, 500);
  if (expectedToken && token === expectedToken) return true;

  if (boolSetting(env.LAB_TRUST_CF_ACCESS)) {
    const email = labAccessEmail(request);
    const allowedEmails = String(env.LAB_ALLOWED_EMAILS || "")
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean);
    if (email && (!allowedEmails.length || allowedEmails.includes(email))) return true;
  }

  return false;
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
  counts.leads = waitlistLeadCount;
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
    stats: { waitlist_leads: waitlistLeadCount },
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

function gqlString(value) {
  return JSON.stringify(String(value || ""));
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

async function requestGeneratedContent(env, trigger, mode) {
  const publishUrl = cleanText(env.POCKET_CONTENT_PUBLISH_URL, 800);
  const token = cleanText(env.POCKET_ACCESS_TOKEN, 500);
  if (!publishUrl || !token) {
    throw new Error("POCKET_CONTENT_PUBLISH_URL or POCKET_ACCESS_TOKEN is not configured.");
  }
  const response = await fetch(publishUrl, {
    method: "POST",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/json",
      "X-Pocket-Token": token,
      "User-Agent": "maison-flou-worker/0.1 (+https://maisonflou.com)",
    },
    body: JSON.stringify({
      publish_buffer: false,
      draft_buffer: false,
      source: trigger,
      record_activity: true,
      mode,
    }),
  });
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text.slice(0, 1000) };
  }
  if (!response.ok) {
    throw new Error(`Content origin HTTP ${response.status}: ${JSON.stringify(payload).slice(0, 500)}`);
  }
  return payload;
}

async function runContentPublish(env, { trigger = "cloudflare-lab", mode = "shareNow", saveToDraft = false } = {}) {
  const generated = await requestGeneratedContent(env, trigger, mode);
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
      category: generated.category || "",
      buffer,
      origin_post_record: generated.post_record || {},
    },
  });
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
    buffer,
  };
}

async function handleScheduled(controller, env) {
  if (!env.DB) return;
  await setContentSetting(env, "scheduler_last_seen_at", utcTimestamp());
  await setContentSetting(env, "scheduler_last_cron", controller.cron || "");

  const enabled = schedulerEnabled(await getContentSetting(env, "content_scheduler_enabled", DEFAULT_SCHEDULER_ENABLED));
  if (!enabled) {
    await appendOfficeEvent(
      env,
      "content.scheduler.idle",
      "Content scheduler idle",
      "Cron fired, but autonomous publishing is disabled in D1 settings.",
      "info",
      { cron: controller.cron || "", runtime: "cloudflare_worker" }
    );
    return;
  }

  if (!cleanText(env.POCKET_CONTENT_PUBLISH_URL, 800) || !cleanText(env.POCKET_ACCESS_TOKEN, 500)) {
    await appendOfficeEvent(
      env,
      "content.scheduler.needs_review",
      "Content scheduler missing origin",
      "Autonomous publishing is enabled, but Termux publish URL or token is not configured.",
      "needs_review",
      { cron: controller.cron || "", runtime: "cloudflare_worker" }
    );
    return;
  }

  const mode = await getContentSetting(env, "content_scheduler_mode", DEFAULT_SCHEDULER_MODE);
  try {
    await runContentPublish(env, {
      trigger: "cloudflare-cron",
      mode: mode === "draft" ? "addToQueue" : "shareNow",
      saveToDraft: mode === "draft",
    });
  } catch (error) {
    await logContentRun(env, {
      status: "failed",
      trigger: "cloudflare-cron",
      metadata: { cron: controller.cron || "", error: String(error).slice(0, 500) },
    });
    await appendOfficeEvent(
      env,
      "content.scheduler.failed",
      "Content scheduler failed",
      "The scheduled publishing request failed.",
      "failed",
      { cron: controller.cron || "", error: String(error).slice(0, 500), runtime: "cloudflare_worker" }
    );
    throw error;
  }
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
      </div>
      <div class="card" id="event-count">0 events</div>
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
      <p class="label">Controls</p>
      <div class="card">
        <label class="label" for="scheduler-enabled">Scheduler</label>
        <select id="scheduler-enabled"><option value="false">Disabled</option><option value="true">Enabled</option></select>
        <label class="label" for="scheduler-mode" style="margin-top:10px">Mode</label>
        <select id="scheduler-mode"><option value="publish">Publish now</option><option value="draft">Draft</option></select>
        <div class="toolbar">
          <button id="save-settings">Save settings</button>
          <button id="publish-now">Publish now</button>
        </div>
        <div class="subtle" id="control-result"></div>
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
      const rows = [["Generated", counts.generated], ["Published", counts.published], ["Review", counts.needs_review], ["Leads", counts.leads], ["Lead Events", counts.lead_events], ["Emails", counts.emails], ["Replies", counts.replies], ["Failed", counts.failed]];
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
      document.getElementById("last-action").textContent = data.last_action_label ? \`Last action: \${data.last_action_label}\` : "No logged action yet.";
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
    document.getElementById("refresh-tldr").addEventListener("click", () => loadTldr(true));
    document.getElementById("reveal-leads").addEventListener("click", () => loadLeads(true));
    document.getElementById("save-settings").addEventListener("click", async () => {
      const result = document.getElementById("control-result");
      result.textContent = "Saving...";
      await api("/api/maison-flou/settings", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ content_scheduler_enabled: document.getElementById("scheduler-enabled").value, content_scheduler_mode: document.getElementById("scheduler-mode").value }) });
      result.textContent = "Settings saved.";
      await loadSettings();
    });
    document.getElementById("publish-now").addEventListener("click", async event => {
      const result = document.getElementById("control-result");
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
    async function boot() {
      await Promise.all([loadStatus(), loadTldr(false), loadSettings(), loadLeads(false), loadPosts()]);
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
  if (!labAccessAllowed(request, env)) return unauthorizedResponse(request);
  const url = new URL(request.url);
  return jsonResponse(request, await buildOfficeStatus(env, url.searchParams.get("day") || ""));
}

async function handleOfficeTldr(request, env) {
  if (!labAccessAllowed(request, env)) return unauthorizedResponse(request);
  const url = new URL(request.url);
  const payload = request.method === "POST" ? await readPayload(request).catch(() => ({})) : {};
  const refresh = boolSetting(url.searchParams.get("refresh") || payload.refresh);
  const summary = await buildOfficeStatus(env, url.searchParams.get("day") || payload.day || "");
  return jsonResponse(request, await generateOfficeTldr(env, summary, refresh));
}

async function handleLeads(request, env) {
  if (!labAccessAllowed(request, env)) return unauthorizedResponse(request);
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
  if (!labAccessAllowed(request, env)) return unauthorizedResponse(request);
  const url = new URL(request.url);
  return jsonResponse(request, {
    business_id: DEFAULT_BUSINESS_ID,
    posts: await readContentRuns(env, Number(url.searchParams.get("limit") || "50")),
  });
}

async function handleSettings(request, env) {
  if (!labAccessAllowed(request, env)) return unauthorizedResponse(request);
  if (request.method === "GET") {
    return jsonResponse(request, { business_id: DEFAULT_BUSINESS_ID, settings: await readContentSettings(env) });
  }
  if (request.method !== "POST") {
    return jsonResponse(request, { ok: false, error: "method_not_allowed" }, 405);
  }
  const payload = await readPayload(request).catch(() => ({}));
  const allowed = {
    content_scheduler_enabled: boolSetting(payload.content_scheduler_enabled) ? "true" : "false",
    content_scheduler_mode: cleanText(payload.content_scheduler_mode, 20) === "draft" ? "draft" : "publish",
  };
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

async function handleContentPublish(request, env) {
  if (!labAccessAllowed(request, env)) return unauthorizedResponse(request);
  if (request.method !== "POST") {
    return jsonResponse(request, { ok: false, error: "method_not_allowed" }, 405);
  }
  const payload = await readPayload(request).catch(() => ({}));
  try {
    const result = await runContentPublish(env, {
      trigger: "cloudflare-lab",
      mode: cleanText(payload.mode, 40) || "shareNow",
      saveToDraft: boolSetting(payload.save_to_draft),
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
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders(request) });
  }
  if (url.pathname === WAITLIST_PATH) return handleWaitlist(request, env);
  if (url.pathname === LAB_PATH_PREFIX || url.pathname === `${LAB_PATH_PREFIX}/` || url.pathname === `${LAB_PATH_PREFIX}/maison-flou`) {
    if (!labAccessAllowed(request, env)) return htmlResponse(renderLabDashboard(), 401);
    return htmlResponse(renderLabDashboard());
  }
  if (url.pathname === `${API_PREFIX}/office/status`) return handleOfficeStatus(request, env);
  if (url.pathname === `${API_PREFIX}/office/tldr`) return handleOfficeTldr(request, env);
  if (url.pathname === `${API_PREFIX}/waitlist/leads`) return handleLeads(request, env);
  if (url.pathname === `${API_PREFIX}/posts`) return handlePosts(request, env);
  if (url.pathname === `${API_PREFIX}/settings`) return handleSettings(request, env);
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
