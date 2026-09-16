<template>
  <aside class="sidebar">
    <div class="r18-row">
      <span class="r18-label">显示 R-18</span>
      <n-switch size="small" :value="store.r18" @update:value="v => store.r18 = v" />
    </div>

    <div v-for="(values, cat) in store.tagValues" :key="cat" class="group">
      <div class="group-title">{{ catLabel(cat) }}</div>
      <div class="chips">
        <span v-for="v in values" :key="v" class="chip"
              :class="{ active: (store.filters[cat] || []).includes(v) }"
              @click="toggle(cat, v)">{{ v }}</span>
      </div>
    </div>

    <n-button v-if="selectedCount" quaternary size="small" class="clear" @click="clearAll">
      清除全部筛选
    </n-button>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { NSwitch, NButton } from 'naive-ui'
import { store } from '../store'

const CAT_LABELS = { work: '作品', author: '作者', character: '角色', cm: 'CM', censored: '修正' }
const catLabel = c => CAT_LABELS[c] || c
const selectedCount = computed(() =>
  Object.values(store.filters).reduce((n, v) => n + v.length, 0))

function toggle(cat, val) {
  const arr = store.filters[cat] || []
  const next = arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val]
  if (next.length) store.filters = { ...store.filters, [cat]: next }
  else {
    const { [cat]: _drop, ...rest } = store.filters
    store.filters = rest
  }
}
function clearAll() { store.filters = {} }
</script>

<style scoped>
.sidebar {
  width: 228px; flex: none;
  padding: 18px 16px;
  border-right: 1px solid var(--border, rgba(128,128,128,.2));
  overflow-y: auto;
}
.r18-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.r18-label { color: #d03050; font-size: 13px; font-weight: 600; }
.group { margin-bottom: 16px; }
.group-title {
  font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
  opacity: .55; margin-bottom: 8px; text-transform: uppercase;
}
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  padding: 3px 10px; border-radius: 6px;
  border: 1px solid transparent;
  font-size: 12px; cursor: pointer; user-select: none;
  background: var(--chip-bg, rgba(128,128,128,.12));
  transition: all .15s;
}
.chip:hover { border-color: var(--border-strong, rgba(128,128,128,.4)); }
.chip.active {
  background: var(--chip-bg, rgba(24,160,88,.18));
  border-color: var(--ms-primary, #18a058);
  color: var(--ms-primary, #18a058);
}
.clear { margin-top: 8px; width: 100%; }
</style>
