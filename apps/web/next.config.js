/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  images: {
    domains: ['localhost'],
    remotePatterns: [
      {
        protocol: 'http',
        hostname: 'localhost',
        port: '9000',
        pathname: '/cymatic/**',
      },
    ],
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

module.exports = nextConfig;
