<template>
  <!-- 整条顶栏均可拖动：按下后移交系统原生拖动（还原最大化/贴靠由系统处理），
       交互控件以 mousedown.stop 排除 -->
  <div class="topbar" @mousedown="barMouseDown">
    <!-- 虚拟框一：与左侧栏等宽，logo 保持左对齐（与侧栏分隔线位置分割，不画线）。
         收起态下侧栏仅剩 28px 细条，logo 被裁切只留侧栏切换钮 -->
    <div class="tb-logo-box">
      <n-button quaternary size="small" class="sb-toggle" title="切换侧栏（Ctrl+B）"
                @mousedown.stop @click="toggleSidebar(sidebarView)">
        <template #icon><IconPanelLeft :size="15" /></template>
      </n-button>
      <span class="logo">MangaShelf</span>
      <!-- 删除进行中提示：字号与搜索框文字一致（14px） -->
      <span v-if="store.deleting" class="del-busy">
        <n-spin :size="13" /> 正在删除
      </span>
    </div>
    <!-- 虚拟框二：内容区，搜索框左缘对齐第一列卡片左缘 -->
    <div class="tb-search-box">
      <div class="search-wrap">
        <n-input ref="searchEl" v-model:value="kw" class="search" round
                 placeholder="搜索对象名或标签…  (Ctrl+F)" clearable
                 @mousedown.stop @focus="suggestOpen = true" @blur="suggestOpen = false">
          <template #prefix><IconSearch :size="15" /></template>
        </n-input>
        <!-- 搜索建议：匹配标签值/系列名，标注类别；点击以该词发起搜索 -->
        <div v-if="suggestOpen && suggestions.length" class="suggest-panel">
          <div v-for="s in suggestions" :key="s.key" class="suggest-item"
               @mousedown.prevent="pickSuggestion(s)">
            <span class="suggest-type">{{ s.type }}</span>
            <span class="suggest-value">{{ s.value }}</span>
          </div>
        </div>
      </div>
      <div class="spacer" />
      <n-switch class="theme-switch" :value="store.theme === 'dark'" size="small" @mousedown.stop @update:value="toggleTheme">
        <template #checked><IconMoon :size="12" /></template>
        <template #unchecked><IconSun :size="12" /></template>
      </n-switch>
      <n-button @mousedown.stop @click="store.ui.library = true">
        <template #icon><IconLibrary :size="15" /></template>
        库管理
      </n-button>
      <n-button type="primary" @mousedown.stop @click="store.ui.import = true">
        <template #icon><IconFolderPlus :size="15" /></template>
        导入
      </n-button>
    </div>
    <!-- 窗口按钮并入顶栏行尾并贴住窗口右缘，取消独立标题栏条 -->
    <WindowControls class="tb-win-controls" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { NInput, NButton, NSwitch, NSpin } from 'naive-ui'
import { store, toggleTheme } from '../store'
import { toggleSidebar } from '../sidebar'
import { catLabel } from '../constants'
import { debounce } from '../utils'
import { barMouseDown } from '../windowState'
import WindowControls from './WindowControls.vue'
import {
  IconSearch, IconMoon, IconSun, IconLibrary, IconFolderPlus, IconPanelLeft,
} from './icons'

// 侧栏切换钮作用的视图（阅读器视图不显示顶栏，无需兜底）
const sidebarView = computed(() => store.view.name)

const kw = ref(store.keyword)
const searchEl = ref(null)
const suggestOpen = ref(false)

const applyKeyword = debounce(v => { store.keyword = v }, 200)
watch(kw, applyKeyword)

// ── 搜索建议：当前输入匹配标签值与系列名，标注类别（作者/系列优先） ──
const suggestions = computed(() => {
  const q = kw.value.trim().toLowerCase()
  if (!q) return []
  const out = []
  for (const [cat, vals] of Object.entries(store.tagValues)) {
    if (cat === 'r18') continue
    for (const v of vals || []) {
      if (v.toLowerCase().includes(q)) out.push({ key: `t-${cat}-${v}`, type: catLabel(cat), value: v })
    }
  }
  for (const s of store.series || []) {
    const v = s.name
    if (v && v.toLowerCase().includes(q)) out.push({ key: `s-${v}`, type: '系列', value: v })
  }
  const pri = { '作者': 0, '系列': 1 }
  return out
    .sort((a, b) => (pri[a.type] ?? 2) - (pri[b.type] ?? 2))
    .slice(0, 8)
})

function pickSuggestion(s) {
  kw.value = s.value            // 触发 watch → store.keyword → 书架搜索
  suggestOpen.value = false
}

function onKey(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
    e.preventDefault()
    searchEl.value?.focus()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.topbar {
  height: 58px; flex: none;
  display: flex; align-items: stretch;
  /* 窗口按钮贴住窗口右缘，不预留右侧空白 */
  border-bottom: 1px solid var(--border);
}
.tb-logo-box {
  flex: none; width: var(--sidebar-w);
  display: flex; align-items: center; gap: 6px;
  padding-left: 8px;
  user-select: none;
  /* 侧栏收起/拖动时宽度随动：超出的 logo 文字裁掉，切换钮始终可见 */
  overflow: hidden; white-space: nowrap;
  transition: width .22s ease;
}
.sb-toggle { flex: none; }
.tb-search-box {
  flex: 1; min-width: 0;
  display: flex; align-items: center; gap: 12px;
  padding-left: var(--content-pad);
}
.logo { font-family: Georgia, serif; font-size: 17px; font-weight: 700; letter-spacing: .5px; }
/* 删除中提示：14px 与搜索框文字一致 */
.del-busy {
  display: inline-flex; align-items: center; gap: 5px;
  margin-left: 12px; font-size: 14px; color: var(--text2);
  user-select: none;
}
/* 搜索框：限制最宽 380，同时保底 200——窗口压到最小宽度时被压缩到不可用的程度 */
.search-wrap { position: relative; flex: 1; max-width: 380px; min-width: 200px; }
.search { width: 100%; }
/* 搜索建议面板：悬于搜索框正下方 */
.suggest-panel {
  position: absolute; top: 100%; left: 0; right: 0; margin-top: 6px; z-index: 60;
  background: var(--card, #fff);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, .18);
  overflow: hidden;
  user-select: none;
}
.suggest-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px; font-size: 13px; cursor: pointer;
}
.suggest-item:hover { background: var(--chip-bg); }
.suggest-type {
  flex: none; font-size: 11px; padding: 1px 6px; border-radius: 4px;
  background: var(--chip-bg); opacity: .85;
}
.suggest-value { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* 明暗切换开关：不可压缩，避免窄窗口时被挤压变形 */
.theme-switch { flex: none; }
.spacer { flex: 1; user-select: none; }
.tb-win-controls { margin-left: 12px; }
</style>
