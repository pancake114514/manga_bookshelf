<template>
  <main class="reader" :class="{ idle: !chromeVisible }" @wheel="onWheel" @mousemove="pokeChrome">
    <div class="top">
      <n-button size="small" @click="back"><IconBack :size="14" /> 返回</n-button>
      <span class="obj-title">{{ reader.obj.name }}</span>
      <span class="spacer" />
      <span class="filename">{{ pageLabelFilename }}</span>
      <n-button-group size="small">
        <n-button :type="zoom === 'fit' ? 'primary' : 'default'" :secondary="zoom !== 'fit'" @click="setZoom('fit')">适应页面</n-button>
        <n-button :type="zoom === 'width' ? 'primary' : 'default'" :secondary="zoom !== 'width'" @click="setZoom('width')">适应宽度</n-button>
        <n-button :type="zoom === 'original' ? 'primary' : 'default'" :secondary="zoom !== 'original'" @click="setZoom('original')">原始</n-button>
      </n-button-group>
      <n-button size="small" :type="double ? 'primary' : 'default'" :secondary="!double"
                :title="double ? '退出双页对开' : '双页对开（快捷键 D）'" @click="toggleDouble">
        <IconDoublePage :size="14" /> 双页
      </n-button>
      <n-button size="small" @click="toggleFullscreen"><IconMaximize :size="13" /> 全屏</n-button>
    </div>

    <div class="reader-stage" :class="[`zoom-${zoom}`]" @click="onStageClick">
      <template v-if="double">
        <div class="spread">
          <img v-if="spreadLeft" :src="spreadLeft" alt="">
          <img v-if="spreadRight" :src="spreadRight" alt="">
        </div>
        <n-spin v-if="!spreadRight" size="large" class="spread-spin" />
      </template>
      <template v-else>
        <img v-if="loadedSrc" :src="loadedSrc" alt="">
        <n-spin v-else size="large" class="stage-spin" />
      </template>
    </div>

    <div class="bottom">
      <div ref="barEl" class="progress" @pointerdown="onBarDown" @pointermove="onBarMove" @pointerup="dragging = false">
        <div class="track" />
        <div class="filled" :style="{ width: `${fillPct}%` }" />
        <div class="knob" :style="{ right: `${fillPct}%` }" />
        <div class="page-label">{{ label }}</div>
      </div>
    </div>
  </main>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { NButton, NButtonGroup, NSpin } from 'naive-ui'
import { api } from '../api'
import { store } from '../store'
import { IconBack, IconMaximize, IconDoublePage } from './icons'

const ZOOMS = ['fit', 'width', 'original']
const CFG_DOUBLE = 'ui_reader_double'
const CFG_ZOOM = 'ui_reader_zoom'

const reader = store.reader
const index = ref(Math.max(0, Math.min(reader.index, reader.images.length - 1)))
const loadedSrc = ref('')
const dragging = ref(false)
const barEl = ref(null)
const double = ref(false)
const zoom = ref('fit')
const chromeVisible = ref(true)
let saveTimer = null
let hideTimer = null

const total = reader.images.length
const current = computed(() => reader.images[index.value])
// 进度条从右向左：index=0 在最右端
const fillPct = computed(() => (total > 1 ? (index.value / (total - 1)) * 100 : 0))
const label = computed(() =>
  double.value && index.value + 1 < total
    ? `${index.value + 1}-${index.value + 2} / ${total}`
    : `${index.value + 1} / ${total}`)
const pageLabelFilename = computed(() =>
  double.value
    ? [current.value?.filename, reader.images[index.value + 1]?.filename].filter(Boolean).join(' · ')
    : current.value?.filename)

// 双页对开：右页在前（日漫右开本），展开为 [index+1 左, index 右]
const spreadRight = computed(() => current.value?.image_url || '')
const spreadLeft = computed(() => (double.value ? reader.images[index.value + 1]?.image_url : ''))

function align(i) {
  const n = Math.max(0, Math.min(i, total - 1))
  return double.value ? n - (n % 2) : n
}

function saveProgress() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    api.lastRead(reader.obj.id, index.value).catch(() => {})
  }, 400)
}

function goTo(i) {
  const n = align(i)
  if (n === index.value) return
  index.value = n
  saveProgress()
  preload(n)
}

function next() { goTo(index.value + (double.value ? 2 : 1)) }
function prev() { goTo(index.value - (double.value ? 2 : 1)) }

