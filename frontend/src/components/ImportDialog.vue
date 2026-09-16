<template>
  <n-modal v-model:show="show" preset="card" title="导入图片" style="width: 520px;">
    <div class="mode-list">
      <n-button block size="large" class="mode-btn" @click="mode = 'new'">
        📁  新建目录（导入整个文件夹）
      </n-button>
      <n-button block size="large" class="mode-btn" @click="mode = 'append'">
        🗂  导入文件夹到已有目录
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

    <n-alert v-if="errMsg" type="error" class="alert">{{ errMsg }}</n-alert>
    <n-progress v-if="busy" type="line" :show-indicator="false" processing />

    <template #footer>
      <div class="footer">
        <n-button v-if="mode" @click="mode = null; errMsg = ''">返回</n-button>
        <n-button type="primary" :disabled="!mode" :loading="busy" @click="run">
          开始导入
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, computed } from 'vue'
import {
  NModal, NButton, NInput, NInputGroup, NSelect, NAlert, NProgress, useMessage,
} from 'naive-ui'
import { api, bridge } from '../api'
import { store, refreshTagValues } from '../store'
import TagFields from './TagFields.vue'

const props = defineProps({ show: Boolean })
const emit = defineEmits(['update:show', 'done'])

const show = computed({
  get: () => props.show,
  set: v => emit('update:show', v),
})

const message = useMessage()
const mode = ref(null)            // null | 'new' | 'append'
const sourceDir = ref('')
const name = ref('')
const newTags = ref({})
const targetId = ref(null)
const errMsg = ref('')
const busy = ref(false)

const objectOptions = computed(() =>
  store.objects.map(o => ({ label: o.name, value: o.id })))

async function pickSource() {
  const dir = await bridge.pickDir('选择要导入的文件夹')
  if (dir) {
    sourceDir.value = dir
    if (mode.value === 'new' && !name.value) {
      name.value = dir.split(/[\\/]/).filter(Boolean).pop() || ''
    }
  } else if (!bridge.available()) {
    const p = window.prompt('浏览器调试模式：请输入源文件夹完整路径')
    if (p) sourceDir.value = p
  }
}

async function run() {
  errMsg.value = ''
  if (!sourceDir.value) { errMsg.value = '请先选择源文件夹'; return }
  busy.value = true
  try {
    let result
    if (mode.value === 'new') {
      if (!name.value.trim()) { errMsg.value = '请输入对象名称'; return }
      const check = await api.validateName(name.value.trim())
      if (!check.ok) { errMsg.value = check.error; return }
      result = await api.importDirectory({
        source_dir: sourceDir.value,
        name: name.value.trim(),
        tags: newTags.value,
        is_new: true,
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
    mode.value = null
    sourceDir.value = ''
    name.value = ''
    newTags.value = {}
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
.row { margin-top: 10px; }
.field-label { font-size: 12px; font-weight: 700; opacity: .6; margin: 12px 0 6px; letter-spacing: 1px; }
.alert { margin-top: 12px; }
.footer { display: flex; justify-content: flex-end; gap: 10px; }
</style>
