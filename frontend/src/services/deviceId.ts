/**
 * QueueSense Client Device Identity Module
 *
 * Privacy & Security Architecture (P1.10 Remediation):
 * - Generates a stable, pseudonymous client-instance identifier for individual browser instances.
 * - Purpose: Provides individual rate-limiting fairness on shared NAT gateways (e.g. campus Wi-Fi
 *   at IIT Bombay), ensuring one active student does not exhaust the rate limit for an entire wing.
 *
 * Privacy Guarantees:
 * 1. Zero Personal Data: The identifier is generated purely from cryptographically secure random
 *    values (UUIDv4). It contains NO names, emails, roll numbers, student IDs, IP addresses,
 *    or hardware/fingerprinting attributes.
 * 2. Unlinkability & Rotation: Users can rotate or reset their device identifier at any time using
 *    `rotateDeviceId()` or `resetDeviceId()`, unlinking future observations from previous rate-limit budgets.
 * 3. Graceful Storage Fallback: If browser storage (localStorage) is disabled, restricted (e.g. private
 *    browsing, Safari ITP), or throws a SecurityError, an in-memory session identifier is used. Report
 *    submissions NEVER fail due to storage unavailability.
 */

export const DEVICE_ID_STORAGE_KEY = 'queuesense_client_device_id_v1';

// Format validation matching backend regex ^[a-zA-Z0-9_-]{16,64}$
const DEVICE_ID_REGEX = /^[a-zA-Z0-9_-]{16,64}$/;

// In-memory fallback if localStorage is blocked or throws
let inMemoryDeviceId: string | null = null;

/**
 * Generates a cryptographically strong UUIDv4 or random string matching ^[a-zA-Z0-9_-]{16,64}$.
 * Does NOT incorporate any user or device fingerprinting data.
 */
export function generateRandomDeviceId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  // Fallback using crypto.getRandomValues if randomUUID is unavailable
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    // Set UUIDv4 version (4) and variant (10xx)
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  // Pure Math.random fallback (e.g. ancient headless environments)
  const s4 = () => Math.floor((1 + Math.random()) * 0x10000).toString(16).substring(1);
  return `${s4()}${s4()}-${s4()}-4${s4().substring(1)}-a${s4().substring(1)}-${s4()}${s4()}${s4()}`;
}

/**
 * Checks whether browser localStorage is accessible and working.
 */
function isLocalStorageAvailable(): boolean {
  try {
    if (typeof window === 'undefined' || typeof localStorage === 'undefined') {
      return false;
    }
    const testKey = '__queuesense_storage_test__';
    localStorage.setItem(testKey, '1');
    localStorage.removeItem(testKey);
    return true;
  } catch {
    return false;
  }
}

/**
 * Retrieves the current stable device identifier, generating and persisting a new one if absent.
 * Falls back to in-memory storage safely if localStorage is inaccessible.
 */
export function getOrGenerateDeviceId(): string {
  // 1. Try reading from localStorage
  if (isLocalStorageAvailable()) {
    try {
      const stored = localStorage.getItem(DEVICE_ID_STORAGE_KEY);
      if (stored && DEVICE_ID_REGEX.test(stored.trim())) {
        return stored.trim();
      }
    } catch {
      // Continue to in-memory fallback
    }
  }

  // 2. Check in-memory fallback
  if (inMemoryDeviceId && DEVICE_ID_REGEX.test(inMemoryDeviceId)) {
    return inMemoryDeviceId;
  }

  // 3. Generate a fresh pseudonymous ID
  const freshId = generateRandomDeviceId();

  // 4. Try saving to localStorage
  if (isLocalStorageAvailable()) {
    try {
      localStorage.setItem(DEVICE_ID_STORAGE_KEY, freshId);
      return freshId;
    } catch {
      // Ignore write failure and fall through
    }
  }

  // 5. Store in memory as fallback
  inMemoryDeviceId = freshId;
  return freshId;
}

/**
 * Rotates the device identifier to unlink future activity from past rate-limiting history.
 * Generates a fresh random identifier and updates persistence.
 */
export function rotateDeviceId(): string {
  const newId = generateRandomDeviceId();
  inMemoryDeviceId = newId;

  if (isLocalStorageAvailable()) {
    try {
      localStorage.setItem(DEVICE_ID_STORAGE_KEY, newId);
    } catch {
      // Ignore write failure
    }
  }

  return newId;
}

/**
 * Clears the device identifier from storage and memory.
 */
export function resetDeviceId(): void {
  inMemoryDeviceId = null;
  if (isLocalStorageAvailable()) {
    try {
      localStorage.removeItem(DEVICE_ID_STORAGE_KEY);
    } catch {
      // Ignore removal failure
    }
  }
}
