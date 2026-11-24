import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import puppeteer, { Browser, Page, HTTPRequest } from 'puppeteer-core';
import { CHROME_PATH } from './helpers/browser';
const PREVIEW_URL = 'http://localhost:4173/';

const mockLocations = [
  {
    id: 'iitb-mess-h12-14',
    name: 'Hostel 12-14 Dining Complex',
    category: 'MESS',
    description: 'Central dining complex',
    landmarkLocation: 'Lakeside Road',
    openHours: '07:30-21:30',
    active: true,
    estimate: {
      predictedWaitMinutes: 8,
      predictedQueueLength: 12,
      confidence: 0.85,
      confidenceLabel: 'HIGH',
      congestion: 'LOW',
      freshness: 'LIVE',
      reportCount: 5,
      recentReportCount: 5,
      updatedAt: new Date().toISOString(),
    },
  },
  {
    id: 'iitb-cafe-brew',
    name: 'Brew & Bite Express',
    category: 'CAFE',
    description: 'Campus cafe',
    landmarkLocation: 'Student Activity Centre',
    openHours: '08:00-23:00',
    active: true,
    estimate: {
      predictedWaitMinutes: 4,
      predictedQueueLength: 6,
      confidence: 0.9,
      confidenceLabel: 'HIGH',
      congestion: 'LOW',
      freshness: 'LIVE',
      reportCount: 6,
      recentReportCount: 6,
      updatedAt: new Date().toISOString(),
    },
  },
];

const mockRecommendation = {
  recommendedLocationId: 'iitb-cafe-brew',
  recommendedLocationName: 'Brew & Bite Express',
  predictedWaitMinutes: 4,
  congestion: 'LOW',
  confidence: 0.9,
  confidenceLabel: 'HIGH',
  reason: 'Shortest estimated wait (~4 min) verified by live reports.',
  isEligible: true,
  state: 'recommended',
  minReportsRequired: 3,
  minConfidenceRequired: 0.5,
  candidateCount: 2,
  eligibleCount: 2,
};

interface CapturedReport {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: any;
  timestamp: number;
}

