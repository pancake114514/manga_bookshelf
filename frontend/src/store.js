import { reactive } from 'vue'
import { api } from './api'

// UI 偏好的 config 键
const CFG = {
  theme: 'ui_theme',
  r18: 'ui_r18',
  sort: 'ui_sort',
  density: 'ui_density',
  grouped: 'ui_shelf_grouped',
  // 侧栏：分视图记忆收起态与宽度（书架看筛选常开、详情看内容常关的习惯不同）
  sidebarShelf: 'ui_sidebar_shelf',
  sidebarDir: 'ui_sidebar_directory',
  sidebarWShelf: 'ui_sidebar_w_shelf',
  sidebarWDir: 'ui_sidebar_w_directory',
}
const DENSITIES = ['compact', 'standard', 'large']
const SIDEBAR_W_MIN = 180, SIDEBAR_W_MAX = 400
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
  grouped: false,

  objects: [],
  series: [],
  reloadTick: 0,
  view: { name: 'shelf' }, // shelf | directory | reader

  deleting: 0,   // 正在执行中的删除任务数（顶栏提示/退出确认依据）

  ui: { import: false, library: false, sidebar: { shelf: false, directory: false } },
  sidebarW: { shelf: 228, directory: 228 },
  sidebarDragging: null,   // 拖动分隔条中的视图名：用于全局禁用宽度过渡

  reader: null,
  directory: null,
})

export async function boot() {
  store.bootError = null
  try {
    const st = await api.state()
    store.storageRoot = st.valid ? st.storage_root : null
    const [theme, r18, sort, density, grouped, sbShelf, sbDir, sbWShelf, sbWDir] = await Promise.all([
      readConfig(CFG.theme), readConfig(CFG.r18),
      readConfig(CFG.sort), readConfig(CFG.density), readConfig(CFG.grouped),
      readConfig(CFG.sidebarShelf), readConfig(CFG.sidebarDir),
      readConfig(CFG.sidebarWShelf), readConfig(CFG.sidebarWDir),
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
    store.grouped = grouped === '1'
    store.ui.sidebar.shelf = sbShelf === '1'
    store.ui.sidebar.directory = sbDir === '1'
    const wShelf = parseInt(sbWShelf, 10)
    if (wShelf >= SIDEBAR_W_MIN && wShelf <= SIDEBAR_W_MAX) store.sidebarW.shelf = wShelf
    const wDir = parseInt(sbWDir, 10)
    if (wDir >= SIDEBAR_W_MIN && wDir <= SIDEBAR_W_MAX) store.sidebarW.directory = wDir
    if (store.storageRoot) {
      store.tagValues = await api.tagValues().catch(() => ({}))
      await loadSeries()
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

export async function loadSeries() {
  store.series = await api.series().catch(() => [])
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

export function setGrouped(v) {
  store.grouped = !!v
  api.setConfig(CFG.grouped, v ? '1' : '0').catch(() => {})
}

// 侧栏收起态 / 宽度：view = 'shelf' | 'directory'
export function setSidebarCollapsed(view, v) {
  store.ui.sidebar[view] = !!v
  api.setConfig(view === 'shelf' ? CFG.sidebarShelf : CFG.sidebarDir, v ? '1' : '0').catch(() => {})
}
export function setSidebarWidth(view, w) {
  w = Math.round(Math.min(SIDEBAR_W_MAX, Math.max(SIDEBAR_W_MIN, w)))
  store.sidebarW[view] = w
  api.setConfig(view === 'shelf' ? CFG.sidebarWShelf : CFG.sidebarWDir, String(w)).catch(() => {})
}
