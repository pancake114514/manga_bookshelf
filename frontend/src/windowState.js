import { ref } from 'vue'
import { bridge } from './api'

// 最大化状态共享：原生拖动还原/贴靠后按钮图标由轮询同步，避免陈旧
export const maximized = ref(false)

export async function syncMaximized() {
  maximized.value = await bridge.winIsMaximized()
}

// 顶栏按下：经桥接三段式移动拖拽（begin → move → end 含边缘贴靠判定）。
// pywebview 的 API 调用是并发派发的，用串行队列保证 begin/move/end 严格按序；
// 未移动即松开且为双击，则切换最大化
let lastDown = 0
let dragQueue = Promise.resolve()

export function barMouseDown(ev) {
  if (ev.button !== 0) return
  const now = Date.now()
  const isDbl = now - lastDown < 450
  lastDown = now
  const sx = ev.screenX
  const sy = ev.screenY
  let moved = false
  let aborted = false

  const enqueue = (fn) => {
    dragQueue = dragQueue.then(fn).catch(() => {})
  }
  const onMove = (e) => {
    if (aborted) return
    moved = true
    const x = e.screenX
    const y = e.screenY
    enqueue(() => bridge.winMoveDragTo(x, y))
  }
  const onUp = (e) => {
    cleanup()
    const x = e.screenX
    const y = e.screenY
    // 无论是否移动都结束拖动（后端清 _mv）；未移动而未清会让拖动状态泄漏，
    // 之后所有最大化切换都会被「拖动中」守卫拒绝。双击切换在 end 之后执行
    if (!aborted) {
      enqueue(() => bridge.winEndMoveDrag(x, y, moved).then(() => {
        if (!moved && isDbl) {
          return bridge.winToggleMaximize().then(v => { maximized.value = !!v })
        }
        return syncMaximized()
      }))
    }
    scheduleSync()
  }
  const cleanup = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
  enqueue(() => bridge.winBeginMoveDrag(sx, sy).then((ok) => {
    if (!ok) aborted = true   // 全屏等场景不支持拖动
  }))
}

function scheduleSync() {
  for (const ms of [400, 1200, 2600]) setTimeout(syncMaximized, ms)
}
