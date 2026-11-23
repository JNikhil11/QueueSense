import { describe, it, expect } from 'vitest';
import { computeClientEstimate } from '../services/api';
import { QueueReport } from '../types';

describe('Client-Side Queue Estimation Logic', () => {
  it('returns no recent data when report list is empty', () => {
    const est = computeClientEstimate([]);
    expect(est.predictedWaitMinutes).toBeNull();
    expect(est.freshness).toBe('NO RECENT DATA');
    expect(est.confidence).toBe(0);
    expect(est.confidenceLabel).toBe('NO DATA');
  });

  it('weights recent reports correctly and assigns LIVE freshness', () => {
    const now = Date.now();
    const reports: QueueReport[] = [
      {
        reportId: 'r1',
        locationId: 'mess-a',
        reportedWaitMinutes: 6,
        queueLength: 10,
        timestamp: new Date(now - 2 * 60 * 1000).toISOString(), // 2m ago
      },
      {
        reportId: 'r2',
        locationId: 'mess-a',
        reportedWaitMinutes: 8,
        queueLength: 12,
        timestamp: new Date(now - 5 * 60 * 1000).toISOString(), // 5m ago
      },
    ];

    const est = computeClientEstimate(reports);
    expect(est.predictedWaitMinutes).toBeGreaterThanOrEqual(6);
    expect(est.predictedWaitMinutes).toBeLessThanOrEqual(8);
    expect(est.freshness).toBe('LIVE');
    expect(est.congestion).toBe('MODERATE');
    expect(est.confidence).toBeGreaterThan(0.3);
  });

  it('disregards reports older than 60 minutes', () => {
    const now = Date.now();
    const oldReports: QueueReport[] = [
      {
        reportId: 'r_old',
        locationId: 'mess-b',
        reportedWaitMinutes: 10,
        queueLength: 15,
        timestamp: new Date(now - 75 * 60 * 1000).toISOString(), // 75m ago
      },
    ];

    const est = computeClientEstimate(oldReports);
    expect(est.predictedWaitMinutes).toBeNull();
    expect(est.freshness).toBe('NO RECENT DATA');
  });
});
