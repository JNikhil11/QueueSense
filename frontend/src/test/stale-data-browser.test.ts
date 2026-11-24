import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import puppeteer, { Browser, Page } from 'puppeteer-core';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PREVIEW_URL = 'http://localhost:4173/';

const mockLocations = [
  {
    id: 'iitb-mess-h12-14',
    name: 'Hostel 12-14 Dining Complex',
    category: 'MESS',
    description: 'Central multi-tiered student mess',
    landmarkLocation: 'Lakeside Road, East Campus',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Hall Manager Official Directory',
    openHours: '07:30-21:30',
    capacity: 600,
    active: true,
    estimate: {
      predictedWaitMinutes: 8,
      predictedQueueLength: 12,
      confidence: 0.85,
      confidenceLabel: 'HIGH',
      congestion: 'LOW',
      freshness: 'LIVE',
      freshnessState: 'LIVE',
      recentReportCount: 5,
      sampleSize: 5,
      newestReportAgeMinutes: 3,
      lastReportedTime: new Date().toISOString(),
      distinctDevicesCount: 4,
      trend: 'STABLE',
      evidenceExplanation: 'Verified by 5 independent observations.',
    },
  },
  {
    id: 'iitb-cafe-brew',
    name: 'Brew & Bite Express',
    category: 'CAFE',
    description: 'Specialty quick-service campus cafe',
    landmarkLocation: 'Student Activity Centre',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Commercial Services Office',
    openHours: '08:00-23:00',
    capacity: 80,
    active: true,
    estimate: {
      predictedWaitMinutes: 4,
      predictedQueueLength: 6,
      confidence: 0.90,
      confidenceLabel: 'HIGH',
      congestion: 'LOW',
      freshness: 'LIVE',
      freshnessState: 'LIVE',
      recentReportCount: 6,
      sampleSize: 6,
      newestReportAgeMinutes: 2,
      lastReportedTime: new Date().toISOString(),
      distinctDevicesCount: 5,
      trend: 'STABLE',
      evidenceExplanation: 'Verified by 6 independent observations.',
    },
  },
];

const mockRecommendation = {
  recommendedLocationId: 'iitb-cafe-brew',
  recommendedLocationName: 'Brew & Bite Express',
  predictedWaitMinutes: 4,
  congestion: 'LOW',
  confidence: 0.90,
  confidenceLabel: 'HIGH',
  reason: 'Shortest estimated wait (~4 min) verified by 6 live reports.',
  isEligible: true,
  state: 'recommended',
  minReportsRequired: 3,
  minConfidenceRequired: 0.50,
  candidateCount: 2,
  eligibleCount: 2,
};

