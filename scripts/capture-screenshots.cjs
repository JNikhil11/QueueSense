const puppeteer = require('../frontend/node_modules/puppeteer-core');
const path = require('path');
const fs = require('fs');

async function capture() {
  const screenshotDir = path.resolve(__dirname, '../docs/screenshots');
  if (!fs.existsSync(screenshotDir)) {
    fs.mkdirSync(screenshotDir, { recursive: true });
  }

  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
  });

  const page = await browser.newPage();

  // 1. Desktop Screenshot
  await page.setViewport({ width: 1280, height: 850 });
  await page.goto('http://localhost:4173/', { waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(screenshotDir, 'desktop_redesign.png'), fullPage: false });
  console.log('Saved desktop_redesign.png');

  // 2. Open Detail Modal
  const detailBtns = await page.$$("button[title='View details and history']");
  if (detailBtns.length > 0) {
    await detailBtns[0].click();
    await new Promise(r => setTimeout(r, 600));
    await page.screenshot({ path: path.join(screenshotDir, 'modal_detail.png') });
    console.log('Saved modal_detail.png');
    await page.keyboard.press('Escape');
    await new Promise(r => setTimeout(r, 400));
  }

  // 3. Open Report Modal
  const reportBtns = await page.$$("button");
  for (const btn of reportBtns) {
    const text = await page.evaluate(el => el.textContent, btn);
    if (text && text.includes('Report Queue')) {
      await btn.click();
      await new Promise(r => setTimeout(r, 600));
      await page.screenshot({ path: path.join(screenshotDir, 'modal_report.png') });
      console.log('Saved modal_report.png');
      await page.keyboard.press('Escape');
      await new Promise(r => setTimeout(r, 400));
      break;
    }
  }

  // 4. Mobile Screenshot
  await page.setViewport({ width: 390, height: 844, isMobile: true });
  await page.goto('http://localhost:4173/', { waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: path.join(screenshotDir, 'mobile_redesign.png'), fullPage: false });
  console.log('Saved mobile_redesign.png');

  await browser.close();
  console.log('Screenshot capture completed successfully.');
}

capture().catch(err => {
  console.error('Screenshot capture failed:', err);
  process.exit(1);
});
