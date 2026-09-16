<template>
  <main class="shelf">
    <div class="result-hint">
      共 {{ shown.length }} 个对象{{ store.r18 ? '' : '（R-18 已隐藏）' }}{{ store.keyword ? ` · 搜索「${store.keyword}」` : '' }}
    </div>
    <div ref="gridEl" class="shelf-grid" :class="phase">
      <ObjectCard v-for="(o, i) in shown" :key="o.id" :obj="o"
        :anim-delay="phase ? Math.min(i * (phase === 'leaving' ? 12 : 26), 420) : 0"
        :revealed="revealedSet.has(o.id)"
        @open="openDir" @edit="editObj" @cover="changeCover" @del="delObj" />
    </div>
    <div v-if="!shown.length && !phase" class="empty">
      书架空空如也<br>点击右上角「导入」添加图片吧
    </div>

    <EditDialog v-model:show="editShow" :obj="editTarget" @saved="silentReload" />
  </main>
</template>

<script setup>
import { ref, watch, onMounted, h } from 'vue'
import { useMessage, useDialog, NCheckbox } from 'naive-ui'
import { api } from '../api'
import { store, refreshTagValues } from '../store'
import { bridge } from '../api'
import ObjectCard from './ObjectCard.vue'
import EditDialog from './EditDialog.vue'

const message = useMessage()
const dialog = useDialog()

const shown = ref([])
const phase = ref('')            // '' | 'leaving' | 'entering'
const revealedSet = ref(new Set())
const editShow = ref(false)
const editTarget = ref(null)

const OUT_MS = 200
let seq = 0

async function fetchObjects() {
  return await api.objects(store.keyword, store.r18, store.filters)
}

// 筛选/搜索/R18 变化：整批卡片向右滑出 → 新结果从左滑入
watch(() => [store.filters, store.keyword, store.r18], async () => {
  const my = ++seq
  const next = await fetchObjects().catch(() => [])
  if (my !== seq) return

  if (!shown.value.length) {           // 首次或从空态恢复：直接入场动画
    shown.value = next
    phase.value = 'entering'
    setTimeout(() => { if (my === seq) phase.value = '' }, 900)
    return
  }

  phase.value = 'leaving'
  const wait = OUT_MS + shown.value.length * 12
  setTimeout(() => {
    if (my !== seq) return
    shown.value = next
    phase.value = 'entering'
    setTimeout(() => { if (my === seq) phase.value = '' }, 900)
  }, wait)
})

// 静默刷新（编辑/删除/换封面/导入后）：不做过渡动画
async function silentReload() {
  const my = ++seq
  phase.value = ''
  shown.value = await fetchObjects().catch(() => [])
  refreshTagValues()
}

onMounted(async () => {
  shown.value = await fetchObjects().catch(() => [])
  phase.value = 'entering'
  setTimeout(() => { phase.value = '' }, 900)
})

// ── 卡片操作 ──
async function openDir(obj) {
  const detail = await api.object(obj.id)
  store.directory = { obj: detail }
  store.view = { name: 'directory' }
}

function editObj(obj) {
  editTarget.value = obj
  editShow.value = true
}

async function changeCover(obj) {
  let path = await bridge.pickFiles('选择封面图片')
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

function delObj(obj) {
  const checked = { value: false }
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
.shelf { flex: 1; overflow-y: auto; padding: 22px 26px 40px; }
.result-hint { font-size: 12px; opacity: .55; margin-bottom: 14px; }
.empty { text-align: center; padding: 80px 0; opacity: .5; font-size: 16px; line-height: 2; }

.shelf-grid.leaving :deep(.obj-card) {
  animation: card-out .2s ease-in forwards; pointer-events: none;
}
.shelf-grid.entering :deep(.obj-card) {
  animation: card-in .34s cubic-bezier(.22, .9, .36, 1) backwards;
}
</style>
