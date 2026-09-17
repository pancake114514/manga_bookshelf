<template>
  <!-- 无边框窗口的最小化/最大化/关闭按钮（桌面模式；高度随父容器拉伸） -->
  <div class="win-controls" @mousedown.stop @dblclick.stop>
    <button class="wc-btn" title="最小化" @click="bridge.winMinimize()">
      <IconMinus :size="15" />
    </button>
    <button class="wc-btn" :title="maximized ? '还原' : '最大化'" @click="toggleMax">
      <IconWinRestore v-if="maximized" :size="14" />
      <IconWinMax v-else :size="13" />
    </button>
    <button class="wc-btn wc-close" title="关闭" @click="bridge.winClose()">
      <IconX :size="15" />
    </button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { bridge } from '../api'
import { IconMinus, IconWinMax, IconWinRestore, IconX } from './icons'

// 无边框窗口无原生最大化状态可查，由按钮点击路径自行跟踪
const maximized = ref(false)

async function toggleMax() {
  maximized.value = await bridge.winToggleMaximize()
}
</script>

<style scoped>
.win-controls { display: flex; align-items: stretch; flex: none; }
.wc-btn {
  width: 46px; border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  background: transparent; color: var(--text);
  transition: background .15s, color .15s;
}
.wc-btn:hover { background: var(--chip-bg); }
.wc-close:hover { background: #e81123; color: #fff; }
</style>
