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

function setCrypto(value: any) {
  Object.defineProperty(globalThis, 'crypto', {
    value,
    writable: true,
    configurable: true,
  });
}

describe('P1.10: Client Device Identity & Fairness Integration', () => {
  const originalFetch = globalThis.fetch;
  const originalLocalStorage = (globalThis as any).localStorage;
  const originalWindow = (globalThis as any).window;
  const originalCrypto = globalThis.crypto;
  let mockStorage: LocalStorageMock;

  beforeEach(() => {
    mockStorage = new LocalStorageMock();
    (globalThis as any).localStorage = mockStorage;
    (globalThis as any).window = globalThis;
    setCrypto(originalCrypto);
    resetDeviceId();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    (globalThis as any).localStorage = originalLocalStorage;
    (globalThis as any).window = originalWindow;
    setCrypto(originalCrypto);
    resetDeviceId();
    vi.restoreAllMocks();
  });

  it('1. crypto.randomUUID() generates a valid ID matching ^[a-zA-Z0-9_-]{16,64}$', () => {
    const id = generateRandomDeviceId();
    expect(id).not.toBeNull();
    expect(typeof id).toBe('string');
    expect(/^[a-zA-Z0-9_-]{16,64}$/.test(id!)).toBe(true);
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  });

  it('2. crypto.getRandomValues() generates a valid ID when randomUUID is unavailable', () => {
    // Mock crypto without randomUUID, but with working getRandomValues
    setCrypto({
      getRandomValues: (array: Uint8Array) => {
        for (let i = 0; i < array.length; i++) {
          array[i] = Math.floor(Math.sin(i + 1) * 10000) & 0xff;
        }
        return array;
      },
      randomUUID: undefined,
    });

    const id = generateRandomDeviceId();
    expect(id).not.toBeNull();
    expect(typeof id).toBe('string');
    expect(/^[a-zA-Z0-9_-]{16,64}$/.test(id!)).toBe(true);
  });

  it('3. Both crypto APIs unavailable: no new device ID is generated (returns null)', () => {
    // Remove all crypto randomness APIs
    setCrypto(undefined);

    const generated = generateRandomDeviceId();
    expect(generated).toBeNull();

    const retrieved = getOrGenerateDeviceId();
    expect(retrieved).toBeNull();

    const rotated = rotateDeviceId();
    expect(rotated).toBeNull();
  });

  it('4. Existing valid stored ID remains usable when crypto APIs are unavailable', () => {
    const existingStoredId = 'pre-existing-valid-device-uuid-1234567890';
    mockStorage.setItem(DEVICE_ID_STORAGE_KEY, existingStoredId);

    // Disable crypto
    setCrypto(undefined);

    // Must return the existing stored ID safely without attempting insecure generation
    const retrieved = getOrGenerateDeviceId();
    expect(retrieved).toBe(existingStoredId);
  });

  it('5. Report submission succeeds without X-Device-ID when secure randomness is unavailable', async () => {
    // Disable crypto APIs and clear storage
    setCrypto(undefined);
    mockStorage.clear();

    let capturedHeaders: Record<string, string> = {};
    let capturedBody: any = null;

    globalThis.fetch = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
      capturedHeaders = (init?.headers as Record<string, string>) || {};
      capturedBody = JSON.parse((init?.body as string) || '{}');

      return new Response(
        JSON.stringify({
          data: {
            report: {
              id: 'rep_fallback_123',
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
      note: 'Fallback test without device ID',
      idempotencyKey: 'idem_caller_supplied_fallback_key',
    });

    expect(result.isLive).toBe(true);
    // X-Device-ID header must NOT be attached (no fabricated anon-client or fake ID)
    expect(capturedHeaders['X-Device-ID']).toBeUndefined();
    expect(capturedHeaders['Content-Type']).toBe('application/json');
    expect(capturedHeaders['X-Idempotency-Key']).toBe('idem_caller_supplied_fallback_key');
    expect(capturedBody.reportedWaitMinutes).toBe(10);
  });

  it('6. No code path in deviceId uses Math.random() for security-sensitive identity generation', () => {
    const mathRandomSpy = vi.spyOn(Math, 'random');

    // Run all identity operations
    generateRandomDeviceId();
    getOrGenerateDeviceId();
    rotateDeviceId();
    resetDeviceId();

    // With crypto disabled
    setCrypto(undefined);
    generateRandomDeviceId();
    getOrGenerateDeviceId();
    rotateDeviceId();

    // Verify Math.random was NEVER invoked
    expect(mathRandomSpy).not.toHaveBeenCalled();
  });

  it('contains zero personal information or identifiable attributes', () => {
    const id = getOrGenerateDeviceId();
    expect(id).not.toBeNull();
    // Verify it is a random UUID/hex pattern and does not contain PII tokens
    expect(id!).not.toMatch(/@/); // No emails
    expect(id!).not.toMatch(/iitb/i); // No campus/roll markers
    expect(id!).not.toMatch(/student/i);
    expect(id!).not.toMatch(/192\.|10\.|172\./); // No embedded private IPs
    expect(id!).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  });

  it('remains stable across multiple calls within normal browser sessions', () => {
    const id1 = getOrGenerateDeviceId();
    const id2 = getOrGenerateDeviceId();
    const id3 = getOrGenerateDeviceId();
    expect(id1).toBe(id2);
    expect(id2).toBe(id3);
    expect(mockStorage.getItem(DEVICE_ID_STORAGE_KEY)).toBe(id1);
  });

  it('rotateDeviceId generates a fresh, distinct identifier and updates persistence', () => {
    const initialId = getOrGenerateDeviceId();
    const rotatedId = rotateDeviceId();

    expect(rotatedId).not.toBe(initialId);
    expect(/^[a-zA-Z0-9_-]{16,64}$/.test(rotatedId!)).toBe(true);
    expect(mockStorage.getItem(DEVICE_ID_STORAGE_KEY)).toBe(rotatedId);
    expect(getOrGenerateDeviceId()).toBe(rotatedId);
  });

  it('resetDeviceId purges the identifier from storage and memory', () => {
    getOrGenerateDeviceId();
    expect(mockStorage.getItem(DEVICE_ID_STORAGE_KEY)).toBeTruthy();

    resetDeviceId();
    expect(mockStorage.getItem(DEVICE_ID_STORAGE_KEY)).toBeNull();
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
    expect(id1).not.toBeNull();
    expect(/^[a-zA-Z0-9_-]{16,64}$/.test(id1!)).toBe(true);

    const id2 = getOrGenerateDeviceId();
    expect(id2).toBe(id1); // In-memory persistence within session
  });
});
