#!/usr/bin/env node
// 开发模式随机端口启动器
//
// 用法（项目根目录）：node dev.mjs
//
// 在 20000-60000 间探测一个空闲端口，同时注入两侧保证一致：
//   - 环境变量 MANGASHELF_DEV_PORT → vite.config.js 的 server.port
//   - tauri dev --config 覆盖       → build.devUrl
// 避免残留 vite 进程占用 5173 导致 "Port already in use" 启动失败。
// 直接运行 ./frontend/node_modules/.bin/tauri dev 仍回退默认 5173，行为不变。

import net from 'node:net'
import { spawn } from 'node:child_process'
import { randomInt } from 'node:crypto'
import { writeFile, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

const MIN_PORT = 20000
const MAX_PORT = 60000

/** 探测端口是否可绑定（在 127.0.0.1 上模拟 vite 的监听） */
function tryBind(port) {
  return new Promise((resolve) => {
    const srv = net.createServer()
    srv.once('error', () => resolve(false))
    srv.once('listening', () => srv.close(() => resolve(true)))
    srv.listen(port, '127.0.0.1')
  })
}

/** 随机挑选空闲端口；该区间被占满属极端情况，最多尝试 50 次 */
async function pickPort() {
  for (let i = 0; i < 50; i++) {
    const p = randomInt(MIN_PORT, MAX_PORT)
    if (await tryBind(p)) return p
  }
  throw new Error(`在 ${MIN_PORT}-${MAX_PORT} 间找不到空闲端口`)
}

const port = await pickPort()
console.log(`[dev] 本次使用随机端口: ${port}`)

const isWin = process.platform === 'win32'
const tauriBin = isWin
  ? 'frontend\\node_modules\\.bin\\tauri.cmd'
  : './frontend/node_modules/.bin/tauri'

// 配置覆盖写临时文件而非命令行内联 JSON：Windows 下 .cmd 须经 shell 启动，
// 内联 JSON 的双引号会被 cmd 剥掉导致解析失败；文件路径无此问题
const cfgPath = path.join(os.tmpdir(), `mangashelf-tauri-dev-${port}.json`)
await writeFile(
  cfgPath,
  JSON.stringify({ build: { devUrl: `http://localhost:${port}` } }),
)

const child = spawn(tauriBin, ['dev', '--config', cfgPath], {
  stdio: 'inherit',
  env: { ...process.env, MANGASHELF_DEV_PORT: String(port) },
  shell: isWin, // Windows 下 .cmd 必须经 shell 启动
})
child.on('error', (e) => {
  console.error(`[dev] 启动 tauri 失败: ${e.message}`)
  process.exit(1)
})
child.on('exit', (code) => {
  rm(cfgPath, { force: true }).finally(() => process.exit(code ?? 0))
})
