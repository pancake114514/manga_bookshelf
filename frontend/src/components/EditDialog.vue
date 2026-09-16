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

      <div class="field-label r18-label">R-18</div>
      <n-switch v-model:value="r18" />
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
import { NModal, NInput, NButton, NSwitch, NRate, NDynamicTags, NAutoComplete, useMessage } from 'naive-ui'
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
const tagDrafts = ref({})
const inputVal = ref('')
const saving = ref(false)

watch(() => props.show, v => {
  if (!v || !props.obj) return
  name.value = props.obj.name || ''
  r18.value = !!props.obj.tags?.r18
  rating.value = Number(props.obj.tags?.rating?.[0] || 0)
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
    await api.updateObject(props.obj.id, { name: name.value.trim(), tags })
    message.success('已保存')
    emit('update:show', false)
    emit('saved')
  } catch (e) {
    message.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.form { display: flex; flex-direction: column; gap: 8px; }
.field-label { font-size: 12px; font-weight: 700; opacity: .6; margin-top: 8px; letter-spacing: 1px; }
.r18-label { color: var(--ms-danger); }
.footer { display: flex; justify-content: flex-end; gap: 10px; }
</style>
