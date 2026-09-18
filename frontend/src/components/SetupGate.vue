<template>
  <div class="setup-wrap">
    <n-card class="setup-card" :title="'欢迎使用 MangaShelf'">
      <p class="desc">
        请选择一个目录作为图库的存储根目录，所有导入的图片将被复制到该目录下管理。<br>
        注意：请选择有写入权限的目录（避免 Program Files 等系统目录）。
      </p>
      <n-input-group>
        <n-input v-model:value="path" placeholder="选择目录…" readonly />
        <n-button @click="browse">浏览…</n-button>
      </n-input-group>
      <n-alert v-if="warn" type="error" class="warn">{{ warn }}</n-alert>
      <template #footer>
        <n-button type="primary" block :disabled="!path" :loading="saving" @click="confirm">
          确定并开始使用
        </n-button>
        <n-text v-if="!bridgeOk" depth="3" class="hint">
          当前为浏览器调试模式：无法打开系统目录选择框，可手动输入路径后回车
        </n-text>
      </template>
    </n-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { NCard, NButton, NInput, NInputGroup, NAlert, NText, useMessage } from 'naive-ui'
import { api, dialog } from '../api'
import { store } from '../store'

const message = useMessage()
const path = ref('')
const warn = ref('')
const saving = ref(false)
const bridgeOk = ref(true)

async function browse() {
  const dir = await dialog.pickDir('选择图库根目录')
  if (dir) path.value = dir
}

async function confirm() {
  if (!path.value) return
  saving.value = true
  try {
    await api.setup(path.value)
    store.storageRoot = path.value
    message.success('图库目录已设置')
  } catch (e) {
    warn.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.setup-wrap {
  height: 100vh; display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.setup-card { width: 520px; }
.desc { margin-bottom: 16px; line-height: 1.7; }
.warn { margin-top: 12px; }
.hint { display: block; margin-top: 10px; font-size: 12px; }
</style>
