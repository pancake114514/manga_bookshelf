// 全局常量：标签类别体系（单一真源，组件内不要再重复定义）
export const CATS = ['work', 'author', 'character', 'cm', 'censored']

export const CAT_LABELS = {
  work: '作品',
  author: '作者',
  character: '角色',
  cm: 'CM',
  censored: '修正',
  r18: 'R-18',
  rating: '评分',
}

export const catLabel = c => CAT_LABELS[c] || c

export const RATING_CAT = 'rating'

// 侧栏几何（单一真源）：store 校验持久化宽度与 sidebar 拖动共用同一上下限
export const SIDEBAR_RAIL = 28     // 收起后的细条宽
export const SIDEBAR_MIN = 180     // 拖动调宽下限
export const SIDEBAR_MAX = 400     // 拖动调宽上限
export const SIDEBAR_SNAP = 110    // 拖到此宽度以下松手 → 吸附为收起态
