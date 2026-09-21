// naming.js 解析函数单测（node 直接运行，无依赖）
import { parseMangaName, applyParsedTags } from '../src/naming.js'

let failed = 0
function check(desc, actual, expected) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a !== e) {
    failed++
    console.error(`[FAIL] ${desc}\n  actual:   ${a}\n  expected: ${e}`)
  } else {
    console.log(`[PASS] ${desc}`)
  }
}

// ① 完整格式：编号-(CM号)[作者名] 本名
check('完整格式',
  parseMangaName('1762328-(COMIC1☆17) [OrangeMaru (YD)] Nightmare (FateGrand Order) [Chinese] [黎欧x新桥月白日语社]'),
  { name: 'Nightmare (FateGrand Order) [Chinese] [黎欧x新桥月白日语社]', cm: 'COMIC1☆17', author: 'OrangeMaru (YD)' })

// ② 无编号
check('无编号',
  parseMangaName('(C102) [谁家作者] 作品名'),
  { name: '作品名', cm: 'C102', author: '谁家作者' })

// ③ 无 CM 段：编号- [作者名] 本名
check('无CM段',
  parseMangaName('999888-[作者甲] 只有本名'),
  { name: '只有本名', cm: null, author: '作者甲' })

// ④ 只有编号和本名
check('编号+本名',
  parseMangaName('1234567-Plain Title Here'),
  { name: 'Plain Title Here', cm: null, author: null })

// ⑤ 完全不匹配：原样保留
check('完全不匹配',
  parseMangaName('随便一个文件夹名'),
  { name: '随便一个文件夹名', cm: null, author: null })

// ⑥ 空值防御
check('空字符串', parseMangaName(''), { name: '', cm: null, author: null })
check('null', parseMangaName(null), { name: '', cm: null, author: null })

// ⑦ 纯数字圆括号不误判为 CM（避免 (2) 之类的序号段）
check('纯数字括号不算CM',
  parseMangaName('[作者乙] 本名 (2)'),
  { name: '本名 (2)', cm: null, author: '作者乙' })

// ⑧ 应用到标签草稿：不覆盖已有值
check('applyParsedTags 填充空类别',
  applyParsedTags({}, { name: 'x', cm: 'C101', author: 'A桑' }),
  { cm: ['C101'], author: ['A桑'] })
check('applyParsedTags 不覆盖已有',
  applyParsedTags({ cm: ['已有CM'] }, { name: 'x', cm: 'C101', author: null }),
  { cm: ['已有CM'] })
check('applyParsedTags null 安全',
  applyParsedTags({ author: ['A'] }, { name: 'x', cm: null, author: null }),
  { author: ['A'] })

console.log(failed ? `\nFAILED: ${failed}` : '\nALL PASS')
process.exit(failed ? 1 : 0)
