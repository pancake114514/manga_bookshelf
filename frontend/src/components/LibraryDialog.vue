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

    <div class="field-label">缩略图缓存</div>
    <div class="cache-row">
      <span class="hint-inline">
        清理失效缓存（已删除对象/被替换源文件的残留），总量超过 2GB 时按最旧优先删除
      </span>
      <n-button size="small" :loading="pruneBusy" :disabled="!store.storageRoot" @click="runPrune">
        清理缓存
      </n-button>
    </div>

    <div class="field-label">库校验</div>
    <div class="cache-row">
      <span class="hint-inline">
        外部删除/移动/手动添加文件后对账：先生成只读报告，修复按勾选执行
      </span>
      <n-button size="small" :loading="verifyBusy" :disabled="!store.storageRoot" @click="runVerify">
        校验库
      </n-button>
    </div>

    <!-- 校验报告与修复 -->
    <div v-if="report" class="verify-panel">
      <div v-if="!report.abnormal.length && !report.orphan_dirs.length" class="verify-ok">
        ✓ 库与磁盘一致（共 {{ report.objects_total }} 个对象）
      </div>
      <template v-else>
        <div v-if="report.abnormal.length" class="fix-checks">
          <n-checkbox v-model:checked="fixRemoveMissing" :disabled="!missingIds.length">
            移除缺失图片记录（{{ report.missing_images_total }} 张）
          </n-checkbox>
          <n-checkbox v-model:checked="fixRegister" :disabled="!registerIds.length">
            补登记未登记文件（{{ report.unregistered_total }} 张）
          </n-checkbox>
          <n-checkbox v-model:checked="fixRemoveEmpty" :disabled="!emptyIds.length">
            删除已无有效图片的对象（{{ emptyIds.length }} 个，不删文件）
          </n-checkbox>
        </div>
        <div class="abnormal-list">
          <div v-for="o in report.abnormal" :key="o.obj_id" class="abn-item" :title="o.storage_path">
            {{ o.name }}：
            <template v-if="!o.dir_exists">目录缺失（{{ o.missing_images.length }} 张记录）</template>
            <template v-else-if="!o.missing_images.length && !o.unregistered_files.length">空对象</template>
            <template v-else>{{ o.missing_images.length ? `缺 ${o.missing_images.length} 张` : '' }}{{ o.missing_images.length && o.unregistered_files.length ? ' · ' : '' }}{{ o.unregistered_files.length ? `未登记 ${o.unregistered_files.length} 张` : '' }}</template>
          </div>
        </div>
        <div v-if="report.orphan_dirs.length" class="orphan">
          孤儿目录（磁盘有、库里无记录，可导入）：{{ report.orphan_dirs.join('、') }}
        </div>
        <div v-if="report.abnormal.length" class="verify-actions">
          <n-button size="small" type="primary" :loading="fixBusy" @click="runFix">应用修复</n-button>
        </div>
      </template>
    </div>

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
import { NModal, NButton, NInput, NInputGroup, NAlert, NProgress, NCheckbox, useMessage } from 'naive-ui'
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
const pruneBusy = ref(false)

// 清理缩略图缓存：删除失效条目与超限旧文件，报告删除数量与释放空间
async function runPrune() {
  pruneBusy.value = true
  try {
    const r = await api.pruneThumbCache()
    if (!r.removed) {
      message.success('缓存已是最新，无需清理')
    } else {
      const mb = (r.freed_bytes / 1024 / 1024).toFixed(1)
      message.success(`已清理 ${r.removed} 个缓存文件，释放 ${mb} MB`)
    }
  } catch (e) {
    message.error(e.message || String(e))
  } finally {
    pruneBusy.value = false
  }
}

// ── 库校验 ──
const report = ref(null)
const verifyBusy = ref(false)
const fixBusy = ref(false)
const fixRemoveMissing = ref(true)
const fixRegister = ref(true)
const fixRemoveEmpty = ref(false)   // 删除对象属破坏性操作，默认不勾

const missingIds = computed(() =>
  (report.value?.abnormal || []).filter(o => o.missing_images.length).map(o => o.obj_id))
const registerIds = computed(() =>
  (report.value?.abnormal || []).filter(o => o.unregistered_files.length).map(o => o.obj_id))
// 空对象判定：目录缺失，或（补登记前）已无任何有效图片
const emptyIds = computed(() =>
  (report.value?.abnormal || []).filter(o =>
    !o.dir_exists || o.image_count === 0 || o.missing_images.length >= o.image_count)
    .map(o => o.obj_id))

async function runVerify() {
  verifyBusy.value = true
  report.value = null
  try {
    report.value = await api.verifyLibrary()
  } catch (e) {
    message.error(e.message || String(e))
  } finally {
    verifyBusy.value = false
  }
}

async function runFix() {
  fixBusy.value = true
  try {
    const r = await api.applyVerifyFixes({
      remove_missing: fixRemoveMissing.value ? missingIds.value : [],
      register: fixRegister.value ? registerIds.value : [],
      remove_empty: fixRemoveEmpty.value ? emptyIds.value : [],
    })
    message.success(`修复完成：移除 ${r.removed_rows} 条失效记录，补登记 ${r.registered} 张，删除 ${r.removed_objects} 个空对象`)
    await runVerify()   // 复审刷新报告
    store.reloadTick++  // 书架同步刷新（可能有对象被移除）
  } catch (e) {
    message.error(e.message || String(e))
  } finally {
    fixBusy.value = false
  }
}

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
.cache-row { display: flex; align-items: center; gap: 12px; }
.hint-inline { flex: 1; font-size: 12px; opacity: .55; line-height: 1.5; }
.verify-panel { margin-top: 10px; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; }
.verify-ok { font-size: 13px; color: var(--ms-primary); }
.fix-checks { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.abnormal-list { max-height: 180px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.abn-item { font-size: 12px; opacity: .8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.orphan { margin-top: 8px; font-size: 12px; opacity: .6; }
.verify-actions { margin-top: 10px; display: flex; justify-content: flex-end; }
</style>
