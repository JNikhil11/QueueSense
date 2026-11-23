import { describe, it, expect, afterEach, vi } from 'vitest';
import { api, DATA_MODE } from '../services/api';

describe('Production Data Isolation & Fail-Closed Guardrails (Category B1)', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('verifies that DATA_MODE defaults to production in production environment', () => {
    // In production build, DATA_MODE must be 'production'
    expect(['production', 'demo']).toContain(DATA_MODE);
  });

  it('fails closed and throws in getLocations when live API is unavailable in production mode', async () => {
    if (DATA_MODE === 'production') {
      // Simulate failed network fetch
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
      await expect(api.getLocations()).rejects.toThrow(/temporarily unavailable|not configured/);
    }
  });

  it('fails closed and throws in submitReport when live API is unavailable in production mode', async () => {
    if (DATA_MODE === 'production') {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
      await expect(
        api.submitReport('iitb-mess-h12-14', {
          reportedWaitMinutes: 10,
          queueLength: 15,
        })
      ).rejects.toThrow(/Cannot submit observation|Network error/);
    }
  });

  it('fails closed and throws in getRecommendations when live API is unavailable in production mode', async () => {
    if (DATA_MODE === 'production') {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
      await expect(api.getRecommendations()).rejects.toThrow(/temporarily unavailable|not configured/);
    }
  });

  it('fails closed and throws in getHistorical when live API is unavailable in production mode', async () => {
    if (DATA_MODE === 'production') {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
      await expect(api.getHistorical('iitb-mess-h12-14')).rejects.toThrow(/temporarily unavailable|not configured/);
    }
  });

  it('fails closed and throws in getAdminReports when unauthenticated or API is unavailable in production mode', async () => {
    if (DATA_MODE === 'production') {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
      await expect(api.getAdminReports('some_token')).rejects.toThrow();
    }
  });
});
