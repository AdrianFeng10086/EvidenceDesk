/**
 * PostCSS 配置。
 *
 * Next.js 只有在存在 PostCSS 配置时才会调用 Tailwind 处理
 * `@tailwind` / `@apply` 指令。缺少此文件时 globals.css 会被原样输出，
 * Tailwind 工具类不会生成，页面表现为“样式不生效”。
 */
/** @type {import('postcss-load-config').Config} */
const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};

export default config;
