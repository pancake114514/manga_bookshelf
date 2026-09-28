<template>
  <main class="dir-view" v-if="detail">
    <div class="info-bar">
      <!-- 渐进磨砂材质层：纯色（上 80%）→ 磨砂透明（下 20%），透明度下增、模糊度下减 -->
      <div class="bar-glass" aria-hidden="true"><i class="gl gl-1" /><i class="gl gl-2" /><i class="gl gl-3" /></div>
      <n-button size="small" @click="back"><IconBack :size="14" /> 书架</n-button>
      <div class="info-row">
        <!-- 封面加载失败（无封面/文件缺失）时隐藏整块，显示底色空白而非破碎图标。
             封面已等比缩小（140×196），底缘距栏底 70px、位于熔起点（64px）之上，
             始终落在纯色区，不再需要渐熔处理 -->
        <div v-if="coverOk" class="cover-wrap">
          <img class="cover" :src="detail.cover_url" alt="" @error="coverOk = false">
        </div>
        <div class="meta">
          <div class="title-row">
            <h2 class="title">{{ detail.name }}</h2>
            <n-button v-if="detail.images?.length" type="primary" @click="continueRead"><IconPlay :size="13" /> 继续阅读</n-button>
          </div>
          <div v-if="detail.series_name" class="series-line">
            {{ detail.series_name }}<template v-if="detail.volume != null"> · 第 {{ detail.volume }} 卷</template>
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
          <!-- 该页书签标记 -->
          <span v-if="bmSet.has(i)" class="bm-badge" title="已加书签"><IconBookmark :size="10" /></span>
          <img :src="img.thumb_url" loading="lazy" alt="">
          <span class="fname">{{ img.filename }}</span>
        </div>
      </div>
    </div>
  </main>
</template>

<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { NButton, NRate } from 'naive-ui'
import { api } from '../api'
import { store } from '../store'
import { catLabel } from '../constants'
import { IconBack, IconPlay, IconBookmark } from './icons'

const props = defineProps({ obj: { type: Object, required: true } })
const detail = computed(() => props.obj)

// 书签页集合：卡片右上角显示标记（从阅读器返回时组件重建会重新拉取）
const bmSet = ref(new Set())
onMounted(async () => {
  try {
    const list = await api.bookmarks(props.obj.id)
    bmSet.value = new Set(list.map(b => b.page_idx))
  } catch { /* 书签拉取失败不阻塞详情页 */ }
})

// 封面可用性：加载失败置 false 隐藏 img；封面 URL 变化（换图）时复位重试
const coverOk = ref(true)
watch(() => props.obj.cover_url, () => { coverOk.value = true })

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
/* 整页滚动：内容在粘性顶栏下方向下滑入其磨砂区（原 grid-wrap 独立滚动已并入） */
.dir-view { flex: 1; display: flex; flex-direction: column; min-height: 0; overflow-y: auto; }
/* 顶栏：粘性吸附；上部纯色，底部渐熔为磨砂透明（透明度下增、模糊度下减）。
   底部 padding 70px：封面底缘因此距栏底 70px，落在熔起点（64px）之上的纯色区 */
.info-bar {
  position: sticky; top: 0; z-index: 20; flex: none;
  padding: 14px 20px 70px;
}
/* 材质层容器：底色渐变（纯色 → 透明），位于内容之下。
   距底 px 锚定（非百分比）：栏高 H = 14+28+12+196+70 = 320px，
   熔起点 = 距底 64px → calc(100% - 64px)，与封面缩小后的底缘（70px）对齐 */
.bar-glass {
  position: absolute; inset: 0; z-index: 0; pointer-events: none;
  background: linear-gradient(to bottom,
    var(--bg) 0%, var(--bg) calc(100% - 64px),
    color-mix(in srgb, var(--bg) 60%, transparent) calc(100% - 32px),
    transparent 100%);
}
/* 三层递减模糊，各自用渐隐遮罩限定作用带：叠出「上强下弱」的连续磨砂 */
.bar-glass .gl { position: absolute; inset: 0; }
.gl-1 {
  -webkit-backdrop-filter: blur(20px) saturate(170%);
  backdrop-filter: blur(20px) saturate(170%);
  -webkit-mask-image: linear-gradient(to bottom, #000 0%, #000 calc(100% - 76px), transparent calc(100% - 24px));
  mask-image: linear-gradient(to bottom, #000 0%, #000 calc(100% - 76px), transparent calc(100% - 24px));
}
.gl-2 {
  -webkit-backdrop-filter: blur(10px) saturate(170%);
  backdrop-filter: blur(10px) saturate(170%);
  -webkit-mask-image: linear-gradient(to bottom, #000 0%, #000 calc(100% - 68px), transparent calc(100% - 10px));
  mask-image: linear-gradient(to bottom, #000 0%, #000 calc(100% - 68px), transparent calc(100% - 10px));
}
.gl-3 {
  -webkit-backdrop-filter: blur(4px);
  backdrop-filter: blur(4px);
  -webkit-mask-image: linear-gradient(to bottom, #000 0%, #000 calc(100% - 58px), transparent 100%);
  mask-image: linear-gradient(to bottom, #000 0%, #000 calc(100% - 58px), transparent 100%);
}
/* 文字与控件抬到材质层之上 */
.info-bar > :not(.bar-glass) { position: relative; z-index: 1; }
/* 背板滤镜不可用：降级为不透明纯色栏 */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .bar-glass { background: var(--bg); }
}
.info-row { display: flex; gap: 16px; margin-top: 12px; }
/* 封面：等比缩小为 140×196（5:7），底缘距栏底 70px、位于熔起点（64px）之上，
   始终处于纯色区，无需渐熔；栏高因此保持 320px 不变 */
.cover-wrap {
  position: relative; flex: none;
  width: 140px; aspect-ratio: 5 / 7;
  border-radius: 10px; overflow: hidden;
  background: var(--chip-bg, rgba(128,128,128,.12));
}
.cover { width: 100%; height: 100%; object-fit: cover; display: block; }
.meta { flex: 1; min-width: 0; }
.rate-row { margin-top: 8px; line-height: 1; }
.title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.title { font-size: 20px; font-weight: 700; word-break: break-all; }
.series-line { margin-top: 6px; font-size: 13px; opacity: .6; }
.tag-row { display: flex; gap: 6px; margin-top: 8px; align-items: center; flex-wrap: wrap; }
.cat { font-size: 12px; opacity: .55; }
.tag {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: var(--chip-bg);
}
.tag.clickable { cursor: pointer; transition: background .15s, color .15s; }
.tag.clickable:hover { background: var(--ms-primary); color: #fff; }
.no-tag { font-size: 12px; opacity: .5; }
.grid-wrap { flex: none; padding: 20px; }   /* 滚动已上移至 .dir-view，此处只留内边距 */
.thumb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, 150px);   /* 固定列宽，不随窗口伸缩 */
  gap: 12px;
}
.thumb-card {
  border: 1px solid var(--border, rgba(128,128,128,.2));
  border-radius: 8px; overflow: hidden; cursor: pointer;
  transition: transform .15s, border-color .15s;
  position: relative;
}
/* 书签标记：卡片右上角小角标（琥珀橙） */
.bm-badge {
  position: absolute; top: 4px; right: 4px; z-index: 2;
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; border-radius: 4px;
  background: #f5a623; color: #fff;
  pointer-events: none;
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
