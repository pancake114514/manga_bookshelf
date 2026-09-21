<template>
  <n-modal v-model:show="show" preset="card" title="导入图片" style="width: 520px;">
    <div class="mode-list">
      <n-button block size="large" class="mode-btn" @click="setMode('new')">
        <IconFolder /> 新建目录（导入整个文件夹）
      </n-button>
      <n-button block size="large" class="mode-btn" @click="setMode('append')">
        <IconLibrary /> 导入文件夹到已有目录
      </n-button>
      <n-button block size="large" class="mode-btn" @click="setMode('files')">
        <IconImage /> 导入图片文件到已有目录
      </n-button>
      <n-button block size="large" class="mode-btn" @click="setMode('batch')">
        <IconLibrary /> 批量导入（按子文件夹建目录）
      </n-button>
    </div>

    <!-- 新建目录 -->
    <template v-if="mode === 'new'">
      <n-input-group class="row">
        <n-input v-model:value="sourceDir" placeholder="源文件夹路径…" readonly />
        <n-button @click="pickSource">浏览…</n-button>
      </n-input-group>
      <div class="field-label">对象名称</div>
      <n-input v-model:value="name" placeholder="输入对象名称" />
      <TagFields v-model:tags="newTags" />
      <div class="field-label">评分</div>
      <n-rate v-model:value="rating" />
    </template>

    <!-- 追加到已有目录 -->
    <template v-if="mode === 'append'">
      <div class="field-label">目标目录</div>
      <n-select v-model:value="targetId" :options="objectOptions" filterable placeholder="选择目标目录" />
      <n-input-group class="row">
        <n-input v-model:value="sourceDir" placeholder="源文件夹路径…" readonly />
        <n-button @click="pickSource">浏览…</n-button>
      </n-input-group>
    </template>

    <!-- 导入图片文件到已有目录 -->
    <template v-if="mode === 'files'">
      <div class="field-label">目标目录</div>
      <n-select v-model:value="targetId" :options="objectOptions" filterable placeholder="选择目标目录" />
      <div class="field-label">选择图片</div>
      <n-button block @click="pickImages">选择图片…</n-button>
      <div v-if="selectedFiles.length" class="file-list">
        <span class="file-count">已选 {{ selectedFiles.length }} 个文件</span>
        <div class="file-tags">
          <n-tag
            v-for="(file, i) in selectedFiles"
            :key="i"
            closable
            @close="removeFile(i)"
          >{{ basename(file) }}</n-tag>
        </div>
      </div>
    </template>

    <!-- 批量导入：直接多选漫画文件夹，每个文件夹各建一个目录对象 -->
    <template v-if="mode === 'batch'">
      <div class="batch-summary">
        共 {{ batchEntries.length }} 个文件夹，已选 {{ checkedCount }} 个
        <n-button quaternary size="tiny" @click="resetBatchScan(); openBatchPicker()">重选</n-button>
      </div>
      <div class="batch-list">
        <div v-for="(e, i) in batchEntries" :key="e.path" class="batch-item">
          <n-checkbox v-model:checked="e.checked" :disabled="batchRunning" />
          <div class="batch-item-main">
            <n-input v-model:value="e.name" size="small" placeholder="对象名称" :disabled="batchRunning" />
            <span class="batch-sub">{{ e.folder }} · {{ e.image_count }} 张{{ e.image_count === 0 ? '（无图片，不建议导入）' : '' }}</span>
          </div>
        </div>
      </div>
      <div class="field-label">统一标签（应用到所有勾选项，可留空）</div>
      <TagFields v-model:tags="newTags" />
      <div class="field-label">评分</div>
      <n-rate v-model:value="rating" :disabled="batchRunning" />

      <!-- 进度与逐项结果 -->
      <template v-if="batchRunning || batchResults.length">
        <n-progress type="line" :percentage="batchProgress" :show-indicator="false" processing />
        <div class="batch-results">
          <div v-for="(r, i) in batchResults" :key="i"
               class="batch-result" :class="r.ok ? 'ok' : 'err'">
            {{ r.ok ? '✓' : '✗' }} {{ r.folder }}{{ r.error ? '：' + r.error : '' }}
          </div>
        </div>
      </template>
    </template>

    <n-alert v-if="errMsg" type="error" class="alert">{{ errMsg }}</n-alert>
    <n-progress v-if="busy" type="line" :show-indicator="false" processing />

    <template #footer>
      <div class="footer">
        <n-button v-if="batchRunning" @click="batchCancelled = true">停止剩余</n-button>
        <n-button v-else-if="mode" @click="mode = null; errMsg = ''; selectedFiles = []">返回</n-button>
        <n-button type="primary" :disabled="!mode" :loading="busy || batchRunning" @click="run">
          {{ mode === 'batch' && batchRunning ? '导入中…' : '开始导入' }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  NModal, NButton, NInput, NInputGroup, NSelect, NAlert, NProgress, NRate, NTag, NCheckbox, useMessage,
} from 'naive-ui'
import { api, dialog } from '../api'
import { store, refreshTagValues } from '../store'
import TagFields from './TagFields.vue'
import { IconFolder, IconLibrary, IconImage } from './icons'
import { parseMangaName, applyParsedTags } from '../naming'

