// 侧栏共用逻辑：宽度/收起态计算、拖动分隔条、切换
// 状态存于 store（ui.sidebar / sidebarW），持久化由 store 的 setter 负责；
// 拖动过程中只改内存态，松手才落盘（避免拖动期间高频写配置）
import { store, setSidebarCollapsed, setSidebarWidth } from './store'

export const SIDEBAR_RAIL = 28     // 收起后的细条宽
export const SIDEBAR_MIN = 180     // 拖动调宽下限
export const SIDEBAR_MAX = 400     // 拖动调宽上限
export const SIDEBAR_SNAP = 110    // 拖到此宽度以下松手 → 吸附为收起态

// 当前视图侧栏的有效宽度（收起 → 细条宽）
export function sidebarWidth(view) {
  return store.ui.sidebar[view] ? SIDEBAR_RAIL : store.sidebarW[view]
}

export function toggleSidebar(view) {
  if (view !== 'shelf' && view !== 'directory') return
  setSidebarCollapsed(view, !store.ui.sidebar[view])
}

// 拖动分隔条：pointermove 实时调宽，低于吸附阈值进入收起态预览；
// 从收起细条向右拖 = 直接拖出恢复。拖动期间置 store.sidebarDragging
// 供全局禁用宽度过渡（否则拖动会拖着动画尾巴）
export function startSidebarDrag(view, e) {
  if (e.button !== 0) return
  e.preventDefault()
  const startX = e.clientX
  const startW = sidebarWidth(view)
  store.sidebarDragging = view
  const move = ev => {
    const w = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_RAIL, startW + ev.clientX - startX))
    if (w < SIDEBAR_SNAP) {
      store.ui.sidebar[view] = true
    } else {
      store.ui.sidebar[view] = false
      store.sidebarW[view] = Math.round(Math.max(SIDEBAR_MIN, w))
    }
  }
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    store.sidebarDragging = null
    setSidebarCollapsed(view, store.ui.sidebar[view])
    if (!store.ui.sidebar[view]) setSidebarWidth(view, store.sidebarW[view])
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}
