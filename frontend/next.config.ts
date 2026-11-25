import type { NextConfig } from 'next';
const config: NextConfig = {
  output: 'standalone',
  trailingSlash: true,
  // Tests import backend fixtures that are outside the Docker build context;
  // `npm run typecheck` still covers them locally.
  typescript: { tsconfigPath: 'tsconfig.build.json' },
  async redirects() {
    return [
      { source: '/how-it-works', destination: '/', permanent: true },
      { source: '/security', destination: '/', permanent: true },
    ];
  },
};
export default config;
