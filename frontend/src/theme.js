// Naive UI 主题配置：对应设计稿的深/浅两套调色板
import { darkTheme } from 'naive-ui'

export const darkCommon = {
  primary: '#63e2b7',
  primaryHover: '#7fe7c4',
  primaryPressed: '#5acea7',
  bodyColor: '#101014',
  cardColor: '#1e1e26',
  modalColor: '#1e1e26',
  popoverColor: '#24242e',
  borderColor: 'rgba(255,255,255,.09)',
  dividerColor: 'rgba(255,255,255,.09)',
  textColorBase: '#ececf1',
  textColor1: '#ececf1',
  textColor2: '#a0a0ac',
  textColor3: '#6b6b78',
  borderRadius: '8px',
  fontFamily: '"Segoe UI", "Microsoft YaHei UI", sans-serif',
}

export const lightCommon = {
  primary: '#18a058',
  primaryHover: '#36ad6a',
  primaryPressed: '#0c7a43',
  bodyColor: '#f5f6f8',
  cardColor: '#ffffff',
  modalColor: '#ffffff',
  popoverColor: '#ffffff',
  borderColor: 'rgba(0,0,0,.09)',
  dividerColor: 'rgba(0,0,0,.09)',
  textColorBase: '#1f1f25',
  textColor1: '#1f1f25',
  textColor2: '#55555e',
  textColor3: '#9a9aa2',
  borderRadius: '8px',
  fontFamily: '"Segoe UI", "Microsoft YaHei UI", sans-serif',
}

export function naiveTheme(theme) {
  return theme === 'dark' ? darkTheme : null
}

export function themeOverrides(theme) {
  return { common: theme === 'dark' ? darkCommon : lightCommon }
}
