import { describe, it, expect, afterEach, vi } from 'vitest';
import {
  createApiClient,
  generateSecureIdempotencyKey,
} from '../services/api';
import * as deviceIdModule from '../services/deviceId';

describe('Workstream A, B, C & D — API Consistency, Idempotency, Device Identity & Schema Contracts', () => {
  const originalFetch = globalThis.fetch;
  const originalCrypto = globalThis.crypto;

  function setCrypto(value: any) {
    Object.defineProperty(globalThis, 'crypto', {
      value,
      writable: true,
      configurable: true,
    });
  }

  afterEach(() => {
    globalThis.fetch = originalFetch;
    setCrypto(originalCrypto);
    vi.restoreAllMocks();
  });

  // =========================================================================
  // WORKSTREAM A: SECURE IDEMPOTENCY KEY GENERATION
  // =========================================================================
  describe('Workstream A — Secure Idempotency Key Generation', () => {
    it('1. Generates secure key via crypto.randomUUID() when available', () => {
      const key = generateSecureIdempotencyKey();
      expect(key.startsWith('idem_')).toBe(true);
      expect(key.length).toBeGreaterThan(16);
      expect(/^idem_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(key)).toBe(true);
    });

    it('2. Generates secure key via crypto.getRandomValues() when randomUUID is unavailable', () => {
      setCrypto({
        getRandomValues: (array: Uint8Array) => {
          for (let i = 0; i < array.length; i++) {
            array[i] = (i * 17 + 42) & 0xff;
          }
          return array;
        },
        randomUUID: undefined,
      });

      const key = generateSecureIdempotencyKey();
      expect(key.startsWith('idem_')).toBe(true);
      expect(key.length).toBe(37); // 'idem_' (5) + 32 hex chars = 37
      expect(/^idem_[0-9a-f]{32}$/.test(key)).toBe(true);
    });

    it('3. Fails safely with explicit error when neither secure crypto API is available', () => {
      setCrypto(undefined);

      expect(() => generateSecureIdempotencyKey()).toThrow(
        /Cryptographically secure randomness is unavailable\. Cannot generate a secure idempotency key\./
      );
    });

    it('4. Rejects predictable fallbacks: never calls Math.random() or performance.now()', () => {
      const mathRandomSpy = vi.spyOn(Math, 'random');

      generateSecureIdempotencyKey();
      expect(mathRandomSpy).not.toHaveBeenCalled();

      // Even with partial crypto
      setCrypto({
        getRandomValues: (arr: Uint8Array) => arr.fill(1),
        randomUUID: undefined,
      });
      generateSecureIdempotencyKey();
      expect(mathRandomSpy).not.toHaveBeenCalled();
    });

    it('5. Submitting report without crypto and without caller key fails safely', async () => {
      setCrypto(undefined);
      const prodApi = createApiClient({
        dataMode: 'production',
        apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
      });

      await expect(
        prodApi.submitReport('loc-1', {
          reportedWaitMinutes: 10,
          queueLength: 5,
        })
      ).rejects.toThrow(
        /Cryptographically secure randomness is unavailable/
      );
    });

    it('6. Accepts and preserves valid caller-supplied idempotency key', async () => {
      let capturedHeader = '';
      let capturedBodyKey = '';

      globalThis.fetch = vi.fn().mockImplementation(async (_url, init) => {
        capturedHeader = init.headers['X-Idempotency-Key'];
        const body = JSON.parse(init.body);
        capturedBodyKey = body.idempotencyKey;
        return {
          ok: true,
          status: 201,
          json: async () => ({
            success: true,
            data: {
              report: {
                reportId: 'rep_1',
                reportedWaitMinutes: 5,
                queueLength: 2,
                timestamp: new Date().toISOString(),
              },
              updatedEstimate: {
                predictedWaitMinutes: 5,
                predictedQueueLength: 2,
                congestion: 'LOW',
                confidence: 0.8,
                freshness: 'LIVE',
              },
            },
          }),
        } as Response;
      });

      const prodApi = createApiClient({
        dataMode: 'production',
        apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
      });

      const customKey = 'idem_caller_supplied_stable_key_12345';
      await prodApi.submitReport('loc-1', {
        reportedWaitMinutes: 5,
        queueLength: 2,
        idempotencyKey: customKey,
      });

      expect(capturedHeader).toBe(customKey);
      expect(capturedBodyKey).toBe(customKey);
    });

    it('7. Rejects malformed caller-supplied idempotency key (< 8 chars or unsafe chars)', async () => {
      const prodApi = createApiClient({
        dataMode: 'production',
        apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
      });

      // Too short (< 8 chars)
      await expect(
        prodApi.submitReport('loc-1', {
          reportedWaitMinutes: 5,
          queueLength: 2,
          idempotencyKey: 'short',
        })
      ).rejects.toThrow(/Invalid idempotency key format/);

      // Unsafe characters
      await expect(
        prodApi.submitReport('loc-1', {
          reportedWaitMinutes: 5,
          queueLength: 2,
          idempotencyKey: 'key_with_spaces_and_quotes"<>',
        })
      ).rejects.toThrow(/Invalid idempotency key format/);
    });

    it('8. Retry reuse: preserves identical idempotency key across retry attempts of same submission', async () => {
      const keysUsed: string[] = [];

      globalThis.fetch = vi.fn().mockImplementation(async (_url, init) => {
        keysUsed.push(init.headers['X-Idempotency-Key']);
        return {
          ok: false,
          status: 500,
          json: async () => ({ error: 'Transient error' }),
        } as Response;
      });

      const prodApi = createApiClient({
        dataMode: 'production',
        apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
      });

      const retryKey = 'idem_logical_submission_retry_token_abc123';
      const submission = {
        reportedWaitMinutes: 8,
        queueLength: 4,
        idempotencyKey: retryKey,
      };

      // Attempt 1 fails
      await expect(prodApi.submitReport('loc-1', submission)).rejects.toThrow();

      // Attempt 2 (retry of same logical submission)
      await expect(prodApi.submitReport('loc-1', submission)).rejects.toThrow();

      expect(keysUsed.length).toBe(2);
      expect(keysUsed[0]).toBe(retryKey);
      expect(keysUsed[1]).toBe(retryKey); // Reused! No accidental duplicate submission
    });

    it('9. Repeated independent submissions without caller key generate independent keys', async () => {
      const keysUsed: string[] = [];

      globalThis.fetch = vi.fn().mockImplementation(async (_url, init) => {
        keysUsed.push(init.headers['X-Idempotency-Key']);
        return {
          ok: true,
          status: 201,
          json: async () => ({
            success: true,
            data: {
              report: {
                reportId: `rep_${Date.now()}`,
                reportedWaitMinutes: 5,
                queueLength: 2,
                timestamp: new Date().toISOString(),
              },
              updatedEstimate: {
                predictedWaitMinutes: 5,
                predictedQueueLength: 2,
                congestion: 'LOW',
                confidence: 0.8,
                freshness: 'LIVE',
              },
            },
          }),
        } as Response;
      });

      const prodApi = createApiClient({
        dataMode: 'production',
        apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
      });

      await prodApi.submitReport('loc-1', { reportedWaitMinutes: 5, queueLength: 2 });
      await prodApi.submitReport('loc-1', { reportedWaitMinutes: 10, queueLength: 4 });

      expect(keysUsed.length).toBe(2);
      expect(keysUsed[0]).not.toBe(keysUsed[1]);
      expect(keysUsed[0].startsWith('idem_')).toBe(true);
      expect(keysUsed[1].startsWith('idem_')).toBe(true);
    });
  });

  // =========================================================================
  // WORKSTREAM B: DEVICE IDENTITY BEHAVIOUR & BACKEND CONTRACT
  // =========================================================================
  describe('Workstream B — Device Identity Behaviour and Backend Contract', () => {
    const prodApi = createApiClient({
      dataMode: 'production',
      apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
    });

    it('1. Attaches X-Device-ID header when a valid device ID is present', async () => {
      vi.spyOn(deviceIdModule, 'getOrGenerateDeviceId').mockReturnValue('device-uuid-test-12345678');
      let capturedHeaders: Record<string, string> = {};

      globalThis.fetch = vi.fn().mockImplementation(async (_url, init) => {
        capturedHeaders = init.headers;
        return {
          ok: true,
          status: 201,
          json: async () => ({
            success: true,
            data: {
              report: {
                reportId: 'rep_1',
                reportedWaitMinutes: 5,
                queueLength: 2,
                timestamp: new Date().toISOString(),
              },
              updatedEstimate: {
                predictedWaitMinutes: 5,
                predictedQueueLength: 2,
                congestion: 'LOW',
                confidence: 0.8,
                freshness: 'LIVE',
              },
            },
          }),
        } as Response;
      });

      await prodApi.submitReport('loc-1', { reportedWaitMinutes: 5, queueLength: 2 });

      expect(capturedHeaders['X-Device-ID']).toBe('device-uuid-test-12345678');
    });

    it('2. Strictly omits X-Device-ID when device ID is null (no fabricated anon-client or fake ID)', async () => {
      vi.spyOn(deviceIdModule, 'getOrGenerateDeviceId').mockReturnValue(null);
      let capturedHeaders: Record<string, string> = {};

      globalThis.fetch = vi.fn().mockImplementation(async (_url, init) => {
        capturedHeaders = init.headers;
        return {
          ok: true,
          status: 201,
          json: async () => ({
            success: true,
            data: {
              report: {
                reportId: 'rep_1',
                reportedWaitMinutes: 5,
                queueLength: 2,
                timestamp: new Date().toISOString(),
              },
              updatedEstimate: {
                predictedWaitMinutes: 5,
                predictedQueueLength: 2,
                congestion: 'LOW',
                confidence: 0.8,
                freshness: 'LIVE',
              },
            },
          }),
        } as Response;
      });

      await prodApi.submitReport('loc-1', {
        reportedWaitMinutes: 5,
        queueLength: 2,
        idempotencyKey: 'idem_caller_key_for_missing_dev_id',
      });

      expect(capturedHeaders['X-Device-ID']).toBeUndefined();
      // Ensure NO fabricated fallback identity is present in any header
      expect(capturedHeaders['X-Device-ID']).not.toBe('anon-client');
      expect(capturedHeaders['X-Client-ID']).toBeUndefined();
    });

    it('3. Idempotency is independent of device identity: idempotency key is always attached', async () => {
      vi.spyOn(deviceIdModule, 'getOrGenerateDeviceId').mockReturnValue(null);
      let capturedHeaders: Record<string, string> = {};

      globalThis.fetch = vi.fn().mockImplementation(async (_url, init) => {
        capturedHeaders = init.headers;
        return {
          ok: true,
          status: 201,
          json: async () => ({
            success: true,
            data: {
              report: {
                reportId: 'rep_1',
                reportedWaitMinutes: 5,
                queueLength: 2,
                timestamp: new Date().toISOString(),
              },
              updatedEstimate: {
                predictedWaitMinutes: 5,
                predictedQueueLength: 2,
                congestion: 'LOW',
                confidence: 0.8,
                freshness: 'LIVE',
              },
            },
          }),
        } as Response;
      });

      await prodApi.submitReport('loc-1', { reportedWaitMinutes: 5, queueLength: 2 });

      expect(capturedHeaders['X-Device-ID']).toBeUndefined();
      expect(capturedHeaders['X-Idempotency-Key']).toBeTruthy();
      expect(capturedHeaders['X-Idempotency-Key'].startsWith('idem_')).toBe(true);
    });
  });

  // =========================================================================
  // WORKSTREAM C: FIELD-LEVEL VALIDATION & NEGATIVE TESTS
  // =========================================================================
  describe('Workstream C — Field-Level Validation and Negative Boundary Tests', () => {
    const prodApi = createApiClient({
      dataMode: 'production',
      apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
    });

    describe('GET /locations Field-Level Validation', () => {
      it('rejects location with empty string id', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: '   ', name: 'Mess', category: 'MESS' }],
          }),
        } as Response);

        await expect(prodApi.getLocations()).rejects.toThrow(/id must be a non-empty string/);
      });

      it('rejects location with missing or empty name', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'loc-1', name: '', category: 'MESS' }],
          }),
        } as Response);

        await expect(prodApi.getLocations()).rejects.toThrow(/name must be a non-empty string/);
      });

      it('rejects location with invalid category', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'loc-1', name: 'Bar', category: 'NIGHT_CLUB' }],
          }),
        } as Response);

        await expect(prodApi.getLocations()).rejects.toThrow(/category has invalid value/);
      });

      it('rejects location when nested estimate has boolean confidence', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              {
                id: 'loc-1',
                name: 'Mess',
                category: 'MESS',
                estimate: {
                  confidence: true, // boolean where number expected!
                  congestion: 'LOW',
                  freshness: 'LIVE',
                },
              },
            ],
          }),
        } as Response);

        await expect(prodApi.getLocations()).rejects.toThrow(/confidence must be a number between 0 and 1/);
      });

      it('rejects location when nested estimate confidence is out of [0, 1] range', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              {
                id: 'loc-1',
                name: 'Mess',
                category: 'MESS',
                estimate: {
                  confidence: 1.5, // > 1.0
                  congestion: 'LOW',
                  freshness: 'LIVE',
                },
              },
            ],
          }),
        } as Response);

        await expect(prodApi.getLocations()).rejects.toThrow(/confidence must be a number between 0 and 1/);
      });

      it('rejects location when nested estimate predictedWaitMinutes is negative', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              {
                id: 'loc-1',
                name: 'Mess',
                category: 'MESS',
                estimate: {
                  confidence: 0.8,
                  congestion: 'LOW',
                  freshness: 'LIVE',
                  predictedWaitMinutes: -5, // negative wait time!
                },
              },
            ],
          }),
        } as Response);

        await expect(prodApi.getLocations()).rejects.toThrow(/predictedWaitMinutes must be null or number between 0 and 120/);
      });

      it('accepts valid locations with null estimates or boundary values', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              {
                id: 'loc-1',
                name: 'Hostel 12 Mess',
                category: 'MESS',
                estimate: {
                  confidence: 1.0,
                  congestion: 'SURGE',
                  freshness: 'LIVE',
                  predictedWaitMinutes: 120, // boundary max
                  predictedQueueLength: 300, // boundary max
                  reportCount: 0,
                  recentReportCount: 0,
                },
              },
              {
                id: 'loc-2',
                name: 'Hostel 2 Mess',
                category: 'CANTEEN',
                estimate: {
                  confidence: 0.0, // boundary min
                  congestion: 'UNKNOWN',
                  freshness: 'NO RECENT DATA',
                  predictedWaitMinutes: null, // legitimate null
                  predictedQueueLength: null, // legitimate null
                },
              },
            ],
          }),
        } as Response);

        const res = await prodApi.getLocations();
        expect(res.data.length).toBe(2);
        expect(res.data[0].estimate?.predictedWaitMinutes).toBe(120);
        expect(res.data[1].estimate?.predictedWaitMinutes).toBeNull();
      });
    });

    describe('GET /locations/{id}/queue Field-Level Validation', () => {
      it('rejects queue response when location is invalid', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              location: { id: '', name: 'Mess' }, // empty id
              estimate: { confidence: 0.8, congestion: 'LOW', freshness: 'LIVE' },
              reports: [],
            },
          }),
        } as Response);

        await expect(prodApi.getLocationQueue('loc-1')).rejects.toThrow(/id must be a non-empty string/);
      });

      it('rejects queue response when estimate has invalid congestion enum', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              location: { id: 'loc-1', name: 'Mess', category: 'MESS' },
              estimate: { confidence: 0.8, congestion: 'CROWDED_LINE', freshness: 'LIVE' }, // invalid enum
              reports: [],
            },
          }),
        } as Response);

        await expect(prodApi.getLocationQueue('loc-1')).rejects.toThrow(/congestion has invalid value/);
      });

      it('rejects queue response when reports array contains negative reportedWaitMinutes', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              location: { id: 'loc-1', name: 'Mess', category: 'MESS' },
              estimate: { confidence: 0.8, congestion: 'LOW', freshness: 'LIVE' },
              reports: [
                {
                  reportId: 'rep-1',
                  reportedWaitMinutes: -2, // negative!
                  queueLength: 5,
                  timestamp: new Date().toISOString(),
                },
              ],
            },
          }),
        } as Response);

        await expect(prodApi.getLocationQueue('loc-1')).rejects.toThrow(/reportedWaitMinutes must be a number between 0 and 120/);
      });

      it('rejects queue response when report queueLength is fractional or boolean', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              location: { id: 'loc-1', name: 'Mess', category: 'MESS' },
              estimate: { confidence: 0.8, congestion: 'LOW', freshness: 'LIVE' },
              reports: [
                {
                  reportId: 'rep-1',
                  reportedWaitMinutes: 5,
                  queueLength: 4.5, // fractional people!
                  timestamp: new Date().toISOString(),
                },
              ],
            },
          }),
        } as Response);

        await expect(prodApi.getLocationQueue('loc-1')).rejects.toThrow(/queueLength must be an integer between 0 and 300/);
      });

      it('rejects queue response when report timestamp is not a valid date string', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              location: { id: 'loc-1', name: 'Mess', category: 'MESS' },
              estimate: { confidence: 0.8, congestion: 'LOW', freshness: 'LIVE' },
              reports: [
                {
                  reportId: 'rep-1',
                  reportedWaitMinutes: 5,
                  queueLength: 4,
                  timestamp: 'invalid-date-string-not-iso',
                },
              ],
            },
          }),
        } as Response);

        await expect(prodApi.getLocationQueue('loc-1')).rejects.toThrow(/timestamp must be a valid ISO date string/);
      });
    });

    describe('GET /recommendations Field-Level Validation', () => {
      it('rejects recommendations when isEligible is string instead of boolean', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              isEligible: 'true', // string where boolean required!
              reason: 'Good option',
              confidence: 0.8,
              state: 'recommended',
            },
          }),
        } as Response);

        await expect(prodApi.getRecommendations()).rejects.toThrow(
          /expected recommendation object with isEligible, reason, and confidence/
        );
      });

      it('rejects recommendations when state is unknown enum value', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              isEligible: false,
              reason: 'No options',
              confidence: 0.0,
              state: 'INVALID_RECOMMENDATION_STATE',
            },
          }),
        } as Response);

        await expect(prodApi.getRecommendations()).rejects.toThrow(/recommendations\.state has invalid value/);
      });

      it('rejects eligible recommendation missing recommendedLocationId', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              isEligible: true,
              reason: 'Fastest outlet',
              confidence: 0.85,
              state: 'recommended',
              recommendedLocationId: '', // empty!
              recommendedLocationName: 'Mess',
              predictedWaitMinutes: 5,
              congestion: 'LOW',
            },
          }),
        } as Response);

        await expect(prodApi.getRecommendations()).rejects.toThrow(/must have non-empty recommendedLocationId/);
      });

      it('accepts compliant ineligible recommendation with null location fields', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              isEligible: false,
              reason: 'All campus observations are stale',
              confidence: 0.0,
              state: 'stale_data',
              recommendedLocationId: null,
              recommendedLocationName: null,
              predictedWaitMinutes: null,
              candidateCount: 8,
              eligibleCount: 0,
            },
          }),
        } as Response);

        const res = await prodApi.getRecommendations();
        expect(res.data.isEligible).toBe(false);
        expect(res.data.state).toBe('stale_data');
        expect(res.data.recommendedLocationId).toBeNull();
      });
    });

    describe('GET /locations/{id}/historical Field-Level Validation', () => {
      it('rejects historical response when totalObservations is negative', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              locationId: 'loc-1',
              status: 'available',
              totalObservations: -10, // negative!
              isCapped: false,
              hourlyTrends: [],
            },
          }),
        } as Response);

        await expect(prodApi.getHistorical('loc-1')).rejects.toThrow(/totalObservations must be a non-negative integer/);
      });

      it('rejects historical response when trend hour is out of [0, 23]', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              locationId: 'loc-1',
              status: 'available',
              totalObservations: 20,
              isCapped: false,
              hourlyTrends: [
                { hour: 25, label: '25:00', averageWaitMinutes: 10, observationCount: 5 }, // 25 > 23!
              ],
            },
          }),
        } as Response);

        await expect(prodApi.getHistorical('loc-1')).rejects.toThrow(/hour must be an integer between 0 and 23/);
      });

      it('rejects historical response when trend averageWaitMinutes is negative', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              locationId: 'loc-1',
              status: 'available',
              totalObservations: 20,
              isCapped: false,
              hourlyTrends: [
                { hour: 12, label: '12:00', averageWaitMinutes: -3, observationCount: 5 },
              ],
            },
          }),
        } as Response);

        await expect(prodApi.getHistorical('loc-1')).rejects.toThrow(/averageWaitMinutes must be null or number between 0 and 120/);
      });

      it('accepts compliant historical response with boundary hours and null averages', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              locationId: 'loc-1',
              status: 'available',
              totalObservations: 42,
              isCapped: true,
              hourlyTrends: [
                { hour: 0, label: '00:00', averageWaitMinutes: null, observationCount: 0 },
                { hour: 23, label: '23:00', averageWaitMinutes: 15.5, observationCount: 8 },
              ],
              busiestHour: null,
              quietestHour: null,
            },
          }),
        } as Response);

        const res = await prodApi.getHistorical('loc-1');
        expect(res.data.locationId).toBe('loc-1');
        expect(res.data.isCapped).toBe(true);
        expect(res.data.hourlyTrends[0].averageWaitMinutes).toBeNull();
        expect(res.data.hourlyTrends[1].averageWaitMinutes).toBe(15.5);
      });
    });

    describe('GET /admin/reports Field-Level Validation', () => {
      it('rejects admin response when report in reports array is malformed', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({
            data: {
              reports: [
                {
                  reportId: 'rep-1',
                  reportedWaitMinutes: 10,
                  queueLength: -1, // negative!
                  timestamp: new Date().toISOString(),
                },
              ],
            },
          }),
        } as Response);

        await expect(prodApi.getAdminReports('valid-token')).rejects.toThrow(/queueLength must be an integer between 0 and 300/);
      });
    });
  });

  // =========================================================================
  // WORKSTREAM D: PRODUCTION FAIL-CLOSED BEHAVIOUR
  // =========================================================================
  describe('Workstream D — Production Fail-Closed Behaviour', () => {
    it('fails closed when API URL is not configured', async () => {
      const api = createApiClient({ dataMode: 'production', apiBaseUrl: '' });
      await expect(api.getLocations()).rejects.toThrow(/Production mode active: Live API URL/);
      await expect(api.getRecommendations()).rejects.toThrow(/Production mode active: Live API URL/);
      await expect(api.getLocationQueue('loc-1')).rejects.toThrow(/Production mode active: Live API URL/);
      await expect(api.getHistorical('loc-1')).rejects.toThrow(/Production mode active: Live API URL/);
      await expect(api.getAdminReports('tok')).rejects.toThrow(/Production mode active: Live API URL/);
    });

    it('fails closed on network failure (rejects immediately without mock fallback)', async () => {
      const api = createApiClient({
        dataMode: 'production',
        apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
      });

      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network dropped'));

      await expect(api.getLocations()).rejects.toThrow(/Network dropped/);
      await expect(api.getRecommendations()).rejects.toThrow(/Network dropped/);
      await expect(api.getLocationQueue('loc-1')).rejects.toThrow(/Network dropped/);
    });

    it('fails closed on HTTP 4xx and 5xx responses without falling back to demo fixtures', async () => {
      const api = createApiClient({
        dataMode: 'production',
        apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
      });

      // 404
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: 'Outlet not found' }),
      } as Response);

      await expect(api.getLocations()).rejects.toThrow(/API returned status 404/);

      // 500
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ error: 'Internal Error' }),
      } as Response);

      await expect(api.getLocationQueue('loc-1')).rejects.toThrow(/API returned status 500/);
    });

    it('fails closed on request timeout', async () => {
      const api = createApiClient({
        dataMode: 'production',
        apiBaseUrl: 'https://api.queuesense.iitb.ac.in',
      });

      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Request timed out'));

      await expect(api.getRecommendations()).rejects.toThrow(/Request timed out/);
    });
  });
});
