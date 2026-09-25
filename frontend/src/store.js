import { reactive } from 'vue'
import { api } from './api'

// UI 偏好的 config 键
const CFG = {
  theme: 'ui_theme',
  r18: 'ui_r18',
  sort: 'ui_sort',
  density: 'ui_density',
}
const DENSITIES = ['compact', 'standard', 'large']
const DEFAULT_SORT = { key: 'created_at', desc: true }

function readConfig(key) {
  return Promise.resolve(api.getConfig(key)).catch(() => null)
}

// 全局状态
export const store = reactive({
  ready: false,
  bootError: null,
  storageRoot: null,

  theme: 'dark',
  r18: false,
  keyword: '',
  filters: {},
  tagValues: {},

  sort: { ...DEFAULT_SORT },
  density: 'standard',

  objects: [],
  reloadTick: 0,
  view: { name: 'shelf' }, // shelf | directory | reader

  deleting: 0,   // 正在执行中的删除任务数（顶栏提示/退出确认依据）

  ui: { import: false, library: false },

  reader: null,
  directory: null,
})

export async function boot() {
  store.bootError = null
  try {
    const st = await api.state()
    store.storageRoot = st.valid ? st.storage_root : null
    const [theme, r18, sort, density] = await Promise.all([
      readConfig(CFG.theme), readConfig(CFG.r18),
      readConfig(CFG.sort), readConfig(CFG.density),
    ])
    if (theme === 'light' || theme === 'dark') store.theme = theme
    store.r18 = r18 === '1'
    try {
      if (sort) {
        const s = JSON.parse(sort)
        if (s && typeof s.key === 'string') store.sort = { key: s.key, desc: !!s.desc }
      }
    } catch { /* 忽略损坏的偏好值 */ }
    if (DENSITIES.includes(density)) store.density = density
    if (store.storageRoot) {
      store.tagValues = await api.tagValues().catch(() => ({}))
    }
  } catch (e) {
    store.bootError = e.message || String(e)
  } finally {
    store.ready = true
  }
}

export async function refreshTagValues() {
  store.tagValues = await api.tagValues().catch(() => ({}))
}

export function toggleTheme() {
  store.theme = store.theme === 'dark' ? 'light' : 'dark'
  api.setConfig(CFG.theme, store.theme).catch(() => {})
}

export function setR18(v) {
  store.r18 = v
  api.setConfig(CFG.r18, v ? '1' : '0').catch(() => {})
}

export function setSort(sort) {
  store.sort = { ...sort }
  api.setConfig(CFG.sort, JSON.stringify(store.sort)).catch(() => {})
}

export function setDensity(d) {
  if (!DENSITIES.includes(d)) return
  store.density = d
  api.setConfig(CFG.density, d).catch(() => {})
}
