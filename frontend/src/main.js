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
