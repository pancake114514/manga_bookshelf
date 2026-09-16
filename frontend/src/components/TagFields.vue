<template>
  <template v-for="cat in cats" :key="cat">
    <div class="field-label">{{ catLabel(cat) }}</div>
    <n-dynamic-tags v-model:value="draft[cat]" />
  </template>
  <div class="field-label r18-label">R-18</div>
  <n-switch :value="props.tags.r18 === true"
            @update:value="v => emit('update:tags', { ...props.tags, r18: v })" />
</template>

<script setup>
import { reactive, watch } from 'vue'
import { NDynamicTags, NSwitch } from 'naive-ui'
import { CATS, catLabel } from '../constants'

const props = defineProps({ tags: { type: Object, default: () => ({}) } })
const emit = defineEmits(['update:tags'])

const draft = reactive({ work: [], author: [], character: [], cm: [], censored: [] })

watch(() => props.tags, t => {
  for (const cat of CATS) draft[cat] = [...(t?.[cat] || [])]
}, { immediate: true, deep: true })

// 任一类别变化时同步上抛
for (const cat of CATS) {
  watch(() => draft[cat], vals => {
    emit('update:tags', { ...props.tags, [cat]: [...vals] })
  }, { deep: true })
}
</script>

<style scoped>
.field-label { font-size: 12px; font-weight: 700; opacity: .6; margin: 12px 0 6px; letter-spacing: 1px; }
.r18-label { color: var(--ms-danger); }
</style>
