<template>
  <main class="reader" :class="{ idle: !chromeVisible }" @wheel="onWheel" @mousemove="pokeChrome">
    <!-- 顶栏与主界面等高，整条均可拖动（系统原生拖动），交互控件以 mousedown.stop 排除 -->
    <div class="top" @mousedown="barMouseDown">
      <!-- 左区：返回 + 对象名 -->
      <div class="left">
        <n-button size="small" @mousedown.stop @click="back"><IconBack :size="14" /> 返回</n-button>
        <span class="obj-title">{{ reader.obj.name }}</span>
      </div>
      <!-- 中区：缩放/方向/双页/全屏，随左右等宽区天然居中 -->
      <div class="center">
        <n-button-group size="small" @mousedown.stop>
          <n-button :type="zoom === 'fit' ? 'primary' : 'default'" :secondary="zoom !== 'fit'" @click="setZoom('fit')">适应页面</n-button>
          <n-button :type="zoom === 'width' ? 'primary' : 'default'" :secondary="zoom !== 'width'" @click="setZoom('width')">适应宽度</n-button>
          <n-button :type="zoom === 'original' ? 'primary' : 'default'" :secondary="zoom !== 'original'" @click="setZoom('original')">原始</n-button>
        </n-button-group>
        <n-button size="small" @mousedown.stop :type="rtl ? 'primary' : 'default'" :secondary="!rtl"
                  :title="rtl ? '阅读方向：右→左（日漫）' : '阅读方向：左→右'"
                  @click="toggleDir">{{ rtl ? '右→左' : '左→右' }}</n-button>
        <n-button size="small" @mousedown.stop :type="double ? 'primary' : 'default'" :secondary="!double"
                  :title="double ? '退出双页对开' : '双页对开（快捷键 D）'" @click="toggleDouble">
          <IconDoublePage :size="14" /> 双页
        </n-button>
        <n-button size="small" @mousedown.stop :type="fullscreen ? 'primary' : 'default'" @click="toggleFullscreen">
          <IconMaximize :size="13" /> {{ fullscreen ? '退出全屏' : '全屏' }}
        </n-button>
      </div>
      <!-- 右区：窗口按钮贴最右缘，与主界面顶栏一致 -->
      <div class="right">
        <WindowControls />
      </div>
    </div>

    <div class="reader-stage" :class="[`zoom-${zoom}`]" @click="onStageClick">
      <template v-if="double">
        <div class="spread">
          <img v-if="shownLeft" :src="shownLeft" alt="">
          <img v-if="shownRight" :src="shownRight" alt="">
        </div>
        <n-spin v-if="!(rtl ? shownRight : shownLeft)" size="large" class="spread-spin" />
      </template>
      <template v-else>
        <img v-if="shownSingle" :src="shownSingle" alt="">
        <n-spin v-else size="large" class="stage-spin" />
      </template>
    </div>

    <div class="bottom">
      <div ref="barEl" class="progress" @pointerdown="onBarDown" @pointermove="onBarMove"
           @pointerup="onBarUp" @pointercancel="onBarUp">
        <div class="track" />
        <!-- 填充与滑块统一按「轨道有效长度」计算（两侧各内缩 20px），滑块圆心与填充边缘重合；
             RTL 自右端起（index=0 在最右），LTR 自左端起 -->
        <div class="filled" :style="fillStyle" />
        <div class="knob" :class="{ ltr: !rtl }" :style="knobStyle" />
        <div class="page-label">{{ label }}</div>
      </div>
    </div>
  </main>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { NButton, NButtonGroup, NSpin } from 'naive-ui'
import { api, win } from '../api'
import { store } from '../store'
import { barMouseDown } from '../windowState'
import { IconBack, IconMaximize, IconDoublePage } from './icons'
import WindowControls from './WindowControls.vue'

const ZOOMS = ['fit', 'width', 'original']
const CFG_DOUBLE = 'ui_reader_double'
const CFG_ZOOM = 'ui_reader_zoom'
const CFG_DIR = 'ui_reader_direction'

const reader = store.reader
const index = ref(Math.max(0, Math.min(reader.index, reader.images.length - 1)))
const dragging = ref(false)
const barEl = ref(null)
const double = ref(false)
const zoom = ref('fit')
const rtl = ref(true)
const chromeVisible = ref(true)
const fullscreen = ref(false)
let saveTimer = null
let hideTimer = null

// 图片显示层：新图完整解码后才切换 src，旧图保持显示（消除翻页闪白）。
// 代际计数丢弃过期加载：快速连翻时，旧请求晚到不回写。
const shownSingle = ref('')
const shownLeft = ref('')
const shownRight = ref('')
let singleGen = 0
let spreadGen = 0

