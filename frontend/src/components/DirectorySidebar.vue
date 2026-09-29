<template>
  <!-- 详情页对象侧栏（常驻）：同系列分卷导航 + 书签列表 + 信息脚注。
       分卷/书签段按内容显隐；脚注永远保留，避免整栏消失的突兀感。
       可收起为细条（收起钮 / 拖动分隔条 / Ctrl+B），宽度 180–400 拖动可调 -->
  <aside class="dir-side" :class="{ collapsed }" :style="{ width: width + 'px' }">
    <div class="side-inner">
      <div class="side-head">
        <button class="side-toggle" title="收起侧栏（Ctrl+B）" @click="toggleSidebar('directory')">
          <IconChevronLeft :size="13" />
        </button>
      </div>
      <div v-if="vols.length > 1" class="side-group">
        <div class="side-title">系列 · {{ obj.series_name }}</div>
        <div class="vol-list">
          <div v-for="v in vols" :key="v.id" class="vol-row"             :class="{ current: v.id === obj.id }"
               :title="v.id === obj.id ? v.name : `打开「${v.name}」`"
               @click="v.id !== obj.id && openVol(v)">
            <img class="vol-cover" :src="v.cover_url" alt=""
                 @error="e => e.target.style.visibility = 'hidden'">
            <div class="vol-meta">
              <div class="vol-label">{{ v.volume != null ? `第 ${v.volume} 卷` : v.name }}</div>
              <div class="vol-sub">{{ v.image_count }} 张</div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="bookmarks.length" class="side-group">
        <div class="side-title">书签</div>
        <div class="bm-list">
          <div v-for="b in bookmarks" :key="b.id" class="bm-row"
               :title="b.note ? `P${b.page_idx + 1}：${b.note}` : `跳到第 ${b.page_idx + 1} 页`"
               @click="goBookmark(b)">
            <span class="bm-ico"><IconBookmark :size="11" /></span>
            <span class="bm-page">P{{ b.page_idx + 1 }}</span>
            <span class="bm-note">{{ b.note || obj.images[b.page_idx]?.filename || '' }}</span>
          </div>
        </div>
      </div>

      <div class="side-foot">
        <span class="foot-stats">
          {{ obj.image_count }} 张<template v-if="progressPct"> · 已读 {{ progressPct }}%</template>
        </span>
        <button class="foot-btn" title="在资源管理器中打开存储目录" @click="openFolder">
          <IconFolder :size="13" />
        </button>
      </div>
    </div>

    <!-- 收起态细条：点击任意处展开 -->
    <div class="side-rail" title="展开侧栏（Ctrl+B）" @click="toggleSidebar('directory')">
      <button class="side-toggle"><IconChevronRight :size="13" /></button>
      <span class="rail-label">分卷·书签</span>
    </div>
    <div class="side-divider" title="拖动调整宽度，双击收起/展开"
         @pointerdown="e => startSidebarDrag('directory', e)"
         @dblclick="toggleSidebar('directory')" />
  </aside>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { NButton } from 'naive-ui'
import { api } from '../api'
import { store } from '../store'
import { sidebarWidth, toggleSidebar, startSidebarDrag } from '../sidebar'
import { IconBookmark, IconFolder, IconChevronLeft, IconChevronRight } from './icons'
import { useMessage } from 'naive-ui'

const props = defineProps({ obj: { type: Object, required: true } })
const message = useMessage()

const collapsed = computed(() => store.ui.sidebar.directory)
const width = computed(() => sidebarWidth('directory'))

const vols = ref([])
const bookmarks = ref([])

watch(() => props.obj.id, load, { immediate: true })

async function load() {
  vols.value = []
  bookmarks.value = []
  const o = props.obj
  if (!o) return
  // 加载失败进控制台告警而非静默吞掉（否则表现为侧栏内容无声消失，无法诊断）
  bookmarks.value = await api.bookmarks(o.id)
    .catch(e => { console.warn('[详情侧栏] 书签加载失败:', e); return [] })
  if (o.series_id) {
    vols.value = await api.seriesVolumes(o.series_id)
      .catch(e => { console.warn('[详情侧栏] 分卷加载失败:', e); return [] })
  }
}