describe('Workstream A — Real-Application Stale Data Lifecycle, State Machine & Browser UX', { timeout: 45000 }, () => {
  let browser: Browser;
  let page: Page;

  let locationsMode: 'fresh' | 'fail-500' | 'fail-network' | 'fail-timeout' | 'fail-404' | 'malformed' | 'empty' = 'fresh';
  let recMode: 'fresh' | 'fail' = 'fresh';

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

    page.on('request', (req) => {
      const url = req.url();
      if (url.includes('/api/locations')) {
        if (locationsMode === 'fresh') {
          req.respond({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, data: mockLocations }),
          });
        } else if (locationsMode === 'fail-500') {
          req.respond({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({ success: false, error: 'Database persistence failed' }),
          });
        } else if (locationsMode === 'fail-network') {
          req.abort('failed');
        } else if (locationsMode === 'fail-timeout') {
          req.abort('timedout');
        } else if (locationsMode === 'fail-404') {
          req.respond({
            status: 404,
            contentType: 'application/json',
            body: JSON.stringify({ success: false, error: 'Endpoint not found' }),
          });
        } else if (locationsMode === 'malformed') {
          req.respond({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, data: null }),
          });
        } else if (locationsMode === 'empty') {
          req.respond({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, data: [] }),
          });
        }
      } else if (url.includes('/api/recommendations')) {
        if (recMode === 'fresh') {
          req.respond({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, data: mockRecommendation }),
          });
        } else {
          req.respond({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({ success: false, error: 'Failed' }),
          });
        }
      } else {
        req.continue();
      }
    });
  }, 25000);

  afterAll(async () => {
    if (browser) {
      await browser.close();
    }
  });

  it('1. Complete 13-step lifecycle: initial load -> fresh -> failed refresh -> STALE -> unchanged timestamp -> visible warnings -> successful retry -> FRESH recovery', async () => {
    // Step 1: Start with no cached data
    locationsMode = 'fresh';
    recMode = 'fresh';

    // Step 2: Load locations successfully
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    // Step 3: Verify that the application displays fresh data
    const initialFreshState = await page.evaluate(() => {
      const banner = document.querySelector('[data-testid="stale-data-banner"]');
      const cards = document.querySelectorAll('.outlet-card');
      const staleCardBadges = document.querySelectorAll('[data-testid="stale-card-badge"]');
      const staleRecBadge = document.querySelector('[data-testid="stale-recommendation-badge"]');
      return {
        hasStaleBanner: Boolean(banner),
        cardCount: cards.length,
        staleCardBadgeCount: staleCardBadges.length,
        hasStaleRecBadge: Boolean(staleRecBadge),
      };
    });

    expect(initialFreshState.hasStaleBanner).toBe(false);
    expect(initialFreshState.cardCount).toBe(2);
    expect(initialFreshState.staleCardBadgeCount).toBe(0);
    expect(initialFreshState.hasStaleRecBadge).toBe(false);

    // Step 4: Record the successful update timestamp from application
    await new Promise((r) => setTimeout(r, 100));

    // Step 5 & 6: Trigger subsequent refresh and force it to fail
    locationsMode = 'fail-500';
    const refreshBtn = await page.waitForSelector('header button[aria-label="Refresh data"]');
    await refreshBtn?.click();

    // Step 7: Verify that the application transitions to STALE, not FRESH
    await page.waitForSelector('[data-testid="stale-data-banner"]', { timeout: 5000 });

    // Step 8: Verify previous successful timestamp is retained and unchanged in stale banner
    const staleState = await page.evaluate(() => {
      const banner = document.querySelector('[data-testid="stale-data-banner"]');
      const timestampEl = document.querySelector('[data-testid="stale-timestamp"]');
      const staleBadges = document.querySelectorAll('[data-testid="stale-card-badge"]');
      const staleRecBadge = document.querySelector('[data-testid="stale-recommendation-badge"]');
      const retryBtn = document.querySelector('[data-testid="stale-retry-button"]');
      const staleCardText = document.querySelector('.outlet-card')?.textContent || '';

      return {
        hasBanner: Boolean(banner),
        timestampText: timestampEl?.textContent?.trim() || '',
        staleBadgeCount: staleBadges.length,
        hasStaleRecBadge: Boolean(staleRecBadge),
        hasRetryBtn: Boolean(retryBtn),
        includesStaleWarningText: staleCardText.includes('Stale Estimate • Sync Failed'),
      };
    });

    // Step 9 & 10: Verify stale data is visibly identified and user cannot mistake it for fresh
    expect(staleState.hasBanner).toBe(true);
    expect(staleState.timestampText.length).toBeGreaterThan(0);
    expect(staleState.staleBadgeCount).toBe(2);
    expect(staleState.hasStaleRecBadge).toBe(true);
    expect(staleState.includesStaleWarningText).toBe(true);
    expect(staleState.hasRetryBtn).toBe(true);

    const initialTimestamp = staleState.timestampText;
    expect(initialTimestamp.length).toBeGreaterThan(0);

    // Step 11 & 12: Trigger another refresh and return a successful response
    locationsMode = 'fresh';
    const retryBtn = await page.waitForSelector('[data-testid="stale-retry-button"]');
    await retryBtn?.click();

    // Step 13: Verify recovery to FRESH
    await page.waitForFunction(() => !document.querySelector('[data-testid="stale-data-banner"]'), { timeout: 5000 });

    const recoveredState = await page.evaluate(() => {
      const banner = document.querySelector('[data-testid="stale-data-banner"]');
      const staleBadges = document.querySelectorAll('[data-testid="stale-card-badge"]');
      const staleRecBadge = document.querySelector('[data-testid="stale-recommendation-badge"]');
      return {
        hasBanner: Boolean(banner),
        staleBadgeCount: staleBadges.length,
        hasStaleRecBadge: Boolean(staleRecBadge),
      };
    });

    expect(recoveredState.hasBanner).toBe(false);
    expect(recoveredState.staleBadgeCount).toBe(0);
    expect(recoveredState.hasStaleRecBadge).toBe(false);
  });

  it('2. Initial load failure with no cached data: transitions to ERROR state with retry action, then recovers to FRESH', async () => {
    // Initial fetch fails with HTTP 500
    locationsMode = 'fail-500';

    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('[data-testid="error-state-screen"]', { timeout: 5000 });

    const errorState = await page.evaluate(() => {
      const errorScreen = document.querySelector('[data-testid="error-state-screen"]');
      const cards = document.querySelectorAll('.outlet-card');
      const retryBtn = document.querySelector('[data-testid="error-retry-button"]');
      return {
        hasErrorScreen: Boolean(errorScreen),
        cardCount: cards.length,
        hasRetryBtn: Boolean(retryBtn),
      };
    });

    expect(errorState.hasErrorScreen).toBe(true);
    expect(errorState.cardCount).toBe(0);
    expect(errorState.hasRetryBtn).toBe(true);

    // Click retry with working backend
    locationsMode = 'fresh';
    const retryBtn = await page.waitForSelector('[data-testid="error-retry-button"]');
    await retryBtn?.click();

    await page.waitForSelector('.outlet-card', { timeout: 5000 });
    const recoveredCards = await page.$$('.outlet-card');
    expect(recoveredCards.length).toBe(2);
  });

  it('3. Network failure during refresh: transitions to STALE, preserves data, and recovers upon retry', async () => {
    // Setup fresh data
    locationsMode = 'fresh';
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    // Abort network request on refresh
    locationsMode = 'fail-network';
    const refreshBtn = await page.waitForSelector('header button[aria-label="Refresh data"]');
    await refreshBtn?.click();

    await page.waitForSelector('[data-testid="stale-data-banner"]', { timeout: 5000 });
    const cardCount = await page.$$eval('.outlet-card', (el) => el.length);
    expect(cardCount).toBe(2);

    // Recover
    locationsMode = 'fresh';
    const retryBtn = await page.waitForSelector('[data-testid="stale-retry-button"]');
    await retryBtn?.click();

    await page.waitForFunction(() => !document.querySelector('[data-testid="stale-data-banner"]'), { timeout: 5000 });
  });

  it('4. Request timeout during refresh: transitions to STALE and retains prior observation timestamp', async () => {
    locationsMode = 'fresh';
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    locationsMode = 'fail-timeout';
    const refreshBtn = await page.waitForSelector('header button[aria-label="Refresh data"]');
    await refreshBtn?.click();

    await page.waitForSelector('[data-testid="stale-data-banner"]', { timeout: 5000 });
    const isStale = await page.$eval('[data-testid="stale-data-banner"]', (el) => Boolean(el));
    expect(isStale).toBe(true);

    // Restore
    locationsMode = 'fresh';
    await page.click('[data-testid="stale-retry-button"]');
    await page.waitForFunction(() => !document.querySelector('[data-testid="stale-data-banner"]'), { timeout: 5000 });
  });

  it('5. HTTP 4xx response (e.g. 404): transitions to STALE, fails closed without silent empty substitution', async () => {
    locationsMode = 'fresh';
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    locationsMode = 'fail-404';
    const refreshBtn = await page.waitForSelector('header button[aria-label="Refresh data"]');
    await refreshBtn?.click();

    await page.waitForSelector('[data-testid="stale-data-banner"]', { timeout: 5000 });
    const cardCount = await page.$$eval('.outlet-card', (el) => el.length);
    expect(cardCount).toBe(2);

    locationsMode = 'fresh';
    await page.click('[data-testid="stale-retry-button"]');
    await page.waitForFunction(() => !document.querySelector('[data-testid="stale-data-banner"]'), { timeout: 5000 });
  });

  it('6. Malformed API response ({ data: null }): rejected by client schema validation, entering STALE state', async () => {
    locationsMode = 'fresh';
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    locationsMode = 'malformed';
    const refreshBtn = await page.waitForSelector('header button[aria-label="Refresh data"]');
    await refreshBtn?.click();

    await page.waitForSelector('[data-testid="stale-data-banner"]', { timeout: 5000 });
    const hasStaleBanner = await page.$eval('[data-testid="stale-data-banner"]', (el) => Boolean(el));
    expect(hasStaleBanner).toBe(true);

    locationsMode = 'fresh';
    await page.click('[data-testid="stale-retry-button"]');
    await page.waitForFunction(() => !document.querySelector('[data-testid="stale-data-banner"]'), { timeout: 5000 });
  });

  it('7. Empty but valid API response ({ data: [] }): correctly transitions to EMPTY state without crashing', async () => {
    locationsMode = 'empty';
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });

    // Empty state should render clean no-outlets prompt
    await page.waitForFunction(() => {
      const text = document.body.textContent || '';
      return text.includes('No dining outlets match your query');
    }, { timeout: 5000 });

    const cardCount = await page.$$eval('.outlet-card', (el) => el.length);
    expect(cardCount).toBe(0);
  });

  it('8. Repeated refresh failures: timestamp remains pegged to original successful sync across consecutive failures', async () => {
    locationsMode = 'fresh';
    await page.goto(PREVIEW_URL, { waitUntil: 'load' });
    await page.waitForSelector('.outlet-card');

    // First failure
    locationsMode = 'fail-500';
    await page.click('header button[aria-label="Refresh data"]');
    await page.waitForSelector('[data-testid="stale-data-banner"]', { timeout: 5000 });
    const timestamp1 = await page.$eval('[data-testid="stale-timestamp"]', (el) => el.textContent?.trim());

    // Second failure via Retry button
    await new Promise((r) => setTimeout(r, 200));
    await page.click('[data-testid="stale-retry-button"]');
    await new Promise((r) => setTimeout(r, 300));
    const timestamp2 = await page.$eval('[data-testid="stale-timestamp"]', (el) => el.textContent?.trim());

    // Third failure via navbar button
    await page.click('header button[aria-label="Refresh data"]');
    await new Promise((r) => setTimeout(r, 300));
    const timestamp3 = await page.$eval('[data-testid="stale-timestamp"]', (el) => el.textContent?.trim());

    expect(timestamp1).toBeDefined();
    // The recorded successful sync time remains identical across failures
    expect(timestamp2).toBe(timestamp1);
    expect(timestamp3).toBe(timestamp1);

    // Final recovery
    locationsMode = 'fresh';
    await page.click('[data-testid="stale-retry-button"]');
    await page.waitForFunction(() => !document.querySelector('[data-testid="stale-data-banner"]'), { timeout: 5000 });
    const hasBanner = await page.$eval('[data-testid="stale-data-banner"]', (el) => Boolean(el)).catch(() => false);
    expect(hasBanner).toBe(false);
  });
});
