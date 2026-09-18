import { ref } from 'vue'
import { win } from './api'

// 最大化状态共享
export const maximized = ref(false)

export async function syncMaximized() {
  maximized.value = await win.isMaximized()
}

// 顶栏按下：Tauri 原生 startDragging 替代 pywebview 三段式手动拖动。
// 双击切换最大化由原生处理（Tauri 窗口管理器支持）。
let lastDown = 0

export async function barMouseDown(ev) {
  if (ev.button !== 0) return
  const now = Date.now()
  const isDbl = now - lastDown < 450
  lastDown = now

  if (isDbl) {
    maximized.value = await win.toggleMaximize()
    return
  }

  // Tauri startDragging 接管拖动，系统原生 Snap Assist 自动生效
  await win.startDrag()
  // 拖动结束后同步最大化状态（可能通过贴靠改变）
  setTimeout(syncMaximized, 100)
}
