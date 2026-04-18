/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
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
