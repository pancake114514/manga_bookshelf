// 通用小工具
export function debounce(fn, ms) {
  let t = null
  return (...args) => {
    clearTimeout(t)
    t = setTimeout(() => fn(...args), ms)
  }
}

// 阅读进度百分比：last_read_idx 为 0 视为未读；末页视为读完（书架卡片与详情侧栏共用）
export function readProgressPct(obj) {
  const n = obj.image_count || 0
  const idx = obj.last_read_idx || 0
  if (n < 2 || idx <= 0) return 0
  return Math.min(100, Math.round((idx / (n - 1)) * 100))
}
