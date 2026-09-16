<template>
  <div v-if="bridgeReady" class="titlebar pywebview-drag-region">
    <div class="tb-controls" @mousedown.stop @dblclick.stop>
      <button class="tb-btn" title="最小化" @click="bridge.winMinimize()">
        <IconMinus :size="15" />
      </button>
      <button class="tb-btn" :title="maximized ? '还原' : '最大化'" @click="toggleMax">
        <IconWinRestore v-if="maximized" :size="14" />
        <IconWinMax v-else :size="13" />
      </button>
      <button class="tb-btn tb-close" title="关闭" @click="bridge.winClose()">
        <IconX :size="15" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { bridge } from '../api'
import { IconMinus, IconWinMax, IconWinRestore, IconX } from './icons'

// pywebview 注入 js_api 有延迟，轮询探测；浏览器调试模式 5s 后放弃（不渲染标题栏）
const bridgeReady = ref(false)
const maximized = ref(false)
let timer = null
let giveUp = null

onMounted(() => {
  timer = setInterval(() => {
    if (bridge.available()) { bridgeReady.value = true; clearInterval(timer) }
  }, 300)
  giveUp = setTimeout(() => clearInterval(timer), 5000)
})
onUnmounted(() => { clearInterval(timer); clearTimeout(giveUp) })

async function toggleMax() {
  maximized.value = await bridge.winToggleMaximize()
}
</script>

<style scoped>
.titlebar {
  height: 38px; flex: none;
  display: flex; align-items: stretch; justify-content: flex-end;
  background: var(--bg);
  user-select: none;
}
.tb-controls { display: flex; align-items: stretch; }
.tb-btn {
  width: 46px; border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  background: transparent; color: var(--text);
  transition: background .15s, color .15s;
}
.tb-btn:hover { background: var(--chip-bg); }
.tb-close:hover { background: #e81123; color: #fff; }
</style>
