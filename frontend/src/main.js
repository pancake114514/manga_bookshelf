import { createApp } from 'vue'
import App from './App.vue'
import './styles.css'

createApp(App).mount('#app')

// 全局禁用 WebView 默认右键菜单（桌面应用内无意义）；
// 输入框 / 文本域保留系统菜单，便于右键粘贴等操作
document.addEventListener('contextmenu', (e) => {
  const el = e.target
  if (el.closest?.('input, textarea') || el.isContentEditable) return
  e.preventDefault()
})

// 全局禁用浏览器快捷键（桌面应用内无意义，且刷新/缩放会破坏应用状态）：
// F5 / Ctrl+R 刷新；F12 / Ctrl+Shift+I / J / C 开发者工具；Ctrl+P 打印；
// Ctrl + 加/减/0 页面缩放
window.addEventListener('keydown', (e) => {
  const k = e.key.toLowerCase()
  if (e.key === 'F5' || (e.ctrlKey && k === 'r')) return e.preventDefault()
  if (e.key === 'F12') return e.preventDefault()
  if (e.ctrlKey && e.shiftKey && ['i', 'j', 'c'].includes(k)) return e.preventDefault()
  if (e.ctrlKey && k === 'p') return e.preventDefault()
  if (e.ctrlKey && ['+', '-', '=', '0'].includes(k)) return e.preventDefault()
}, true)
// Ctrl+滚轮缩放同样禁用（保留普通滚轮滚动）
window.addEventListener('wheel', (e) => {
  if (e.ctrlKey) e.preventDefault()
}, { passive: false })
