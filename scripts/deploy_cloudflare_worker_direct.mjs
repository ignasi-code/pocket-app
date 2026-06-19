#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const ROOT_DIR = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const API_BASE = "https://api.cloudflare.com/client/v4";
const MAISON_FLOU_ENV_PATH = path.join(ROOT_DIR, "office", "businesses", "maison-flou", ".env");
const OFFICE_HOST = "office.maisonflou.com";
const GOOGLE_IDP_NAME = "Google";

function cleanValue(value) {
  let text = String(value || "").trim();
  for (let i = 0; i < 2; i += 1) {
    if (text.length >= 2 && text[0] === text[text.length - 1] && ["'", '"'].includes(text[0])) {
      text = text.slice(1, -1).trim();
    }
  }
  return text;
}

function readEnvFile(filePath) {
  const values = {};
  if (!fs.existsSync(filePath)) return values;

  for (const rawLine of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const index = line.indexOf("=");
    values[line.slice(0, index).trim()] = cleanValue(line.slice(index + 1));
  }
  return values;
}

function parseBoolean(value, defaultValue = false) {
  const text = cleanValue(value).toLowerCase();
  if (!text) return defaultValue;
  return ["1", "true", "yes", "on"].includes(text);
}

function loadConfig() {
  const env = {
    ...readEnvFile(path.join(ROOT_DIR, ".env")),
    ...readEnvFile(MAISON_FLOU_ENV_PATH),
    ...process.env,
  };
  const routePattern = cleanValue(env.CLOUDFLARE_WORKER_ROUTE) || "maisonflou.com/api/maison-flou/waitlist*";
  const workerRoutes = [
    routePattern,
    "maisonflou.com/api/maison-flou/*",
    "maisonflou.com/lab*",
    `${OFFICE_HOST}/*`,
    ...cleanValue(env.CLOUDFLARE_WORKER_ROUTES).split(","),
  ].map(cleanValue).filter(Boolean);
  const accessAllowedEmails = (
    cleanValue(env.ACCESS_ALLOWED_EMAILS)
    || cleanValue(env.LAB_ALLOWED_EMAILS)
    || cleanValue(env.RESEND_TEST_EMAIL)
  )
    .split(",")
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean);
  return {
    apiToken: cleanValue(env.CLOUDFLARE_API_TOKEN),
    accountId: cleanValue(env.CLOUDFLARE_ACCOUNT_ID),
    zoneId: cleanValue(env.CLOUDFLARE_ZONE_ID),
    scriptName: cleanValue(env.CLOUDFLARE_WORKER_SCRIPT) || "maison-flou-api",
    routePattern,
    workerRoutes: [...new Set(workerRoutes)],
    workerPath: path.resolve(ROOT_DIR, cleanValue(env.CLOUDFLARE_WORKER_PATH) || "workers/maison-flou-api/worker.js"),
    d1DatabaseName: cleanValue(env.CLOUDFLARE_D1_DATABASE) || "maison_flou",
    workerCron: cleanValue(env.CLOUDFLARE_WORKER_CRON) || "*/15 * * * *",
    resendApiKey: cleanValue(env.RESEND_API_KEY),
    bufferApiKey: cleanValue(env.BUFFER_API_KEY),
    bufferChannelId: cleanValue(env.BUFFER_MAISON_FLOU_CHANNEL_ID) || cleanValue(env.BUFFER_CHANNEL_ID),
    geminiApiKey: cleanValue(env.GEMINI_API_KEY),
    maisonFlouGeminiModel: cleanValue(env.MAISON_FLOU_GEMINI_MODEL),
    maisonFlouImageModel: cleanValue(env.MAISON_FLOU_IMAGE_MODEL),
    metaAccessToken: cleanValue(env.META_ACCESS_TOKEN),
    metaGraphVersion: cleanValue(env.META_GRAPH_VERSION) || "v25.0",
    labAccessToken: cleanValue(env.LAB_ACCESS_TOKEN),
    labAllowedEmails: cleanValue(env.LAB_ALLOWED_EMAILS) || accessAllowedEmails.join(","),
    labTrustCfAccess: cleanValue(env.LAB_TRUST_CF_ACCESS) || "1",
    googleOauthClientId: cleanValue(env.GOOGLE_OAUTH_CLIENT_ID) || cleanValue(env.ACCESS_GOOGLE_CLIENT_ID),
    officeAllowedEmails: cleanValue(env.OFFICE_ALLOWED_EMAILS) || cleanValue(env.LAB_ALLOWED_EMAILS) || accessAllowedEmails.join(","),
    officeSessionSecret: cleanValue(env.OFFICE_SESSION_SECRET),
    publicMediaBaseUrl: cleanValue(env.PUBLIC_MEDIA_BASE_URL) || "https://maisonflou.com",
    officeHost: cleanValue(env.OFFICE_HOST) || OFFICE_HOST,
    accessAppName: cleanValue(env.ACCESS_APP_NAME) || "Maison Flou Office",
    accessAllowedEmails,
    accessGoogleIdpName: cleanValue(env.ACCESS_GOOGLE_IDP_NAME) || GOOGLE_IDP_NAME,
    accessSessionDuration: cleanValue(env.ACCESS_SESSION_DURATION) || "24h",
    accessAutoRedirectToIdentity: parseBoolean(env.ACCESS_AUTO_REDIRECT_TO_IDENTITY, false),
    accessOfficeEnabled: parseBoolean(env.ACCESS_OFFICE_ENABLED, false),
    pocketAccessToken: cleanValue(env.POCKET_ACCESS_TOKEN),
    pocketContentPublishUrl: cleanValue(env.POCKET_CONTENT_PUBLISH_URL)
      || (cleanValue(env.POCKET_PUBLIC_BASE_URL)
        ? `${cleanValue(env.POCKET_PUBLIC_BASE_URL).replace(/\/+$/, "")}/api/maison-flou/content/publish`
        : ""),
    originUrl: cleanValue(env.MAISON_FLOU_WAITLIST_ORIGIN_URL)
      || "https://changes-sic-dans-directive.trycloudflare.com/api/maison-flou/waitlist",
  };
}