// 进度条拖动状态：
//   scrubIndex   拖动中的页码（数字/滑块即时跟随）
//   scrubPreview 节流后的预览页码（驱动图片加载，快速扫动只在停顿处加载）
// 拖动中不触发相邻页预载排队与进度落库，松手才真正 goTo
const scrubIndex = ref(null)
const scrubPreview = ref(null)
let scrubTimer = null

const total = reader.images.length
// 展示层页码：拖动预览期间跟随 scrubPreview
const displayIndex = computed(() => (scrubPreview.value ?? index.value))
const current = computed(() => reader.images[displayIndex.value])
// 展示页码：拖动中跟随 scrubIndex
const viewIndex = computed(() => (scrubIndex.value ?? index.value))
// 进度条：RTL 时 index=0 在最右端
const fillPct = computed(() => (total > 1 ? (viewIndex.value / (total - 1)) * 100 : 0))
const label = computed(() => {
  const i = viewIndex.value
  return double.value && i + 1 < total
    ? `${i + 1}-${i + 2} / ${total}`
    : `${i + 1} / ${total}`
})
const fillStyle = computed(() => ({
  [rtl.value ? 'right' : 'left']: '20px',
  width: `calc((100% - 40px) * ${fillPct.value / 100})`,
}))
const knobStyle = computed(() => ({
  [rtl.value ? 'right' : 'left']: `calc(20px + (100% - 40px) * ${fillPct.value / 100})`,
}))

// 双页对开：当前页为「主位」、下一页为「副位」；RTL 主位在右（日漫右开本），
// LTR 主位在左。封面（第 1 页）单独成屏，从第 2 页起对开。
const primarySrc = computed(() => current.value?.image_url || '')
const secondarySrc = computed(() =>
  double.value && displayIndex.value > 0 && displayIndex.value + 1 < total
    ? (reader.images[displayIndex.value + 1]?.image_url || '')
    : '')
const spreadLeft = computed(() => (rtl.value ? secondarySrc.value : primarySrc.value))
const spreadRight = computed(() => (rtl.value ? primarySrc.value : secondarySrc.value))

