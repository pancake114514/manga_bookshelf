<template>
  <aside class="sidebar">
    <div class="r18-row">
      <span class="r18-label">显示 R-18</span>
      <n-switch size="small" :value="store.r18" @update:value="setR18" />
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
import { store, setR18 } from '../store'
import { catLabel } from '../constants'

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
  border-right: 1px solid var(--border);
  overflow-y: auto;
}
.r18-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.r18-label { color: var(--ms-danger); font-size: 13px; font-weight: 600; }
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
  background: var(--chip-bg);
  transition: all .15s;
}
.chip:hover { border-color: var(--border-strong); }
.chip.active {
  background: var(--chip-bg);
  border-color: var(--ms-primary);
  color: var(--ms-primary);
}
.clear { margin-top: 8px; width: 100%; }
</style>
