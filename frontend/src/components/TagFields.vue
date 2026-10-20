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

const sameList = (a, b) =>
  a.length === b.length && a.every((v, i) => v === b[i])

// props → draft：仅在内容实际变化时赋值。
// 两侧互相 watch 时若每次都重建数组引用，会形成
// 编辑 → emit → props 变 → 重建 draft → 再 emit 的无界循环（Vue 报递归上限并卡顿），
// 因此比较内容后再决定是否同步。
watch(() => props.tags, t => {
  for (const cat of CATS) {
    const incoming = t?.[cat] || []
    if (!sameList(draft[cat], incoming)) draft[cat] = [...incoming]
  }
}, { immediate: true, deep: true })

// 任一类别变化时同步上抛（内容与外部一致时不再 emit，彻底切断回流）
for (const cat of CATS) {
  watch(() => draft[cat], vals => {
    const prev = props.tags?.[cat] || []
    if (sameList(prev, vals)) return
    emit('update:tags', { ...props.tags, [cat]: [...vals] })
  }, { deep: true })
}
</script>

<style scoped>
.field-label { font-size: 12px; font-weight: 700; opacity: .6; margin: 12px 0 6px; letter-spacing: 1px; }
.r18-label { color: var(--ms-accent-text); }
</style>
