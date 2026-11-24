import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import puppeteer, { Browser, Page } from 'puppeteer-core';
import { CHROME_PATH } from './helpers/browser';
const PREVIEW_URL = 'http://localhost:4173/';

describe('Outlet Card Layout & Interaction Verification', { timeout: 25000 }, () => {
  let browser: Browser;
  let page: Page;

  beforeAll(async () => {
    browser = await puppeteer.launch({
      executablePath: CHROME_PATH,
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    });
    page = await browser.newPage();
  }, 20000);

  afterAll(async () => {
    if (browser) {
      await browser.close();
    }
  });

  it('contains all footer action buttons strictly inside parent cards on desktop (1280px)', async () => {
    await page.setViewport({ width: 1280, height: 900 });
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card', { timeout: 10000 });

    const overflows = await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll('.outlet-card'));
      return cards.map((card, idx) => {
        const cardRect = card.getBoundingClientRect();
        const buttons = Array.from(card.querySelectorAll('button'));
        const protruding = buttons.filter((btn) => {
          const btnRect = btn.getBoundingClientRect();
          return btnRect.right > cardRect.right + 0.5 || btnRect.left < cardRect.left - 0.5;
        });
        return { cardIndex: idx, protrudingCount: protruding.length };
      });
    });

    expect(overflows.length).toBeGreaterThan(0);
    overflows.forEach((o) => {
      expect(o.protrudingCount, `Card ${o.cardIndex} has protruding footer buttons`).toBe(0);
    });
  });

  it('contains all footer action buttons strictly inside parent cards on mobile (390px)', async () => {
    await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card', { timeout: 10000 });

    const overflows = await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll('.outlet-card'));
      return cards.map((card, idx) => {
        const cardRect = card.getBoundingClientRect();
        const buttons = Array.from(card.querySelectorAll('button'));
        const protruding = buttons.filter((btn) => {
          const btnRect = btn.getBoundingClientRect();
          return btnRect.right > cardRect.right + 0.5 || btnRect.left < cardRect.left - 0.5;
        });
        return { cardIndex: idx, protrudingCount: protruding.length };
      });
    });

    expect(overflows.length).toBeGreaterThan(0);
    overflows.forEach((o) => {
      expect(o.protrudingCount, `Mobile Card ${o.cardIndex} has protruding footer buttons`).toBe(0);
    });
  });

  it('ensures Report button is visible, clickable, and triggers the observation modal', async () => {
    await page.setViewport({ width: 1280, height: 900 });
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    const firstCard = await page.$('.outlet-card');
    expect(firstCard).not.toBeNull();

    // Scroll card into view
    await firstCard!.evaluate((el) => el.scrollIntoView({ behavior: 'instant', block: 'center' }));

    const reportBtn = await firstCard!.$('button[title*="observation"]');
    expect(reportBtn).not.toBeNull();

    // Verify button is visible and not clipped
    const isVisible = await reportBtn!.isIntersectingViewport();
    expect(isVisible).toBe(true);

    // Click report button and verify modal opens
    await reportBtn!.click();
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 });

    const modalTitle = await page.$eval('[role="dialog"] h3', (el) => el.textContent);
    expect(modalTitle).toContain('Report Current Queue');

    // Close modal
    const closeBtn = await page.$('[role="dialog"] button[aria-label*="dialog"], [role="dialog"] button[aria-label*="Close"]');
    if (closeBtn) await closeBtn.click();
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'), { timeout: 5000 });
  }, 25000);

  it('ensures external-link arrow button is contained and opens outlet details', async () => {
    await page.setViewport({ width: 1280, height: 900 });
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    const firstCard = await page.$('.outlet-card');
    await firstCard!.evaluate((el) => el.scrollIntoView({ behavior: 'instant', block: 'center' }));

    const detailBtn = await firstCard!.$('button[title*="details"]');
    expect(detailBtn).not.toBeNull();

    await detailBtn!.click();
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 });

    const dialogText = await page.$eval('[role="dialog"]', (el) => el.textContent);
    expect(dialogText).toBeDefined();

    // Close detail dialog by clicking close button or pressing Escape
    const closeBtn = await page.$('[role="dialog"] button:has(svg)');
    if (closeBtn) await closeBtn.click();
    else await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'), { timeout: 5000 });
  }, 25000);

  it('guarantees zero horizontal card overflow across multiple responsive breakpoints (320px to 1440px)', async () => {
    const testWidths = [320, 360, 375, 414, 640, 768, 1024, 1280, 1440];
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    for (const width of testWidths) {
      await page.setViewport({ width, height: 800 });
      const hasOverflow = await page.evaluate(() => {
        const cards = Array.from(document.querySelectorAll('.outlet-card'));
        return cards.some((card) => {
          const cardRect = card.getBoundingClientRect();
          const buttons = Array.from(card.querySelectorAll('button'));
          return buttons.some((btn) => {
            const b = btn.getBoundingClientRect();
            return b.right > cardRect.right + 0.5 || b.left < cardRect.left - 0.5;
          });
        });
      });

      expect(hasOverflow, `Overflow detected at viewport width ${width}px`).toBe(false);
    }
  }, 40000);

  it('respects prefers-reduced-motion media query', async () => {
    await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
    await page.setViewport({ width: 1280, height: 900 });
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    const transitionStyle = await page.$eval('.outlet-card', (el) => {
      const computed = window.getComputedStyle(el);
      return computed.transitionDuration;
    });

    // In reduced motion, transition is set to 0s or none
    expect(['0s', 'none', '']).toContain(transitionStyle);
  });
});