const progressPct = computed(() => {
  const n = props.obj.image_count || 0
  const idx = props.obj.last_read_idx || 0
  if (n < 2 || idx <= 0) return 0
  return Math.min(100, Math.round((idx / (n - 1)) * 100))
})

// 跳转同系列其他卷：整册详情载入后替换 store.directory（保持 directory 视图）
async function openVol(v) {
  try {
    const detail = await api.object(v.id)
    store.directory = { obj: detail }
  } catch (e) {
    message.error(e.message || String(e))
  }
}

// 书签直达阅读器对应页
function goBookmark(b) {
  store.reader = { obj: props.obj, images: props.obj.images, index: b.page_idx, from: 'directory' }
  store.view = { name: 'reader' }
}

async function openFolder() {
  try {
    await api.openInExplorer(props.obj.id)
  } catch (e) {
    message.error(e.message || String(e))
  }
}
</script>

<style scoped>
.dir-side {
  position: relative; flex: none;   /* 宽度由行内 style 绑定（收起/拖动联动 --sidebar-w） */
  padding: 12px 16px 18px;
  border-right: 1px solid var(--border);
  overflow-y: auto;
}
.dir-side.collapsed { overflow: hidden; padding: 0; }
/* 内容列：承载原 .dir-side 的纵向流式布局，脚注用 margin-top:auto 压底 */
.dir-side .side-inner {
  display: flex; flex-direction: column; gap: 18px;
  min-height: 100%;
}
.side-title {
  font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
  opacity: .55; margin-bottom: 8px; text-transform: uppercase;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.side-group { min-width: 0; }

/* 分卷列表 */
/* 分卷列表：超长系列封顶滚动，避免把书签/脚注挤出视野 */
.vol-list {
  display: flex; flex-direction: column; gap: 6px;
  max-height: 400px; overflow-y: auto;
}
.vol-row {
  display: flex; align-items: center; gap: 8px;
  padding: 4px; border-radius: 8px; cursor: pointer;
  /* 常驻透明边框：选中态只换颜色——描边画在盒内不被滚动容器裁切，且布局零位移 */
  border: 1px solid transparent;
  transition: background .15s, border-color .15s;
}
.vol-row:hover { background: var(--chip-bg); }
.vol-row.current { background: var(--chip-bg); border-color: var(--ms-primary); }
.vol-cover {
  width: 38px; aspect-ratio: 5 / 7; object-fit: cover; border-radius: 4px;
  background: var(--chip-bg); flex: none;
}
.vol-meta { min-width: 0; }
.vol-label {
  font-size: 12px; font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.vol-row.current .vol-label { color: var(--ms-primary); }
.vol-sub { font-size: 11px; opacity: .55; margin-top: 2px; }

/* 书签列表 */
.bm-list { display: flex; flex-direction: column; gap: 4px; }
.bm-row {
  display: flex; align-items: center; gap: 7px;
  padding: 4px 6px; border-radius: 6px; cursor: pointer;
  font-size: 12px; transition: background .15s;
}
.bm-row:hover { background: var(--chip-bg); }
.bm-ico { color: #f5a623; display: inline-flex; flex: none; }
.bm-page { flex: none; font-weight: 600; opacity: .85; }
.bm-note {
  min-width: 0; opacity: .6;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* 信息脚注 */
.side-foot {
  margin-top: auto; padding-top: 12px;
  border-top: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.foot-stats { font-size: 12px; opacity: .6; }
.foot-btn {
  border: none; background: transparent; cursor: pointer;
  color: var(--text2, inherit); opacity: .7;
  padding: 4px; border-radius: 6px; display: inline-flex;
  transition: background .15s, opacity .15s;
}
.foot-btn:hover { background: var(--chip-bg); opacity: 1; }
</style>
