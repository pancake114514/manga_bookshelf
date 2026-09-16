<template>
  <div class="topbar">
    <!-- 虚拟框一：与左侧栏等宽，logo 保持左对齐（与侧栏分隔线位置分割，不画线） -->
    <div class="tb-logo-box">
      <span class="logo">MangaShelf</span>
    </div>
    <!-- 虚拟框二：内容区，搜索框左缘对齐第一列卡片左缘 -->
    <div class="tb-search-box">
      <n-input ref="searchEl" v-model:value="kw" class="search" round
               placeholder="搜索对象名或标签…  (Ctrl+F)" clearable>
        <template #prefix><IconSearch :size="15" /></template>
      </n-input>
      <div class="spacer" />
      <n-switch :value="store.theme === 'dark'" size="small" @update:value="toggleTheme">
        <template #checked><IconMoon :size="12" /></template>
        <template #unchecked><IconSun :size="12" /></template>
      </n-switch>
      <n-button @click="store.ui.library = true">
        <template #icon><IconLibrary :size="15" /></template>
        库管理
      </n-button>
      <n-button type="primary" @click="store.ui.import = true">
        <template #icon><IconFolderPlus :size="15" /></template>
        导入
      </n-button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { NInput, NButton, NSwitch } from 'naive-ui'
import { store, toggleTheme } from '../store'
import { debounce } from '../utils'
import {
  IconSearch, IconMoon, IconSun, IconLibrary, IconFolderPlus,
} from './icons'

const kw = ref(store.keyword)
const searchEl = ref(null)

const applyKeyword = debounce(v => { store.keyword = v }, 200)
watch(kw, applyKeyword)

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
  padding-right: 18px;
  border-bottom: 1px solid var(--border);
}
.tb-logo-box {
  flex: none; width: var(--sidebar-w);
  display: flex; align-items: center;
  padding-left: 18px;
}
.tb-search-box {
  flex: 1; min-width: 0;
  display: flex; align-items: center; gap: 12px;
  padding-left: var(--content-pad);
}
.logo { font-family: Georgia, serif; font-size: 17px; font-weight: 700; letter-spacing: .5px; }
.search { max-width: 380px; }
.spacer { flex: 1; }
</style>
