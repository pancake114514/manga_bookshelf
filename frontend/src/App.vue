<template>
  <n-config-provider :theme="naiveTheme(store.theme)" :theme-overrides="themeOverrides(store.theme)">
    <n-message-provider>
      <n-dialog-provider>
        <div class="app-shell" :class="`theme-${store.theme}`">
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
            </template>
          </template>
          <div v-else class="boot-loading"><n-spin size="large" /></div>
        </div>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { NConfigProvider, NMessageProvider, NDialogProvider, NSpin } from 'naive-ui'
import { store, boot } from './store'
import { naiveTheme, themeOverrides } from './theme'
import SetupGate from './components/SetupGate.vue'
import TopBar from './components/TopBar.vue'
import TagSidebar from './components/TagSidebar.vue'
import Bookshelf from './components/Bookshelf.vue'
import DirectoryView from './components/DirectoryView.vue'
import Reader from './components/Reader.vue'

const showSidebar = computed(() =>
  store.view.name === 'shelf' || store.view.name === 'directory')

onMounted(() => boot().catch(() => { store.ready = true }))
</script>

<style scoped>
.boot-loading {
  height: 100vh; display: flex; align-items: center; justify-content: center;
}
</style>
