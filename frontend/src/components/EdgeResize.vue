<template>
  <!-- 无边框窗口的边缘缩放热区（仅桌面模式渲染）；WebView2 覆盖客户区导致
       Win32 边缘命中不可达，缩放由热区拖动经桥接驱动，z-index 高于全部内容 -->
  <template v-if="ready">
    <div v-for="e in EDGES" :key="e" :class="['edge', `edge-${e}`]"
         @mousedown.prevent="begin($event, e)" />
  </template>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { bridge } from '../api'

// pywebview 注入 js_api 有延迟，轮询探测；浏览器调试模式 5s 后放弃（不渲染热区）
const ready = ref(false)
let timer = null
let giveUp = null
let dragging = null

const EDGES = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

// pywebview API 调用并发派发不保序，用串行队列保证 begin/move/end 严格按序
let resizeQueue = Promise.resolve()
const enqueue = (fn) => {
  resizeQueue = resizeQueue.then(fn).catch(() => {})
}

function begin(ev, dir) {
  dragging = dir
  const x = ev.screenX
  const y = ev.screenY
  enqueue(() => bridge.winBeginResize(dir, x, y))
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}
function onMove(ev) {
  if (dragging) {
    const x = ev.screenX
    const y = ev.screenY
    enqueue(() => bridge.winResizeMove(x, y))
  }
}
function onUp() {
  dragging = null
  enqueue(() => bridge.winEndResize())
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
}

onMounted(() => {
  timer = setInterval(() => {
    if (bridge.available()) { ready.value = true; clearInterval(timer) }
  }, 300)
  giveUp = setTimeout(() => clearInterval(timer), 15000)
})
onUnmounted(() => { clearInterval(timer); clearTimeout(giveUp); onUp() })
</script>

<style scoped>
.edge { position: fixed; z-index: 9999; }
.edge-n { top: 0; left: 16px; right: 16px; height: 8px; cursor: ns-resize; }
.edge-s { bottom: 0; left: 16px; right: 16px; height: 8px; cursor: ns-resize; }
.edge-e { right: 0; top: 16px; bottom: 16px; width: 8px; cursor: ew-resize; }
.edge-w { left: 0; top: 16px; bottom: 16px; width: 8px; cursor: ew-resize; }
.edge-ne { top: 0; right: 0; width: 20px; height: 20px; cursor: nesw-resize; }
.edge-nw { top: 0; left: 0; width: 20px; height: 20px; cursor: nwse-resize; }
.edge-se { bottom: 0; right: 0; width: 20px; height: 20px; cursor: nwse-resize; }
.edge-sw { bottom: 0; left: 0; width: 20px; height: 20px; cursor: nesw-resize; }
</style>
