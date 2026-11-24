import { describe, it, expect, afterEach, vi } from 'vitest';
import { createApiClient } from '../services/api';

describe('Workstream C — API Consistency, Schema Contracts & Fail-Closed Validation', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  describe('Production Fail-Closed Integrity & Configuration Safety', () => {
    it('1. Production mode with unconfigured live API URL fails closed and never returns mock fixtures', async () => {
      const unconfiguredProdApi = createApiClient({
        dataMode: 'production',
        apiBaseUrl: '',
      });

      await expect(unconfiguredProdApi.getLocations()).rejects.toThrow(
        /Production mode active: Live API URL/
      );
      await expect(unconfiguredProdApi.getRecommendations()).rejects.toThrow(
        /Production mode active: Live API URL/
      );
      await expect(unconfiguredProdApi.getLocationQueue('iitb-mess-h12-14')).rejects.toThrow(
        /Production mode active: Live API URL/
      );
      await expect(unconfiguredProdApi.getHistorical('iitb-mess-h12-14')).rejects.toThrow(
        /Production mode active: Live API URL/
      );
      await expect(unconfiguredProdApi.getAdminReports('valid-token')).rejects.toThrow(
        /Production mode active: Live API URL/
      );
    });

    it('2. Supports relative API base URLs (e.g. /api) as valid live API configuration', () => {
      const relativeApi = createApiClient({
        dataMode: 'production',
        apiBaseUrl: '/api',
      });
      expect(relativeApi.isLiveApiConfigured()).toBe(true);
    });
  });

  describe('Endpoint Contract 1: GET /locations', () => {
    const prodApi = createApiClient({
      dataMode: 'production',
      apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
    });

    it('validates required fields: id, name, category, and rejects corrupted entries', async () => {
      // Missing 'name' in second item
      const invalidPayload = [
        { id: 'loc-1', name: 'Valid Outlet', category: 'MESS', active: true },
        { id: 'loc-2', category: 'CAFE', active: true }, // missing name!
      ];

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ success: true, data: invalidPayload }),
      } as Response);

      await expect(prodApi.getLocations()).rejects.toThrow(
        /Malformed API response: invalid location entry in locations array/
      );
    });

    it('rejects payload when data is not an array', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ success: true, data: { notAnArray: true } }),
      } as Response);

      await expect(prodApi.getLocations()).rejects.toThrow(
        /Malformed API response: expected locations array/
      );
    });
  });

  describe('Endpoint Contract 2: GET /recommendations', () => {
    const prodApi = createApiClient({
      dataMode: 'production',
      apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
    });

    it('validates required fields: isEligible (boolean), reason (string), confidence (number)', async () => {
      // isEligible missing
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          data: {
            recommendedLocationId: 'loc-1',
            reason: 'Fastest line',
            confidence: 0.8,
            // isEligible is missing!
          },
        }),
      } as Response);

      await expect(prodApi.getRecommendations()).rejects.toThrow(
        /Malformed API response: expected recommendation object with isEligible, reason, and confidence/
      );
    });

    it('accepts compliant recommendation contract', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          data: {
            recommendedLocationId: 'loc-1',
            recommendedLocationName: 'Hostel Mess',
            predictedWaitMinutes: 5,
            congestion: 'LOW',
            confidence: 0.85,
            confidenceLabel: 'HIGH',
            reason: 'Fastest line with high confidence',
            isEligible: true,
            state: 'recommended',
          },
        }),
      } as Response);

      const res = await prodApi.getRecommendations();
      expect(res.data.isEligible).toBe(true);
      expect(res.data.recommendedLocationId).toBe('loc-1');
      expect(res.isLive).toBe(true);
    });
  });

  describe('Endpoint Contract 3: GET /locations/{id}/queue', () => {
    const prodApi = createApiClient({
      dataMode: 'production',
      apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
    });

    it('validates presence of location, estimate, and reports array', async () => {
      // reports is missing
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          data: {
            location: { id: 'loc-1', name: 'Mess' },
            estimate: { predictedWaitMinutes: 5 },
            // reports missing!
          },
        }),
      } as Response);

      await expect(prodApi.getLocationQueue('loc-1')).rejects.toThrow(
        /Malformed API response: expected queue data object with location, estimate, and reports/
      );
    });
  });

  describe('Endpoint Contract 4: GET /locations/{id}/historical', () => {
    const prodApi = createApiClient({
      dataMode: 'production',
      apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
    });

    it('rejects malformed historical responses without trends', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          data: {
            invalidField: 123,
          },
        }),
      } as Response);

      await expect(prodApi.getHistorical('loc-1')).rejects.toThrow(
        /Malformed API response: expected historical data object with hourly trends/
      );
    });
  });

  describe('Endpoint Contract 5: GET /admin/reports', () => {
    const prodApi = createApiClient({
      dataMode: 'production',
      apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
    });

    it('requires bearer token and throws UNAUTHORIZED on missing or 401 response', async () => {
      await expect(prodApi.getAdminReports('')).rejects.toThrow('UNAUTHORIZED');

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ error: 'Unauthorized' }),
      } as Response);

      await expect(prodApi.getAdminReports('invalid-token')).rejects.toThrow('UNAUTHORIZED');
    });

    it('rejects malformed admin payload where reports is not an array', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          data: { reports: 'not-an-array' },
        }),
      } as Response);

      await expect(prodApi.getAdminReports('valid-token')).rejects.toThrow(
        /Malformed API response: expected admin reports array/
      );
    });
  });

  describe('Endpoint Contract 6: POST /locations/{id}/reports', () => {
    const prodApi = createApiClient({
      dataMode: 'production',
      apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
    });

    it('submits report successfully even if device ID is absent', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async (_url, init) => {
        const headers = init.headers;
        expect(headers['Content-Type']).toBe('application/json');
        expect(headers['X-Idempotency-Key']).toBeDefined();

        return {
          ok: true,
          status: 201,
          json: async () => ({
            success: true,
            data: {
              report: {
                reportId: 'rep_123',
                locationId: 'loc-1',
                reportedWaitMinutes: 5,
                queueLength: 10,
                timestamp: new Date().toISOString(),
              },
              updatedEstimate: {
                predictedWaitMinutes: 5,
                predictedQueueLength: 10,
                confidence: 0.7,
              },
            },
          }),
        } as Response;
      });

      const res = await prodApi.submitReport('loc-1', {
        reportedWaitMinutes: 5,
        queueLength: 10,
      });

      expect(res.report.reportId).toBe('rep_123');
      expect(res.updatedEstimate.predictedWaitMinutes).toBe(5);
      expect(res.isLive).toBe(true);
    });

    it('generates a unique client-side idempotency key for each submission', async () => {
      const capturedKeys: string[] = [];

      globalThis.fetch = vi.fn().mockImplementation(async (_url, init) => {
        capturedKeys.push(init.headers['X-Idempotency-Key']);
        return {
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            data: {
              report: { reportId: 'rep_1' },
              updatedEstimate: { predictedWaitMinutes: 5 },
            },
          }),
        } as Response;
      });

      await prodApi.submitReport('loc-1', { reportedWaitMinutes: 5, queueLength: 10 });
      await prodApi.submitReport('loc-1', { reportedWaitMinutes: 10, queueLength: 20 });

      expect(capturedKeys.length).toBe(2);
      expect(capturedKeys[0]).not.toBe(capturedKeys[1]);
      expect(capturedKeys[0].startsWith('idem_')).toBe(true);
    });
  });
});
