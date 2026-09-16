/* 截取深浅两套主题的书架截图 */
const { chromium } = require('playwright-core')

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
  await page.goto('http://127.0.0.1:8765', { waitUntil: 'networkidle' })
  await page.waitForSelector('.obj-card', { timeout: 15000 })
  await page.waitForTimeout(1200)
  await page.screenshot({ path: 'H:/VsCode/manga_bookshelf/design/theme_dark.png' })
  await page.locator('.topbar .n-switch').click()
  await page.waitForTimeout(700)
  await page.screenshot({ path: 'H:/VsCode/manga_bookshelf/design/theme_light.png' })
  await browser.close()
  console.log('screenshots saved')
}

main().catch(e => { console.error('ERR:', e.message); process.exit(1) })
