/* 主题切换真机验证：用系统 Edge 无头模式打开应用，点击主题开关，
   读取 .app-shell 的 class 与计算背景色，判断主题是否真正生效。 */
const { chromium } = require('playwright-core')

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
  await page.goto('http://127.0.0.1:8765', { waitUntil: 'networkidle' })
  await page.waitForSelector('.app-shell', { timeout: 10000 })
  await page.waitForTimeout(500)

  const read = () => page.locator('.app-shell').evaluate(
    el => `${el.className} | bg=${getComputedStyle(el).backgroundColor}`)

  const before = await read()
  await page.locator('.topbar .n-switch').click()
  await page.waitForTimeout(700)
  const after = await read()

  console.log('BEFORE:', before)
  console.log('AFTER :', after)
  console.log(before !== after ? 'THEME-SWITCH: OK' : 'THEME-SWITCH: BROKEN')
  await browser.close()
}

main().catch(e => { console.error('ERR:', e.message); process.exit(1) })
