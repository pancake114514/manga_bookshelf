// Tauri API 封装 — 替代原 fetch /api/* 调用
// 所有后端调用通过 Tauri IPC invoke，不再走 HTTP

import { invoke } from '@tauri-apps/api/core'
import { open as openDialog } from '@tauri-apps/plugin-dialog'
import { getCurrentWindow } from '@tauri-apps/api/window'

// ── 后端调用 ──────────────────────────────────────────────────────────────

export const api = {
  // 状态 / 初始化
  state: () => invoke('get_state'),
  setup: (path) => invoke('setup', { body: { path } }),
  checkWritable: (path) => invoke('check_writable', { body: { path } }),
  validateName: (name) => invoke('validate_name', { body: { name } }),

  // 对象查询
  objects: (q = '', includeR18 = false, filters = {}) =>
    invoke('get_objects', { q, includeR18, filters: JSON.stringify(filters) }),
  object: (id) => invoke('get_object_detail', { oid: id }),
  tagValues: () => invoke('get_tag_values'),

  // 对象变更
  updateObject: (id, patch) => invoke('update_object', { oid: id, body: patch }),
  deleteObject: (id, deleteFiles = false) =>
    invoke('delete_object', { oid: id, deleteFiles }),
  lastRead: (id, idx) => invoke('set_last_read', { oid: id, body: { idx } }),

  // 导入
  importDirectory: (body) => invoke('import_directory', { body }),
  importFiles: (body) => invoke('import_files', { body }),
  countImages: (dir) => invoke('count_images', { dir }),

  // 库管理
  migrate: (newRoot) => invoke('migrate', { body: { newRoot } }),
  pruneThumbCache: () => invoke('prune_thumb_cache'),
  verifyLibrary: () => invoke('verify_library'),
  applyVerifyFixes: (plan) => invoke('apply_verify_fixes', { plan }),

  // 系统集成
  openInExplorer: (id) => invoke('open_in_explorer', { oid: id }),

  // 配置
  getConfig: (key) => invoke('get_config_value', { key }).then(r => r.value),
  setConfig: (key, value) =>
    invoke('set_config_value', { body: { key, value } }),
}

// ── 窗口控制 ──────────────────────────────────────────────────────────────

export const win = {
  async minimize() {
    await getCurrentWindow().minimize()
  },
  async toggleMaximize() {
    const w = getCurrentWindow()
    if (await w.isMaximized()) {
      await w.unmaximize()
      return false
    } else {
      await w.maximize()
      return true
    }
  },
  async isMaximized() {
    return await getCurrentWindow().isMaximized()
  },
  async toggleFullscreen() {
    const w = getCurrentWindow()
    const isFs = await w.isFullscreen()
    await w.setFullscreen(!isFs)
    return !isFs
  },
  async exitFullscreen() {
    await getCurrentWindow().setFullscreen(false)
  },
  close() {
    getCurrentWindow().close()
  },
  // 无边框窗口拖拽 — Tauri 原生支持，只需调用 startDragging
  async startDrag() {
    await getCurrentWindow().startDragging()
  },
}

// ── 文件/目录选择对话框 ───────────────────────────────────────────────────

export const dialog = {
  async pickDir(title = '选择目录') {
    const result = await openDialog({ directory: true, title })
    return result || null
  },
  // 多选文件夹（每选中的一个即为一个漫画文件夹，下一级直接是内容图片）
  async pickDirs(title = '选择文件夹') {
    const result = await openDialog({ directory: true, multiple: true, title })
    if (!result) return []
    return Array.isArray(result) ? result : [result]
  },
  async pickFiles(title = '选择文件') {
    const result = await openDialog({
      multiple: true,
      title,
      filters: [{
        name: '图片文件',
        extensions: ['jpg', 'jpeg', 'png', 'bmp', 'webp', 'gif', 'tiff', 'tif'],
      }],
    })
    if (!result) return []
    return Array.isArray(result) ? result : [result]
  },
}

// ── 常量 ─────────────────────────────────────────────────────────────────

export const TAG_CATEGORIES = {
  work: '作品',
  author: '作者',
  character: '角色',
  cm: 'CM',
  censored: '修正',
  r18: 'R-18',
}

export const TAG_CATEGORY_ORDER = ['work', 'author', 'character', 'cm', 'censored', 'r18']
