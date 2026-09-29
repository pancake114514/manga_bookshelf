<template>
  <n-modal v-model:show="show" preset="card" title="编辑对象信息" style="width: 560px;">
    <div class="form">
      <div class="field-label">对象名称</div>
      <n-input v-model:value="name" placeholder="输入对象名称" />

      <template v-for="cat in cats" :key="cat">
        <div class="field-label">{{ catLabel(cat) }}</div>
        <!-- 自渲染标签列表：n-dynamic-tags 无逐项插槽无法支持双击编辑。
             双击标签进入内联编辑（回车/失焦/选建议提交，Esc 取消，清空提交=取消） -->
        <div class="tag-editor">
          <template v-for="(t, i) in tagDrafts[cat]" :key="i">
            <n-auto-complete
              v-if="editing.cat === cat && editing.index === i"
              ref="editInput"
              v-model:value="editing.value"
              size="small"
              class="tag-edit-input"
              :options="suggestions(cat)"
              @select="v => commitEdit(cat, v)"
              @keyup.enter="onEditEnter"
              @keyup.esc="cancelEdit"
              @blur="commitEdit(cat)"
            />
            <n-tag v-else size="medium" closable class="tag-item" title="双击编辑"
                   @close="tagDrafts[cat].splice(i, 1)"
                   @dblclick="startEdit(cat, i)">
              {{ t }}
            </n-tag>
          </template>
          <!-- 添加入口默认收起为 + 号标签（与标签同高），点击展开为输入框；
               失焦或提交后自动收回 -->
          <n-auto-complete
            v-if="addingCat === cat"
            ref="addInput"
            v-model:value="inputVals[cat]"
            size="small"
            class="tag-add-input"
            :options="suggestions(cat)"
            placeholder="输入新标签，回车提交"
            @select="v => addTag(cat, v)"
            @keyup.enter="onAddEnter($event, cat)"
            @blur="addingCat = null"
          />
          <n-tag v-else size="medium" class="tag-add-btn" title="添加标签"
                 @click="startAdd(cat)">+</n-tag>
        </div>
      </template>

      <div class="field-label">评分</div>
      <n-rate v-model:value="rating" />

      <div class="field-label">系列</div>
      <!-- 下拉选择已有系列（可筛选/可输入新系列/可清除）；选中后自动预填下一卷号 -->
      <n-select v-model:value="seriesName" :options="seriesOptions"
                filterable tag clearable
                placeholder="选择系列，或输入名称创建新系列（留空清除）"
                @update:value="onSeriesChange" />

      <div class="field-label">卷号 <span class="hint-inline">选中系列后自动预填下一可用卷号，可修改</span></div>
      <n-input-number v-model:value="volume" :min="1" placeholder="留空表示无卷号"
                      button-placement="both" clearable class="volume-input" />

      <div class="r18-row">
        <span class="field-label r18-label">R-18</span>
        <n-switch v-model:value="r18" />
      </div>
    </div>

    <template #footer>
      <div class="footer">
        <n-button @click="show = false">取消</n-button>
        <n-button type="primary" :loading="saving" @click="save">确定</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, watch, computed, nextTick } from 'vue'
import { NModal, NInput, NInputNumber, NButton, NSwitch, NRate, NTag, NAutoComplete, NSelect, useMessage } from 'naive-ui'
import { api } from '../api'
import { store, loadSeries } from '../store'
import { CATS, catLabel } from '../constants'

const props = defineProps({
  show: Boolean,
  obj: { type: Object, default: null },
})
const emit = defineEmits(['update:show', 'saved'])

const show = computed({
  get: () => props.show,
  set: v => emit('update:show', v),
})

const message = useMessage()
const cats = CATS

const name = ref('')
const r18 = ref(false)
const rating = ref(0)
const seriesName = ref('')
const volume = ref(null)
const tagDrafts = ref({})
const inputVals = ref({})         // 各分类独立的「添加」输入草稿（共享单值会互相串字）
const saving = ref(false)

// IME 组词中的回车（确认候选）不提交
const imeComposing = e => e.isComposing || e.keyCode === 229

// 添加入口：+ 号标签点击展开为输入框（自动聚焦），提交或失焦后收回；
// 任一时刻只有一个分类的添加框处于展开态
const addingCat = ref(null)
const addInput = ref(null)
function startAdd(cat) {
  addingCat.value = cat
  nextTick(() => addInput.value?.focus())
}

// 添加新标签：选中建议或回车提交自由文本；去重、上限 20
function addTag(cat, v) {
  const val = (v ?? '').toString().trim()
  const arr = tagDrafts.value[cat] || (tagDrafts.value[cat] = [])
  if (val && !arr.includes(val) && arr.length < 20) arr.push(val)
  inputVals.value[cat] = ''
  addingCat.value = null
}
function onAddEnter(e, cat) {
  if (imeComposing(e)) return
  addTag(cat, inputVals.value[cat])
}

