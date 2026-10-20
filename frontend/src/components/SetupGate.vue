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
      </template>
    </n-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { NCard, NButton, NInput, NInputGroup, NAlert, useMessage } from 'naive-ui'
import { api, dialog } from '../api'
import { store } from '../store'

const message = useMessage()
const path = ref('')
const warn = ref('')
const saving = ref(false)

async function browse() {
  const dir = await dialog.pickDir('选择图库根目录')
  if (dir) path.value = dir
}

async function confirm() {
  if (!path.value) return
  saving.value = true
  try {
    // 后端对不可写目录返回 Ok({ok:false})，不是 reject：必须查 ok 字段，
    // 否则只读目录会被当作设置成功，重启后又回到本页
    const res = await api.setup(path.value)
    if (!res.ok) {
      warn.value = res.error || '该目录不可写，请换一个目录'
      return
    }
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
</style>
