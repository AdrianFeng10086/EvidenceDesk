/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    // PDF.js worker 配置
    config.resolve.alias.canvas = false;
    return config;
  },
};

export default nextConfig;
