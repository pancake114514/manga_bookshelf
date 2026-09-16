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

export const R18_CAT = 'r18'
export const RATING_CAT = 'rating'