describe('ReportModal Idempotency Lifecycle & Pending Non-Dismissal Integrity (Browser Tests)', { timeout: 60000 }, () => {
  let browser: Browser;
  let page: Page;

  let reportResponseMode: 'success' | 'fail-500' | 'pending' = 'fail-500';
  let capturedReports: CapturedReport[] = [];
  let pendingRequestResolver: (() => void) | null = null;

  beforeAll(async () => {
    browser = await puppeteer.launch({
      executablePath: CHROME_PATH,
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    });
    page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });

    await page.evaluateOnNewDocument(() => {
      (window as any).__QUEUESENSE_API_URL__ = '/api';
      (window as any).__QUEUESENSE_DATA_MODE__ = 'production';
    });

    await page.setRequestInterception(true);

    page.on('request', (req: HTTPRequest) => {
      const url = req.url();
      if (url.includes('/api/locations') && url.includes('/reports')) {
        let parsedBody: any = {};
        try {
          parsedBody = JSON.parse(req.postData() || '{}');
        } catch {
          parsedBody = {};
        }

        capturedReports.push({
          url,
          method: req.method(),
          headers: req.headers(),
          body: parsedBody,
          timestamp: Date.now(),
        });

        if (reportResponseMode === 'fail-500') {
          req.respond({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({
              success: false,
              error: 'Database persistence failed. Observation could not be durably recorded.',
              errorCode: 'PERSISTENCE_FAILED',
            }),
          });
        } else if (reportResponseMode === 'pending') {
          // Keep request open until resolver is triggered
          const resolveThisRequest = () => {
            req.respond({
              status: 500,
              contentType: 'application/json',
              body: JSON.stringify({
                success: false,
                error: 'Simulated pending failure settlement.',
                errorCode: 'PERSISTENCE_FAILED',
              }),
            });
          };
          pendingRequestResolver = resolveThisRequest;
        } else if (reportResponseMode === 'success') {
          req.respond({
            status: 201,
            contentType: 'application/json',
            body: JSON.stringify({
              success: true,
              data: {
                report: {
                  reportId: `rep_${Date.now()}`,
                  locationId: parsedBody.locationId || 'iitb-mess-h12-14',
                  reportedWaitMinutes: parsedBody.reportedWaitMinutes || 5,
                  queueLength: parsedBody.queueLength || 8,
                  timestamp: new Date().toISOString(),
                },
                updatedEstimate: {
                  predictedWaitMinutes: parsedBody.reportedWaitMinutes || 5,
                  predictedQueueLength: parsedBody.queueLength || 8,
                  confidence: 0.88,
                  confidenceLabel: 'HIGH',
                  congestion: 'LOW',
                  freshness: 'LIVE',
                  reportCount: 6,
                  recentReportCount: 6,
                  updatedAt: new Date().toISOString(),
                },
              },
            }),
          });
        }
      } else if (url.includes('/api/locations')) {
        req.respond({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, data: mockLocations, isPartial: false }),
        });
      } else if (url.includes('/api/recommendations')) {
        req.respond({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, data: mockRecommendation }),
        });
      } else {
        req.continue();
      }
    });
  }, 30000);

  afterAll(async () => {
    if (browser) {
      await browser.close();
    }
  });

  beforeEach(async () => {
    capturedReports = [];
    pendingRequestResolver = null;
    reportResponseMode = 'fail-500';

    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('header button.btn-electric');
  });

  it('1. Failed submission followed by retry: same logical submission reuses the identical idempotency key', async () => {
    // Open report modal
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();
    await page.waitForSelector('[role="dialog"]');

    // First submit attempt (will fail 500)
    reportResponseMode = 'fail-500';
    const submitBtn = await page.waitForSelector('button[type="submit"]');
    await submitBtn?.click();

    // Verify error alert is displayed
    await page.waitForSelector('[role="alert"]');
    expect(capturedReports.length).toBe(1);

    const firstKey = capturedReports[0].headers['x-idempotency-key'] || capturedReports[0].body.idempotencyKey;
    expect(firstKey).toBeTruthy();
    expect(firstKey.startsWith('idem_')).toBe(true);

    // Verify modal remains open
    const dialogVisible = await page.$('[role="dialog"]');
    expect(dialogVisible).not.toBeNull();

    // Retry submission without modifying any form inputs
    const retrySubmitBtn = await page.waitForSelector('button[type="submit"]:not([disabled])');
    await retrySubmitBtn?.click();

    // Wait for second submission to complete
    await new Promise((r) => setTimeout(r, 300));
    expect(capturedReports.length).toBe(2);

    const secondKey = capturedReports[1].headers['x-idempotency-key'] || capturedReports[1].body.idempotencyKey;
    expect(secondKey).toBeTruthy();

    // Strict idempotency assertion: identical key reused across retry
    expect(secondKey).toBe(firstKey);
  });

  it('2. Pending submission: Escape, top-right close and backdrop clicks must not dismiss the modal', async () => {
    // Open report modal
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();
    await page.waitForSelector('[role="dialog"]');

    // Configure request to stay pending in-flight
    reportResponseMode = 'pending';
    const submitBtn = await page.waitForSelector('button[type="submit"]');
    await submitBtn?.click();

    // Wait for in-flight submitting state (button displays 'Recording...' and is disabled)
    await page.waitForSelector('button[type="submit"][disabled]');
    expect(capturedReports.length).toBe(1);

    const initialKey = capturedReports[0].headers['x-idempotency-key'] || capturedReports[0].body.idempotencyKey;
    expect(initialKey).toBeTruthy();

    // A. Attempt Escape key dismissal while request is pending
    await page.keyboard.press('Escape');
    await new Promise((r) => setTimeout(r, 100));
    expect(await page.$('[role="dialog"]')).not.toBeNull();

    // B. Attempt top-right close button dismissal while request is pending
    const closeBtn = await page.$('button[aria-label="Close dialog"]');
    const isCloseDisabled = await page.evaluate((el) => (el as HTMLButtonElement)?.disabled, closeBtn);
    expect(isCloseDisabled).toBe(true);
    await closeBtn?.click();
    await new Promise((r) => setTimeout(r, 100));
    expect(await page.$('[role="dialog"]')).not.toBeNull();

    // C. Attempt backdrop overlay click while request is pending
    await page.click('[role="dialog"]', { offset: { x: 10, y: 10 } });
    await new Promise((r) => setTimeout(r, 100));
    expect(await page.$('[role="dialog"]')).not.toBeNull();

    // Settle the pending request
    if (pendingRequestResolver) {
      pendingRequestResolver();
    }
    await page.waitForSelector('[role="alert"]');
    expect(await page.$('[role="dialog"]')).not.toBeNull();
  });

  it('3. Successful submission: retained idempotency key is cleared, and subsequent submission generates new key', async () => {
    // Open report modal
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();
    await page.waitForSelector('[role="dialog"]');

    // Submit with success response
    reportResponseMode = 'success';
    const submitBtn = await page.waitForSelector('button[type="submit"]');
    await submitBtn?.click();

    // Wait for success toast / message and automatic modal closure
    await page.waitForSelector('[role="dialog"]', { hidden: true, timeout: 5000 });
    expect(capturedReports.length).toBe(1);

    const firstSuccessKey = capturedReports[0].headers['x-idempotency-key'] || capturedReports[0].body.idempotencyKey;
    expect(firstSuccessKey).toBeTruthy();

    // Reopen modal for a second, independent submission
    const reopenBtn = await page.waitForSelector('header button.btn-electric');
    await reopenBtn?.click();
    await page.waitForSelector('[role="dialog"]');

    // Submit second observation
    const secondSubmitBtn = await page.waitForSelector('button[type="submit"]:not([disabled])');
    await secondSubmitBtn?.click();

    await page.waitForSelector('[role="dialog"]', { hidden: true, timeout: 5000 });
    expect(capturedReports.length).toBe(2);

    const secondSuccessKey = capturedReports[1].headers['x-idempotency-key'] || capturedReports[1].body.idempotencyKey;
    expect(secondSuccessKey).toBeTruthy();

    // Verification: successful submission cleared the retained key; second submission has a fresh key
    expect(secondSuccessKey).not.toBe(firstSuccessKey);
  });

  it('4. Failed submission followed by input changes: next logical submission receives a new key', async () => {
    // Open report modal
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();
    await page.waitForSelector('[role="dialog"]');

    // Attempt 1: fails
    reportResponseMode = 'fail-500';
    const submitBtn = await page.waitForSelector('button[type="submit"]');
    await submitBtn?.click();

    await page.waitForSelector('[role="alert"]');
    expect(capturedReports.length).toBe(1);

    const failedKey = capturedReports[0].headers['x-idempotency-key'] || capturedReports[0].body.idempotencyKey;
    expect(failedKey).toBeTruthy();

    // Modify observation payload: change wait time via quick-select button
    const wait15Btn = await page.waitForSelector('button[aria-label="15 minutes wait"]');
    await wait15Btn?.click();
    await new Promise((r) => setTimeout(r, 100));

    // Submit modified observation
    const retrySubmitBtn = await page.waitForSelector('button[type="submit"]:not([disabled])');
    await retrySubmitBtn?.click();

    await new Promise((r) => setTimeout(r, 300));
    expect(capturedReports.length).toBe(2);

    const modifiedKey = capturedReports[1].headers['x-idempotency-key'] || capturedReports[1].body.idempotencyKey;
    expect(modifiedKey).toBeTruthy();

    // Verification: changing inputs resets the retained key; new logical observation gets a new key
    expect(modifiedKey).not.toBe(failedKey);
  });

  it('5. No unresolved request may lose its retained key across in-flight state changes', async () => {
    // Open report modal
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();
    await page.waitForSelector('[role="dialog"]');

    // Start in-flight request
    reportResponseMode = 'pending';
    const submitBtn = await page.waitForSelector('button[type="submit"]');
    await submitBtn?.click();

    await page.waitForSelector('button[type="submit"][disabled]');
    expect(capturedReports.length).toBe(1);

    const initialKey = capturedReports[0].headers['x-idempotency-key'] || capturedReports[0].body.idempotencyKey;

    // Simulate window events / layout interactions while request is unresolved
    await page.evaluate(() => {
      window.dispatchEvent(new Event('resize'));
      window.dispatchEvent(new Event('focus'));
    });
    await new Promise((r) => setTimeout(r, 150));

    // Settle the request as failed
    if (pendingRequestResolver) {
      pendingRequestResolver();
    }
    await page.waitForSelector('[role="alert"]');

    // Retry submission
    reportResponseMode = 'fail-500';
    const retrySubmitBtn = await page.waitForSelector('button[type="submit"]:not([disabled])');
    await retrySubmitBtn?.click();

    await new Promise((r) => setTimeout(r, 300));
    expect(capturedReports.length).toBe(2);

    const retryKey = capturedReports[1].headers['x-idempotency-key'] || capturedReports[1].body.idempotencyKey;

    // Verification: in-flight events did not drop or corrupt the retained idempotency key
    expect(retryKey).toBe(initialKey);
  });
});
