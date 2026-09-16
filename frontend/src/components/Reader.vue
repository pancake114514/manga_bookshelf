<template>
  <main class="reader" @wheel="onWheel">
    <div class="top">
      <n-button size="small" @click="back">◀ 返回</n-button>
      <span class="obj-title">{{ reader.obj.name }}</span>
      <span class="spacer" />
      <span class="filename">{{ current?.filename }}</span>
      <n-button size="small" @click="toggleFullscreen">⛶ 全屏</n-button>
    </div>

    <div class="reader-stage" @click="onStageClick">
      <img v-if="loadedSrc" :src="loadedSrc" alt="">
      <n-spin v-else size="large" />
    </div>

    <div class="bottom">
      <div ref="barEl" class="progress" @pointerdown="onBarDown" @pointermove="onBarMove" @pointerup="dragging = false">
        <div class="track" />
        <div class="filled" :style="{ width: `${fillPct}%` }" />
        <div class="knob" :style="{ right: `${fillPct}%` }" />
        <div class="page-label">{{ index + 1 }} / {{ reader.images.length }}</div>
      </div>
    </div>
  </main>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { NButton, NSpin } from 'naive-ui'
import { api } from '../api'
import { store } from '../store'

const reader = store.reader
const index = ref(Math.max(0, Math.min(reader.index, reader.images.length - 1)))
const loadedSrc = ref('')
const dragging = ref(false)
const barEl = ref(null)
let saveTimer = null

const current = computed(() => reader.images[index.value])
// 进度条从右向左：index=0 在最右端
const fillPct = computed(() =>
  reader.images.length > 1 ? (index.value / (reader.images.length - 1)) * 100 : 0)

function saveProgress() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    api.lastRead(reader.obj.id, index.value).catch(() => {})
  }, 400)
}

function goTo(i) {
  const n = Math.max(0, Math.min(i, reader.images.length - 1))
  if (n === index.value) return
  index.value = n
  saveProgress()
  preload(n)
}

function next() { if (index.value < reader.images.length - 1) goTo(index.value + 1) }
function prev() { if (index.value > 0) goTo(index.value - 1) }

// 预加载相邻图片
function preload(i) {
  for (const off of [1, -1, 2, -2]) {
    const n = i + off
    if (n >= 0 && n < reader.images.length) {
      const im = new Image()
      im.src = reader.images[n].image_url
    }
  }
}

// 当前页异步解码，避免大图卡顿翻页闪烁
watch(index, () => { loadedSrc.value = '' }, { immediate: false })

const displaySrc = computed(() => current.value?.image_url)
// 用双层 img 简化：直接显示当前 URL，浏览器缓存保证已预加载的图即时呈现
watch(displaySrc, v => { loadedSrc.value = v }, { immediate: true })

function onStageClick(e) {
  const r = e.currentTarget.getBoundingClientRect()
  const x = e.clientX - r.left
  if (x < r.width / 3) next()            // 左 1/3 → 下一页
  else if (x > (2 * r.width) / 3) prev() // 右 1/3 → 上一页
}
function onWheel(e) {
  if (e.deltaY > 0 || e.deltaX > 0) next()
  else prev()
}

function onKey(e) {
  if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') next()
  else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') prev()
  else if (e.key === 'Escape') back()
  else if (e.key === 'F11' || e.key.toLowerCase() === 'f') toggleFullscreen()
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  clearTimeout(saveTimer)
  api.lastRead(reader.obj.id, index.value).catch(() => {})   // 退出前兜底落库
})

function back() {
  clearTimeout(saveTimer)
  api.lastRead(reader.obj.id, index.value).catch(() => {})
  store.view = { name: 'directory' }
}

function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen()
  else document.documentElement.requestFullscreen().catch(() => {})
}

// ── 进度条拖动 ──
function barToIndex(clientX) {
  const r = barEl.value.getBoundingClientRect()
  const pad = 20
  const w = r.width - pad * 2
  if (w <= 0) return 0
  const ratio = Math.max(0, Math.min(1, (r.width - pad - (clientX - r.left)) / w))
  return Math.round(ratio * (reader.images.length - 1))
}
function onBarDown(e) {
  dragging.value = true
  goTo(barToIndex(e.clientX))
}
function onBarMove(e) {
  if (dragging.value) goTo(barToIndex(e.clientX))
}
</script>

<style scoped>
.reader { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.top {
  height: 44px; flex: none;
  display: flex; align-items: center; gap: 12px;
  padding: 0 12px;
  border-bottom: 1px solid var(--border, rgba(128,128,128,.2));
}
.obj-title { font-size: 13px; font-weight: 600; }
.spacer { flex: 1; }
.filename { font-size: 11px; opacity: .55; }

.bottom { height: 56px; flex: none; padding: 4px 24px 8px; }
.progress { position: relative; height: 40px; cursor: pointer; }
.track, .filled, .knob { position: absolute; pointer-events: none; }
.track {
  top: 18px; left: 20px; right: 20px; height: 4px; border-radius: 2px;
  background: rgba(128,128,128,.35);
}
.filled {
  top: 18px; right: 20px; height: 4px; border-radius: 2px;
  background: #6a5c4d;
}
.knob {
  top: 12px; width: 16px; height: 16px; border-radius: 50%;
  transform: translateX(50%);
  background: #f4efe6; border: 2px solid #6a5c4d;
}
.page-label {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  padding-top: 14px;
  font-size: 11px; color: #4a3f35; opacity: .8;
}
</style>
