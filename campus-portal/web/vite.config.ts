import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  // 相对路径：内网常部署在 /portal/ 这类子路径下，构建产物也能直接本地双击打开
  base: './',
  // 显式绑 IPv4，避免 Vite 默认只监听 [::1] 导致 127.0.0.1 访问失败
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // 当前沙箱环境禁止删除文件，构建前不清空输出目录；生产 CI 可改回 true
    emptyOutDir: false,
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
