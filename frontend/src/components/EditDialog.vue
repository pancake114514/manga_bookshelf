<template>
  <n-modal v-model:show="show" preset="card" title="编辑对象信息" style="width: 560px;">
    <div class="form">
      <div class="field-label">对象名称</div>
      <n-input v-model:value="name" placeholder="输入对象名称" />

      <template v-for="cat in cats" :key="cat">
        <div class="field-label">{{ catLabel(cat) }}</div>
        <n-dynamic-tags v-model:value="tagDrafts[cat]" :max="20">
          <template #input="{ submit, deactivate }">
            <n-auto-complete
              v-model:value="inputVal"
              size="small"
              :options="suggestions(cat)"
              @select="v => { submit(v); deactivate(); inputVal = '' }"
            />
          </template>
        </n-dynamic-tags>
      </template>

      <div class="field-label">评分</div>
      <n-rate v-model:value="rating" />

      <div class="field-label">系列</div>
      <!-- 下拉选择已有系列（可筛选/可输入新系列/可清除）；选中后自动预填下一卷号 -->
      <n-select v-model:value="seriesName" :options="seriesOptions"
                filterable tag clearable
                placeholder="选择系列，或输入名称创建新系列（留空清除）"
                @update:value="onSeriesChange" />

      <div class="field-label">卷号 <span class="hint-inline">选中系列后自动预填下一可用卷号，可修改</span></div>
      <n-input-number v-model:value="volume" :min="1" placeholder="留空表示无卷号"
                      button-placement="both" clearable class="volume-input" />

      <div class="r18-row">
        <span class="field-label r18-label">R-18</span>
        <n-switch v-model:value="r18" />
      </div>
    </div>

    <template #footer>
      <div class="footer">
        <n-button @click="show = false">取消</n-button>
        <n-button type="primary" :loading="saving" @click="save">确定</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { NModal, NInput, NInputNumber, NButton, NSwitch, NRate, NDynamicTags, NAutoComplete, NSelect, useMessage } from 'naive-ui'
import { api } from '../api'
import { store, loadSeries } from '../store'
import { CATS, catLabel } from '../constants'

const props = defineProps({
  show: Boolean,
  obj: { type: Object, default: null },
})
const emit = defineEmits(['update:show', 'saved'])

const show = computed({
  get: () => props.show,
  set: v => emit('update:show', v),
})

const message = useMessage()
const cats = CATS

const name = ref('')
const r18 = ref(false)
const rating = ref(0)
const seriesName = ref('')
const volume = ref(null)
const tagDrafts = ref({})
const inputVal = ref('')
const saving = ref(false)

// 系列下拉选项（来自已有系列）；tag 模式允许输入创建新系列
const seriesOptions = computed(() => (store.series || [])
  .filter(s => s.name)
  .map(s => ({ label: s.name, value: s.name })))

// 选中系列后预填下一可用卷号：已有系列 = 现有最大卷号 + 1（排除自身当前卷，
// 重编辑不串号）；新系列 = 1。清空系列时连带清空卷号（卷号语义上属于系列）
async function onSeriesChange(val) {
  const name = (val ?? '').toString().trim()
  if (!name) { volume.value = null; return }
  const s = (store.series || []).find(x => x.name === name)
  if (!s) { volume.value = 1; return }
  try {
    const vols = await api.seriesVolumes(s.id)
    const own = s.id === props.obj.series_id ? props.obj.volume : null
    const nums = vols.map(v => v.volume).filter(v => v != null && v !== own)
    volume.value = nums.length ? Math.max(...nums) + 1 : 1
  } catch {
    volume.value = 1
  }
}

watch(() => props.show, v => {
  if (!v || !props.obj) return
  name.value = props.obj.name || ''
  r18.value = !!props.obj.tags?.r18
  rating.value = Number(props.obj.tags?.rating?.[0] || 0)
  seriesName.value = props.obj.series_name || null
  volume.value = props.obj.volume == null ? null : Number(props.obj.volume)
  const draft = {}
  for (const cat of CATS) draft[cat] = [...(props.obj.tags?.[cat] || [])]
  tagDrafts.value = draft
})

function suggestions(cat) {
  const all = store.tagValues[cat] || []
  const cur = tagDrafts.value[cat] || []
  return all.filter(v => !cur.includes(v)).map(v => ({ label: v, value: v }))
}

async function save() {
  if (!name.value.trim()) { message.warning('名称不能为空'); return }
  saving.value = true
  try {
    const tags = {}
    for (const cat of CATS) if (tagDrafts.value[cat]?.length) tags[cat] = tagDrafts.value[cat]
    if (rating.value) tags.rating = [String(rating.value)]
    tags.r18 = r18.value
    // 系列名：空串转 null（清除）；卷号：空转 null（清除）。始终携带，保证幂等
    const sn = (seriesName.value ?? '').toString().trim()
    await api.updateObject(props.obj.id, {
      name: name.value.trim(),
      tags,
      series_name: sn || null,
      volume: volume.value == null ? null : Number(volume.value),
    })
    if (sn) loadSeries()   // 新建系列后刷新下拉列表
    message.success('已保存')
    emit('update:show', false)
    emit('saved')
  } catch (e) {
    message.error(e.message || String(e))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.form { display: flex; flex-direction: column; gap: 8px; }
.field-label { font-size: 12px; font-weight: 700; opacity: .6; margin-top: 8px; letter-spacing: 1px; }
.hint-inline { font-weight: 400; letter-spacing: 0; opacity: .75; margin-left: 6px; }
/* R-18 行内布局：标签与开关同行居中，避免开关独占一行视觉错位 */
.r18-row { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.r18-row .field-label { margin-top: 0; }
.r18-label { color: var(--ms-danger); }
.volume-input { width: 160px; }
.footer { display: flex; justify-content: flex-end; gap: 10px; }
</style>
