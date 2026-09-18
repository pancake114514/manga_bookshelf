<template>
  <!-- 无边框窗口的边缘缩放热区（仅桌面模式渲染）。
       Tauri decorations:false 下 Win32 原生边缘缩放不可达，
       由热区拖动经 Tauri set_size/set_position 驱动。 -->
  <template v-if="ready">
    <div v-for="e in EDGES" :key="e" :class="['edge', `edge-${e}`]"
         @mousedown.prevent="begin($event, e)" />
  </template>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { getCurrentWindow, LogicalPosition, LogicalSize } from '@tauri-apps/api/window'

const ready = ref(true) // Tauri 模式下始终可用
let dragging = null
let startPos = null
let startRect = null

const EDGES = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

async function begin(ev, dir) {
  dragging = dir
  const win = getCurrentWindow()
  startPos = { x: ev.screenX, y: ev.screenY }
  startRect = {
    x: (await win.outerPosition()).x,
    y: (await win.outerPosition()).y,
    w: (await win.outerSize()).width,
    h: (await win.outerSize()).height,
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

async function onMove(ev) {
  if (!dragging || !startPos || !startRect) return
  const win = getCurrentWindow()
  const dx = ev.screenX - startPos.x
  const dy = ev.screenY - startPos.y
  let { x, y, w, h } = startRect

  if (dragging.includes('e')) w += dx
  if (dragging.includes('w')) { x += dx; w -= dx }
  if (dragging.includes('s')) h += dy
  if (dragging.includes('n')) { y += dy; h -= dy }

  const MIN_W = 1000, MIN_H = 680
  if (w < MIN_W) {
    if (dragging.includes('w')) x -= (MIN_W - w)
    w = MIN_W
  }
  if (h < MIN_H) {
    if (dragging.includes('n')) y -= (MIN_H - h)
    h = MIN_H
  }

  await win.setPosition(new LogicalPosition(x, y))
  await win.setSize(new LogicalSize(w, h))
}

function onUp() {
  dragging = null
  startPos = null
  startRect = null
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
}

onUnmounted(() => onUp())
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
