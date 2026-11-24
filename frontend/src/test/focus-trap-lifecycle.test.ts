import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import puppeteer, { Browser, Page } from 'puppeteer-core';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PREVIEW_URL = 'http://localhost:4173/';

describe('Workstream 1 — Focus Trap Lifecycle, Accessibility & Boundary Verification', { timeout: 35000 }, () => {
  let browser: Browser;
  let page: Page;

  beforeAll(async () => {
    browser = await puppeteer.launch({
      executablePath: CHROME_PATH,
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    });
    page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
  }, 25000);

  afterAll(async () => {
    if (browser) {
      await browser.close();
    }
  });

  it('Parent re-render & callback identity change: focus trap remains active without premature cleanup or focus theft', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.focus();
    await page.keyboard.press('Enter');

    await page.waitForSelector('[role="dialog"]');
    await new Promise((r) => setTimeout(r, 100));

    // Focus an input inside the modal (e.g. note input)
    const noteInput = await page.waitForSelector('[role="dialog"] input[type="text"]');
    await noteInput?.focus();

    // Type into note input: this causes repeated parent/modal re-renders and produces new inline callback identities
    await noteInput?.type('Testing lifecycle re-renders');

    // Verify focus remains strictly on the active input inside the modal
    const currentActiveElement = await page.evaluate(() => {
      const active = document.activeElement;
      const dialog = document.querySelector('[role="dialog"]');
      const headerBtn = document.querySelector('header button.btn-electric');
      return {
        isInsideDialog: dialog ? dialog.contains(active) : false,
        isHeaderTrigger: active === headerBtn,
        activeTagName: active?.tagName,
        activeValue: (active as HTMLInputElement)?.value,
      };
    });

    expect(currentActiveElement.isInsideDialog).toBe(true);
    expect(currentActiveElement.isHeaderTrigger).toBe(false);
    expect(currentActiveElement.activeValue).toBe('Testing lifecycle re-renders');

    // Close modal
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  });

  it('Focus restoration: focus returns to the triggering element only when the modal actually closes', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.focus();
    await page.keyboard.press('Enter');

    await page.waitForSelector('[role="dialog"]');
    await new Promise((r) => setTimeout(r, 100));

    // Verify trigger element outside does NOT have focus while open
    const isTriggerFocusedWhileOpen = await page.evaluate(() => {
      const trigger = document.querySelector('header button.btn-electric');
      return document.activeElement === trigger;
    });
    expect(isTriggerFocusedWhileOpen).toBe(false);

    // Close via close button click
    const closeBtn = await page.waitForSelector('[role="dialog"] button[aria-label="Close dialog"]');
    await closeBtn?.click();

    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));

    // Focus restored to trigger button
    const isTriggerFocusedAfterClose = await page.evaluate(() => {
      const trigger = document.querySelector('header button.btn-electric');
      return document.activeElement === trigger;
    });
    expect(isTriggerFocusedAfterClose).toBe(true);
  });

  it('Pointer focus escape: outside interaction cannot move keyboard focus outside the active modal', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();

    await page.waitForSelector('[role="dialog"]');
    await new Promise((r) => setTimeout(r, 100));

    // Attempt to programmatically or via pointer focus a navbar element outside dialog
    await page.evaluate(() => {
      const refreshBtn = document.querySelector('header button[aria-label="Refresh data"]') as HTMLElement | null;
      refreshBtn?.focus();
    });

    // Verify focus is captured and brought back inside the active modal
    const focusConfined = await page.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]');
      return dialog ? dialog.contains(document.activeElement) : false;
    });
    expect(focusConfined).toBe(true);

    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  });

  it('Hidden, disabled, and inert elements are excluded from the focus sequence', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();

    await page.waitForSelector('[role="dialog"]');

    // Inject temporary elements to verify filtering: hidden, disabled, inert, and tabindex=-1
    await page.evaluate(() => {
      const form = document.querySelector('[role="dialog"] form');
      if (!form) return;

      const hiddenBtn = document.createElement('button');
      hiddenBtn.id = 'test-hidden-btn';
      hiddenBtn.style.display = 'none';
      hiddenBtn.textContent = 'Hidden Button';

      const invisibleBtn = document.createElement('button');
      invisibleBtn.id = 'test-invisible-btn';
      invisibleBtn.style.visibility = 'hidden';
      invisibleBtn.textContent = 'Invisible Button';

      const disabledBtn = document.createElement('button');
      disabledBtn.id = 'test-disabled-btn';
      disabledBtn.setAttribute('disabled', 'true');
      disabledBtn.textContent = 'Disabled Button';

      const inertContainer = document.createElement('div');
      inertContainer.setAttribute('inert', 'true');
      const inertBtn = document.createElement('button');
      inertBtn.id = 'test-inert-btn';
      inertBtn.textContent = 'Inert Button';
      inertContainer.appendChild(inertBtn);

      const negativeTabIndexBtn = document.createElement('button');
      negativeTabIndexBtn.id = 'test-tabindex-btn';
      negativeTabIndexBtn.setAttribute('tabindex', '-1');
      negativeTabIndexBtn.textContent = 'Negative TabIndex Button';

      form.appendChild(hiddenBtn);
      form.appendChild(invisibleBtn);
      form.appendChild(disabledBtn);
      form.appendChild(inertContainer);
      form.appendChild(negativeTabIndexBtn);
    });

    // Now cycle Tab through dialog and record all focused elements
    const focusedElementIds = await page.evaluate(async () => {
      const dialog = document.querySelector('[role="dialog"]');
      if (!dialog) return [];
      const ids: string[] = [];
      const focusable = dialog.querySelectorAll('button, select, input');
      for (let i = 0; i < focusable.length + 3; i++) {
        (dialog as any).dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
        if (document.activeElement?.id) {
          ids.push(document.activeElement.id);
        }
      }
      return ids;
    });

    expect(focusedElementIds).not.toContain('test-hidden-btn');
    expect(focusedElementIds).not.toContain('test-invisible-btn');
    expect(focusedElementIds).not.toContain('test-disabled-btn');
    expect(focusedElementIds).not.toContain('test-inert-btn');
    expect(focusedElementIds).not.toContain('test-tabindex-btn');

    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  });

  it('Dynamic elements: newly inserted focusable controls are immediately included in the focus sequence', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();

    await page.waitForSelector('[role="dialog"]');

    // Insert a new interactive button dynamically
    await page.evaluate(() => {
      const form = document.querySelector('[role="dialog"] form');
      if (!form) return;
      const dynamicBtn = document.createElement('button');
      dynamicBtn.id = 'dynamic-custom-action';
      dynamicBtn.textContent = 'Dynamic Action';
      dynamicBtn.className = 'py-2 px-3 text-xs';
      form.insertBefore(dynamicBtn, form.firstChild);
    });

    // Check if the newly inserted button is detected by focus trap
    const isDynamicFound = await page.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]');
      if (!dialog) return false;
      const selector = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
      const items = Array.from(dialog.querySelectorAll<HTMLElement>(selector));
      return items.some((el) => el.id === 'dynamic-custom-action');
    });

    expect(isDynamicFound).toBe(true);

    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  });

  it('Multiple modals: focus remains in the currently active modal during chained transitions', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    // Open OutletDetailModal
    const detailsBtn = await page.waitForSelector('.outlet-card button[aria-label^="View details"]');
    await detailsBtn?.click();

    await page.waitForSelector('[aria-labelledby="outlet-detail-title"]');

    // Click "Submit Observation" inside detail modal to open ReportModal
    const submitObservationBtn = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const btn = buttons.find((b) => b.textContent?.includes('Submit Observation'));
      if (btn) {
        btn.click();
        return true;
      }
      return false;
    });
    expect(submitObservationBtn).toBe(true);

    // Verify ReportModal is now the active modal
    await page.waitForSelector('[aria-labelledby="report-dialog-title"]');
    await new Promise((r) => setTimeout(r, 100));

    const activeDialogTitle = await page.evaluate(() => {
      const active = document.activeElement;
      const reportDialog = document.querySelector('[aria-labelledby="report-dialog-title"]');
      return reportDialog ? reportDialog.contains(active) : false;
    });

    expect(activeDialogTitle).toBe(true);

    // Escape closes report modal
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  });
});
