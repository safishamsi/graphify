const fs = require("fs");
const path = require("path");

const webRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(webRoot, "..", "..");
const rootEnvPath = path.join(repoRoot, ".env");
const webEnvPath = path.join(webRoot, ".env.local");

function parseEnv(content) {
  const entries = new Map();
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const normalized = line.startsWith("export ") ? line.slice(7).trimStart() : line;
    const eq = normalized.indexOf("=");
    if (eq === -1) continue;
    const key = normalized.slice(0, eq).trim();
    let value = normalized.slice(eq + 1).trim();
    if (!key) continue;
    if (
      value.length >= 2 &&
      ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }
    entries.set(key, value);
  }
  return entries;
}

if (!fs.existsSync(rootEnvPath)) {
  console.warn(`[sync-root-env] No root .env found at ${rootEnvPath}; skipping apps/web/.env.local sync.`);
  process.exit(0);
}

const rootEnv = parseEnv(fs.readFileSync(rootEnvPath, "utf8"));
const lines = [
  "# Auto-generated from the repo root .env by apps/web/scripts/sync-root-env.cjs",
  "# Edit the root .env instead of this file.",
];

function setVar(targetKey, sourceKeys, fallback = "") {
  for (const sourceKey of sourceKeys) {
    const value = rootEnv.get(sourceKey);
    if (value) {
      lines.push(`${targetKey}=${value}`);
      return;
    }
  }
  lines.push(`${targetKey}=${fallback}`);
}

setVar("NEXT_PUBLIC_SUPABASE_URL", ["NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_URL"]);
setVar("NEXT_PUBLIC_SUPABASE_ANON_KEY", ["NEXT_PUBLIC_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY"]);
setVar("NEXT_PUBLIC_DEPOS_API_URL", ["NEXT_PUBLIC_DEPOS_API_URL", "DEPOS_API_URL"], "http://127.0.0.1:8080");

fs.mkdirSync(webRoot, { recursive: true });
fs.writeFileSync(webEnvPath, `${lines.join("\n")}\n`, "utf8");
console.log(`[sync-root-env] Wrote ${path.relative(repoRoot, webEnvPath)} from root .env`);
