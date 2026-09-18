<template>
  <!-- 独立窗口按钮条：仅无顶栏工具行的视图渲染（首启向导/启动异常，见 App.vue） -->
  <div v-if="bridgeReady" class="titlebar" @mousedown="barMouseDown">
    <WindowControls />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { bridge } from '../api'
import { barMouseDown } from '../windowState'
import WindowControls from './WindowControls.vue'

// pywebview 注入 js_api 有延迟，轮询探测；浏览器调试模式 5s 后放弃（不渲染标题栏）
const bridgeReady = ref(false)
let timer = null
let giveUp = null

onMounted(() => {
  timer = setInterval(() => {
    if (bridge.available()) { bridgeReady.value = true; clearInterval(timer) }
  }, 300)
  giveUp = setTimeout(() => clearInterval(timer), 5000)
})
onUnmounted(() => { clearInterval(timer); clearTimeout(giveUp) })
</script>

<style scoped>
.titlebar {
  height: 38px; flex: none;
  display: flex; align-items: stretch; justify-content: flex-end;
  background: var(--bg);
  user-select: none;
}
</style>
