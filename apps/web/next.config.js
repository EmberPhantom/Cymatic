/** @type {import('next').NextConfig} */
const path = require('path');

const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  // Turbopack monorepo root fix — silences "Next.js inferred your workspace root" warning.
  // apps/web has its own package-lock.json; root is P:\Cymatic (two levels up).
  // Next 16 uses `turbopack.root`; `experimental.turbo.root` is deprecated but equivalent for <16.
  turbopack: {
    root: path.join(__dirname, '../..'),
  },
  experimental: {
    // Tree-shake barrel imports: lucide-react (~300 icons), zod.
    // Turbopack + Webpack both honor this; avoids pulling entire packages when only a few exports are used.
    optimizePackageImports: ['lucide-react', 'zod'],
  },
  // Webpack-only fallback for lucide-react icon tree-shaking (Turbopack ignores modularizeImports
  // and relies on optimizePackageImports above). Keep for `next build --no-turbopack` compat.
  modularizeImports: {
    'lucide-react': {
      transform: 'lucide-react/dist/esm/icons/{{kebabCase member}}',
    },
  },
  compiler: {
    // Strip console.* in production builds; preserve error/warn if you prefer:
    // removeConsole: { exclude: ['error', 'warn'] }
    removeConsole: process.env.NODE_ENV === 'production',
  },
  // transpilePackages: [], // no CJS deps needing transpilation currently; add here if needed (e.g., legacy UI libs)
  images: {
    remotePatterns: (() => {
      try {
        const url = new URL(process.env.NEXT_PUBLIC_MINIO_URL || 'http://localhost:9000');
        return [{ protocol: url.protocol.replace(':',''), hostname: url.hostname, port: url.port || (url.protocol === 'https:' ? '443' : '80'), pathname: '/**' }];
      } catch {
        return [{ protocol: 'http', hostname: 'localhost', port: '9000', pathname: '/**' }];
      }
    })(),
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
  async rewrites() {
    const apiBase = process.env.API_INTERNAL_URL
      || (process.env.NODE_ENV === 'production' ? 'http://api:8000' : process.env.NEXT_PUBLIC_API_URL)
      || 'http://localhost:8000';
    return [
      {
        source: '/v1/:path*',
        destination: `${apiBase}/v1/:path*`,
      },
      {
        source: '/api/:path*',
        destination: `${apiBase}/:path*`,
      },
    ];
  },
};

// Bundle analyzer (on-demand, zero prod overhead):
// 1) npm i -D @next/bundle-analyzer
// 2) ANALYZE=true npm run build  # opens HTML reports in .next/analyze/
// Uncomment wrapper below to enable:
// const withBundleAnalyzer = require('@next/bundle-analyzer')({
//   enabled: process.env.ANALYZE === 'true',
// });
// module.exports = withBundleAnalyzer(nextConfig);

// Sharp: not required — no `next/image` usage in src (images.remotePatterns is for MinIO URLs only).
// Next will use its default image optimizer; if you add `next/image` with local transforms,
// `npm i sharp` (already transient via next@16.3.4) will be used automatically.

module.exports = nextConfig;
