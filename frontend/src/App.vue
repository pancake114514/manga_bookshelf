<template>
  <n-config-provider :theme="naiveTheme(store.theme)" :theme-overrides="themeOverrides(store.theme)">
    <n-message-provider>
      <n-dialog-provider>
        <div class="app-shell" :class="`theme-${store.theme}`" :style="cssVars(store.theme)">
          <!-- 无边框窗口的自定义标题栏（仅桌面模式渲染）：主视图的窗口按钮已并入
               TopBar 行尾，此处只为无顶栏工具行的视图（阅读器/首启向导）保留独立条 -->
          <TitleBar v-if="showTitleBar" />
          <template v-if="store.ready">
            <SetupGate v-if="!store.storageRoot" />
            <template v-else>
              <TopBar v-if="store.view.name !== 'reader'" />
              <div class="app-main">
                <TagSidebar v-if="showSidebar" />
                <Bookshelf v-if="store.view.name === 'shelf'" />
                <DirectoryView v-else-if="store.view.name === 'directory'" :obj="store.directory.obj" />
                <Reader v-else-if="store.view.name === 'reader'" />
              </div>
              <!-- 全局对话框：统一挂载在应用层，开关状态在 store.ui -->
              <ImportDialog v-model:show="store.ui.import" @done="store.reloadTick++" />
              <LibraryDialog v-model:show="store.ui.library" />
            </template>
          </template>
          <div v-else-if="store.bootError" class="boot-error">
            <n-result status="error" title="无法连接本地服务" :description="store.bootError">
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
import { computed, onMounted } from 'vue'
import { NConfigProvider, NMessageProvider, NDialogProvider, NSpin, NResult, NButton } from 'naive-ui'
import { store, boot } from './store'
import { naiveTheme, themeOverrides, cssVars } from './theme'
import SetupGate from './components/SetupGate.vue'
import TitleBar from './components/TitleBar.vue'
import TopBar from './components/TopBar.vue'
import TagSidebar from './components/TagSidebar.vue'
import Bookshelf from './components/Bookshelf.vue'
import DirectoryView from './components/DirectoryView.vue'
import Reader from './components/Reader.vue'
import ImportDialog from './components/ImportDialog.vue'
import LibraryDialog from './components/LibraryDialog.vue'

const showSidebar = computed(() =>
  store.view.name === 'shelf' || store.view.name === 'directory')
// 独立标题栏条只在无 TopBar 的视图出现（主视图窗口按钮由 TopBar 行尾提供）
const showTitleBar = computed(() =>
  !store.ready || !store.storageRoot || store.view.name === 'reader')

function retry() { boot() }

onMounted(() => boot())
</script>

<style scoped>
.boot-loading,
.boot-error {
  height: 100vh; display: flex; align-items: center; justify-content: center;
}
</style>
