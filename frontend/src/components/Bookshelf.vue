<template>
  <main class="shelf">
    <div class="toolbar">
      <div class="result-hint">
        共 {{ shown.length }} 个对象{{ store.r18 ? '' : '（R-18 已隐藏）' }}{{ store.keyword ? ` · 搜索「${store.keyword}」` : '' }}
      </div>
      <div class="toolbar-actions">
        <n-select class="sort-select" size="small" :value="store.sort.key"
                  :options="sortOptions" @update:value="k => setSort({ ...store.sort, key: k })" />
        <n-button size="small" :title="store.sort.desc ? '降序' : '升序'"
                  @click="setSort({ ...store.sort, desc: !store.sort.desc })">
          <IconArrowDown v-if="store.sort.desc" :size="14" />
          <IconArrowUp v-else :size="14" />
        </n-button>
        <n-button-group size="small">
          <n-button v-for="(label, d) in DENSITY_LABELS" :key="d"
                    :type="store.density === d ? 'primary' : 'default'"
                    :secondary="store.density !== d"
                    @click="setDensity(d)">{{ label }}</n-button>
        </n-button-group>
        <n-button v-if="!selectMode" size="small" @click="enterSelect">
          <IconCheckSquare :size="14" /> 多选
        </n-button>
      </div>
    </div>

    <div ref="gridEl" class="shelf-grid" :class="[phase, `density-${store.density}`]">
      <ObjectCard v-for="(o, i) in shown" :key="o.id" :obj="o"
        :anim-delay="phase ? Math.min(i * (phase === 'leaving' ? 12 : 26), 420) : 0"
        :revealed="revealedSet.has(o.id)"
        :select-mode="selectMode" :selected="selected.has(o.id)"
        @open="openDir" @read="openReader" @edit="editObj" @cover="changeCover" @del="delObj"
        @rate="rateObj" @toggle-select="toggleSelect" />
    </div>
    <n-empty v-if="!shown.length && !phase" class="empty" size="large"
             description="书架空空如也，点击右上角「导入」添加图片吧" />

    <EditDialog v-model:show="editShow" :obj="editTarget" @saved="silentReload" />

    <!-- 多选模式的底部操作条 -->
    <div v-if="selectMode" class="select-bar">
      <span class="sel-count">已选 {{ selected.size }} 项</span>
      <n-button size="small" @click="toggleAll">{{ selected.size === shown.length ? '取消全选' : '全选' }}</n-button>
      <n-button size="small" type="primary" :disabled="!selected.size" @click="openBatchTag">批量打标签</n-button>
      <n-button size="small" type="error" :disabled="!selected.size" @click="confirmBatchDelete">批量删除</n-button>
      <span class="spacer" />
      <n-button size="small" quaternary @click="exitSelect"><IconX :size="13" /> 退出多选</n-button>
    </div>

    <!-- 批量打标签对话框 -->
    <n-modal v-model:show="batchShow" preset="card" title="批量添加标签" style="width: 520px;">
      <p class="batch-hint">为选中的 {{ selected.size }} 个对象追加标签（保留已有标签，重复值自动去重）。</p>
      <TagFields v-model:tags="batchTags" />
      <template #footer>
        <div class="footer">
          <n-button @click="batchShow = false">取消</n-button>
          <n-button type="primary" :loading="batchBusy" @click="runBatchTag">
            {{ batchProgress || '应用到选中对象' }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </main>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, h } from 'vue'
import { useMessage, useDialog, NCheckbox, NSelect, NButton, NButtonGroup, NModal, NEmpty } from 'naive-ui'
import { api, dialog as fileDialog } from '../api'
import { store, refreshTagValues, setSort, setDensity } from '../store'
import { CATS } from '../constants'
import { IconArrowUp, IconArrowDown, IconCheckSquare, IconX } from './icons'
import ObjectCard from './ObjectCard.vue'
import EditDialog from './EditDialog.vue'
import TagFields from './TagFields.vue'

const message = useMessage()
const dialog = useDialog()

const shown = ref([])
const phase = ref('')            // '' | 'leaving' | 'entering'
const revealedSet = ref(new Set())
const editShow = ref(false)
const editTarget = ref(null)

