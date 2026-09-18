<template>
  <!-- 无边框窗口的最小化/最大化/关闭按钮（桌面模式；高度随父容器拉伸） -->
  <div class="win-controls" @mousedown.stop @dblclick.stop>
    <button class="wc-btn" title="最小化" @click="win.minimize()">
      <IconMinus :size="15" />
    </button>
    <button class="wc-btn" :title="maximized ? '还原' : '最大化'" @click="toggleMax">
      <IconWinRestore v-if="maximized" :size="14" />
      <IconWinMax v-else :size="13" />
    </button>
    <button class="wc-btn wc-close" title="关闭" @click="win.close()">
      <IconX :size="15" />
    </button>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { win } from '../api'
import { maximized, syncMaximized } from '../windowState'
import { IconMinus, IconWinMax, IconWinRestore, IconX } from './icons'

// maximized 为共享状态（windowState）
async function toggleMax() {
  maximized.value = await win.toggleMaximize()
}
onMounted(() => syncMaximized())
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
