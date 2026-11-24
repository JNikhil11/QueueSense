/**
 * QueueSense Client Device Identity Module
 *
 * Privacy & Security Architecture (P1.10 Remediation):
 * - Generates a stable, pseudonymous client-instance identifier for individual browser instances.
 * - Purpose: Provides individual rate-limiting fairness on shared NAT gateways (e.g. campus Wi-Fi
 *   at IIT Bombay), ensuring one active student does not exhaust the rate limit for an entire wing.
 *
 * Cryptographic & Privacy Guarantees:
 * 1. Cryptographically Secure Randomness Only: The identifier is generated strictly using CSPRNG
 *    (crypto.randomUUID() or crypto.getRandomValues()). NO Math.random() or predictable fallbacks
 *    are ever used. If secure randomness is unavailable in the execution environment and no valid
 *    persisted identifier exists, no device ID is generated (returns null).
 * 2. Zero Personal Data: The identifier contains NO names, emails, roll numbers, student IDs,
 *    IP addresses, or hardware/fingerprinting attributes.
 * 3. Graceful Backend Fallback: If no device ID is sent, the backend safely falls back to its
 *    trusted IP rate-limiting budget. Report submissions never fail when secure randomness is absent.
 * 4. Unlinkability & Rotation: Users can rotate or reset their device identifier at any time using
 *    `rotateDeviceId()` or `resetDeviceId()`, unlinking future observations from previous rate-limit budgets.
 * 5. Safe Storage Fallback: If browser storage (localStorage) is disabled or throws a SecurityError,
 *    an in-memory session identifier is used if CSPRNG is available.
 */

export const DEVICE_ID_STORAGE_KEY = 'queuesense_client_device_id_v1';

// Format validation matching backend regex ^[a-zA-Z0-9_-]{16,64}$
const DEVICE_ID_REGEX = /^[a-zA-Z0-9_-]{16,64}$/;

// In-memory fallback if localStorage is blocked or throws
let inMemoryDeviceId: string | null = null;

/**
 * Generates a cryptographically strong UUIDv4 using available CSPRNG APIs.
 * Returns null if neither crypto.randomUUID nor crypto.getRandomValues is available.
 * Never falls back to Math.random() or insecure pseudo-random generators.
 */
export function generateRandomDeviceId(): string | null {
  if (typeof crypto !== 'undefined') {
    if (typeof crypto.randomUUID === 'function') {
      try {
        const id = crypto.randomUUID();
        if (DEVICE_ID_REGEX.test(id)) {
          return id;
        }
      } catch {
        // Fall through to getRandomValues
      }
    }

    if (typeof crypto.getRandomValues === 'function') {
      try {
        const bytes = new Uint8Array(16);
        crypto.getRandomValues(bytes);
        // Set UUIDv4 version (4) and variant (10xx)
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
        const id = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
        if (DEVICE_ID_REGEX.test(id)) {
          return id;
        }
      } catch {
        // CSPRNG failure
      }
    }
  }

  // Strictly no insecure fallback: return null when CSPRNG is unavailable
  return null;
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
 * Retrieves the current stable device identifier.
 * If a valid identifier exists in localStorage or in-memory, returns it.
 * If none exists, generates a new CSPRNG identifier.
 * If secure randomness is unavailable, returns null rather than generating an insecure identifier.
 */
export function getOrGenerateDeviceId(): string | null {
  // 1. Try reading from localStorage (existing valid stored ID remains usable even if crypto is disabled)
  if (isLocalStorageAvailable()) {
    try {
      const stored = localStorage.getItem(DEVICE_ID_STORAGE_KEY);
      if (stored && DEVICE_ID_REGEX.test(stored.trim())) {
        return stored.trim();
      }
    } catch {
      // Continue to in-memory check
    }
  }

  // 2. Check in-memory fallback
  if (inMemoryDeviceId && DEVICE_ID_REGEX.test(inMemoryDeviceId)) {
    return inMemoryDeviceId;
  }

  // 3. Generate a fresh pseudonymous ID using CSPRNG
  const freshId = generateRandomDeviceId();
  if (!freshId) {
    // Secure randomness unavailable; fail closed to null (do not invent insecure ID)
    return null;
  }

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
 * If secure randomness is available, generates and stores a new identifier.
 * If secure randomness is unavailable, clears stored state and returns null.
 */
export function rotateDeviceId(): string | null {
  const newId = generateRandomDeviceId();
  inMemoryDeviceId = newId;

  if (isLocalStorageAvailable()) {
    try {
      if (newId) {
        localStorage.setItem(DEVICE_ID_STORAGE_KEY, newId);
      } else {
        localStorage.removeItem(DEVICE_ID_STORAGE_KEY);
      }
    } catch {
      // Ignore storage write failure
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
