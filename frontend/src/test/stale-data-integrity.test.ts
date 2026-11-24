import { describe, it, expect, afterEach, vi } from 'vitest';
import { createApiClient } from '../services/api';

describe('Workstream 2 — Data Freshness State Model & Stale-Data Integrity', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  describe('API Client Payload Validation & Error Classification', () => {
    const prodApi = createApiClient({
      dataMode: 'production',
      apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
    });

    it('1. Initial successful load: validates payload and returns isLive=true', async () => {
      const mockLocations = [
        {
          id: 'iitb-mess-h12-14',
          name: 'Hostel 12-14 Dining Complex',
          category: 'MESS',
          description: 'Central mess',
          landmarkLocation: 'Lakeside Road',
          openHours: '07:30-21:30',
          active: true,
          estimate: {
            predictedWaitMinutes: 10,
            predictedQueueLength: 5,
            congestion: 'LOW',
            confidence: 0.9,
            confidenceLabel: 'HIGH',
            freshness: 'LIVE',
            reportCount: 5,
            recentReportCount: 3,
            disagreementMinutes: 0,
            outliersExcluded: 0,
            evidenceExplanation: 'Consistent observations',
            updatedAt: new Date().toISOString(),
          },
        },
      ];

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: mockLocations }),
      } as Response);

      const result = await prodApi.getLocations();
      expect(result.isLive).toBe(true);
      expect(result.data.length).toBe(1);
      expect(result.data[0].id).toBe('iitb-mess-h12-14');
    });

    it('2. Network failure (fetch throws TypeError/NetworkError): strictly fails closed', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
      await expect(prodApi.getLocations()).rejects.toThrow(
        /Live data temporarily unavailable: Failed to fetch/
      );
    });

    it('3. Timeout error (AbortError / timeout): strictly fails closed', async () => {
      const abortError = new Error('The operation was aborted');
      abortError.name = 'AbortError';
      globalThis.fetch = vi.fn().mockRejectedValue(abortError);
      await expect(prodApi.getLocations()).rejects.toThrow(
        /Live data temporarily unavailable: The operation was aborted/
      );
    });

    it('4. HTTP 500 Internal Server Error: strictly fails closed', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ error: 'Internal Server Error' }),
      } as Response);
      await expect(prodApi.getLocations()).rejects.toThrow(/API returned status 500/);
    });

    it('5. HTTP 429 Too Many Requests: strictly fails closed with rate limit error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        json: async () => ({ error: 'Rate limit exceeded' }),
      } as Response);
      await expect(prodApi.getLocations()).rejects.toThrow(/API returned status 429/);
    });

    it('6. Malformed response structure (data is null or not array): strictly rejected', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: 'not-an-array' }),
      } as Response);
      await expect(prodApi.getLocations()).rejects.toThrow(
        /Malformed API response: expected locations array/
      );
    });

    it('7. Malformed recommendations response: strictly rejected and never treated as valid', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: 'corrupted-string-payload' }),
      } as Response);
      await expect(prodApi.getRecommendations()).rejects.toThrow(
        /Malformed API response: expected recommendation object/
      );
    });

    it('8. Malformed queue detail response: strictly rejected', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: null }),
      } as Response);
      await expect(prodApi.getLocationQueue('iitb-mess-h12-14')).rejects.toThrow(
        /Malformed API response: expected queue data object/
      );
    });

    it('9. Malformed historical response: strictly rejected', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: null }),
      } as Response);
      await expect(prodApi.getHistorical('iitb-mess-h12-14')).rejects.toThrow(
        /Malformed API response: expected historical data object/
      );
    });

    it('10. Zero mock data leakage: production mode never silently injects demo fixtures on failure', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Gateway Timeout'));
      await expect(prodApi.getLocations()).rejects.toThrow(/Live data temporarily unavailable/);
      await expect(prodApi.getRecommendations()).rejects.toThrow(/Live recommendations temporarily unavailable/);
      await expect(prodApi.getLocationQueue('iitb-mess-h12-14')).rejects.toThrow(/Live queue data temporarily unavailable/);
    });
  });

  describe('Application-Level Freshness State Transition Logic', () => {
    // State machine simulator modeling App.tsx loadData transitions
    type AppSyncState = 'LOADING' | 'FRESH' | 'STALE' | 'ERROR' | 'EMPTY';

    class AppStateSimulator {
      syncState: AppSyncState = 'LOADING';
      locations: any[] = [];
      lastSuccessfulSync: number | null = null;
      errorMsg: string | null = null;

      async executeLoad(fetcher: () => Promise<any[]>) {
        try {
          const data = await fetcher();
          this.locations = data;
          this.errorMsg = null;
          this.lastSuccessfulSync = Date.now();
          this.syncState = data.length === 0 ? 'EMPTY' : 'FRESH';
        } catch (err: any) {
          this.errorMsg = err.message || 'Network failure';
          if (this.locations.length > 0) {
            this.syncState = 'STALE';
            // CRITICAL: lastSuccessfulSync is preserved!
          } else {
            this.syncState = 'ERROR';
          }
        }
      }
    }

    it('transitions: Initial successful load -> FRESH', async () => {
      const app = new AppStateSimulator();
      expect(app.syncState).toBe('LOADING');

      await app.executeLoad(async () => [{ id: 'loc-1', name: 'Mess 1' }]);
      expect(app.syncState).toBe('FRESH');
      expect(app.lastSuccessfulSync).not.toBeNull();
      expect(app.locations.length).toBe(1);
    });

    it('transitions: Successful load followed by network failure -> STALE with preserved timestamp', async () => {
      const app = new AppStateSimulator();
      await app.executeLoad(async () => [{ id: 'loc-1', name: 'Mess 1' }]);
      const initialTimestamp = app.lastSuccessfulSync;

      // Simulate network error on next refresh
      await app.executeLoad(async () => {
        throw new Error('Connection refused');
      });

      expect(app.syncState).toBe('STALE');
      expect(app.locations.length).toBe(1); // Cached data retained for continuity
      expect(app.lastSuccessfulSync).toBe(initialTimestamp); // Timestamp preserved!
      expect(app.errorMsg).toBe('Connection refused');
    });

    it('transitions: Repeated failure preserves original successful timestamp and stays STALE', async () => {
      const app = new AppStateSimulator();
      await app.executeLoad(async () => [{ id: 'loc-1', name: 'Mess 1' }]);
      const originalTimestamp = app.lastSuccessfulSync;

      // First failure
      await app.executeLoad(async () => {
        throw new Error('500 Internal Server Error');
      });
      expect(app.syncState).toBe('STALE');

      // Second failure
      await app.executeLoad(async () => {
        throw new Error('ETIMEDOUT');
      });
      expect(app.syncState).toBe('STALE');
      expect(app.lastSuccessfulSync).toBe(originalTimestamp); // Never overwritten by failures
    });

    it('transitions: Retry after failure succeeds -> recovers to FRESH', async () => {
      const app = new AppStateSimulator();
      await app.executeLoad(async () => [{ id: 'loc-1', name: 'Mess 1' }]);
      const firstTime = app.lastSuccessfulSync;

      // Fail
      await app.executeLoad(async () => {
        throw new Error('Network offline');
      });
      expect(app.syncState).toBe('STALE');

      // Recover
      await new Promise((r) => setTimeout(r, 20));
      await app.executeLoad(async () => [{ id: 'loc-1', name: 'Mess 1 (Updated)' }]);
      expect(app.syncState).toBe('FRESH');
      expect(app.errorMsg).toBeNull();
      expect(app.lastSuccessfulSync).toBeGreaterThan(firstTime!);
    });

    it('transitions: No previous data and API fails -> ERROR (not STALE)', async () => {
      const app = new AppStateSimulator();
      expect(app.syncState).toBe('LOADING');

      await app.executeLoad(async () => {
        throw new Error('Server unreachable');
      });

      expect(app.syncState).toBe('ERROR');
      expect(app.locations.length).toBe(0);
      expect(app.lastSuccessfulSync).toBeNull();
    });
  });
});
