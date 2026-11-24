import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  getOrGenerateDeviceId,
  rotateDeviceId,
  resetDeviceId,
  generateRandomDeviceId,
  DEVICE_ID_STORAGE_KEY,
} from '../services/deviceId';
import { createApiClient } from '../services/api';

class LocalStorageMock {
  private store: Record<string, string> = {};

  clear() {
    this.store = {};
  }

  getItem(key: string): string | null {
    return Object.prototype.hasOwnProperty.call(this.store, key) ? this.store[key] : null;
  }

  setItem(key: string, value: string): void {
    this.store[key] = String(value);
  }

  removeItem(key: string): void {
    delete this.store[key];
  }
}

describe('P1.10: Client Device Identity & Fairness Integration', () => {
  const originalFetch = globalThis.fetch;
  const originalLocalStorage = (globalThis as any).localStorage;
  const originalWindow = (globalThis as any).window;
  let mockStorage: LocalStorageMock;

  beforeEach(() => {
    mockStorage = new LocalStorageMock();
    (globalThis as any).localStorage = mockStorage;
    (globalThis as any).window = globalThis;
    resetDeviceId();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    (globalThis as any).localStorage = originalLocalStorage;
    (globalThis as any).window = originalWindow;
    resetDeviceId();
    vi.restoreAllMocks();
  });

  it('generates a stable, pseudonymous client device identifier matching ^[a-zA-Z0-9_-]{16,64}$', () => {
    const randomId = generateRandomDeviceId();
    expect(/^[a-zA-Z0-9_-]{16,64}$/.test(randomId)).toBe(true);

    const id = getOrGenerateDeviceId();
    expect(typeof id).toBe('string');
    expect(id.length).toBeGreaterThanOrEqual(16);
    expect(id.length).toBeLessThanOrEqual(64);
    expect(/^[a-zA-Z0-9_-]{16,64}$/.test(id)).toBe(true);
  });

  it('contains zero personal information or identifiable attributes', () => {
    const id = getOrGenerateDeviceId();
    // Verify it is a random UUID/hex pattern and does not contain PII tokens
    expect(id).not.toMatch(/@/); // No emails
    expect(id).not.toMatch(/iitb/i); // No campus/roll markers
    expect(id).not.toMatch(/student/i);
    expect(id).not.toMatch(/192\.|10\.|172\./); // No embedded private IPs
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  });

  it('remains stable across multiple calls within normal browser sessions', () => {
    const id1 = getOrGenerateDeviceId();
    const id2 = getOrGenerateDeviceId();
    const id3 = getOrGenerateDeviceId();
    expect(id1).toBe(id2);
    expect(id2).toBe(id3);
    expect(localStorage.getItem(DEVICE_ID_STORAGE_KEY)).toBe(id1);
  });

  it('rotateDeviceId generates a fresh, distinct identifier and updates persistence', () => {
    const initialId = getOrGenerateDeviceId();
    const rotatedId = rotateDeviceId();

    expect(rotatedId).not.toBe(initialId);
    expect(/^[a-zA-Z0-9_-]{16,64}$/.test(rotatedId)).toBe(true);
    expect(localStorage.getItem(DEVICE_ID_STORAGE_KEY)).toBe(rotatedId);
    expect(getOrGenerateDeviceId()).toBe(rotatedId);
  });

  it('resetDeviceId purges the identifier from storage and memory', () => {
    getOrGenerateDeviceId();
    expect(localStorage.getItem(DEVICE_ID_STORAGE_KEY)).toBeTruthy();

    resetDeviceId();
    expect(localStorage.getItem(DEVICE_ID_STORAGE_KEY)).toBeNull();
  });

  it('handles unavailable or throwing localStorage gracefully with in-memory fallback', () => {
    // Simulate private browsing mode or third-party storage restrictions
    vi.spyOn(mockStorage, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError: The operation is insecure.');
    });
    vi.spyOn(mockStorage, 'setItem').mockImplementation(() => {
      throw new Error('SecurityError: The operation is insecure.');
    });

    // Should NOT throw, but generate and maintain an in-memory session identifier
    const id1 = getOrGenerateDeviceId();
    expect(typeof id1).toBe('string');
    expect(/^[a-zA-Z0-9_-]{16,64}$/.test(id1)).toBe(true);

    const id2 = getOrGenerateDeviceId();
    expect(id2).toBe(id1); // In-memory persistence within session
  });

  it('sends X-Device-ID header when submitting reports in live API mode', async () => {
    const mockDeviceId = 'test-client-device-uuid-1234-5678-abcd';
    localStorage.setItem(DEVICE_ID_STORAGE_KEY, mockDeviceId);

    let capturedHeaders: Record<string, string> = {};
    let capturedBody: any = null;

    globalThis.fetch = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
      capturedHeaders = (init?.headers as Record<string, string>) || {};
      capturedBody = JSON.parse((init?.body as string) || '{}');

      return new Response(
        JSON.stringify({
          data: {
            report: {
              id: 'rep_123',
              locationId: 'iitb-mess-h12-14',
              reportedWaitMinutes: 10,
              queueLength: 5,
              timestamp: new Date().toISOString(),
            },
            updatedEstimate: {
              predictedWaitMinutes: 10,
              predictedQueueLength: 5,
              congestion: 'MODERATE',
              confidence: 0.8,
              confidenceLabel: 'HIGH',
              freshness: 'LIVE',
            },
          },
        }),
        { status: 201, headers: { 'Content-Type': 'application/json' } }
      );
    });

    const client = createApiClient({
      apiBaseUrl: 'https://api.queuesense.internal',
      dataMode: 'production',
    });

    const result = await client.submitReport('iitb-mess-h12-14', {
      reportedWaitMinutes: 10,
      queueLength: 5,
      note: 'Normal lunch rush',
    });

    expect(result.isLive).toBe(true);
    expect(capturedHeaders['X-Device-ID']).toBe(mockDeviceId);
    expect(capturedHeaders['Content-Type']).toBe('application/json');
    expect(capturedHeaders['X-Idempotency-Key']).toBeTruthy();
    expect(capturedBody.reportedWaitMinutes).toBe(10);
  });
});
