<template>
  <div class="topbar">
    <span class="logo">MangaShelf</span>
    <n-input v-model:value="kw" class="search" round placeholder="搜索对象名或标签…  (Ctrl+F)" clearable>
      <template #prefix>🔍</template>
    </n-input>
    <div class="spacer" />
    <n-switch :value="store.theme === 'dark'" size="small" @update:value="toggleTheme">
      <template #checked>深色</template>
      <template #unchecked>浅色</template>
    </n-switch>
    <n-button @click="libraryDlg = true">库管理</n-button>
    <n-button type="primary" @click="importDlg = true">＋ 导入</n-button>
  </div>

  <ImportDialog v-model:show="importDlg" />
  <LibraryDialog v-model:show="libraryDlg" />
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { NInput, NButton, NSwitch } from 'naive-ui'
import { store, toggleTheme } from '../store'
import ImportDialog from './ImportDialog.vue'
import LibraryDialog from './LibraryDialog.vue'

const kw = ref(store.keyword)
const importDlg = ref(false)
const libraryDlg = ref(false)

let timer = null
watch(kw, v => {
  clearTimeout(timer)
  timer = setTimeout(() => { store.keyword = v }, 200)
})

function onKey(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
    e.preventDefault()
    document.querySelector('.topbar input')?.focus()
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
  border-bottom: 1px solid var(--border, rgba(128,128,128,.2));
}
.logo { font-family: Georgia, serif; font-size: 17px; font-weight: 700; letter-spacing: .5px; }
.search { max-width: 380px; }
.spacer { flex: 1; }
</style>
