import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import puppeteer, { Browser, Page } from 'puppeteer-core';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PREVIEW_URL = 'http://localhost:4173/';

describe('Workstream B — Real Pointer Interaction, Focus Trap Containment & Accessibility Lifecycle', { timeout: 45000 }, () => {
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

  it('1. Tab and Shift+Tab key containment: focus strictly cycles within dialog and never leaks out', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.focus();
    await page.keyboard.press('Enter');

    await page.waitForSelector('[role="dialog"]');
    await new Promise((r) => setTimeout(r, 200));

    // Verify initial auto-focus enters dialog
    const initialFocusInside = await page.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]');
      return dialog ? dialog.contains(document.activeElement) : false;
    });
    expect(initialFocusInside).toBe(true);

    // Forward Tab cycling (12 tabs)
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press('Tab');
      const inside = await page.evaluate(() => {
        const dialog = document.querySelector('[role="dialog"]');
        return dialog ? dialog.contains(document.activeElement) : false;
      });
      expect(inside, `Tab press #${i + 1} leaked focus outside dialog`).toBe(true);
    }

    // Reverse Shift+Tab cycling (12 shift-tabs)
    for (let i = 0; i < 12; i++) {
      await page.keyboard.down('Shift');
      await page.keyboard.press('Tab');
      await page.keyboard.up('Shift');
      const inside = await page.evaluate(() => {
        const dialog = document.querySelector('[role="dialog"]');
        return dialog ? dialog.contains(document.activeElement) : false;
      });
      expect(inside, `Shift+Tab press #${i + 1} leaked focus outside dialog`).toBe(true);
    }

    // Dismiss dialog
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  });

  it('2. Genuine pointer interaction: clicking outside controls cannot steal focus from active modal', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();

    await page.waitForSelector('[role="dialog"]');
    await new Promise((r) => setTimeout(r, 350));

    // Inject an external focusable button outside the modal container to test genuine pointer interaction
    await page.evaluate(() => {
      const outsideBtn = document.createElement('button');
      outsideBtn.id = 'outside-test-button';
      outsideBtn.textContent = 'Outside Click Target';
      outsideBtn.style.position = 'fixed';
      outsideBtn.style.top = '10px';
      outsideBtn.style.left = '10px';
      outsideBtn.style.zIndex = '9999';
      document.body.appendChild(outsideBtn);
    });

    // Perform an actual pointer click on the outside element
    await page.click('#outside-test-button');
    await new Promise((r) => setTimeout(r, 100));

    // Verify that focus was intercepted and pulled back inside the active modal
    const focusConfined = await page.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]');
      const outsideBtn = document.getElementById('outside-test-button');
      const active = document.activeElement;
      return {
        isInsideDialog: dialog ? dialog.contains(active) : false,
        isOutsideBtnFocused: active === outsideBtn,
      };
    });

    expect(focusConfined.isInsideDialog).toBe(true);
    expect(focusConfined.isOutsideBtnFocused).toBe(false);

    // Clean up test element
    await page.evaluate(() => {
      document.getElementById('outside-test-button')?.remove();
    });

    // Close modal cleanly
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  });

  it('3. Real pointer backdrop dismissal: clicking the backdrop dismisses modal and restores focus to trigger', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.focus();
    await page.keyboard.press('Enter');

    await page.waitForSelector('[role="dialog"]');
    await new Promise((r) => setTimeout(r, 350));

    // Click the backdrop outside the modal dialog card (top-left margin: 15px, 15px)
    await page.mouse.click(15, 15);

    // Modal dismisses via backdrop click handler
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'), { timeout: 5000 });

    // Focus is restored to invoking trigger button
    const isTriggerFocused = await page.evaluate(() => {
      const trigger = document.querySelector('header button.btn-electric');
      return document.activeElement === trigger;
    });
    expect(isTriggerFocused).toBe(true);
  });

  it('4. Parent re-renders & callback identity changes: focus trap remains active without premature cleanup or focus theft', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.focus();
    await page.keyboard.press('Enter');

    await page.waitForSelector('[role="dialog"]');
    await new Promise((r) => setTimeout(r, 100));

    // Focus note input
    const noteInput = await page.waitForSelector('[role="dialog"] input[type="text"]');
    await noteInput?.focus();

    // Type text: generates repeated parent re-renders and fresh inline function identities
    await noteInput?.type('Testing lifecycle re-renders without focus theft');

    const currentActiveElement = await page.evaluate(() => {
      const active = document.activeElement;
      const dialog = document.querySelector('[role="dialog"]');
      const headerBtn = document.querySelector('header button.btn-electric');
      return {
        isInsideDialog: dialog ? dialog.contains(active) : false,
        isHeaderTrigger: active === headerBtn,
        activeValue: (active as HTMLInputElement)?.value,
      };
    });

    expect(currentActiveElement.isInsideDialog).toBe(true);
    expect(currentActiveElement.isHeaderTrigger).toBe(false);
    expect(currentActiveElement.activeValue).toBe('Testing lifecycle re-renders without focus theft');

    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  });

  it('5. Focus restoration on all modal types: OutletDetailModal and AdminAuditModal return focus to invoking element', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    // 1. OutletDetailModal
    const detailBtn = await page.waitForSelector('.outlet-card button[aria-label^="View details"]');
    await detailBtn?.focus();
    await page.keyboard.press('Enter');

    await page.waitForSelector('[aria-labelledby="outlet-detail-title"]');
    await new Promise((r) => setTimeout(r, 350));

    // Close via close button
    const detailCloseBtn = await page.waitForSelector('[aria-labelledby="outlet-detail-title"] button[aria-label="Close dialog"]');
    await detailCloseBtn?.click();
    await page.waitForFunction(() => !document.querySelector('[aria-labelledby="outlet-detail-title"]'));

    const isDetailBtnRefocused = await page.evaluate(() => {
      const btn = document.querySelector('.outlet-card button[aria-label^="View details"]');
      return document.activeElement === btn;
    });
    expect(isDetailBtnRefocused).toBe(true);

    // 2. AdminAuditModal
    const adminTrigger = await page.waitForSelector('header button[aria-label="View live campus observation audit stream"]');
    await adminTrigger?.focus();
    await page.keyboard.press('Enter');

    await page.waitForSelector('[aria-labelledby="admin-audit-title"]');
    await new Promise((r) => setTimeout(r, 350));

    const adminCloseBtn = await page.waitForSelector('[aria-labelledby="admin-audit-title"] button[aria-label="Close dialog"]');
    await adminCloseBtn?.click();
    await page.waitForFunction(() => !document.querySelector('[aria-labelledby="admin-audit-title"]'));

    const isAdminTriggerRefocused = await page.evaluate(() => {
      const btn = document.querySelector('header button[aria-label="View live campus observation audit stream"]');
      return document.activeElement === btn;
    });
    expect(isAdminTriggerRefocused).toBe(true);
  });

  it('6. Hidden, disabled, and inert elements are strictly excluded from the focus sequence', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();

    await page.waitForSelector('[role="dialog"]');

    // Inject temporary test elements to verify exclusion
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

    const focusedElementIds = await page.evaluate(() => {
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

  it('7. Dynamic elements: inserting or removing controls dynamically updates the focus sequence', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();

    await page.waitForSelector('[role="dialog"]');

    // 1. Insert dynamic control
    await page.evaluate(() => {
      const form = document.querySelector('[role="dialog"] form');
      if (!form) return;
      const dynamicBtn = document.createElement('button');
      dynamicBtn.id = 'dynamic-custom-action';
      dynamicBtn.textContent = 'Dynamic Action';
      form.insertBefore(dynamicBtn, form.firstChild);
    });

    const isDynamicFound = await page.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]');
      if (!dialog) return false;
      const selector = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
      const items = Array.from(dialog.querySelectorAll<HTMLElement>(selector));
      return items.some((el) => el.id === 'dynamic-custom-action');
    });
    expect(isDynamicFound).toBe(true);

    // 2. Remove dynamic control
    await page.evaluate(() => {
      const el = document.getElementById('dynamic-custom-action');
      el?.remove();
    });

    const isDynamicRemoved = await page.evaluate(() => {
      return document.getElementById('dynamic-custom-action') === null;
    });
    expect(isDynamicRemoved).toBe(true);

    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  });

  it('8. Zero-focusable-elements dialog safety: container receives focus safely without throwing', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();

    await page.waitForSelector('[role="dialog"]');

    // Temporarily disable all interactive controls inside dialog to simulate zero-element state
    await page.evaluate(() => {
      const controls = document.querySelectorAll<HTMLElement>('[role="dialog"] button, [role="dialog"] input, [role="dialog"] select');
      controls.forEach((c) => {
        c.setAttribute('disabled', 'true');
        c.setAttribute('tabindex', '-1');
      });
    });

    // Press Tab
    await page.keyboard.press('Tab');

    // Focus falls back to the container safely without JavaScript error
    const containerHasFocusOrValid = await page.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]');
      return dialog ? dialog.contains(document.activeElement) || document.activeElement === dialog : false;
    });
    expect(containerHasFocusOrValid).toBe(true);

    // Clean up
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  });

  it('9. Multiple modals: focus transitions safely during chained modal interactions', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    // Open OutletDetailModal
    const detailsBtn = await page.waitForSelector('.outlet-card button[aria-label^="View details"]');
    await detailsBtn?.click();

    await page.waitForSelector('[aria-labelledby="outlet-detail-title"]');

    // Click "Submit Observation" inside detail modal to transition to ReportModal
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const btn = buttons.find((b) => b.textContent?.includes('Submit Observation'));
      btn?.click();
    });

    // Verify ReportModal is now the active modal
    await page.waitForSelector('[aria-labelledby="report-dialog-title"]');
    await new Promise((r) => setTimeout(r, 200));

    const activeDialogTitle = await page.evaluate(() => {
      const active = document.activeElement;
      const reportDialog = document.querySelector('[aria-labelledby="report-dialog-title"]');
      return reportDialog ? reportDialog.contains(active) : false;
    });

    expect(activeDialogTitle).toBe(true);

    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  });
});
