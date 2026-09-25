<template>
  <main class="dir-view" v-if="detail">
    <div class="info-bar">
      <n-button size="small" @click="back"><IconBack :size="14" /> 书架</n-button>
      <div class="info-row">
        <img class="cover" :src="detail.cover_url" alt="">
        <div class="meta">
          <div class="title-row">
            <h2 class="title">{{ detail.name }}</h2>
            <n-button v-if="detail.images?.length" type="primary" @click="continueRead"><IconPlay :size="13" /> 继续阅读</n-button>
          </div>
          <div class="rate-row">
            <n-rate size="small" :value="rating" @update:value="rate" />
          </div>
          <div v-for="(vals, cat) in tagRows" :key="cat" class="tag-row">
            <span class="cat">{{ catLabel(cat) }}：</span>
            <span v-for="v in vals" :key="v" class="tag"
                  :class="{ clickable: cat !== 'r18' }"
                  :title="cat !== 'r18' ? '点击筛选含此标签的对象' : ''"
                  @click="cat !== 'r18' && filterTag(cat, v)">{{ v }}</span>
          </div>
          <span v-if="!hasTags" class="no-tag">暂无标签</span>
        </div>
      </div>
    </div>

    <div class="grid-wrap">
      <div class="thumb-grid">
        <div v-for="(img, i) in detail.images" :key="img.id" class="thumb-card"
             @dblclick="openAt(i)">
          <img :src="img.thumb_url" loading="lazy" alt="">
          <span class="fname">{{ img.filename }}</span>
        </div>
      </div>
    </div>
  </main>
</template>

<script setup>
import { computed } from 'vue'
import { NButton, NRate } from 'naive-ui'
import { api } from '../api'
import { store } from '../store'
import { catLabel } from '../constants'
import { IconBack, IconPlay } from './icons'

const props = defineProps({ obj: { type: Object, required: true } })
const detail = computed(() => props.obj)

const rating = computed(() => Number(props.obj.tags?.rating?.[0] || 0))

const tagRows = computed(() => {
  const tags = props.obj.tags || {}
  const rows = {}
  for (const [cat, vals] of Object.entries(tags)) {
    if (cat === 'r18') {
      if (vals) rows.r18 = ['R-18']
    } else if (cat === 'rating') {
      continue                   // 评分用星星组件展示
    } else if (Array.isArray(vals) && vals.length) {
      rows[cat] = vals
    } else if (vals) {
      rows[cat] = [String(vals)]
    }
  }
  return rows
})
const hasTags = computed(() => Object.keys(tagRows.value).length > 0)

async function rate(v) {
  const tags = { ...props.obj.tags }
  if (v) tags.rating = [String(v)]
  else delete tags.rating
  try {
    await api.updateObject(props.obj.id, { tags })
    props.obj.tags = tags        // 就地更新，界面即时生效
  } catch (e) { console.error(e) }
}

// 点击标签 → 作为筛选条件回到书架
function filterTag(cat, val) {
  store.filters = { ...store.filters, [cat]: [val] }
  store.view = { name: 'shelf' }
}

function back() { store.view = { name: 'shelf' } }
function openAt(idx) {
  store.reader = { obj: props.obj, images: props.obj.images, index: idx, from: 'directory' }
  store.view = { name: 'reader' }
}
function continueRead() {
  openAt(Math.min(props.obj.last_read_idx || 0, props.obj.images.length - 1))
}
</script>

<style scoped>
.dir-view { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.info-bar { flex: none; padding: 14px 20px 16px; border-bottom: 1px solid var(--border, rgba(128,128,128,.2)); }
.info-row { display: flex; gap: 16px; margin-top: 12px; }
.cover { width: 172px; aspect-ratio: 5 / 7; object-fit: cover; border-radius: 10px; background: var(--chip-bg, rgba(128,128,128,.12)); }
.meta { flex: 1; min-width: 0; }
.rate-row { margin-top: 8px; line-height: 1; }
.title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.title { font-size: 20px; font-weight: 700; word-break: break-all; }
.tag-row { display: flex; gap: 6px; margin-top: 8px; align-items: center; flex-wrap: wrap; }
.cat { font-size: 12px; opacity: .55; }
.tag {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: var(--chip-bg);
}
.tag.clickable { cursor: pointer; transition: background .15s, color .15s; }
.tag.clickable:hover { background: var(--ms-primary); color: #fff; }
.no-tag { font-size: 12px; opacity: .5; }
.grid-wrap { flex: 1; overflow-y: auto; padding: 20px; }
.thumb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, 150px);   /* 固定列宽，不随窗口伸缩 */
  gap: 12px;
}
.thumb-card {
  border: 1px solid var(--border, rgba(128,128,128,.2));
  border-radius: 8px; overflow: hidden; cursor: pointer;
  transition: transform .15s, border-color .15s;
}
.thumb-card:hover { transform: translateY(-2px); border-color: var(--ms-primary, #18a058); }
.thumb-card img {
  width: 100%; aspect-ratio: 1; object-fit: cover; display: block;
  background: var(--chip-bg, rgba(128,128,128,.12));
}
.fname {
  display: block; padding: 5px 8px; font-size: 10px; opacity: .6;
  font-family: Georgia, serif;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
</style>
