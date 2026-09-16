import { reactive } from 'vue'
import { api } from './api'

// UI 偏好的 config 键（后端 config 表 KV，值统一为字符串）
const CFG = {
  theme: 'ui_theme',
  r18: 'ui_r18',
  sort: 'ui_sort',
  density: 'ui_density',
}
const DENSITIES = ['compact', 'standard', 'large']
const DEFAULT_SORT = { key: 'created_at', desc: true }

function readConfig(key) {
  return api.getConfig(key).then(r => r.value).catch(() => null)
}

// 全局状态：视图切换 + 书架数据 + 筛选/主题/偏好
export const store = reactive({
  ready: false,
  bootError: null,      // 启动失败信息（后端未就绪等），非空时展示错误态
  storageRoot: null,

  theme: 'dark',
  r18: false,
  keyword: '',
  filters: {},          // { cat: [values] }
  tagValues: {},        // { cat: [values] }

  // 书架偏好（持久化到后端 config）
  sort: { ...DEFAULT_SORT },   // { key: created_at|name|images|rating|progress, desc }
  density: 'standard',         // compact | standard | large

  objects: [],          // 最近一次查询结果（书架与「追加导入」下拉共用）
  reloadTick: 0,        // 导入等外部操作后 +1，书架监听后静默刷新
  view: { name: 'shelf' },   // shelf | directory | reader

  // 全局对话框开关（对话框统一挂载在 App 层）
  ui: { import: false, library: false },

  // 阅读器上下文
  reader: null,         // { obj, images, index }
  directory: null,      // { obj }
})

export async function boot() {
  store.bootError = null
  try {
    const st = await api.state()
    store.storageRoot = st.valid ? st.storage_root : null
    const [theme, r18, sort, density] = await Promise.all([
      readConfig(CFG.theme), readConfig(CFG.r18), readConfig(CFG.sort), readConfig(CFG.density),
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
