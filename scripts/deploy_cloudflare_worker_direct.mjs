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
  return fs
    .readFileSync(config.workerPath, "utf8")
    .replaceAll("__MAISON_FLOU_WAITLIST_ORIGIN_URL__", config.originUrl);
}

async function putWorkerScript(config) {
  const source = renderWorkerSource(config);
  return apiRequest(`/accounts/${config.accountId}/workers/scripts/${config.scriptName}`, {
    token: config.apiToken,
    method: "PUT",
    headers: {
      "Content-Type": "application/javascript+module",
    },
    body: source,
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
    MAISON_FLOU_WAITLIST_ORIGIN_URL: config.originUrl,
  })) {
    if (!value) throw new Error(`${name} is required.`);
  }

  await putWorkerScript(config);
  const route = await upsertRoute(config);
  console.log(JSON.stringify({
    script: config.scriptName,
    route_pattern: config.routePattern,
    origin_url: config.originUrl,
    route,
  }, null, 2));
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
