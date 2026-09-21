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

    <n-alert v-if="errMsg" type="error" class="alert">{{ errMsg }}</n-alert>
    <n-progress v-if="busy" type="line" :show-indicator="false" processing />

    <template #footer>
      <div class="footer">
        <!-- 返回：仅清模式/错误/已选文件，有意保留 targetId 便于重新选择目标 -->
        <n-button v-if="mode" @click="mode = null; errMsg = ''; selectedFiles = []">返回</n-button>
        <n-button type="primary" :disabled="!mode" :loading="busy" @click="run">
          开始导入
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  NModal, NButton, NInput, NInputGroup, NSelect, NAlert, NProgress, NRate, NTag, useMessage,
} from 'naive-ui'
import { api, dialog } from '../api'
import { store, refreshTagValues } from '../store'
import TagFields from './TagFields.vue'
import { IconFolder, IconLibrary, IconImage } from './icons'

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
}

// 切换导入模式，同时清空上一步残留的错误提示
function setMode(m) {
  mode.value = m
  errMsg.value = ''
}

// 弹窗关闭（点 X / 遮罩，未点「返回」）时也全部重置
watch(() => props.show, v => { if (!v) resetAll() })

async function pickSource() {
  const dir = await dialog.pickDir('选择要导入的文件夹')
  if (dir) {
    sourceDir.value = dir
    if (mode.value === 'new' && !name.value) {
      name.value = dir.split(/[\\/]/).filter(Boolean).pop() || ''
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

async function run() {
  errMsg.value = ''
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
</style>
