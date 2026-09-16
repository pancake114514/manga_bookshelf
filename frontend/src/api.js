// 统一 API 封装：非 2xx 抛出后端 detail 信息
async function jfetch(url, opts = {}) {
  const r = await fetch(url, opts)
  if (!r.ok) {
    let msg = r.statusText
    try { const d = await r.json(); msg = typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail) } catch { /* ignore */ }
    throw new Error(msg)
  }
  const ct = r.headers.get('content-type') || ''
  return ct.includes('json') ? r.json() : r
}

const post = (url, body) => jfetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  state: () => jfetch('/api/state'),
  setup: (path) => post('/api/setup', { path }),
  checkWritable: (path) => post('/api/check-writable', { path }),
  validateName: (name) => post('/api/validate-name', { name }),

  objects: (q, includeR18, filters) =>
    jfetch(`/api/objects?q=${encodeURIComponent(q)}&include_r18=${includeR18}&filters=${encodeURIComponent(JSON.stringify(filters))}`),
  object: (id) => jfetch(`/api/objects/${id}`),
  tagValues: () => jfetch('/api/tag-values'),

  updateObject: (id, patch) => jfetch(`/api/objects/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  }),
  deleteObject: (id, deleteFiles) =>
    jfetch(`/api/objects/${id}?delete_files=${deleteFiles}`, { method: 'DELETE' }),
  lastRead: (id, idx) => post(`/api/objects/${id}/last-read`, { idx }),

  importDirectory: (body) => post('/api/import/directory', body),
  importFiles: (body) => post('/api/import/files', body),
  migrate: (newRoot) => post('/api/migrate', { new_root: newRoot }),

  getConfig: (key) => jfetch(`/api/config/${key}`),
  setConfig: (key, value) => jfetch('/api/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, value }),
  }),
}

// pywebview 桥：桌面模式下用原生对话框选目录/文件；浏览器模式降级
export const bridge = {
  available: () => typeof window !== 'undefined' && !!window.pywebview?.api,
  async pickDir(title = '选择目录') {
    if (this.available()) return await window.pywebview.api.pick_dir(title)
    return null
  },
  async pickFiles(title = '选择文件') {
    if (this.available()) return await window.pywebview.api.pick_files(title)
    return null
  },
}
