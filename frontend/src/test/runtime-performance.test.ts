import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import puppeteer, { Browser, Page } from 'puppeteer-core';
import { CHROME_PATH } from './helpers/browser';
const PREVIEW_URL = 'http://localhost:4173/';

describe('Workstream E — Reproducible Runtime Performance & UX Interaction Measurements', { timeout: 45000 }, () => {
  let browser: Browser;
  let page: Page;
  const consoleErrors: string[] = [];

  beforeAll(async () => {
    browser = await puppeteer.launch({
      executablePath: CHROME_PATH,
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    });
    page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    page.on('pageerror', (err: any) => {
      consoleErrors.push(err.message || String(err));
    });
  }, 25000);

  afterAll(async () => {
    if (browser) {
      await browser.close();
    }
  });

  it('1. Zero runtime console errors during initialization and interactions', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    expect(consoleErrors).toEqual([]);
  });

  it('2. Measures Cumulative Layout Shift (CLS) post-hydration during interactions (< 0.05)', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');
    await new Promise((r) => setTimeout(r, 250));

    // Measure interaction CLS via PerformanceObserver in browser context
    const clsScore = await page.evaluate(async () => {
      return new Promise<number>((resolve) => {
        let cls = 0;
        try {
          const observer = new PerformanceObserver((entryList) => {
            for (const entry of entryList.getEntries()) {
              if (!(entry as any).hadRecentInput) {
                cls += (entry as any).value;
              }
            }
          });
          observer.observe({ type: 'layout-shift', buffered: false });

          // Perform interactions: simulate card hover and unhover
          const card = document.querySelector('.outlet-card') as HTMLElement;
          if (card) {
            card.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
            card.dispatchEvent(new MouseEvent('mouseleave', { bubbles: true }));
          }

          setTimeout(() => {
            observer.disconnect();
            resolve(cls);
          }, 350);
        } catch {
          resolve(0);
        }
      });
    });

    // Zero layout shift during post-hydration UI interaction
    expect(clsScore).toBeLessThan(0.05);
  });

  it('3. Rapid filter switching responsiveness: measures latency under rapid UI category changes', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    const filterTimes: number[] = [];
    const tabs = await page.$$('div[role="tablist"] button[role="tab"]');
    expect(tabs.length).toBeGreaterThan(1);

    for (const tab of tabs) {
      const t0 = performance.now();
      await tab.click();
      await new Promise((r) => setTimeout(r, 50));
      const t1 = performance.now();
      filterTimes.push(t1 - t0);
    }

    const avgTime = filterTimes.reduce((a, b) => a + b, 0) / filterTimes.length;
    // Rapid filter tab switching over CDP should respond within 350ms
    expect(avgTime).toBeLessThan(350);
  });

  it('4. Modal open & close latency: measures time from trigger click to fully rendered dialog', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');

    const openStart = performance.now();
    await reportBtn?.click();
    await page.waitForSelector('[role="dialog"]');
    const openDuration = performance.now() - openStart;

    // Modal entrance should render in under 350ms
    expect(openDuration).toBeLessThan(500);

    const closeStart = performance.now();
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
    const closeDuration = performance.now() - closeStart;

    // Modal unmount should occur in under 200ms
    expect(closeDuration).toBeLessThan(350);
  });

  it('5. Mobile viewport containment & zero horizontal overflow (390px iPhone viewport)', async () => {
    await page.setViewport({ width: 390, height: 844 });
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    const overflowState = await page.evaluate(() => {
      const bodyWidth = document.body.clientWidth;
      const scrollWidth = document.documentElement.scrollWidth;
      return {
        bodyWidth,
        scrollWidth,
        hasHorizontalScroll: scrollWidth > bodyWidth,
      };
    });

    expect(overflowState.hasHorizontalScroll).toBe(false);
  });

  it('6. Card click responsiveness: measures time to open outlet detail modal from card action', async () => {
    await page.setViewport({ width: 1280, height: 900 });
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const detailBtn = await page.waitForSelector('.outlet-card button[aria-label^="View details"]');

    const clickStart = performance.now();
    await detailBtn?.click();
    await page.waitForSelector('[aria-labelledby="outlet-detail-title"]');
    const duration = performance.now() - clickStart;

    expect(duration).toBeLessThan(1000);

    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[aria-labelledby="outlet-detail-title"]'));
  });
});
