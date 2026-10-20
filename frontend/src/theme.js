// Naive UI 主题配置：Minimalism & Swiss Style 深/浅两套调色板
// 纪律：纯黑白单色 + 单一强调色（瑞士红）、直角、无阴影无渐变、Inter 单字族字重分层
// 同时是 CSS 设计令牌的单一真源：cssVars() 把同一批值映射为 --xx 变量，
// 由 App.vue 绑定到 .app-shell，自绘 DOM（书架网格/阅读器等）一律引用变量，
// 避免与 Naive UI 令牌两处手工同步。
import { darkTheme } from 'naive-ui'

export const darkCommon = {
  primary: '#E30613',
  primaryHover: '#ff2b3a',
  primaryPressed: '#b30510',
  bodyColor: '#161616',
  surfaceColor: '#222222',
  cardColor: '#161616',
  modalColor: '#1f1f1f',
  popoverColor: '#1f1f1f',
  borderColor: '#333333',
  borderStrongColor: '#e8e8e8',
  chipBgColor: '#262626',
  overlayColor: 'rgba(0,0,0,.72)',
  r18Color: '#E30613',
  starColor: '#E30613',
  textColorBase: '#f2f2f2',
  textColor1: '#f2f2f2',
  textColor2: '#a8a8a8',
  textColor3: '#666666',
  borderRadius: '0px',
  fontFamily: '"Inter", "Helvetica Neue", "Segoe UI", "Microsoft YaHei UI", sans-serif',
}

export const lightCommon = {
  primary: '#E30613',
  primaryHover: '#c00510',
  primaryPressed: '#96040d',
  bodyColor: '#ffffff',
  surfaceColor: '#f5f5f5',
  cardColor: '#ffffff',
  modalColor: '#ffffff',
  popoverColor: '#ffffff',
  borderColor: '#e0e0e0',
  borderStrongColor: '#000000',
  chipBgColor: '#f0f0f0',
  overlayColor: 'rgba(255,255,255,.85)',
  r18Color: '#E30613',
  starColor: '#E30613',
  textColorBase: '#000000',
  textColor1: '#000000',
  textColor2: '#555555',
  textColor3: '#999999',
  borderRadius: '0px',
  fontFamily: '"Inter", "Helvetica Neue", "Segoe UI", "Microsoft YaHei UI", sans-serif',
}

// CSS 变量名 → 令牌键名（--text 用 textColorBase，与 Naive 的 textColor1 同值）
const CSS_VARS = {
  '--bg': 'bodyColor',
  '--surface': 'surfaceColor',
  '--card': 'cardColor',
  '--text': 'textColorBase',
  '--text2': 'textColor2',
  '--text3': 'textColor3',
  '--border': 'borderColor',
  '--border-strong': 'borderStrongColor',
  '--chip-bg': 'chipBgColor',
  '--ms-primary': 'primary',
  '--ms-overlay': 'overlayColor',
  '--ms-danger': 'r18Color',
  '--ms-star': 'starColor',
}

export function naiveTheme(theme) {
  return theme === 'dark' ? darkTheme : null
}

export function themeOverrides(theme) {
  return { common: theme === 'dark' ? darkCommon : lightCommon }
}

// 返回可直接绑定到 :style 的 CSS 自定义属性对象
export function cssVars(theme) {
  const c = theme === 'dark' ? darkCommon : lightCommon
  const vars = {}
  for (const [name, key] of Object.entries(CSS_VARS)) vars[name] = c[key]
  return vars
}