// 预加载相邻图片（前后各 3 张）
function preload(i) {
  for (const off of [1, -1, 2, -2, 3, -3]) {
    const n = i + off
    if (n >= 0 && n < total) {
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

// 切换双页时对齐到偶数页
watch(double, () => { index.value = align(index.value) })

function toggleDouble() { setDouble(!double.value) }
function setDouble(v) {
  double.value = v
  api.setConfig(CFG_DOUBLE, v ? '1' : '0').catch(() => {})
}
function setZoom(z) {
  if (!ZOOMS.includes(z)) return
  zoom.value = z
  api.setConfig(CFG_ZOOM, z).catch(() => {})
}

// 工具栏自动隐藏：鼠标静止 2.2s 后淡出
function pokeChrome() {
  chromeVisible.value = true
  clearTimeout(hideTimer)
  hideTimer = setTimeout(() => { chromeVisible.value = false }, 2200)
}

function onStageClick(e) {
  const r = e.currentTarget.getBoundingClientRect()
  const x = e.clientX - r.left
  if (x < r.width / 3) next()            // 左 1/3 → 下一页
  else if (x > (2 * r.width) / 3) prev() // 右 1/3 → 上一页
}
function onWheel(e) {
  if (zoom.value !== 'fit') return       // 滚动模式下滚轮用于滚动页面
  if (e.deltaY > 0 || e.deltaX > 0) next()
  else prev()
}

function onKey(e) {
  if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') next()
  else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') prev()
  else if (e.key === 'Escape') back()
  else if (e.key === 'F11' || e.key.toLowerCase() === 'f') toggleFullscreen()
  else if (e.key.toLowerCase() === 'd') toggleDouble()
}
onMounted(() => {
  window.addEventListener('keydown', onKey)
  pokeChrome()
  // 恢复阅读器偏好
  api.getConfig(CFG_DOUBLE).then(r => { if (r.value === '1') double.value = true }).catch(() => {})
  api.getConfig(CFG_ZOOM).then(r => { if (ZOOMS.includes(r.value)) zoom.value = r.value }).catch(() => {})
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  clearTimeout(saveTimer)
  clearTimeout(hideTimer)
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
  return Math.round(ratio * (total - 1))
}
function onBarDown(e) {
  dragging.value = true
  pokeChrome()
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
  display: flex; align-items: center; gap: 10px;
  padding: 0 12px;
  border-bottom: 1px solid var(--border);
  transition: opacity .3s;
}
.obj-title { font-size: 13px; font-weight: 600; }
.spacer { flex: 1; }
.filename { font-size: 11px; opacity: .55; }

/* 工具栏自动隐藏 */
.reader.idle .top,
.reader.idle .bottom { opacity: 0; pointer-events: none; }

.reader-stage {
  flex: 1; min-height: 0;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; position: relative;
  overflow: hidden;
}
.reader-stage img {
  max-width: 100%; max-height: 100%;
  object-fit: contain;
  user-select: none; -webkit-user-drag: none;
}
.stage-spin, .spread-spin { position: absolute; }

/* 适应宽度：纵向滚动 */
.reader-stage.zoom-width { flex-direction: column; align-items: center; overflow-y: auto; }
.reader-stage.zoom-width img { width: 100%; height: auto; max-height: none; }
/* 原始尺寸：自由滚动 */
.reader-stage.zoom-original { overflow: auto; }
.reader-stage.zoom-original img { max-width: none; max-height: none; }

/* 双页对开 */
.spread {
  display: flex; align-items: center; justify-content: center;
  width: 100%; height: 100%; gap: 2px;
}
.spread img { max-width: calc(50% - 1px); max-height: 100%; object-fit: contain; }
.zoom-width .spread { flex: none; width: 100%; }
.zoom-width .spread img { width: calc(50% - 1px); height: auto; max-height: none; }
.zoom-original .spread { width: max-content; }
.zoom-original .spread img { max-width: none; max-height: none; }

.bottom { height: 56px; flex: none; padding: 4px 24px 8px; transition: opacity .3s; }
.progress { position: relative; height: 40px; cursor: pointer; }
.track, .filled, .knob { position: absolute; pointer-events: none; }
.track {
  top: 18px; left: 20px; right: 20px; height: 4px; border-radius: 2px;
  background: rgba(128,128,128,.35);
}
.filled {
  top: 18px; right: 20px; height: 4px; border-radius: 2px;
  background: var(--ms-primary);
}
.knob {
  top: 12px; width: 16px; height: 16px; border-radius: 50%;
  transform: translateX(50%);
  background: var(--card); border: 2px solid var(--ms-primary);
}
.page-label {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  padding-top: 14px;
  font-size: 11px; color: var(--text2); opacity: .8;
}
</style>
