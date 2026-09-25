import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',
  // Tauri dev 模式不需要 proxy（IPC 直通），生产模式不在 vite 下运行
  server: {
    // dev.mjs 随机端口经 MANGASHELF_DEV_PORT 注入；直接 tauri dev 时回退 5173
    // strictPort 必须为 true：端口被占时立即失败，避免 vite 自行换端口后与
    // tauri.conf.json 的 devUrl 不一致导致窗口加载到错误地址
    port: Number(process.env.MANGASHELF_DEV_PORT) || 5173,
    strictPort: true,
  },
  // 构建：不内联大资源（Tauri 打包优化）
  build: {
    target: 'es2021',
    chunkSizeWarningLimit: 1500,
  },
})
