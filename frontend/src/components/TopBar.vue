<template>
  <div class="topbar">
    <span class="logo">MangaShelf</span>
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
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { NInput, NButton, NSwitch } from 'naive-ui'
import { store, toggleTheme } from '../store'
import {
  IconSearch, IconMoon, IconSun, IconLibrary, IconFolderPlus,
} from './icons'

const kw = ref(store.keyword)
const searchEl = ref(null)

let timer = null
watch(kw, v => {
  clearTimeout(timer)
  timer = setTimeout(() => { store.keyword = v }, 200)
})

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
  display: flex; align-items: center; gap: 12px;
  padding: 0 18px;
  border-bottom: 1px solid var(--border);
}
.logo { font-family: Georgia, serif; font-size: 17px; font-weight: 700; letter-spacing: .5px; }
.search { max-width: 380px; }
.spacer { flex: 1; }
</style>
