<template>
  <n-modal v-model:show="show" preset="card" title="库管理" style="width: 600px;">
    <p class="desc">
      修改库路径会迁移所有已导入对象到新的根目录。迁移完成前，当前库路径不会生效。
    </p>

    <div class="field-label">当前库路径</div>
    <n-input :value="store.storageRoot || '未设置'" readonly />

    <div class="field-label">新库路径</div>
    <n-input-group>
      <n-input v-model:value="newRoot" placeholder="选择新目录…" readonly />
      <n-button @click="browse">浏览…</n-button>
    </n-input-group>

    <n-alert v-if="errMsg" type="error" class="alert">{{ errMsg }}</n-alert>
    <n-progress v-if="busy" type="line" :show-indicator="false" processing />
    <p class="hint">
      迁移会同步更新对象目录、图片路径和封面路径。目标目录下若已存在同名目录，
      会自动添加序号后缀重命名；图库外的封面/图片路径不会随迁移更新，完成后会有提示。
    </p>

    <template #footer>
      <div class="footer">
        <n-button type="primary" :disabled="!newRoot || newRoot === store.storageRoot"
                  :loading="busy" @click="run">
          开始迁移
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, computed } from 'vue'
import { NModal, NButton, NInput, NInputGroup, NAlert, NProgress, useMessage } from 'naive-ui'
import { api, dialog } from '../api'
import { store } from '../store'

const props = defineProps({ show: Boolean })
const emit = defineEmits(['update:show'])

const show = computed({
  get: () => props.show,
  set: v => emit('update:show', v),
})

const message = useMessage()
const newRoot = ref('')
const errMsg = ref('')
const busy = ref(false)

async function browse() {
  const dir = await dialog.pickDir('选择新的图库目录')
  if (dir) newRoot.value = dir
}

async function run() {
  errMsg.value = ''
  busy.value = true
  try {
    const result = await api.migrate(newRoot.value)
    store.storageRoot = newRoot.value
    if (result.warnings?.length) {
      message.warning(`迁移完成（${result.moved} 个对象），有 ${result.warnings.length} 条库外路径警告`)
      console.warn('迁移警告：', result.warnings)
    } else {
      message.success(`迁移成功：${result.moved} 个对象`)
    }
    newRoot.value = ''
    emit('update:show', false)
  } catch (e) {
    errMsg.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.desc { line-height: 1.7; margin-bottom: 8px; }
.field-label { font-size: 12px; font-weight: 700; opacity: .6; margin: 12px 0 6px; letter-spacing: 1px; }
.alert { margin-top: 12px; }
.hint { font-size: 12px; opacity: .55; line-height: 1.7; margin-top: 12px; }
.footer { display: flex; justify-content: flex-end; }
</style>
