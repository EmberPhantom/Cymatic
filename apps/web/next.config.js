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
    return [
      {
        source: '/dashboard/projects/:path*',
        destination: '/projects/:path*',
      },
      {
        source: '/api/:path*',
        destination: `${process.env.API_INTERNAL_URL || (process.env.NODE_ENV === 'production' ? 'http://api:8000' : process.env.NEXT_PUBLIC_API_URL) || 'http://localhost:8000'}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