// 双击编辑：回车/失焦/选建议提交，Esc 取消；清空提交视为取消（删除走 X）；
// 提交值与其他标签重名时合并（删掉被编辑的）。任一时刻只有一个编辑框，单一 ref 即可
const editing = ref({ cat: null, index: -1, value: '' })
const editInput = ref(null)
function startEdit(cat, i) {
  editing.value = { cat, index: i, value: tagDrafts.value[cat][i] }
  nextTick(() => editInput.value?.focus())
}
function commitEdit(cat, selected) {
  const { cat: ec, index, value } = editing.value
  if (ec !== cat || index < 0) return          // 已提交/已取消（blur 与 select 竞态去重）
  cancelEdit()
  const v = (selected ?? value).trim()
  if (!v) return
  const arr = tagDrafts.value[cat]
  if (arr.some((t, j) => t === v && j !== index)) arr.splice(index, 1)
  else arr.splice(index, 1, v)
}
function cancelEdit() {
  editing.value = { cat: null, index: -1, value: '' }
}
function onEditEnter(e) {
  if (imeComposing(e)) return
  commitEdit(editing.value.cat)
}

// 系列下拉选项（来自已有系列）；tag 模式允许输入创建新系列
const seriesOptions = computed(() => (store.series || [])
  .filter(s => s.name)
  .map(s => ({ label: s.name, value: s.name })))

// 选中系列后预填下一可用卷号：已有系列 = 现有最大卷号 + 1（排除自身当前卷，
// 重编辑不串号）；新系列 = 1。清空系列时连带清空卷号（卷号语义上属于系列）
async function onSeriesChange(val) {
  const name = (val ?? '').toString().trim()
  if (!name) { volume.value = null; return }
  const s = (store.series || []).find(x => x.name === name)
  if (!s) { volume.value = 1; return }
  try {
    const vols = await api.seriesVolumes(s.id)
    const own = s.id === props.obj.series_id ? props.obj.volume : null
    const nums = vols.map(v => v.volume).filter(v => v != null && v !== own)
    volume.value = nums.length ? Math.max(...nums) + 1 : 1
  } catch {
    volume.value = 1
  }
}

watch(() => props.show, v => {
  if (!v || !props.obj) return
  name.value = props.obj.name || ''
  r18.value = !!props.obj.tags?.r18
  rating.value = Number(props.obj.tags?.rating?.[0] || 0)
  seriesName.value = props.obj.series_name || null
  volume.value = props.obj.volume == null ? null : Number(props.obj.volume)
  const draft = {}
  for (const cat of CATS) draft[cat] = [...(props.obj.tags?.[cat] || [])]
  tagDrafts.value = draft
  inputVals.value = {}
  cancelEdit()
  addingCat.value = null
})

function suggestions(cat) {
  const all = store.tagValues[cat] || []
  const cur = tagDrafts.value[cat] || []
  return all.filter(v => !cur.includes(v)).map(v => ({ label: v, value: v }))
}

async function save() {
  if (!name.value.trim()) { message.warning('名称不能为空'); return }
  saving.value = true
  try {
    const tags = {}
    for (const cat of CATS) if (tagDrafts.value[cat]?.length) tags[cat] = tagDrafts.value[cat]
    if (rating.value) tags.rating = [String(rating.value)]
    tags.r18 = r18.value
    // 系列名：空串转 null（清除）；卷号：空转 null（清除）。始终携带，保证幂等
    const sn = (seriesName.value ?? '').toString().trim()
    await api.updateObject(props.obj.id, {
      name: name.value.trim(),
      tags,
      series_name: sn || null,
      volume: volume.value == null ? null : Number(volume.value),
    })
    if (sn) loadSeries()   // 新建系列后刷新下拉列表
    message.success('已保存')
    emit('update:show', false)
    emit('saved')
  } catch (e) {
    message.error(e.message || String(e))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.form { display: flex; flex-direction: column; gap: 8px; }
.field-label { font-size: 12px; font-weight: 700; opacity: .6; margin-top: 8px; letter-spacing: 1px; }
/* 标签编辑器：标签 + 常驻添加输入框同行流式排列；双击标签进入内联编辑 */
.tag-editor { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.tag-item { user-select: none; }
.tag-edit-input { width: 150px; }
.tag-add-input { width: 130px; }
/* + 号添加入口：与已有标签同尺寸（medium，28px，与 small 输入框等高）、同边框 */
.tag-add-btn { cursor: pointer; }
.hint-inline { font-weight: 400; letter-spacing: 0; opacity: .75; margin-left: 6px; }
/* R-18 行内布局：标签与开关同行居中，避免开关独占一行视觉错位 */
.r18-row { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.r18-row .field-label { margin-top: 0; }
.r18-label { color: var(--ms-danger); }
.volume-input { width: 160px; }
.footer { display: flex; justify-content: flex-end; gap: 10px; }
</style>
