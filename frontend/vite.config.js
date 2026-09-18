import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',
  // Tauri dev 模式不需要 proxy（IPC 直通），生产模式不在 vite 下运行
  server: {
    port: 5173,
    strictPort: true,
  },
  // 构建：不内联大资源（Tauri 打包优化）
  build: {
    target: 'es2021',
    chunkSizeWarningLimit: 1500,
  },
})