async function apiRequest(pathname, { token, method = "GET", headers = {}, body } = {}) {
  const response = await fetch(`${API_BASE}${pathname}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...headers,
    },
    body,
  });
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }

  if (!response.ok || payload.success === false) {
    const errors = payload.errors || payload.raw || response.statusText;
    throw new Error(`${method} ${pathname} failed: ${JSON.stringify(errors)}`);
  }

  return Object.prototype.hasOwnProperty.call(payload, "result") ? payload.result : payload;
}

function renderWorkerSource(config) {
  if (!fs.existsSync(config.workerPath)) {
    throw new Error(`Worker source does not exist: ${config.workerPath}`);
  }
  const source = fs
    .readFileSync(config.workerPath, "utf8")
    .replaceAll("__MAISON_FLOU_WAITLIST_ORIGIN_URL__", config.originUrl);
  return source;
}

async function getOrCreateD1Database(config) {
  const databases = await apiRequest(`/accounts/${config.accountId}/d1/database`, {
    token: config.apiToken,
  });
  const existing = databases.find((database) => database.name === config.d1DatabaseName);
  if (existing) return { ...existing, created: false };
  const created = await apiRequest(`/accounts/${config.accountId}/d1/database`, {
    token: config.apiToken,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: config.d1DatabaseName }),
  });
  return { ...created, created: true };
}

async function queryD1(config, databaseId, sql, params = []) {
  return apiRequest(`/accounts/${config.accountId}/d1/database/${databaseId}/query`, {
    token: config.apiToken,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sql, params }),
  });
}

async function queryD1Optional(config, databaseId, sql, params = []) {
  try {
    return await queryD1(config, databaseId, sql, params);
  } catch (error) {
    const message = String(error.message || error);
    if (message.includes("duplicate column name")) return null;
    throw error;
  }
}

async function migrateD1(config, databaseId) {
  const statements = [
    `CREATE TABLE IF NOT EXISTS waitlist_leads (
      id TEXT PRIMARY KEY,
      timestamp TEXT NOT NULL,
      email TEXT NOT NULL,
      email_hash TEXT NOT NULL UNIQUE,
      instagram TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT 'maisonflou.com',
      user_agent TEXT NOT NULL DEFAULT '',
      remote_addr_hash TEXT NOT NULL DEFAULT '',
      confirmation_status TEXT NOT NULL DEFAULT 'pending',
      confirmation_sent_at TEXT NOT NULL DEFAULT '',
      notification_status TEXT NOT NULL DEFAULT 'pending',
      notification_sent_at TEXT NOT NULL DEFAULT '',
      resend_id TEXT NOT NULL DEFAULT ''
    )`,
    "ALTER TABLE waitlist_leads ADD COLUMN confirmation_status TEXT NOT NULL DEFAULT 'pending'",
    "ALTER TABLE waitlist_leads ADD COLUMN confirmation_sent_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE waitlist_leads ADD COLUMN notification_status TEXT NOT NULL DEFAULT 'pending'",
    "ALTER TABLE waitlist_leads ADD COLUMN notification_sent_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE waitlist_leads ADD COLUMN resend_id TEXT NOT NULL DEFAULT ''",
    "CREATE INDEX IF NOT EXISTS idx_waitlist_leads_timestamp ON waitlist_leads(timestamp)",
    `CREATE TABLE IF NOT EXISTS office_events (
      id TEXT PRIMARY KEY,
      timestamp TEXT NOT NULL,
      business_id TEXT NOT NULL,
      event_type TEXT NOT NULL,
      status TEXT NOT NULL,
      subject TEXT NOT NULL DEFAULT '',
      message TEXT NOT NULL DEFAULT '',
      metadata TEXT NOT NULL DEFAULT '{}'
    )`,
    "CREATE INDEX IF NOT EXISTS idx_office_events_business_timestamp ON office_events(business_id, timestamp)",
    `CREATE TABLE IF NOT EXISTS content_settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL DEFAULT ''
    )`,
    `CREATE TABLE IF NOT EXISTS content_runs (
      id TEXT PRIMARY KEY,
      timestamp TEXT NOT NULL,
      status TEXT NOT NULL,
      trigger TEXT NOT NULL DEFAULT '',
      object_number TEXT NOT NULL DEFAULT '',
      image_url TEXT NOT NULL DEFAULT '',
      caption TEXT NOT NULL DEFAULT '',
      buffer_post_id TEXT NOT NULL DEFAULT '',
      metadata TEXT NOT NULL DEFAULT '{}'
    )`,
    "CREATE INDEX IF NOT EXISTS idx_content_runs_timestamp ON content_runs(timestamp)",
    `CREATE TABLE IF NOT EXISTS office_tldr_cache (
      business_id TEXT PRIMARY KEY,
      signature TEXT NOT NULL DEFAULT '',
      text TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT '',
      generated_at TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL DEFAULT ''
    )`,
    `CREATE TABLE IF NOT EXISTS content_images (
      id TEXT PRIMARY KEY,
      timestamp TEXT NOT NULL,
      object_number TEXT NOT NULL DEFAULT '',
      kind TEXT NOT NULL DEFAULT '',
      mime_type TEXT NOT NULL DEFAULT '',
      bytes_base64 TEXT NOT NULL,
      width INTEGER NOT NULL DEFAULT 0,
      height INTEGER NOT NULL DEFAULT 0,
      metadata TEXT NOT NULL DEFAULT '{}'
    )`,
    "CREATE INDEX IF NOT EXISTS idx_content_images_object_timestamp ON content_images(object_number, timestamp)",
    `CREATE TABLE IF NOT EXISTS technology_changes (
      id TEXT PRIMARY KEY,
      timestamp TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'git',
      title TEXT NOT NULL DEFAULT '',
      details TEXT NOT NULL DEFAULT '',
      metadata TEXT NOT NULL DEFAULT '{}'
    )`,
    "CREATE INDEX IF NOT EXISTS idx_technology_changes_timestamp ON technology_changes(timestamp)",
    `CREATE TABLE IF NOT EXISTS meta_ad_sync (
      id TEXT PRIMARY KEY,
      timestamp TEXT NOT NULL,
      business_id TEXT NOT NULL DEFAULT 'maison-flou',
      content_run_id TEXT NOT NULL UNIQUE,
      object_number TEXT NOT NULL DEFAULT '',
      instagram_media_id TEXT NOT NULL DEFAULT '',
      instagram_permalink TEXT NOT NULL DEFAULT '',
      ad_account_id TEXT NOT NULL DEFAULT '',
      campaign_id TEXT NOT NULL DEFAULT '',
      adset_id TEXT NOT NULL DEFAULT '',
      creative_id TEXT NOT NULL DEFAULT '',
      ad_id TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT '',
      metadata TEXT NOT NULL DEFAULT '{}'
    )`,
    "CREATE INDEX IF NOT EXISTS idx_meta_ad_sync_timestamp ON meta_ad_sync(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_meta_ad_sync_instagram_media ON meta_ad_sync(instagram_media_id)",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('content_scheduler_enabled', 'false', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('content_scheduler_mode', 'publish', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('content_posts_per_day', '1', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('content_publish_times', '09:00', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('office_timezone', 'Europe/Madrid', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('recap_enabled', 'true', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('recap_email', 'atelier@maisonflou.com', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('recap_time', '18:00', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('meta_ad_account_id', '', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('meta_campaign_id', '', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('meta_adset_id', '', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('meta_page_id', '', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('meta_instagram_user_id', '', datetime('now'))",
    "INSERT OR IGNORE INTO content_settings (key, value, updated_at) VALUES ('object_sequence', '12', datetime('now'))",
  ];
  for (const statement of statements) {
    if (statement.startsWith("ALTER TABLE")) {
      await queryD1Optional(config, databaseId, statement);
    } else {
      await queryD1(config, databaseId, statement);
    }
  }
}

function readGitTechnologyChanges() {
  try {
    const output = execFileSync(
      "git",
      ["log", "--since=7 days ago", "--pretty=format:%H%x1f%h%x1f%cI%x1f%s"],
      { cwd: ROOT_DIR, encoding: "utf8" }
    );
    return output.split("\n").filter(Boolean).slice(0, 80).map((line) => {
      const [hash, shortHash, timestamp, ...titleParts] = line.split("\x1f");
      return {
        id: cleanValue(hash),
        timestamp: cleanValue(timestamp),
        source: "git",
        title: cleanValue(titleParts.join(" ")),
        details: "",
        metadata: {
          short_hash: cleanValue(shortHash),
          deployed_at: new Date().toISOString(),
        },
      };
    }).filter((change) => change.id && change.timestamp && change.title);
  } catch {
    return [];
  }
}

async function syncTechnologyChanges(config, databaseId) {
  const changes = readGitTechnologyChanges();
  for (const change of changes) {
    await queryD1(
      config,
      databaseId,
      `INSERT OR IGNORE INTO technology_changes (
        id, timestamp, source, title, details, metadata
      ) VALUES (?, ?, ?, ?, ?, ?)`,
      [
        change.id,
        change.timestamp,
        change.source,
        change.title,
        change.details,
        JSON.stringify(change.metadata),
      ]
    );
  }
  return changes.length;
}

async function putWorkerScript(config, databaseId) {
  const source = renderWorkerSource(config);
  const metadata = {
    main_module: "worker.js",
    bindings: [
      {
        type: "d1",
        name: "DB",
        id: databaseId,
      },
    ],
  };
  const formData = new FormData();
  formData.append("metadata", JSON.stringify(metadata));
  formData.append("worker.js", new Blob([source], { type: "application/javascript+module" }), "worker.js");
  return apiRequest(`/accounts/${config.accountId}/workers/scripts/${config.scriptName}`, {
    token: config.apiToken,
    method: "PUT",
    body: formData,
  });
}

async function putWorkerSecret(config, name, value) {
  if (!value) throw new Error(`${name} is required.`);
  return apiRequest(`/accounts/${config.accountId}/workers/scripts/${config.scriptName}/secrets`, {
    token: config.apiToken,
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      text: value,
      type: "secret_text",
    }),
  });
}

async function putOptionalWorkerSecret(config, name, value) {
  if (!value) return null;
  return putWorkerSecret(config, name, value);
}

async function upsertSchedules(config) {
  if (!config.workerCron) return null;
  return apiRequest(`/accounts/${config.accountId}/workers/scripts/${config.scriptName}/schedules`, {
    token: config.apiToken,
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify([{ cron: config.workerCron }]),
  });
}

async function upsertRoute(config) {
  const routes = await apiRequest(`/zones/${config.zoneId}/workers/routes`, {
    token: config.apiToken,
  });
  const existing = routes.find((route) => route.pattern === config.routePattern);
  const payload = JSON.stringify({
    pattern: config.routePattern,
    script: config.scriptName,
  });
  if (existing) {
    return apiRequest(`/zones/${config.zoneId}/workers/routes/${existing.id}`, {
      token: config.apiToken,
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: payload,
    });
  }
  return apiRequest(`/zones/${config.zoneId}/workers/routes`, {
    token: config.apiToken,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
  });
}

async function upsertRoutes(config) {
  const results = [];
  for (const routePattern of config.workerRoutes) {
    results.push(await upsertRoute({ ...config, routePattern }));
  }
  return results;
}

async function upsertOfficeDns(config) {
  const records = await apiRequest(`/zones/${config.zoneId}/dns_records?name=${encodeURIComponent(config.officeHost)}`, {
    token: config.apiToken,
  });
  const existing = records.find((record) => record.name === config.officeHost);
  const payload = JSON.stringify({
    type: "CNAME",
    name: config.officeHost,
    content: "maisonflou.com",
    ttl: 1,
    proxied: true,
    comment: "Maison Flou private office routed to Cloudflare Worker",
  });
  if (existing) {
    return apiRequest(`/zones/${config.zoneId}/dns_records/${existing.id}`, {
      token: config.apiToken,
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: payload,
    });
  }
  return apiRequest(`/zones/${config.zoneId}/dns_records`, {
    token: config.apiToken,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
  });
}

async function getAccessIdentityProviders(config) {
  return apiRequest(`/accounts/${config.accountId}/access/identity_providers`, {
    token: config.apiToken,
  });
}

async function findAccessGoogleIdp(config) {
  const providers = await getAccessIdentityProviders(config);
  return providers.find((provider) => (
    provider.type === "google"
    && (!config.accessGoogleIdpName || provider.name === config.accessGoogleIdpName)
  )) || providers.find((provider) => provider.type === "google");
}

async function resolveGoogleOauthClientId(config) {
  if (config.googleOauthClientId) return config.googleOauthClientId;
  const googleIdp = await findAccessGoogleIdp(config).catch(() => null);
  return cleanValue(googleIdp && googleIdp.config && googleIdp.config.client_id);
}

async function upsertAccessOrganizationBranding(config) {
  try {
    const organization = await apiRequest(`/accounts/${config.accountId}/access/organizations`, {
      token: config.apiToken,
    });
    return await apiRequest(`/accounts/${config.accountId}/access/organizations`, {
      token: config.apiToken,
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: organization.name,
        auth_domain: organization.auth_domain,
        login_design: {
          background_color: "#f5f1e8",
          text_color: "#15130f",
          header_text: "Private atelier access",
          footer_text: "MAISON FLOU OFFICE",
        },
      }),
    });
  } catch (error) {
    return { skipped: true, error: String(error.message || error).slice(0, 500) };
  }
}

async function upsertAccessOfficeApp(config) {
  if (!config.accessAllowedEmails.length) {
    throw new Error("ACCESS_ALLOWED_EMAILS, LAB_ALLOWED_EMAILS, or RESEND_TEST_EMAIL is required for the office Access policy.");
  }
  const googleIdp = await findAccessGoogleIdp(config);
  if (!googleIdp) {
    throw new Error("No Google Access identity provider found. Create it in Cloudflare One first.");
  }
  const apps = await apiRequest(`/accounts/${config.accountId}/access/apps`, {
    token: config.apiToken,
  });
  const existing = apps.find((app) => app.domain === config.officeHost || app.name === config.accessAppName);
  const payload = {
    name: config.accessAppName,
    type: "self_hosted",
    domain: config.officeHost,
    allowed_idps: [googleIdp.id || googleIdp.uid],
    auto_redirect_to_identity: config.accessAutoRedirectToIdentity,
    session_duration: config.accessSessionDuration,
    policies: [
      {
        name: "Allow Maison Flou operators",
        decision: "allow",
        precedence: 1,
        session_duration: config.accessSessionDuration,
        include: config.accessAllowedEmails.map((email) => ({ email: { email } })),
        exclude: [],
        require: [],
      },
    ],
  };
  if (existing) {
    return apiRequest(`/accounts/${config.accountId}/access/apps/${existing.id}`, {
      token: config.apiToken,
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }
  return apiRequest(`/accounts/${config.accountId}/access/apps`, {
    token: config.apiToken,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function deleteAccessOfficeApp(config) {
  const apps = await apiRequest(`/accounts/${config.accountId}/access/apps`, {
    token: config.apiToken,
  });
  const existing = apps.find((app) => app.domain === config.officeHost || app.name === config.accessAppName);
  if (!existing) return { enabled: false, deleted: false };
  await apiRequest(`/accounts/${config.accountId}/access/apps/${existing.id}`, {
    token: config.apiToken,
    method: "DELETE",
  });
  return {
    enabled: false,
    deleted: true,
    app_id: existing.id,
    app_name: existing.name,
    domain: existing.domain,
  };
}

async function main() {
  const config = loadConfig();
  for (const [name, value] of Object.entries({
    CLOUDFLARE_API_TOKEN: config.apiToken,
    CLOUDFLARE_ACCOUNT_ID: config.accountId,
    CLOUDFLARE_ZONE_ID: config.zoneId,
    RESEND_API_KEY: config.resendApiKey,
  })) {
    if (!value) throw new Error(`${name} is required.`);
  }

  const database = await getOrCreateD1Database(config);
  const databaseId = database.uuid || database.id;
  if (!databaseId) throw new Error("Cloudflare did not return a D1 database id.");
  await migrateD1(config, databaseId);
  const technologyChangesSynced = await syncTechnologyChanges(config, databaseId);
  await putWorkerScript(config, databaseId);
  const googleOauthClientId = await resolveGoogleOauthClientId(config);
  await putWorkerSecret(config, "RESEND_API_KEY", config.resendApiKey);
  await putOptionalWorkerSecret(config, "POCKET_ACCESS_TOKEN", config.pocketAccessToken);
  await putOptionalWorkerSecret(config, "POCKET_CONTENT_PUBLISH_URL", config.pocketContentPublishUrl);
  await putOptionalWorkerSecret(config, "BUFFER_API_KEY", config.bufferApiKey);
  await putOptionalWorkerSecret(config, "BUFFER_CHANNEL_ID", config.bufferChannelId);
  await putOptionalWorkerSecret(config, "GEMINI_API_KEY", config.geminiApiKey);
  await putOptionalWorkerSecret(config, "MAISON_FLOU_GEMINI_MODEL", config.maisonFlouGeminiModel);
  await putOptionalWorkerSecret(config, "MAISON_FLOU_IMAGE_MODEL", config.maisonFlouImageModel);
  await putOptionalWorkerSecret(config, "META_ACCESS_TOKEN", config.metaAccessToken);
  await putOptionalWorkerSecret(config, "META_GRAPH_VERSION", config.metaGraphVersion);
  await putOptionalWorkerSecret(config, "GOOGLE_OAUTH_CLIENT_ID", googleOauthClientId);
  await putOptionalWorkerSecret(config, "OFFICE_ALLOWED_EMAILS", config.officeAllowedEmails);
  await putOptionalWorkerSecret(config, "OFFICE_SESSION_SECRET", config.officeSessionSecret);
  await putOptionalWorkerSecret(config, "LAB_ACCESS_TOKEN", config.labAccessToken);
  await putOptionalWorkerSecret(config, "LAB_ALLOWED_EMAILS", config.labAllowedEmails);
  await putOptionalWorkerSecret(config, "LAB_TRUST_CF_ACCESS", config.labTrustCfAccess);
  await putOptionalWorkerSecret(config, "PUBLIC_MEDIA_BASE_URL", config.publicMediaBaseUrl);
  const officeDns = await upsertOfficeDns(config);
  const routes = await upsertRoutes(config);
  const schedules = await upsertSchedules(config);
  const accessBranding = config.accessOfficeEnabled
    ? await upsertAccessOrganizationBranding(config)
    : { skipped: true, error: "" };
  const accessOfficeApp = config.accessOfficeEnabled
    ? await upsertAccessOfficeApp(config)
    : await deleteAccessOfficeApp(config);
  console.log(JSON.stringify({
    script: config.scriptName,
    route_patterns: config.workerRoutes,
    office_host: config.officeHost,
    cron: config.workerCron,
    d1_database: {
      name: config.d1DatabaseName,
      id: databaseId,
      created: Boolean(database.created),
    },
    office_dns: {
      id: officeDns.id,
      type: officeDns.type,
      name: officeDns.name,
      content: officeDns.content,
      proxied: officeDns.proxied,
    },
    access: {
      enabled: config.accessOfficeEnabled,
      app_id: accessOfficeApp.id || accessOfficeApp.app_id || "",
      app_name: accessOfficeApp.name || accessOfficeApp.app_name || "",
      domain: accessOfficeApp.domain || "",
      allowed_idps: accessOfficeApp.allowed_idps || [],
      deleted: Boolean(accessOfficeApp.deleted),
      policy_count: (accessOfficeApp.policies || []).length,
      branding_skipped: Boolean(accessBranding.skipped),
      branding_error: accessBranding.error || "",
    },
    google_oauth_client_configured: Boolean(googleOauthClientId),
    meta_token_configured: Boolean(config.metaAccessToken),
    meta_graph_version: config.metaGraphVersion,
    technology_changes_synced: technologyChangesSynced,
    routes,
    schedules,
  }, null, 2));
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
