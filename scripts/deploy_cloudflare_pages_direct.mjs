#!/usr/bin/env node
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const require = createRequire(import.meta.url);

const ROOT_DIR = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const API_BASE = "https://api.cloudflare.com/client/v4";
const MAX_BUCKET_BYTES = 50 * 1024 * 1024;
const MAX_BUCKET_FILES = 5000;

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
    projectName: cleanValue(env.CLOUDFLARE_PAGES_PROJECT) || "maison-flou",
    branch: cleanValue(env.CLOUDFLARE_PAGES_BRANCH) || "master",
    outputDir: path.resolve(ROOT_DIR, cleanValue(env.CLOUDFLARE_PAGES_OUTPUT_DIR) || "sites/maison-flou"),
  };
}

function loadBlake3() {
  try {
    return require("blake3-wasm");
  } catch {}

  const npxDir = path.join(os.homedir(), ".npm", "_npx");
  if (fs.existsSync(npxDir)) {
    for (const entry of fs.readdirSync(npxDir)) {
      const candidate = path.join(npxDir, entry, "node_modules", "blake3-wasm");
      if (!fs.existsSync(candidate)) continue;
      try {
        return require(candidate);
      } catch {}
    }
  }

  throw new Error(
    "Missing blake3-wasm. Cache it with: npm_config_ignore_scripts=true npx -y wrangler@3 --version"
  );
}

function contentTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const types = {
    ".css": "text/css",
    ".html": "text/html",
    ".ico": "image/x-icon",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".js": "application/javascript",
    ".json": "application/json",
    ".map": "application/json",
    ".md": "text/markdown",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
    ".webmanifest": "application/manifest+json",
    ".webp": "image/webp",
    ".xml": "application/xml",
  };
  return types[ext] || "application/octet-stream";
}

function shouldIgnore(relativePath) {
  const parts = relativePath.split(path.sep);
  if (relativePath === "_worker.js" || relativePath === "_headers" || relativePath === "_redirects" || relativePath === "_routes.json") {
    return true;
  }
  if (relativePath.endsWith(`${path.sep}.DS_Store`) || relativePath === ".DS_Store") {
    return true;
  }
  return parts.includes("functions") || parts.includes("node_modules") || parts.includes(".git");
}

function walkFiles(directory) {
  const files = [];
  for (const name of fs.readdirSync(directory)) {
    const absolutePath = path.join(directory, name);
    const stat = fs.statSync(absolutePath);
    if (stat.isSymbolicLink()) continue;
    if (stat.isDirectory()) {
      files.push(...walkFiles(absolutePath));
    } else {
      files.push(absolutePath);
    }
  }
  return files;
}

function buildFileMap(outputDir) {
  const blake3 = loadBlake3();
  const fileMap = new Map();
  for (const absolutePath of walkFiles(outputDir)) {
    const relativePath = path.relative(outputDir, absolutePath);
    if (shouldIgnore(relativePath)) continue;

    const normalizedPath = relativePath.split(path.sep).join("/");
    const bytes = fs.readFileSync(absolutePath);
    const base64 = bytes.toString("base64");
    const extension = path.extname(absolutePath).slice(1);
    const hash = blake3.hash(base64 + extension).toString("hex").slice(0, 32);
    fileMap.set(normalizedPath, {
      path: absolutePath,
      contentType: contentTypeFor(absolutePath),
      hash,
      sizeInBytes: bytes.byteLength,
    });
  }
  return fileMap;
}

