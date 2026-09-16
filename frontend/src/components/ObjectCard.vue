<template>
  <div class="obj-card" :class="{ 'is-r18': isR18 }" :style="animStyle"
       @dblclick="$emit('open', obj)">
    <div class="cover-box">
      <img :src="coverUrl" loading="lazy" alt="">
      <template v-if="isR18 && !revealed">
        <span class="r18-badge">R-18</span>
        <div class="r18-lock">
          <span style="font-size:20px">🔒</span>
          <span>内容已隐藏</span>
        </div>
      </template>
      <div class="hover-overlay">
        <div class="ov-title">{{ obj.name }}</div>
        <div class="ov-row">
          <span v-for="t in tagList" :key="t" class="mini-tag">{{ t }}</span>
        </div>
        <div class="actions">
          <n-button size="tiny" quaternary title="阅读" @click.stop="$emit('open', obj)">▶</n-button>
          <n-button size="tiny" quaternary title="编辑" @click.stop="$emit('edit', obj)">✎</n-button>
          <n-button size="tiny" quaternary title="设置封面" @click.stop="$emit('cover', obj)">🖼</n-button>
          <n-button size="tiny" quaternary title="删除" @click.stop="$emit('del', obj)">🗑</n-button>
        </div>
      </div>
    </div>
    <div class="card-info">
      <div class="card-title">{{ obj.name }}</div>
      <div class="card-meta">
        <span>{{ obj.image_count }} 张</span>
        <span>{{ timeLabel }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { NButton } from 'naive-ui'
import { store } from '../store'

const props = defineProps({
  obj: { type: Object, required: true },
  anim: { type: String, default: '' },      // '' | 'card-enter' | 'card-leave'
  animDelay: { type: Number, default: 0 },
  revealed: { type: Boolean, default: false },
})
defineEmits(['open', 'edit', 'cover', 'del'])

const isR18 = computed(() => !!props.obj.tags?.r18)
const coverUrl = computed(() => `/api/objects/${props.obj.id}/cover?kind=card&_=${props.obj.cover_url ?? ''}`)
const animStyle = computed(() => props.anim
  ? { animationName: undefined, animationDelay: `${props.animDelay}ms` }
  : {})
const tagList = computed(() => {
  const tags = props.obj.tags || {}
  const out = []
  for (const [cat, vals] of Object.entries(tags)) {
    if (cat === 'r18') continue
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
  background: var(--chip-bg, rgba(128,128,128,.18));
}
.actions { display: flex; gap: 4px; margin-top: 6px; }
</style>
