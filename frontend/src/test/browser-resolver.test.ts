import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';
import { resolveChromePath } from './helpers/browser';

const CURRENT_DIR = path.resolve(fileURLToPath(import.meta.url), '..');

const BROWSER_TEST_FILES = [
  'a11y-and-resilience.test.ts',
  'card-layout-containment.test.ts',
  'focus-trap-lifecycle.test.ts',
  'report-modal-idempotency-browser.test.ts',
  'runtime-performance.test.ts',
  'stale-data-browser.test.ts',
  'video-background.test.ts',
];

describe('Portable Chrome Path Discovery & Cross-Suite Hygiene', () => {
  it('resolves explicit CHROME_BIN when present and prioritizes it over PUPPETEER_EXECUTABLE_PATH', () => {
    const resolved = resolveChromePath({
      env: {
        CHROME_BIN: '/custom/ci/chrome',
        PUPPETEER_EXECUTABLE_PATH: '/other/puppeteer/chromium',
      },
      platform: 'linux',
      existsSync: (p) => p === '/custom/ci/chrome' || p === '/other/puppeteer/chromium',
    });
    expect(resolved).toBe('/custom/ci/chrome');
  });

  it('throws clear error if explicit CHROME_BIN does not exist', () => {
    expect(() =>
      resolveChromePath({
        env: { CHROME_BIN: '/nonexistent/chrome-bin' },
        platform: 'linux',
        existsSync: (p) => p === '/usr/bin/google-chrome',
      })
    ).toThrow(/CHROME_BIN is set to '\/nonexistent\/chrome-bin'/);
  });

  it('resolves explicit PUPPETEER_EXECUTABLE_PATH when CHROME_BIN is unset', () => {
    const resolved = resolveChromePath({
      env: { PUPPETEER_EXECUTABLE_PATH: '/opt/chromium/chrome' },
      platform: 'linux',
      existsSync: (p) => p === '/opt/chromium/chrome',
    });
    expect(resolved).toBe('/opt/chromium/chrome');
  });

  it('throws clear error if explicit PUPPETEER_EXECUTABLE_PATH does not exist', () => {
    expect(() =>
      resolveChromePath({
        env: { PUPPETEER_EXECUTABLE_PATH: '/bad/puppeteer/path' },
        platform: 'linux',
        existsSync: () => false,
      })
    ).toThrow(/PUPPETEER_EXECUTABLE_PATH is set to '\/bad\/puppeteer\/path'/);
  });

  it('simulates Linux and macOS candidate discovery logic (unit simulation only; live execution tested on Windows)', () => {
    const linuxFound = resolveChromePath({
      env: {},
      platform: 'linux',
      existsSync: (p) => p === '/usr/bin/chromium-browser',
    });
    expect(linuxFound).toBe('/usr/bin/chromium-browser');

    const macFound = resolveChromePath({
      env: {},
      platform: 'darwin',
      existsSync: (p) => p === '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    });
    expect(macFound).toBe('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
  });

  it('resolves Windows candidate paths without creating empty relative paths when LOCALAPPDATA is unset', () => {
    const checkedPaths: string[] = [];
    const winFound = resolveChromePath({
      env: { ProgramFiles: 'D:\\Apps' },
      platform: 'win32',
      existsSync: (p) => {
        checkedPaths.push(p);
        return p === 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe';
      },
    });
    expect(winFound).toBe('C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe');
    expect(checkedPaths).toContain('D:\\Apps\\Google\\Chrome\\Application\\chrome.exe');
    expect(checkedPaths.some((p) => p.startsWith('Google\\Chrome'))).toBe(false);
  });

  it('throws descriptive error listing checked candidate paths when no executable is found', () => {
    expect(() =>
      resolveChromePath({
        env: {},
        platform: 'linux',
        existsSync: () => false,
      })
    ).toThrow(/Chrome\/Chromium executable not found across candidate paths for platform 'linux'/);
  });

  it('ensures zero hardcoded machine-specific browser paths remain in any of the seven Puppeteer test files', () => {
    for (const fileName of BROWSER_TEST_FILES) {
      const fullPath = path.join(CURRENT_DIR, fileName);
      const source = fs.readFileSync(fullPath, 'utf-8');
      expect(source).not.toMatch(/C:\\+Program Files/i);
      expect(source).not.toMatch(/chrome\.exe/i);
      expect(source).toContain("from './helpers/browser'");
    }
  });
});
