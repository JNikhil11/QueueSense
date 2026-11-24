import fs from 'node:fs';
import path from 'node:path';

export interface ResolveChromeOptions {
  env?: Record<string, string | undefined>;
  platform?: string;
  existsSync?: (candidate: string) => boolean;
}

export function resolveChromePath(options: ResolveChromeOptions = {}): string {
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  const existsSync = options.existsSync ?? fs.existsSync;

  // 1. Explicit environment overrides (fail fast if explicitly misconfigured)
  const explicitChromeBin = env.CHROME_BIN?.trim();
  if (explicitChromeBin) {
    if (existsSync(explicitChromeBin)) {
      return explicitChromeBin;
    }
    throw new Error(
      `CHROME_BIN is set to '${explicitChromeBin}', but no executable was found at that path.`
    );
  }

  const explicitPuppeteerPath = env.PUPPETEER_EXECUTABLE_PATH?.trim();
  if (explicitPuppeteerPath) {
    if (existsSync(explicitPuppeteerPath)) {
      return explicitPuppeteerPath;
    }
    throw new Error(
      `PUPPETEER_EXECUTABLE_PATH is set to '${explicitPuppeteerPath}', but no executable was found at that path.`
    );
  }

  // 2. Platform-specific standard candidate paths
  const rawCandidates: string[] = [];

  if (platform === 'win32') {
    const winJoin = path.win32?.join ?? path.join;
    const programFiles = env.ProgramFiles?.trim() || 'C:\\Program Files';
    const programFilesX86 = env['ProgramFiles(x86)']?.trim() || 'C:\\Program Files (x86)';
    const localAppData = env.LOCALAPPDATA?.trim();

    rawCandidates.push(
      winJoin(programFiles, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      winJoin(programFilesX86, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    );
    if (localAppData) {
      rawCandidates.push(winJoin(localAppData, 'Google', 'Chrome', 'Application', 'chrome.exe'));
    }
    rawCandidates.push(
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
      winJoin(programFiles, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      winJoin(programFilesX86, 'Microsoft', 'Edge', 'Application', 'msedge.exe')
    );
  } else if (platform === 'darwin') {
    rawCandidates.push(
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
      '/Applications/Chromium.app/Contents/MacOS/Chromium'
    );
  } else {
    // Linux and other POSIX platforms
    rawCandidates.push(
      '/usr/bin/google-chrome',
      '/usr/bin/google-chrome-stable',
      '/usr/bin/chromium',
      '/usr/bin/chromium-browser',
      '/snap/bin/chromium'
    );
  }

  const candidates = Array.from(new Set(rawCandidates.filter(Boolean)));

  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }

  throw new Error(
    `Chrome/Chromium executable not found across candidate paths for platform '${platform}': ${candidates.join(', ')}. ` +
      `Please set CHROME_BIN or PUPPETEER_EXECUTABLE_PATH environment variable.`
  );
}

export const CHROME_PATH = resolveChromePath();
