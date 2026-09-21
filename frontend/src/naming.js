// 漫画文件夹命名规则解析
// 格式：[数字编号-](CM号)[作者名] 本名
// 例：1762328-(COMIC1☆17) [OrangeMaru (YD)] Nightmare (FateGrand Order) [Chinese] [黎欧x新桥月白日语社]
// 各段均可缺省；尾部 [Chinese] [汉化组] 等语言/汉化组信息保留在本名中。

/**
 * 解析漫画文件夹名。
 * @param {string} raw 文件夹名（或用户输入的对象名）
 * @returns {{name: string, cm: string|null, author: string|null}} 解析结果；
 *   不符合规则时 name 为去掉首尾空白的原值，cm/author 为 null。
 */
export function parseMangaName(raw) {
  let s = (raw || '').trim()
  if (!s) return { name: '', cm: null, author: null }

  // ① 可选的数字编号前缀（后跟 '-'）：如 "1762328-"
  const idMatch = s.match(/^(\d+)\s*-\s*/)
  if (idMatch) s = s.slice(idMatch[0].length).trim()

  // ② CM 号：第一个圆括号段（如 "(COMIC1☆17)"），且内容非纯数字
  //    （避免把本名里的 "(FateGrand Order)" 之类误当 CM：CM 段必须出现在
  //     作者方括号之前或作为开头段）
  let cm = null
  const cmMatch = s.match(/^\(([^()]+)\)\s*/)
  if (cmMatch && !/^\d+$/.test(cmMatch[1].trim())) {
    cm = cmMatch[1].trim()
    s = s.slice(cmMatch[0].length).trim()
  }

  // ③ 作者：第一个方括号段（如 "[OrangeMaru (YD)]"），紧随其后（或直接开头）
  let author = null
  const authorMatch = s.match(/^\[([^\[\]]+)\]\s*/)
  if (authorMatch) {
    author = authorMatch[1].trim()
    s = s.slice(authorMatch[0].length).trim()
  }

  // ④ 剩余部分即本名（含尾部 [Chinese] [汉化组] 等）
  return { name: s.trim(), cm, author }
}

/**
 * 应用解析结果到标签草稿：仅填充为空的类别，不覆盖已有值。
 * @param {object} tags 标签草稿 { cm: [], author: [], ... }
 * @param {{name: string, cm: string|null, author: string|null}} parsed
 * @returns {object} 新的标签对象
 */
export function applyParsedTags(tags, parsed) {
  const next = { ...tags }
  if (parsed.cm && !(next.cm || []).length) next.cm = [parsed.cm]
  if (parsed.author && !(next.author || []).length) next.author = [parsed.author]
  return next
}
