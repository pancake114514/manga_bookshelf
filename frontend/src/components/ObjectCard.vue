<template>
  <div class="obj-card" :class="{ 'is-r18': isR18, selected }" :style="animStyle"
       @click="selectMode && $emit('toggle-select', obj.id)"
       @dblclick.stop="!selectMode && $emit('open', obj)">
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
      <div v-else class="hover-overlay">
        <div class="ov-title">{{ obj.name }}</div>
        <div class="ov-row">
          <span v-for="t in tagList" :key="t" class="mini-tag">{{ t }}</span>
        </div>
        <div class="ov-rate" title="点击打分，再次点击当前分值清除" @click.stop @dblclick.stop>
          <n-rate size="small" :value="rating" @update:value="v => $emit('rate', obj, v)" />
        </div>
        <div class="actions">
          <n-button size="tiny" quaternary title="阅读" @click.stop="$emit('open', obj)"><IconPlay :size="13" /></n-button>
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
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { NButton, NRate } from 'naive-ui'
import { IconLock, IconPlay, IconEdit, IconImage, IconTrash, IconCheck, IconStarFill } from './icons'

const props = defineProps({
  obj: { type: Object, required: true },
  animDelay: { type: Number, default: 0 },
  revealed: { type: Boolean, default: false },
  selectMode: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
})
defineEmits(['open', 'edit', 'cover', 'del', 'rate', 'toggle-select'])

const isR18 = computed(() => !!props.obj.tags?.r18)
const rating = computed(() => Number(props.obj.tags?.rating?.[0] || 0))
const coverUrl = computed(() => `/api/objects/${props.obj.id}/cover?kind=card&_=${props.obj.cover_url ?? ''}`)
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
</style>
