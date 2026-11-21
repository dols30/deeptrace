import type { NextConfig } from 'next';
const config: NextConfig = {
  output: 'standalone',
  trailingSlash: true,
  async redirects() {
    return [
      { source: '/how-it-works', destination: '/', permanent: true },
      { source: '/security', destination: '/', permanent: true },
    ];
  },
};
export default config;