// 排序 / 密度
const DENSITY_LABELS = { compact: '紧凑', standard: '标准', large: '大图' }
const SORTERS = {
  created_at: o => o.created_at || '',
  name: o => o.name || '',
  images: o => o.image_count || 0,
  rating: o => Number(o.tags?.rating?.[0] || 0),
  progress: o => (o.image_count ? (o.last_read_idx || 0) / o.image_count : 0),
}
const sortOptions = [
  { label: '添加时间', value: 'created_at' },
  { label: '名称', value: 'name' },
  { label: '页数', value: 'images' },
  { label: '评分', value: 'rating' },
  { label: '阅读进度', value: 'progress' },
]

function applySort(list) {
  const fn = SORTERS[store.sort.key] || SORTERS.created_at
  return [...list].sort((a, b) => {
    const va = fn(a), vb = fn(b)
    const c = typeof va === 'string' ? va.localeCompare(String(vb), 'zh') : va - vb
    return store.sort.desc ? -c : c
  })
}

// 多选
const selectMode = ref(false)
const selected = ref(new Set())
const batchShow = ref(false)
const batchTags = ref({})
const batchBusy = ref(false)
const batchProgress = ref('')

const OUT_MS = 200
let seq = 0

async function fetchObjects() {
  const list = await api.objects(store.keyword, store.r18, store.filters)
  store.objects = list          // 回写全局，供「追加导入」下拉等处消费
  return list
}

// 筛选/搜索/R18 变化：整批卡片向右滑出 → 新结果从左滑入
watch(() => [store.filters, store.keyword, store.r18], async () => {
  const my = ++seq
  const next = await fetchObjects().catch(() => [])
  if (my !== seq) return
  exitSelect()

  const sorted = applySort(next)
  if (!shown.value.length) {           // 首次或从空态恢复：直接入场动画
    shown.value = sorted
    phase.value = 'entering'
    setTimeout(() => { if (my === seq) phase.value = '' }, 900)
    return
  }

  phase.value = 'leaving'
  const wait = OUT_MS + shown.value.length * 12
  setTimeout(() => {
    if (my !== seq) return
    shown.value = sorted
    phase.value = 'entering'
    setTimeout(() => { if (my === seq) phase.value = '' }, 900)
  }, wait)
})

// 排序变化：只重排当前结果，不重新请求、不做过渡动画
watch(() => [store.sort.key, store.sort.desc], () => {
  shown.value = applySort(shown.value)
})

// 静默刷新（编辑/删除/换封面/导入后）：不做过渡动画
async function silentReload() {
  const my = ++seq
  phase.value = ''
  shown.value = applySort(await fetchObjects().catch(() => []))
  refreshTagValues()
}

// 导入完成等外部数据变更（App 层转发 reloadTick）
watch(() => store.reloadTick, () => { silentReload() })

onMounted(async () => {
  shown.value = applySort(await fetchObjects().catch(() => []))
  phase.value = 'entering'
  setTimeout(() => { phase.value = '' }, 900)
})

// ── 多选 ──
function enterSelect() { selectMode.value = true }
function exitSelect() {
  if (!selectMode.value && !selected.value.size) return
  selectMode.value = false
  selected.value = new Set()
}
function toggleSelect(id) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}
function toggleAll() {
  selected.value = selected.value.size === shown.value.length
    ? new Set()
    : new Set(shown.value.map(o => o.id))
}

function openBatchTag() {
  batchTags.value = {}
  batchProgress.value = ''
  batchShow.value = true
}

async function runBatchTag() {
  const objs = shown.value.filter(o => selected.value.has(o.id))
  if (!objs.length) return
  batchBusy.value = true
  try {
    let done = 0
    for (const o of objs) {
      const tags = { ...o.tags }
      for (const cat of CATS) {
        const add = batchTags.value[cat] || []
        if (!add.length) continue
        const cur = Array.isArray(tags[cat]) ? tags[cat] : []
        tags[cat] = [...new Set([...cur, ...add])]
      }
      await api.updateObject(o.id, { tags })
      o.tags = tags           // 本地同步，卡片标签即时更新
      done++
      batchProgress.value = `${done} / ${objs.length}`
    }
    message.success(`已为 ${done} 个对象添加标签`)
    batchShow.value = false
    exitSelect()
    refreshTagValues()
  } catch (e) {
    message.error(e.message)
  } finally {
    batchBusy.value = false
  }
}

function confirmBatchDelete() {
  const n = selected.value.size
  // 必须用 ref：对话框内容是渲染函数，普通对象无响应式，勾选状态不会回显
  const checked = ref(false)
  dialog.warning({
    title: '批量删除',
    content: () => h('div', null, [
      h('p', { style: 'margin-bottom:8px' }, `确定要删除选中的 ${n} 个对象吗？删除后无法撤销！`),
      h(NCheckbox, {
        checked: checked.value,
        'onUpdate:checked': v => { checked.value = v },
      }, { default: () => '同时删除本地图片文件' }),
    ]),
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: () => runBatchDelete(checked.value),
  })
}