const TAG_MERGE_CATS = ['work', 'author', 'character', 'cm', 'censored']

const props = defineProps({ show: Boolean })
const emit = defineEmits(['update:show', 'done'])

const show = computed({
  get: () => props.show,
  set: v => emit('update:show', v),
})

const message = useMessage()
const mode = ref(null)            // null | 'new' | 'append' | 'files'
const sourceDir = ref('')
const name = ref('')
const newTags = ref({})
const rating = ref(0)
const targetId = ref(null)
const selectedFiles = ref([])
const errMsg = ref('')
const busy = ref(false)

// 批量导入状态
const batchEntries = ref([])      // { folder, path, image_count, name, checked }
const batchRunning = ref(false)
const batchCancelled = ref(false)
const batchResults = ref([])      // { folder, ok, error? }
const batchIndex = ref(0)
const batchTotal = ref(0)

const checkedCount = computed(() => batchEntries.value.filter(e => e.checked).length)
const batchProgress = computed(() =>
  batchTotal.value ? Math.round((batchIndex.value / batchTotal.value) * 100) : 0)

const objectOptions = computed(() =>
  store.objects.map(o => ({ label: o.name, value: o.id })))

// 重置全部表单状态（关闭弹窗 / 导入成功时调用）
function resetAll() {
  mode.value = null
  sourceDir.value = ''
  name.value = ''
  newTags.value = {}
  rating.value = 0
  targetId.value = null
  selectedFiles.value = []
  errMsg.value = ''
  resetBatchScan()
  batchRunning.value = false
  batchCancelled.value = false
  batchResults.value = []
  batchIndex.value = 0
  batchTotal.value = 0
}

function resetBatchScan() {
  batchEntries.value = []
}

// 切换导入模式，同时清空上一步残留的错误提示；
// 批量模式不做任何停留，直接弹出多选文件夹对话框（取消则回到方式列表）
function setMode(m) {
  mode.value = m
  errMsg.value = ''
  if (m === 'batch') openBatchPicker()
}

async function openBatchPicker() {
  const dirs = await dialog.pickDirs('选择多个漫画文件夹（可按住 Ctrl 多选）')
  if (!dirs.length) {
    if (mode.value === 'batch') mode.value = null   // 取消选择 → 回到方式列表
    return
  }
  await addEntries(dirs)
}

// 弹窗关闭（点 X / 遮罩，未点「返回」）时也全部重置
watch(() => props.show, v => { if (!v) resetAll() })

async function pickSource() {
  const dir = await dialog.pickDir('选择要导入的文件夹')
  if (dir) {
    sourceDir.value = dir
    if (mode.value === 'new') {
      // 按命名规则解析文件夹名：对象名预填全名（去数字编号），cm/author 进标签
      const folder = dir.split(/[\\/]/).filter(Boolean).pop() || ''
      const parsed = parseMangaName(folder)
      name.value = parsed.full || folder
      newTags.value = applyParsedTags(newTags.value, parsed)
    }
  }
}

function basename(path) {
  return path.split(/[\\/]/).filter(Boolean).pop() || path
}

async function pickImages() {
  const files = await dialog.pickFiles('选择要导入的图片')
  if (files.length) {
    const set = new Set(selectedFiles.value)
    for (const f of files) set.add(f)
    selectedFiles.value = [...set]
  }
}

function removeFile(i) {
  selectedFiles.value.splice(i, 1)
}

// ── 批量导入 ──
async function addEntries(paths) {
  const existing = new Set(batchEntries.value.map(e => e.path))
  const added = []
  for (const p of paths) {
    if (existing.has(p)) continue
    existing.add(p)
    let count = 0
    try { count = await api.countImages(p) } catch { /* 目录读不了按 0 处理 */ }
    const folder = p.split(/[\\/]/).filter(Boolean).pop() || p
    const parsed = parseMangaName(folder)
    added.push({
      path: p,
      folder,
      image_count: count,
      name: parsed.full || folder,  // 对象名 = 全名（去数字编号），命名规则解析预填
      checked: count > 0,
    })
  }
  if (!added.length) { errMsg.value = '所选文件夹已在清单中'; return }
  batchEntries.value = [...batchEntries.value, ...added]
}

// 单个子项的最终标签 = 命名规则解析值 + 统一标签（合并去重，解析值在前）
function mergeBatchTags(entry) {
  const parsed = parseMangaName(entry.folder)
  const tags = {}
  for (const cat of TAG_MERGE_CATS) {
    const merged = new Set()
    if (parsed[cat]) merged.add(parsed[cat])
    for (const v of newTags.value[cat] || []) merged.add(v)
    if (merged.size) tags[cat] = [...merged]
  }
  if (newTags.value.r18 === true) tags.r18 = true
  if (rating.value) tags.rating = [String(rating.value)]
  return tags
}

