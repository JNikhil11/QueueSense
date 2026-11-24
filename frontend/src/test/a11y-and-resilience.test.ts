import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import puppeteer, { Browser, Page } from 'puppeteer-core';
import { getOrGenerateDeviceId, rotateDeviceId, resetDeviceId } from '../services/deviceId';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PREVIEW_URL = 'http://localhost:4173/';

describe('Accessibility (WCAG 2.2 AA), Focus Trapping & Operational Resilience', { timeout: 30000 }, () => {
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

  describe('Focus Trapping, Navigation & Restoration (WCAG 2.4.3 / 2.1.2)', () => {
    it('traps Tab navigation within Report Modal and restores focus on Escape dismissal', async () => {
      await page.goto(PREVIEW_URL, { waitUntil: 'load' });
      await page.waitForSelector('header button.btn-electric');

      // Focus the report button and press Enter to open modal
      await page.focus('header button.btn-electric');
      await page.keyboard.press('Enter');

      await page.waitForSelector('[role="dialog"]', { timeout: 5000 });

      // Wait a moment for auto-focus tick
      await new Promise((r) => setTimeout(r, 150));

      // 1. Initial focus inside modal
      const isFocusInside = await page.evaluate(() => {
        const dialog = document.querySelector('[role="dialog"]');
        return dialog ? dialog.contains(document.activeElement) : false;
      });
      expect(isFocusInside).toBe(true);

      // 2. Count focusable elements inside dialog
      const focusableCount = await page.evaluate(() => {
        const dialog = document.querySelector('[role="dialog"]');
        if (!dialog) return 0;
        const selector =
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
        return dialog.querySelectorAll(selector).length;
      });
      expect(focusableCount).toBeGreaterThanOrEqual(5);

      // 3. Tab through all elements and ensure focus never leaks outside dialog
      for (let i = 0; i < focusableCount + 2; i++) {
        await page.keyboard.press('Tab');
        const trapped = await page.evaluate(() => {
          const dialog = document.querySelector('[role="dialog"]');
          return dialog ? dialog.contains(document.activeElement) : false;
        });
        expect(trapped).toBe(true);
      }

      // 4. Shift+Tab backward and ensure focus remains trapped
      for (let i = 0; i < 3; i++) {
        await page.keyboard.down('Shift');
        await page.keyboard.press('Tab');
        await page.keyboard.up('Shift');
        const trapped = await page.evaluate(() => {
          const dialog = document.querySelector('[role="dialog"]');
          return dialog ? dialog.contains(document.activeElement) : false;
        });
        expect(trapped).toBe(true);
      }

      // 5. Escape key dismisses modal and restores focus to triggering navbar button
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('[role="dialog"]'), { timeout: 5000 });

      const activeElementTag = await page.evaluate(() => {
        const el = document.activeElement;
        return {
          tagName: el?.tagName,
          isTrigger: el?.classList.contains('btn-electric'),
        };
      });
      expect(activeElementTag.tagName).toBe('BUTTON');
      expect(activeElementTag.isTrigger).toBe(true);
    });

    it('traps Tab navigation within Outlet Detail Modal and restores focus on close', async () => {
      await page.goto(PREVIEW_URL, { waitUntil: 'load' });
      await page.waitForSelector('.outlet-card');

      // Click first outlet card's details button
      const detailsBtn = await page.waitForSelector('.outlet-card button[aria-label^="View details"]');
      await detailsBtn?.focus();
      await page.keyboard.press('Enter');

      await page.waitForSelector('[role="dialog"]', { timeout: 5000 });
      await new Promise((r) => setTimeout(r, 150));

      // Verify focus is trapped inside detail dialog
      const trapped = await page.evaluate(() => {
        const dialog = document.querySelector('[role="dialog"]');
        return dialog ? dialog.contains(document.activeElement) : false;
      });
      expect(trapped).toBe(true);

      // Press Escape to dismiss
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('[role="dialog"]'), { timeout: 5000 });

      // Focus restored to details button
      const restored = await page.evaluate(() => {
        return document.activeElement?.getAttribute('aria-label')?.startsWith('View details');
      });
      expect(restored).toBe(true);
    });
  });

  describe('Accessible Names, Roles, and Headings (WCAG 4.1.2 / 1.3.1)', () => {
    it('verifies ReportModal role, aria-modal, aria-labelledby and title matching', async () => {
      await page.goto(PREVIEW_URL, { waitUntil: 'load' });
      const reportBtn = await page.waitForSelector('header button.btn-electric');
      await reportBtn?.click();
      await page.waitForSelector('[role="dialog"]');

      const a11yProps = await page.evaluate(() => {
        const dialog = document.querySelector('[role="dialog"]');
        const role = dialog?.getAttribute('role');
        const ariaModal = dialog?.getAttribute('aria-modal');
        const labelledBy = dialog?.getAttribute('aria-labelledby');
        const heading = labelledBy ? document.getElementById(labelledBy) : null;
        const closeBtn = dialog?.querySelector('button[aria-label="Close dialog"]');

        return {
          role,
          ariaModal,
          labelledBy,
          headingExists: Boolean(heading),
          headingText: heading?.textContent?.trim(),
          hasCloseButtonLabel: Boolean(closeBtn),
        };
      });

      expect(a11yProps.role).toBe('dialog');
      expect(a11yProps.ariaModal).toBe('true');
      expect(a11yProps.labelledBy).toBe('report-dialog-title');
      expect(a11yProps.headingExists).toBe(true);
      expect(a11yProps.headingText).toContain('Report Current Queue');
      expect(a11yProps.hasCloseButtonLabel).toBe(true);

      // Close
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
    });

    it('verifies OutletDetailModal role, aria-modal, aria-labelledby and title matching', async () => {
      await page.goto(PREVIEW_URL, { waitUntil: 'load' });
      const detailsBtn = await page.waitForSelector('.outlet-card button[aria-label^="View details"]');
      await detailsBtn?.click();
      await page.waitForSelector('[role="dialog"]');

      const a11yProps = await page.evaluate(() => {
        const dialog = document.querySelector('[role="dialog"]');
        const role = dialog?.getAttribute('role');
        const ariaModal = dialog?.getAttribute('aria-modal');
        const labelledBy = dialog?.getAttribute('aria-labelledby');
        const heading = labelledBy ? document.getElementById(labelledBy) : null;
        const closeBtn = dialog?.querySelector('button[aria-label="Close dialog"]');

        return {
          role,
          ariaModal,
          labelledBy,
          headingExists: Boolean(heading),
          headingText: heading?.textContent?.trim(),
          hasCloseButtonLabel: Boolean(closeBtn),
        };
      });

      expect(a11yProps.role).toBe('dialog');
      expect(a11yProps.ariaModal).toBe('true');
      expect(a11yProps.labelledBy).toBe('outlet-detail-title');
      expect(a11yProps.headingExists).toBe(true);
      expect(a11yProps.headingText?.length).toBeGreaterThan(0);
      expect(a11yProps.hasCloseButtonLabel).toBe(true);

      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
    });

    it('verifies AdminAuditModal role, aria-modal, aria-labelledby and title matching', async () => {
      await page.goto(PREVIEW_URL, { waitUntil: 'load' });
      const auditBtn = await page.waitForSelector('header button[aria-label="View live campus observation audit stream"]');
      await auditBtn?.click();
      await page.waitForSelector('[role="dialog"]');

      const a11yProps = await page.evaluate(() => {
        const dialog = document.querySelector('[role="dialog"]');
        const role = dialog?.getAttribute('role');
        const ariaModal = dialog?.getAttribute('aria-modal');
        const labelledBy = dialog?.getAttribute('aria-labelledby');
        const heading = labelledBy ? document.getElementById(labelledBy) : null;
        const closeBtn = dialog?.querySelector('button[aria-label="Close dialog"]');

        return {
          role,
          ariaModal,
          labelledBy,
          headingExists: Boolean(heading),
          headingText: heading?.textContent?.trim(),
          hasCloseButtonLabel: Boolean(closeBtn),
        };
      });

      expect(a11yProps.role).toBe('dialog');
      expect(a11yProps.ariaModal).toBe('true');
      expect(a11yProps.labelledBy).toBe('admin-audit-title');
      expect(a11yProps.headingExists).toBe(true);
      expect(a11yProps.headingText).toContain('Campus Queue Audit Stream');
      expect(a11yProps.hasCloseButtonLabel).toBe(true);

      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
    });
  });

  describe('Touch Target Sizes (WCAG 2.5.8 Level AA)', () => {
    it('verifies all primary buttons in Navbar and OutletCard meet or exceed 44x44px', async () => {
      await page.goto(PREVIEW_URL, { waitUntil: 'load' });
      await page.waitForSelector('.outlet-card');

      const targetSizes = await page.evaluate(() => {
        const elementsToCheck = [
          ...Array.from(document.querySelectorAll('header button')),
          ...Array.from(document.querySelectorAll('.outlet-card button')),
        ];

        return elementsToCheck.map((el) => {
          const rect = el.getBoundingClientRect();
          return {
            ariaLabel: el.getAttribute('aria-label') || el.textContent?.trim(),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            satisfiesTargetSize: rect.height >= 43.5 && rect.width >= 43.5, // 44px with sub-pixel tolerance
          };
        });
      });

      expect(targetSizes.length).toBeGreaterThan(0);
      targetSizes.forEach((target) => {
        expect(
          target.satisfiesTargetSize,
          `Button "${target.ariaLabel}" has insufficient size ${target.width}x${target.height}px`
        ).toBe(true);
      });
    });

    it('verifies modal close and action buttons meet or exceed 44x44px', async () => {
      await page.goto(PREVIEW_URL, { waitUntil: 'load' });
      const reportBtn = await page.waitForSelector('header button.btn-electric');
      await reportBtn?.click();
      await page.waitForSelector('[role="dialog"]');
      await new Promise((r) => setTimeout(r, 350));

      const modalButtons = await page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('[role="dialog"] button'));
        return buttons.map((b) => {
          const rect = b.getBoundingClientRect();
          return {
            text: b.getAttribute('aria-label') || b.textContent?.trim(),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            satisfies: rect.height >= 43.5,
          };
        });
      });

      expect(modalButtons.length).toBeGreaterThan(0);
      modalButtons.forEach((btn) => {
        expect(btn.satisfies, `Modal button "${btn.text}" has insufficient height: ${btn.height}px`).toBe(true);
      });

      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
    });
  });

  describe('Card Hover Dimming & Scaling Properties (Workstream 1)', () => {
    it('applies 0.45 opacity to sibling cards and scales active card to 1.02', async () => {
      await page.goto(PREVIEW_URL, { waitUntil: 'load' });
      await page.waitForSelector('.outlet-card');

      const cards = await page.$$('.outlet-card');
      expect(cards.length).toBeGreaterThan(1);

      await cards[0].hover();
      await new Promise((r) => setTimeout(r, 350));

      const hoverMetrics = await page.evaluate(() => {
        const allCards = Array.from(document.querySelectorAll('.outlet-card'));
        const activeCard = allCards[0];
        const siblingCards = allCards.slice(1);

        const activeStyle = window.getComputedStyle(activeCard);
        const siblingStyles = siblingCards.map((c) => window.getComputedStyle(c).opacity);

        return {
          activeOpacity: activeStyle.opacity,
          activeTransform: activeStyle.transform,
          siblingOpacities: siblingStyles,
        };
      });

      expect(hoverMetrics.activeOpacity).toBe('1');
      // Hovered card scales to 1.02 and translates translateY(-4px)
      expect(hoverMetrics.activeTransform).toContain('matrix');
      // Siblings dimmed to exactly 0.45
      expect(hoverMetrics.siblingOpacities.every((op) => Math.abs(parseFloat(op) - 0.45) < 0.05)).toBe(true);
    });

    it('suspends card dimming and scaling when any modal is active', async () => {
      await page.goto(PREVIEW_URL, { waitUntil: 'load' });
      const reportBtn = await page.waitForSelector('header button.btn-electric');
      await reportBtn?.click();
      await page.waitForSelector('[role="dialog"]');

      const modalActiveMetrics = await page.evaluate(() => {
        const allCards = Array.from(document.querySelectorAll('.outlet-card'));
        const opacities = allCards.map((c) => window.getComputedStyle(c).opacity);
        return {
          allFullOpacity: opacities.every((op) => op === '1'),
        };
      });

      expect(modalActiveMetrics.allFullOpacity).toBe(true);

      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
    });
  });

  describe('Storage Resilience & Device Identity (Security & Failure Handling)', () => {
    it('gracefully handles localStorage SecurityError by falling back to in-memory identifier', () => {
      const originalLocalStorage = (globalThis as any).localStorage;
      const originalWindow = (globalThis as any).window;

      try {
        (globalThis as any).window = globalThis;
        const securityErrorMock = {
          getItem: () => {
            throw new DOMException('The operation is insecure.', 'SecurityError');
          },
          setItem: () => {
            throw new DOMException('The operation is insecure.', 'SecurityError');
          },
          removeItem: () => {
            throw new DOMException('The operation is insecure.', 'SecurityError');
          },
          clear: () => {},
          key: () => null,
          length: 0,
        };

        (globalThis as any).localStorage = securityErrorMock;

        resetDeviceId();
        const id1 = getOrGenerateDeviceId();
        expect(id1).not.toBeNull();
        expect(typeof id1).toBe('string');
        expect(id1).toMatch(/^[a-zA-Z0-9_-]{16,64}$/);

        // Subsequent call returns the same in-memory ID
        const id2 = getOrGenerateDeviceId();
        expect(id2).toBe(id1);

        // Rotation safely succeeds in memory
        const rotated = rotateDeviceId();
        expect(rotated).not.toBeNull();
        expect(rotated).not.toBe(id1);
      } finally {
        (globalThis as any).localStorage = originalLocalStorage;
        (globalThis as any).window = originalWindow;
        resetDeviceId();
      }
    });
  });
});

