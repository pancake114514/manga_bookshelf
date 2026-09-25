<template>
  <div class="obj-card" :class="{ 'is-r18': isR18, selected }" :style="animStyle"
       @click="selectMode && $emit('toggle-select', obj.id)"
       @dblclick.stop="!selectMode && $emit('open', obj)"
       @contextmenu.prevent="onContextMenu">
    <div class="cover-box">
      <img :src="coverUrl" loading="lazy" alt="">
      <template v-if="isR18 && !revealed">
        <span class="r18-badge">R-18</span>
        <div class="r18-lock">
          <IconLock :size="20" />
          <span>内容已隐藏</span>
        </div>
      </template>
      <div v-if="selectMode" class="select-badge" :class="{ on: selected }">
        <IconCheck v-if="selected" :size="12" />
      </div>
      <!-- 阅读进度可视化：读过的封面底部细条；读至末页显示「读完」角标 -->
      <div v-if="progressPct > 0 && !finished" class="read-progress">
        <div class="fill" :style="{ width: `${progressPct}%` }" />
      </div>
      <span v-if="finished" class="done-badge"><IconCheck :size="11" /> 读完</span>
      <div v-if="!selectMode" class="hover-overlay">
        <div class="ov-title">{{ obj.name }}</div>
        <div class="ov-row">
          <span v-for="t in tagList" :key="t" class="mini-tag">{{ t }}</span>
        </div>
        <div class="ov-rate" title="点击打分，再次点击当前分值清除" @click.stop @dblclick.stop>
          <n-rate size="small" :value="rating" @update:value="v => $emit('rate', obj, v)" />
        </div>
        <div class="actions">
          <n-button size="tiny" quaternary title="继续阅读（从上次进度）" @click.stop="$emit('read', obj)"><IconPlay :size="13" /></n-button>
          <n-button size="tiny" quaternary title="编辑" @click.stop="$emit('edit', obj)"><IconEdit :size="13" /></n-button>
          <n-button size="tiny" quaternary title="设置封面" @click.stop="$emit('cover', obj)"><IconImage :size="13" /></n-button>
          <n-button size="tiny" quaternary title="删除" @click.stop="$emit('del', obj)"><IconTrash :size="13" /></n-button>
        </div>
      </div>
    </div>
    <div class="card-info">
      <div class="card-title">{{ obj.name }}</div>
      <div class="card-meta">
        <span>{{ obj.image_count }} 张</span>
        <span v-if="rating" class="meta-rate"><IconStarFill :size="11" /> {{ rating }}</span>
        <span v-else>{{ timeLabel }}</span>
      </div>
    </div>

    <!-- 右键自定义菜单（替代 WebView 默认菜单） -->
    <n-dropdown trigger="manual" :show="ctxMenu.show" :x="ctxMenu.x" :y="ctxMenu.y"
                :options="menuOptions" placement="bottom-start"
                @select="onMenuSelect" @clickoutside="ctxMenu.show = false" />
  </div>
</template>

<script setup>
import { computed, reactive, h } from 'vue'
import { NButton, NRate, NDropdown, useMessage } from 'naive-ui'
import { api } from '../api'
import { IconLock, IconPlay, IconEdit, IconImage, IconTrash, IconCheck, IconStarFill, IconFolder } from './icons'

const props = defineProps({
  obj: { type: Object, required: true },
  animDelay: { type: Number, default: 0 },
  revealed: { type: Boolean, default: false },
  selectMode: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
})
const emit = defineEmits(['open', 'read', 'edit', 'cover', 'del', 'rate', 'toggle-select'])
const message = useMessage()

// ── 右键菜单 ─────────────────────────────────────────────
const ctxMenu = reactive({ show: false, x: 0, y: 0 })
const renderIcon = (Icon) => () => h(Icon, { size: 15 })
const menuOptions = [
  { label: '在资源管理器中打开', key: 'explore', icon: renderIcon(IconFolder) },
  { type: 'divider' },
  { label: '继续阅读', key: 'read', icon: renderIcon(IconPlay) },
  { label: '编辑对象信息', key: 'edit', icon: renderIcon(IconEdit) },
  { label: '设置封面图', key: 'cover', icon: renderIcon(IconImage) },
  { type: 'divider' },
  { label: '删除', key: 'del', icon: renderIcon(IconTrash), props: { style: 'color: #d03050;' } },
]

function onContextMenu(e) {
  ctxMenu.x = e.clientX
  ctxMenu.y = e.clientY
  ctxMenu.show = true
}

async function onMenuSelect(key) {
  ctxMenu.show = false
  // 打开目录为本组件内直接调用后端，其余复用已有 emit
  if (key === 'explore') {
    try {
      await api.openInExplorer(props.obj.id)
    } catch (err) {
      message.error(`打开失败：${err?.message || err}`)
    }
    return
  }
  emit(key, props.obj)
}

const isR18 = computed(() => !!props.obj.tags?.r18)
const rating = computed(() => Number(props.obj.tags?.rating?.[0] || 0))
// 阅读进度：last_read_idx 为 0 视为未读（无指示）；读至最后一页视为读完
const progressPct = computed(() => {
  const n = props.obj.image_count || 0
  const idx = props.obj.last_read_idx || 0
  if (n < 2 || idx <= 0) return 0
  return Math.min(100, Math.round((idx / (n - 1)) * 100))
})
const finished = computed(() => {
  const n = props.obj.image_count || 0
  return n > 0 && (props.obj.last_read_idx || 0) >= n - 1
})
const coverUrl = computed(() => props.obj.cover_url || '')
const animStyle = computed(() => props.animDelay ? { animationDelay: `${props.animDelay}ms` } : {})
const tagList = computed(() => {
  const tags = props.obj.tags || {}
  const out = []
  for (const [cat, vals] of Object.entries(tags)) {
    if (cat === 'r18' || cat === 'rating') continue
    if (Array.isArray(vals)) out.push(...vals)
    else if (vals) out.push(String(vals))
  }
  return out
})
const timeLabel = computed(() => {
  const d = props.obj.created_at ? new Date(props.obj.created_at.replace(' ', 'T')) : null
  if (!d || isNaN(d)) return ''
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (days <= 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 30) return `${days} 天前`
  return d.toLocaleDateString()
})
</script>

<style scoped>
.mini-tag {
  font-size: 10px; padding: 1px 6px; border-radius: 4px;
  background: var(--chip-bg);
}
.actions { display: flex; gap: 4px; margin-top: 6px; }

.select-badge {
  position: absolute; top: 8px; left: 8px; z-index: 4;
  width: 22px; height: 22px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  border: 2px solid rgba(255, 255, 255, .9);
  background: rgba(0, 0, 0, .35);
  color: #fff;
  transition: background .15s, border-color .15s;
}
.select-badge.on {
  background: var(--ms-primary);
  border-color: var(--ms-primary);
}

.card-meta { gap: 6px; }
.meta-rate {
  display: inline-flex; align-items: center; gap: 3px;
  color: var(--ms-star); font-weight: 700;
}

/* 阅读进度指示（叠在封面上，不拦截鼠标） */
.read-progress {
  position: absolute; left: 0; right: 0; bottom: 0; z-index: 3;
  height: 3px; background: rgba(0, 0, 0, .35);
  pointer-events: none;
}
.read-progress .fill { height: 100%; background: var(--ms-primary); }
.done-badge {
  position: absolute; top: 8px; right: 8px; z-index: 3;
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 10px; line-height: 1; padding: 3px 6px; border-radius: 4px;
  background: rgba(0, 0, 0, .55); color: #fff;
  pointer-events: none;
}
</style>
