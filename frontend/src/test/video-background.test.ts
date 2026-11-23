import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import puppeteer, { Browser, Page } from 'puppeteer-core';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PREVIEW_URL = 'http://localhost:4173/';

describe('Global Cinematic Video Background & Modal Synchronization Engine', () => {
  let browser: Browser;
  let page: Page;

  beforeAll(async () => {
    browser = await puppeteer.launch({
      executablePath: CHROME_PATH,
      headless: true,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--autoplay-policy=no-user-gesture-required',
      ],
    });
    page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
  }, 25000);

  afterAll(async () => {
    if (browser) {
      await browser.close();
    }
  });

  it('renders video element with all required persistent attributes and poster fallback', async () => {
    await page.goto(PREVIEW_URL, { waitUntil: 'networkidle2' });
    await page.waitForSelector('[data-testid="cinematic-video-layer"]', { timeout: 10000 });

    const videoAttrs = await page.evaluate(() => {
      const layer = document.querySelector('[data-testid="cinematic-video-layer"]');
      const video = layer?.querySelector('video');
      const style = layer ? window.getComputedStyle(layer) : null;
      return {
        hasLayer: Boolean(layer),
        layerDisplay: style?.display,
        layerPosition: style?.position,
        layerPointerEvents: style?.pointerEvents,
        hasVideo: Boolean(video),
        src: video?.getAttribute('src') || video?.src,
        poster: video?.getAttribute('poster'),
        loop: video?.loop,
        muted: video?.muted,
        playsInline: video?.hasAttribute('playsinline'),
        preload: video?.getAttribute('preload'),
      };
    });

    expect(videoAttrs.hasLayer).toBe(true);
    expect(videoAttrs.layerDisplay).toBe('block');
    expect(videoAttrs.layerPosition).toBe('fixed');
    expect(videoAttrs.layerPointerEvents).toBe('none');
    expect(videoAttrs.hasVideo).toBe(true);
    expect(videoAttrs.src).toContain('/videos/jellyfish.mp4');
    expect(videoAttrs.poster).toBe('/videos/jellyfish-poster.jpg');
    expect(videoAttrs.loop).toBe(true);
    expect(videoAttrs.muted).toBe(true);
    expect(videoAttrs.playsInline).toBe(true);
    expect(videoAttrs.preload).toBe('auto');
  });

  it('immediately pauses video and hides video layer when Report modal opens', async () => {
    // Open report modal via primary navbar button
    const reportBtn = await page.waitForSelector('header button.btn-electric');
    await reportBtn?.click();

    // Verify modal appears
    await page.waitForSelector('[role="dialog"], .glass-panel-elevated form, form', { timeout: 5000 });

    const state = await page.evaluate(() => {
      const layer = document.querySelector('[data-testid="cinematic-video-layer"]') as HTMLElement | null;
      const video = layer?.querySelector('video') as HTMLVideoElement | null;
      return {
        layerDisplay: layer ? window.getComputedStyle(layer).display : null,
        isPaused: video ? video.paused : null,
        currentTime: video ? video.currentTime : null,
      };
    });

    expect(state.layerDisplay).toBe('none');
    expect(state.isPaused).toBe(true);
  });

  it('instantly reveals video layer and resumes playback from exact timestamp when Report modal closes', async () => {
    // Record current timestamp while paused
    const pausedTime = await page.evaluate(() => {
      const video = document.querySelector('[data-testid="cinematic-video-layer"] video') as HTMLVideoElement | null;
      return video ? video.currentTime : 0;
    });

    // Close the modal by clicking cancel or close button
    const closeBtn = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const cancelBtn = buttons.find((b) => b.textContent?.includes('Cancel') || b.getAttribute('aria-label') === 'Close');
      if (cancelBtn) {
        cancelBtn.click();
        return true;
      }
      return false;
    });
    expect(closeBtn).toBe(true);

    // Wait a brief moment for RAF / effect
    await new Promise((r) => setTimeout(r, 200));

    const resumedState = await page.evaluate(async () => {
      const layer = document.querySelector('[data-testid="cinematic-video-layer"]') as HTMLElement | null;
      const video = layer?.querySelector('video') as HTMLVideoElement | null;
      // Allow brief playback progression
      await new Promise((r) => setTimeout(r, 300));
      return {
        layerDisplay: layer ? window.getComputedStyle(layer).display : null,
        isPaused: video ? video.paused : null,
        currentTime: video ? video.currentTime : null,
      };
    });

    expect(resumedState.layerDisplay).toBe('block');
    expect(resumedState.isPaused).toBe(false);
    expect(resumedState.currentTime).toBeGreaterThanOrEqual(pausedTime);
  });

  it('keeps video paused and layer hidden across chained modal transitions (detail -> report)', async () => {
    // Click details button on first outlet card to open detail modal
    const detailsBtn = await page.waitForSelector('.outlet-card button[aria-label^="View details"]');
    await detailsBtn?.click();

    // Wait for detail modal heading to appear
    await page.waitForSelector('.glass-panel-elevated h2', { timeout: 5000 });

    const detailState = await page.evaluate(() => {
      const layer = document.querySelector('[data-testid="cinematic-video-layer"]') as HTMLElement | null;
      const video = layer?.querySelector('video') as HTMLVideoElement | null;
      return {
        layerDisplay: layer ? window.getComputedStyle(layer).display : null,
        isPaused: video ? video.paused : null,
      };
    });

    expect(detailState.layerDisplay).toBe('none');
    expect(detailState.isPaused).toBe(true);

    // Click "Submit Observation" inside the detail modal
    const chainedClicked = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const reportAction = buttons.find((b) => b.textContent?.includes('Submit Observation'));
      if (reportAction) {
        reportAction.click();
        return true;
      }
      return false;
    });
    expect(chainedClicked).toBe(true);

    // Ensure transition to Report modal maintains hidden/paused video
    await page.waitForSelector('form select, form input', { timeout: 5000 });

    const transitionState = await page.evaluate(() => {
      const layer = document.querySelector('[data-testid="cinematic-video-layer"]') as HTMLElement | null;
      const video = layer?.querySelector('video') as HTMLVideoElement | null;
      return {
        layerDisplay: layer ? window.getComputedStyle(layer).display : null,
        isPaused: video ? video.paused : null,
      };
    });

    expect(transitionState.layerDisplay).toBe('none');
    expect(transitionState.isPaused).toBe(true);

    // Now close report modal
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const cancelBtn = buttons.find((b) => b.textContent?.includes('Cancel') || b.getAttribute('aria-label') === 'Close');
      cancelBtn?.click();
    });

    await new Promise((r) => setTimeout(r, 200));

    const finalState = await page.evaluate(() => {
      const layer = document.querySelector('[data-testid="cinematic-video-layer"]') as HTMLElement | null;
      const video = layer?.querySelector('video') as HTMLVideoElement | null;
      return {
        layerDisplay: layer ? window.getComputedStyle(layer).display : null,
        isPaused: video ? video.paused : null,
      };
    });

    expect(finalState.layerDisplay).toBe('block');
    expect(finalState.isPaused).toBe(false);
  });
});
