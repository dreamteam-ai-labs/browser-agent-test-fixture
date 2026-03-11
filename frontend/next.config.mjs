import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const isDev = process.env.NODE_ENV !== 'production';

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export only for production build; dev server needs rewrites for API proxy
  ...(isDev ? {} : { output: 'export' }),
  trailingSlash: true,
  images: { unoptimized: true },
  webpack(config) {
    config.resolve.alias['@'] = path.join(__dirname, 'src');
    return config;
  },
  // Proxy /api/* to backend in dev mode so relative API calls work
  ...(isDev ? {
    async rewrites() {
      return [
        {
          source: '/api/:path*',
          destination: 'http://localhost:8000/api/:path*',
        },
      ];
    },
  } : {}),
};

export default nextConfig;