async function apiRequest(pathname, { token, method = "GET", headers = {}, body } = {}) {
  const response = await fetch(`${API_BASE}${pathname}`, {
    method,
    headers: {
      ...(body && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
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

function bucketFiles(files) {
  const buckets = [];
  for (const file of [...files].sort((a, b) => b.sizeInBytes - a.sizeInBytes)) {
    let bucket = buckets.find((candidate) => (
      candidate.size + file.sizeInBytes <= MAX_BUCKET_BYTES
      && candidate.files.length < MAX_BUCKET_FILES
    ));
    if (!bucket) {
      bucket = { size: 0, files: [] };
      buckets.push(bucket);
    }
    bucket.files.push(file);
    bucket.size += file.sizeInBytes;
  }
  return buckets;
}

async function uploadAssets({ apiToken, accountId, projectName, fileMap }) {
  const tokenResult = await apiRequest(
    `/accounts/${accountId}/pages/projects/${projectName}/upload-token`,
    { token: apiToken }
  );
  const uploadJwt = tokenResult.jwt;
  if (!uploadJwt) throw new Error("Cloudflare did not return a Pages upload token.");

  const files = [...fileMap.values()];
  const missingHashes = await apiRequest("/pages/assets/check-missing", {
    token: uploadJwt,
    method: "POST",
    body: JSON.stringify({ hashes: files.map((file) => file.hash) }),
  });
  const missing = new Set(missingHashes);
  const filesToUpload = files.filter((file) => missing.has(file.hash));

  for (const bucket of bucketFiles(filesToUpload)) {
    const payload = bucket.files.map((file) => ({
      key: file.hash,
      value: fs.readFileSync(file.path).toString("base64"),
      metadata: { contentType: file.contentType },
      base64: true,
    }));
    await apiRequest("/pages/assets/upload", {
      token: uploadJwt,
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  await apiRequest("/pages/assets/upsert-hashes", {
    token: uploadJwt,
    method: "POST",
    body: JSON.stringify({ hashes: files.map((file) => file.hash) }),
  });

  return {
    manifest: Object.fromEntries([...fileMap.entries()].map(([name, file]) => [`/${name}`, file.hash])),
    uploaded: filesToUpload.length,
    skipped: files.length - filesToUpload.length,
    total: files.length,
  };
}

async function createDeployment({ apiToken, accountId, projectName, branch, outputDir, manifest }) {
  const formData = new FormData();
  formData.append("manifest", JSON.stringify(manifest));
  formData.append("branch", branch);

  for (const specialFile of ["_headers", "_redirects", "_routes.json"]) {
    const specialPath = path.join(outputDir, specialFile);
    if (!fs.existsSync(specialPath)) continue;
    const blob = new Blob([fs.readFileSync(specialPath)], {
      type: contentTypeFor(specialPath),
    });
    formData.append(specialFile, blob, specialFile);
  }

  return apiRequest(`/accounts/${accountId}/pages/projects/${projectName}/deployments`, {
    token: apiToken,
    method: "POST",
    body: formData,
  });
}

async function main() {
  const config = loadConfig();
  for (const [name, value] of Object.entries({
    CLOUDFLARE_API_TOKEN: config.apiToken,
    CLOUDFLARE_ACCOUNT_ID: config.accountId,
    CLOUDFLARE_PAGES_PROJECT: config.projectName,
    CLOUDFLARE_PAGES_OUTPUT_DIR: config.outputDir,
  })) {
    if (!value) throw new Error(`${name} is required.`);
  }
  if (!fs.existsSync(config.outputDir)) throw new Error(`Output directory does not exist: ${config.outputDir}`);

  await apiRequest(`/accounts/${config.accountId}/pages/projects/${config.projectName}`, {
    token: config.apiToken,
  });

  const fileMap = buildFileMap(config.outputDir);
  const uploadResult = await uploadAssets({
    apiToken: config.apiToken,
    accountId: config.accountId,
    projectName: config.projectName,
    fileMap,
  });
  const deployment = await createDeployment({
    apiToken: config.apiToken,
    accountId: config.accountId,
    projectName: config.projectName,
    branch: config.branch,
    outputDir: config.outputDir,
    manifest: uploadResult.manifest,
  });

  const summary = {
    project: config.projectName,
    branch: config.branch,
    files: uploadResult,
    deployment_id: deployment.id,
    url: deployment.url,
    aliases: deployment.aliases || [],
    environment: deployment.environment,
    latest_stage: deployment.latest_stage,
  };
  console.log(JSON.stringify(summary, null, 2));
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
