const WAITLIST_PATH = "/api/maison-flou/waitlist";
const MAX_BODY_BYTES = 16 * 1024;
const FROM_EMAIL = "Maison Flou <atelier@maisonflou.com>";
const REPLY_TO_EMAIL = "atelier@maisonflou.com";
const ATELIER_EMAIL = "atelier@maisonflou.com";
const DEFAULT_SCHEDULER_ENABLED = "false";
const DEFAULT_SCHEDULER_MODE = "publish";
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

  const publishUrl = cleanText(env.POCKET_CONTENT_PUBLISH_URL, 500);
  const token = cleanText(env.POCKET_ACCESS_TOKEN, 500);
  if (!publishUrl || !token) {
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
  const response = await fetch(publishUrl, {
    method: "POST",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/json",
      "X-Pocket-Token": token,
      "User-Agent": "maison-flou-scheduler/0.1 (+https://maisonflou.com)",
    },
    body: JSON.stringify({
      publish_buffer: mode !== "draft",
      draft_buffer: mode === "draft",
      source: "cloudflare-cron",
      record_activity: true,
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
    await logContentRun(env, {
      status: "failed",
      trigger: "cloudflare-cron",
      metadata: { cron: controller.cron || "", response_status: response.status, payload },
    });
    await appendOfficeEvent(
      env,
      "content.scheduler.failed",
      "Content scheduler failed",
      "The scheduled publishing request failed.",
      "failed",
      { cron: controller.cron || "", response_status: response.status, runtime: "cloudflare_worker" }
    );
    throw new Error(`Scheduled publish failed: ${response.status}`);
  }

  const bufferPostId = (((payload.buffer || {}).result || {}).post || {}).id || "";
  await logContentRun(env, {
    status: mode === "draft" ? "drafted" : "published",
    trigger: "cloudflare-cron",
    object_number: payload.object_number || "",
    image_url: payload.image_url || "",
    caption: payload.caption || "",
    buffer_post_id: bufferPostId,
    metadata: { cron: controller.cron || "", source: payload.image_source || "", post_record: payload.post_record || {} },
  });
  await appendOfficeEvent(
    env,
    mode === "draft" ? "content.drafted" : "content.published",
    `Objet ${payload.object_number || ""}`.trim(),
    mode === "draft" ? "Scheduled Buffer draft created." : "Scheduled Buffer post published.",
    "ok",
    { cron: controller.cron || "", buffer_post_id: bufferPostId, runtime: "cloudflare_worker" }
  );
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

async function handleRequest(request, env) {
  const url = new URL(request.url);
  if (url.pathname !== WAITLIST_PATH) {
    return jsonResponse(request, { ok: false, error: "not_found" }, 404);
  }
  return handleWaitlist(request, env);
}

export default {
  async fetch(request, env) {
    return handleRequest(request, env);
  },
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(handleScheduled(controller, env));
  },
};
