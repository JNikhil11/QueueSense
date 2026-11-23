import { describe, it, expect, afterEach, vi } from 'vitest';
import { api, createApiClient, DATA_MODE } from '../services/api';

describe('Production Data Isolation & Fail-Closed Guardrails (Category B1 / Issue 01)', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  describe('Unconfigured Production Mode (VITE_API_URL missing)', () => {
    const unconfiguredProdApi = createApiClient({
      dataMode: 'production',
      apiBaseUrl: '',
    });

    it('fails closed in getLocations and never returns mock locations', async () => {
      await expect(unconfiguredProdApi.getLocations()).rejects.toThrow(
        /Production mode active: Live API URL \(VITE_API_URL\) is not configured/
      );
    });

    it('fails closed in getLocationQueue and never returns mock queue reports', async () => {
      await expect(unconfiguredProdApi.getLocationQueue('iitb-mess-h12-14')).rejects.toThrow(
        /Production mode active: Live API URL is not configured/
      );
    });

    it('fails closed in submitReport and refuses to persist observations locally', async () => {
      await expect(
        unconfiguredProdApi.submitReport('iitb-mess-h12-14', {
          reportedWaitMinutes: 10,
          queueLength: 15,
        })
      ).rejects.toThrow(
        /Production mode active: Cannot submit observation without configured live API endpoint/
      );
    });

    it('fails closed in getRecommendations and never synthesizes a demo recommendation', async () => {
      await expect(unconfiguredProdApi.getRecommendations()).rejects.toThrow(
        /Production mode active: Live API URL is not configured/
      );
    });

    it('fails closed in getHistorical and never returns simulated 24-hour curves', async () => {
      await expect(unconfiguredProdApi.getHistorical('iitb-mess-h12-14')).rejects.toThrow(
        /Production mode active: Live API URL is not configured/
      );
    });

    it('fails closed in getAdminReports and refuses to disclose local fixtures', async () => {
      await expect(unconfiguredProdApi.getAdminReports('some_token')).rejects.toThrow(
        /Production mode active: Live API URL is not configured/
      );
    });
  });

  describe('Configured Production Mode with Network / Server Outages', () => {
    const liveEndpoint = 'https://api.queuesense.iitb.ac.in';
    const prodApi = createApiClient({
      dataMode: 'production',
      apiBaseUrl: liveEndpoint,
    });

    it('fails closed when network fetch throws in getLocations', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Connection reset by peer'));
      await expect(prodApi.getLocations()).rejects.toThrow(
        /Live data temporarily unavailable: Connection reset by peer/
      );
    });

    it('fails closed when API Gateway returns 500 in getLocations', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ error: 'Internal Server Error' }),
      } as Response);
      await expect(prodApi.getLocations()).rejects.toThrow(/API returned status 500/);
    });

    it('fails closed when network fetch throws in submitReport', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('ETIMEDOUT'));
      await expect(
        prodApi.submitReport('iitb-mess-h12-14', {
          reportedWaitMinutes: 12,
          queueLength: 20,
        })
      ).rejects.toThrow(/ETIMEDOUT/);
    });

    it('fails closed when network fetch throws in getRecommendations', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('DNS resolution failed'));
      await expect(prodApi.getRecommendations()).rejects.toThrow(
        /Live recommendations temporarily unavailable: DNS resolution failed/
      );
    });

    it('fails closed when network fetch throws in getHistorical', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('HTTP 502 Bad Gateway'));
      await expect(prodApi.getHistorical('iitb-mess-h12-14')).rejects.toThrow(
        /Historical queue patterns temporarily unavailable/
      );
    });

    it('rejects unauthenticated getAdminReports calls immediately', async () => {
      await expect(prodApi.getAdminReports('')).rejects.toThrow('UNAUTHORIZED');
      await expect(prodApi.getAdminReports('   ')).rejects.toThrow('UNAUTHORIZED');
    });

    it('rejects 401 unauthorized responses from admin endpoint', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ error: 'Unauthorized' }),
      } as Response);
      await expect(prodApi.getAdminReports('expired_token')).rejects.toThrow('UNAUTHORIZED');
    });
  });

  describe('Explicit Demo Mode Operation & Provenance', () => {
    const demoApi = createApiClient({
      dataMode: 'demo',
      apiBaseUrl: '',
    });

    it('returns isLive=false and catalog fixtures in demo getLocations', async () => {
      const result = await demoApi.getLocations();
      expect(result.isLive).toBe(false);
      expect(result.data.length).toBeGreaterThanOrEqual(10);
      expect(result.data[0].id).toMatch(/^iitb-/);
    });

    it('returns isLive=false and cold-start protected recommendation in demo mode', async () => {
      const result = await demoApi.getRecommendations();
      expect(result.isLive).toBe(false);
      expect(result.data).toBeDefined();
      expect(result.data.candidateCount).toBeGreaterThan(0);
    });

    it('returns isLive=false and Asia/Kolkata timezone in demo getHistorical', async () => {
      const result = await demoApi.getHistorical('iitb-mess-h12-14');
      expect(result.isLive).toBe(false);
      expect(result.data.timezone).toBe('Asia/Kolkata');
      expect(result.data.hourlyTrends.length).toBe(24);
    });

    it('returns isLive=false and local report in demo submitReport', async () => {
      const result = await demoApi.submitReport('iitb-mess-h12-14', {
        reportedWaitMinutes: 5,
        queueLength: 6,
        note: 'Vitest isolated demo report',
      });
      expect(result.isLive).toBe(false);
      expect(result.report.reportedWaitMinutes).toBe(5);
      expect(result.report.reportId).toMatch(/^rep_local_/);
    });
  });

  describe('Default API Export Configuration', () => {
    it('exposes a valid data mode that matches the environment', () => {
      expect(['production', 'demo']).toContain(api.getDataMode());
      expect(['production', 'demo']).toContain(DATA_MODE);
    });
  });
});
