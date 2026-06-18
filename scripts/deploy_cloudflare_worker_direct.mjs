#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const ROOT_DIR = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const API_BASE = "https://api.cloudflare.com/client/v4";

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

function loadConfig() {
  const env = { ...readEnvFile(path.join(ROOT_DIR, ".env")), ...process.env };
  return {
    apiToken: cleanValue(env.CLOUDFLARE_API_TOKEN),
    accountId: cleanValue(env.CLOUDFLARE_ACCOUNT_ID),
    zoneId: cleanValue(env.CLOUDFLARE_ZONE_ID),
    scriptName: cleanValue(env.CLOUDFLARE_WORKER_SCRIPT) || "maison-flou-api",
    routePattern: cleanValue(env.CLOUDFLARE_WORKER_ROUTE) || "maisonflou.com/api/maison-flou/waitlist*",
    workerPath: path.resolve(ROOT_DIR, cleanValue(env.CLOUDFLARE_WORKER_PATH) || "workers/maison-flou-api/worker.js"),
    d1DatabaseName: cleanValue(env.CLOUDFLARE_D1_DATABASE) || "maison_flou",
    resendApiKey: cleanValue(env.RESEND_API_KEY),
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
  ];
  for (const statement of statements) {
    if (statement.startsWith("ALTER TABLE")) {
      await queryD1Optional(config, databaseId, statement);
    } else {
      await queryD1(config, databaseId, statement);
    }
  }
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
  await putWorkerScript(config, databaseId);
  await putWorkerSecret(config, "RESEND_API_KEY", config.resendApiKey);
  const route = await upsertRoute(config);
  console.log(JSON.stringify({
    script: config.scriptName,
    route_pattern: config.routePattern,
    d1_database: {
      name: config.d1DatabaseName,
      id: databaseId,
      created: Boolean(database.created),
    },
    route,
  }, null, 2));
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
