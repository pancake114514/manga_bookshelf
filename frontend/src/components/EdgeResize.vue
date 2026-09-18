<template>
  <!-- 无边框窗口的边缘缩放热区（仅桌面模式渲染）。
       按下即调用 Tauri 原生缩放循环，由 OS 驱动
       （DPI、最小尺寸、平滑度与系统边框行为一致，避免 JS 手算坐标的竞态）。 -->
  <template v-if="ready">
    <div v-for="e in EDGES" :key="e" :class="['edge', `edge-${e}`]"
         @mousedown.prevent="begin(e)" />
  </template>
</template>

<script setup>
import { ref } from 'vue'
import { getCurrentWindow } from '@tauri-apps/api/window'

const ready = ref(true) // Tauri 模式下始终可用

const EDGES = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']
const DIRECTIONS = {
  n: 'North', s: 'South', e: 'East', w: 'West',
  ne: 'NorthEast', nw: 'NorthWest', se: 'SouthEast', sw: 'SouthWest',
}

function begin(dir) {
  getCurrentWindow().startResizeDragging(DIRECTIONS[dir])
}
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
