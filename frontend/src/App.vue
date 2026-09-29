<template>
  <n-config-provider :theme="naiveTheme(store.theme)" :theme-overrides="themeOverrides(store.theme)">
    <n-message-provider>
      <n-dialog-provider>
        <div class="app-shell" :class="[`theme-${store.theme}`, { 'sidebar-dragging': !!store.sidebarDragging }]"
             :style="[cssVars(store.theme), { '--sidebar-w': sidebarW + 'px' }]">
          <TitleBar v-if="showTitleBar" />
          <EdgeResize />
          <template v-if="store.ready">
            <SetupGate v-if="!store.storageRoot" />
            <template v-else>
              <TopBar v-if="store.view.name !== 'reader'" />
              <div class="app-main">
                <TagSidebar v-if="showSidebar" />
                <DirectorySidebar v-else-if="store.view.name === 'directory'" :obj="store.directory.obj" />
                <Bookshelf v-if="store.view.name === 'shelf'" />
                <DirectoryView v-else-if="store.view.name === 'directory'" :obj="store.directory.obj" />
                <Reader v-else-if="store.view.name === 'reader'" />
              </div>
              <ImportDialog v-model:show="store.ui.import" @done="store.reloadTick++" />
              <LibraryDialog v-model:show="store.ui.library" />
            </template>
          </template>
          <div v-else-if="store.bootError" class="boot-error">
            <n-result status="error" title="启动失败" :description="store.bootError">
              <template #footer>
                <n-button type="primary" @click="retry">重试</n-button>
              </template>
            </n-result>
          </div>
          <div v-else class="boot-loading"><n-spin size="large" /></div>
        </div>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { NConfigProvider, NMessageProvider, NDialogProvider, NSpin, NResult, NButton } from 'naive-ui'
import { store, boot } from './store'
import { naiveTheme, themeOverrides, cssVars } from './theme'
import { sidebarWidth, toggleSidebar } from './sidebar'
import SetupGate from './components/SetupGate.vue'
import TitleBar from './components/TitleBar.vue'
import TopBar from './components/TopBar.vue'
import EdgeResize from './components/EdgeResize.vue'
import TagSidebar from './components/TagSidebar.vue'
import DirectorySidebar from './components/DirectorySidebar.vue'
import Bookshelf from './components/Bookshelf.vue'
import DirectoryView from './components/DirectoryView.vue'
import Reader from './components/Reader.vue'
import ImportDialog from './components/ImportDialog.vue'
import LibraryDialog from './components/LibraryDialog.vue'

// 主界面侧栏：书架用标签筛选；详情页用对象侧栏（组件内部按内容动态隐藏）
const showSidebar = computed(() => store.view.name === 'shelf')
const showTitleBar = computed(() => !store.ready || !store.storageRoot)

// 当前视图侧栏有效宽度 → 行内 --sidebar-w：顶栏虚拟框分割/卡片左缘对齐随动
const sidebarW = computed(() => {
  const v = store.view.name
  return (v === 'shelf' || v === 'directory') ? sidebarWidth(v) : 228
})

// Ctrl+B：切换当前视图侧栏（输入框内不劫持）
function onKey(e) {
  if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'b') return
  const t = e.target
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
  const v = store.view.name
  if (v === 'shelf' || v === 'directory') { e.preventDefault(); toggleSidebar(v) }
}

function retry() { boot() }
onMounted(() => { boot(); window.addEventListener('keydown', onKey) })
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.boot-loading, .boot-error {
  height: 100vh; display: flex; align-items: center; justify-content: center;
}
</style>