async function runBatchDelete(deleteFiles) {
  const objs = shown.value.filter(o => selected.value.has(o.id))
  let ok = 0, fail = 0
  for (const o of objs) {
    try { await api.deleteObject(o.id, deleteFiles); ok++ } catch { fail++ }
  }
  if (fail) message.warning(`已删除 ${ok} 个，失败 ${fail} 个`)
  else message.success(`已删除 ${ok} 个`)
  exitSelect()
  silentReload()
}

// Esc 退出多选
function onKey(e) {
  if (e.key === 'Escape' && selectMode.value && !batchShow.value) exitSelect()
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

// ── 卡片操作 ──
async function openDir(obj) {
  const detail = await api.object(obj.id)
  store.directory = { obj: detail }
  store.view = { name: 'directory' }
}

// 卡片「继续阅读」：取详情后直达阅读器，恢复上次进度（省去进详情页一跳）
async function openReader(obj) {
  try {
    const detail = await api.object(obj.id)
    if (!detail.images?.length) {
      message.warning('该对象没有内容')
      return
    }
    const idx = Math.min(obj.last_read_idx || 0, detail.images.length - 1)
    store.reader = { obj: detail, images: detail.images, index: idx, from: 'shelf' }
    store.view = { name: 'reader' }
  } catch (e) {
    message.error(e.message || String(e))
  }
}

function editObj(obj) {
  editTarget.value = obj
  editShow.value = true
}

async function changeCover(obj) {
  let path = await fileDialog.pickFiles('选择封面图片')
  if (path === null) {                 // 浏览器模式降级
    path = window.prompt('输入封面图片完整路径：')
    if (!path) return
  }
  if (!path) return
  try {
    await api.updateObject(obj.id, { cover_image: path })
    message.success('封面已更新')
    silentReload()
  } catch (e) { message.error(e.message) }
}

async function rateObj(obj, val) {
  const tags = { ...obj.tags }
  if (val) tags.rating = [String(val)]
  else delete tags.rating
  try {
    await api.updateObject(obj.id, { tags })
    obj.tags = tags           // 本地即时生效
  } catch (e) { message.error(e.message) }
}

function delObj(obj) {
  // 必须用 ref：对话框内容是渲染函数，普通对象无响应式，勾选状态不会回显
  const checked = ref(false)
  dialog.warning({
    title: '删除对象',
    content: () => h('div', null, [
      h('p', { style: 'margin-bottom:8px' }, `确定要从书架删除「${obj.name}」吗？删除后无法撤销！`),
      h(NCheckbox, {
        checked: checked.value,
        'onUpdate:checked': v => { checked.value = v },
      }, { default: () => '同时删除本地图片文件' }),
    ]),
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: () => doDelete(obj, checked.value),
  })
}

async function doDelete(obj, deleteFiles) {
  try {
    await api.deleteObject(obj.id, deleteFiles)
    message.success('已删除')
    silentReload()
  } catch (e) { message.error(e.message) }
}
</script>

<style scoped>
.shelf { flex: 1; overflow-y: auto; padding: 22px 26px 40px; position: relative; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.result-hint { font-size: 12px; opacity: .55; }
.toolbar-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.sort-select { width: 108px; }

.empty { margin-top: 80px; }

.select-bar {
  position: fixed; left: 50%; transform: translateX(-50%);
  bottom: 28px; z-index: 10;
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px;
  border-radius: 10px;
  background: var(--card);
  border: 1px solid var(--border-strong);
  box-shadow: 0 8px 28px rgba(0, 0, 0, .28);
}
.sel-count { font-size: 13px; font-weight: 600; }
.spacer { flex: 1; }

.batch-hint { font-size: 12px; opacity: .6; margin-bottom: 4px; }
.footer { display: flex; justify-content: flex-end; gap: 10px; }

/* 两阶段过渡：整批右出（card-out）→ 左入（card-in），交错延迟由 anim-delay 内联提供 */
.shelf-grid.leaving :deep(.obj-card) {
  animation: card-out .2s ease-in forwards; pointer-events: none;
}
.shelf-grid.entering :deep(.obj-card) {
  animation: card-in .34s cubic-bezier(.22, .9, .36, 1) backwards;
}
</style>