function align(i) {
  const n = Math.max(0, Math.min(i, total - 1))
  if (!double.value) return n
  if (n === 0) return 0            // 封面单显
  return n % 2 === 0 ? n - 1 : n   // 对开基页取奇数（1,3,5…）
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

// 单页：异步解码完成后整体切换，旧图保持显示
watch(() => current.value?.image_url, v => {
  const g = ++singleGen
  if (!v) { shownSingle.value = ''; return }
  const im = new Image()
  im.onload = im.onerror = () => { if (g === singleGen) shownSingle.value = v }
  im.src = v
}, { immediate: true })

// 双页：两页都就绪才整屏切换，避免半屏先跳
watch([spreadLeft, spreadRight], ([l, r]) => {
  const g = ++spreadGen
  if (!l && !r) { shownLeft.value = ''; shownRight.value = ''; return }
  const wait = src => new Promise(res => {
    const im = new Image()
    im.onload = im.onerror = res
    im.src = src
  })
  Promise.all([l, r].filter(Boolean).map(wait)).then(() => {
    if (g !== spreadGen) return
    shownLeft.value = l
    shownRight.value = r
  })
}, { immediate: true })

// 切换双页时按对开基页对齐
watch(double, () => { index.value = align(index.value) })

function toggleDouble() { setDouble(!double.value) }
function setDouble(v) {
  double.value = v
  api.setConfig(CFG_DOUBLE, v ? '1' : '0').catch(() => {})
}
function toggleDir() { setDir(!rtl.value) }
function setDir(v) {
  rtl.value = v
  api.setConfig(CFG_DIR, v ? 'rtl' : 'ltr').catch(() => {})
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
  // 阅读前进侧：RTL 在左 1/3，LTR 在右 1/3
  if (x < r.width / 3) (rtl.value ? next() : prev())
  else if (x > (2 * r.width) / 3) (rtl.value ? prev() : next())
}
function onWheel(e) {
  if (zoom.value !== 'fit') return       // 滚动模式下滚轮用于滚动页面
  if (e.deltaY !== 0) { e.deltaY > 0 ? next() : prev(); return }
  if (e.deltaX === 0) return
  // 横向滚轮沿阅读前进方向为下一页（RTL 向左，LTR 向右）
  ;(e.deltaX > 0) !== rtl.value ? next() : prev()
}

function onKey(e) {
  const k = e.key
  if (k === 'ArrowDown') next()
  else if (k === 'ArrowUp') prev()
  else if (k === 'ArrowLeft') (rtl.value ? next() : prev())
  else if (k === 'ArrowRight') (rtl.value ? prev() : next())
  else if (k === 'Escape') back()
  else if (k === 'F11' || k.toLowerCase() === 'f') toggleFullscreen()
  else if (k.toLowerCase() === 'd') toggleDouble()
}
onMounted(() => {
  window.addEventListener('keydown', onKey)
  pokeChrome()
  // 恢复阅读器偏好
  api.getConfig(CFG_DOUBLE).then(r => { if (r.value === '1') double.value = true }).catch(() => {})
  api.getConfig(CFG_ZOOM).then(r => { if (ZOOMS.includes(r.value)) zoom.value = r.value }).catch(() => {})
  api.getConfig(CFG_DIR).then(r => { if (r.value === 'ltr') rtl.value = false }).catch(() => {})
  preload(index.value)   // 进入时预热相邻页
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  clearTimeout(saveTimer)
  clearTimeout(hideTimer)
  clearTimeout(scrubTimer)
  win.exitFullscreen()                                         // 兜底还原全屏
  api.lastRead(reader.obj.id, index.value).catch(() => {})   // 退出前兜底落库
})

function back() {
  clearTimeout(saveTimer)
  win.exitFullscreen()
  api.lastRead(reader.obj.id, index.value).catch(() => {})
  store.view = { name: 'directory' }
}

// 真全屏走 Win32 窗口层（WebView2 不响应 HTML requestFullscreen）
async function toggleFullscreen() {
  fullscreen.value = await win.toggleFullscreen()
}

// ── 进度条拖动（拖动中即时预览、节流加载，松手才落库+预载） ──
function barToIndex(clientX) {
  const r = barEl.value.getBoundingClientRect()
  const pad = 20
  const w = r.width - pad * 2
  if (w <= 0) return 0
  const pos = rtl.value
    ? r.width - pad - (clientX - r.left)   // RTL：自右端起
    : clientX - r.left - pad               // LTR：自左端起
  const ratio = Math.max(0, Math.min(1, pos / w))
  return Math.round(ratio * (total - 1))
}
function setScrub(i) {
  if (i === scrubIndex.value) return
  scrubIndex.value = i
  // 图片预览按 200ms 节流：快速扫动只在停顿处加载（就绪才切换保证画面稳定）
  clearTimeout(scrubTimer)
  scrubTimer = setTimeout(() => { scrubPreview.value = i }, 200)
}
function onBarDown(e) {
  dragging.value = true
  pokeChrome()
  barEl.value?.setPointerCapture(e.pointerId)
  const i = align(barToIndex(e.clientX))
  scrubIndex.value = i
  scrubPreview.value = i   // 按下立即预览
}
function onBarMove(e) {
  if (dragging.value) setScrub(align(barToIndex(e.clientX)))
}
function onBarUp() {
  if (!dragging.value) return
  dragging.value = false
  clearTimeout(scrubTimer)
  const t = scrubIndex.value
  scrubIndex.value = null
  scrubPreview.value = null
  if (t != null && t !== index.value) goTo(t)
}
</script>

<style scoped>
.reader { flex: 1; display: flex; flex-direction: column; min-height: 0; }
/* 顶栏高度与主界面 TopBar 保持一致（58px）；左右等宽令中区控件天然居中 */
.top {
  height: 58px; flex: none;
  display: flex; align-items: stretch;
  border-bottom: 1px solid var(--border);
  transition: opacity .3s;
  user-select: none;
}
.left {
  flex: 1; min-width: 0;
  display: flex; align-items: center; gap: 10px;
  padding-left: 12px;
}
.center { flex: none; display: flex; align-items: center; gap: 10px; }
.right { flex: 1; display: flex; align-items: stretch; justify-content: flex-end; }
.obj-title { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

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
/* 锚定侧（right/left）由内联样式按阅读方向提供 */
.filled { top: 18px; height: 4px; border-radius: 2px; background: var(--ms-primary); }
.knob {
  top: 12px; width: 16px; height: 16px; border-radius: 50%;
  transform: translateX(50%);
  background: var(--card); border: 2px solid var(--ms-primary);
}
.knob.ltr { transform: translateX(-50%); }
.page-label {
  position: absolute; top: 26px; left: 0; right: 0; bottom: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; line-height: 14px; color: var(--text2); opacity: .8;
}
</style>
