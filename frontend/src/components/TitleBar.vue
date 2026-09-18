<template>
  <!-- 独立窗口按钮条：仅无顶栏工具行的视图渲染（首启向导/启动异常，见 App.vue）
       Tauri 模式下始终可用，无需轮询探测 -->
  <div class="titlebar" @mousedown="barMouseDown">
    <WindowControls />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { barMouseDown } from '../windowState'
import { syncMaximized } from '../windowState'
import WindowControls from './WindowControls.vue'

onMounted(() => syncMaximized())
</script>

<style scoped>
.titlebar {
  height: 38px; flex: none;
  display: flex; align-items: stretch; justify-content: flex-end;
  background: var(--bg);
  user-select: none;
}
</style>