async function runBatch() {
  const items = batchEntries.value.filter(e => e.checked)
  if (!items.length) { errMsg.value = '请至少勾选一个子文件夹'; return }
  batchRunning.value = true
  batchCancelled.value = false
  batchResults.value = []
  batchIndex.value = 0
  batchTotal.value = items.length
  for (const e of items) {
    if (batchCancelled.value || !show.value) break   // 手动停止 / 关闭弹窗
    const displayName = e.name.trim() || e.folder
    try {
      await api.importDirectory({
        source_dir: e.path,
        name: displayName,
        tags: mergeBatchTags(e),
        is_new: true,
      })
      batchResults.value.push({ folder: displayName, ok: true })
    } catch (err) {
      batchResults.value.push({ folder: displayName, ok: false, error: err.message })
    }
    batchIndex.value++
  }
  batchRunning.value = false
  refreshTagValues()
  emit('done')
  const okN = batchResults.value.filter(r => r.ok).length
  const failN = batchResults.value.length - okN
  if (batchCancelled.value) {
    message.info(`已停止：成功 ${okN}，失败 ${failN}，剩余未导入`)
  } else if (failN === 0) {
    message.success(`批量导入完成：${okN} 个全部成功`)
  } else {
    message.warning(`批量导入结束：成功 ${okN}，失败 ${failN}（详见列表）`)
  }
}

async function run() {
  errMsg.value = ''
  if (mode.value === 'batch') {
    await runBatch()
    return
  }
  if (mode.value === 'files') {
    if (!targetId.value) { errMsg.value = '请选择目标目录'; return }
    if (!selectedFiles.value.length) { errMsg.value = '请先选择图片文件'; return }
  } else {
    if (!sourceDir.value) { errMsg.value = '请先选择源文件夹'; return }
  }
  busy.value = true
  try {
    let result
    if (mode.value === 'new') {
      if (!name.value.trim()) { errMsg.value = '请输入对象名称'; return }
      const check = await api.validateName(name.value.trim())
      if (!check.ok) { errMsg.value = check.error; return }
      const tags = { ...newTags.value }
      if (rating.value) tags.rating = [String(rating.value)]
      result = await api.importDirectory({
        source_dir: sourceDir.value,
        name: name.value.trim(),
        tags,
        is_new: true,
      })
    } else if (mode.value === 'files') {
      result = await api.importFiles({
        obj_id: targetId.value,
        paths: selectedFiles.value,
      })
    } else {
      if (!targetId.value) { errMsg.value = '请选择目标目录'; return }
      result = await api.importDirectory({
        source_dir: sourceDir.value,
        name: '',
        tags: {},
        is_new: false,
        obj_id: targetId.value,
      })
    }
    message.success(`导入完成：成功 ${result.success} 张${result.failed ? `，失败 ${result.failed} 张` : ''}`)
    emit('update:show', false)
    resetAll()
    refreshTagValues()
    emit('done')
  } catch (e) {
    errMsg.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.mode-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 14px; }
.mode-btn { justify-content: flex-start; }
.mode-btn :deep(svg) { margin-right: 8px; }
.mode-btn { font-size: 14px; }
.mode-btn :deep(.n-button__content) { transform: translateY(1px); }
.row { margin-top: 10px; }
.field-label { font-size: 12px; font-weight: 700; opacity: .6; margin: 12px 0 6px; letter-spacing: 1px; }
.alert { margin-top: 12px; }
.footer { display: flex; justify-content: flex-end; gap: 10px; }
.file-list { margin-top: 10px; }
.file-count { font-size: 12px; font-weight: 700; opacity: .6; margin-bottom: 6px; display: block; }
.file-tags {
  display: flex; flex-wrap: wrap; gap: 6px;
  max-height: 160px; overflow-y: auto;
  padding: 6px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--chip-bg);
}
.batch-summary { font-size: 12px; font-weight: 700; opacity: .7; margin-top: 12px; display: flex; align-items: center; gap: 8px; }
.batch-list {
  max-height: 220px; overflow-y: auto; margin-top: 10px;
  padding: 6px; border: 1px solid var(--border); border-radius: 6px;
  display: flex; flex-direction: column; gap: 8px;
}
.batch-item { display: flex; align-items: center; gap: 10px; }
.batch-item-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.batch-sub { font-size: 11px; opacity: .55; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.batch-results {
  margin-top: 10px; max-height: 180px; overflow-y: auto;
  padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px;
  display: flex; flex-direction: column; gap: 4px;
  font-size: 12px;
}
.batch-result.ok { color: var(--ms-primary, #18a058); }
.batch-result.err { color: #d03050; word-break: break-all; }
</style>
