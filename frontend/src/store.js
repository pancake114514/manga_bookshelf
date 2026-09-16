import { reactive } from 'vue'
import { api } from './api'

// 全局状态：视图切换 + 书架数据 + 筛选/主题
export const store = reactive({
  ready: false,
  storageRoot: null,

  theme: 'dark',
  r18: false,
  keyword: '',
  filters: {},          // { cat: [values] }
  tagValues: {},        // { cat: [values] }

  objects: [],          // 最近一次查询结果
  view: { name: 'shelf' },   // shelf | directory | reader

  // 阅读器上下文
  reader: null,         // { obj, images, index }
  directory: null,      // { obj }
})

export async function boot() {
  const st = await api.state()
  store.storageRoot = st.valid ? st.storage_root : null
  const saved = await api.getConfig('ui_theme').catch(() => ({ value: null }))
  if (saved.value === 'light' || saved.value === 'dark') store.theme = saved.value
  if (store.storageRoot) {
    store.tagValues = await api.tagValues().catch(() => ({}))
  }
  store.ready = true
}

export async function refreshTagValues() {
  store.tagValues = await api.tagValues().catch(() => ({}))
}

export function toggleTheme() {
  store.theme = store.theme === 'dark' ? 'light' : 'dark'
  api.setConfig('ui_theme', store.theme).catch(() => {})
}

export function selectedFilterCount() {
  return Object.values(store.filters).reduce((n, v) => n + v.length, 0)
}
