const path = require("path");
const { loadEnvConfig } = require("@next/env");

const repoRoot = path.resolve(__dirname, "..", "..");
loadEnvConfig(repoRoot);

const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_SUPABASE_URL:
      process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || "",
    NEXT_PUBLIC_SUPABASE_ANON_KEY:
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY || "",
    NEXT_PUBLIC_DEPOS_API_URL:
      process.env.NEXT_PUBLIC_DEPOS_API_URL || process.env.DEPOS_API_URL || "http://127.0.0.1:8080",
  },
  async redirects() {
    return [
      { source: "/repos", destination: "/orgs", permanent: false },
      { source: "/repos/:path*", destination: "/orgs", permanent: false },
      { source: "/ci", destination: "/orgs", permanent: false },
      { source: "/ci/:path*", destination: "/orgs", permanent: false },
    ];
  },
};

module.exports = nextConfig;
