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
      <n-auto-complete v-model:value="seriesName" :options="seriesOptions"
                       placeholder="输入或选择系列名（留空则清除）" clearable />

      <div class="field-label">卷号</div>
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
import { NModal, NInput, NInputNumber, NButton, NSwitch, NRate, NDynamicTags, NAutoComplete, useMessage } from 'naive-ui'
import { api } from '../api'
import { store } from '../store'
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

// 系列名自动补全：来自 store.series 的 name，允许自由输入新名
const seriesOptions = computed(() => (store.series || []).map(s => s.name).filter(Boolean))

watch(() => props.show, v => {
  if (!v || !props.obj) return
  name.value = props.obj.name || ''
  r18.value = !!props.obj.tags?.r18
  rating.value = Number(props.obj.tags?.rating?.[0] || 0)
  seriesName.value = props.obj.series_name || ''
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
    const sn = seriesName.value.trim()
    await api.updateObject(props.obj.id, {
      name: name.value.trim(),
      tags,
      series_name: sn || null,
      volume: volume.value == null ? null : Number(volume.value),
    })
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
/* R-18 行内布局：标签与开关同行居中，避免开关独占一行视觉错位 */
.r18-row { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.r18-row .field-label { margin-top: 0; }
.r18-label { color: var(--ms-danger); }
.volume-input { width: 160px; }
.footer { display: flex; justify-content: flex-end; gap: 10px; }
</style>
