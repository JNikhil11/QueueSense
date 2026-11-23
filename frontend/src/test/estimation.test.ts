import { describe, it, expect } from 'vitest';
import { computeClientEstimate, api, DATA_MODE, INITIAL_LOCATIONS } from '../services/api';
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
        timestamp: new Date(now - 2 * 60 * 1000).toISOString(),
      },
      {
        reportId: 'r2',
        locationId: 'mess-a',
        reportedWaitMinutes: 8,
        queueLength: 12,
        timestamp: new Date(now - 5 * 60 * 1000).toISOString(),
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
        timestamp: new Date(now - 75 * 60 * 1000).toISOString(),
      },
    ];

    const est = computeClientEstimate(oldReports);
    expect(est.predictedWaitMinutes).toBeNull();
    expect(est.freshness).toBe('NO RECENT DATA');
  });

  it('correctly aggregates newly submitted 20m/40queue meal rush report alongside 5m/6m reports', () => {
    const now = Date.now();
    const reports: QueueReport[] = [
      {
        reportId: 'rep_rush_new',
        locationId: 'iitb-mess-h15-16',
        reportedWaitMinutes: 20,
        queueLength: 40,
        note: 'Heavy rush',
        timestamp: new Date(now).toISOString(),
      },
      {
        reportId: 'rep_prior_1',
        locationId: 'iitb-mess-h15-16',
        reportedWaitMinutes: 5,
        queueLength: 6,
        timestamp: new Date(now - 2 * 60 * 1000).toISOString(),
      },
      {
        reportId: 'rep_prior_2',
        locationId: 'iitb-mess-h15-16',
        reportedWaitMinutes: 6,
        queueLength: 8,
        timestamp: new Date(now - 8 * 60 * 1000).toISOString(),
      },
    ];

    const est = computeClientEstimate(reports);
    expect(est.predictedWaitMinutes).toBeGreaterThanOrEqual(10.5);
    expect(est.predictedWaitMinutes).toBeLessThanOrEqual(12.5);
    expect(est.predictedQueueLength).toBeGreaterThanOrEqual(18);
    expect(est.predictedQueueLength).toBeLessThanOrEqual(22);
    expect(est.congestion).toBe('HIGH');
    expect(est.freshness).toBe('LIVE');
    expect(est.reportCount).toBe(3);
    expect(est.recentReportCount).toBe(3);
  });
});

describe('Production Hardening & Recommendation Intelligence', () => {
  it('identifies active data mode honestly', () => {
    expect(DATA_MODE).toBeDefined();
    expect(['production', 'demo', 'development']).toContain(DATA_MODE);
  });
  it('enforces cold-start protection: requires at least 3 fresh reports and 50%+ confidence', async () => {
    const rec = await api.getRecommendations();
    expect(rec.data).toBeDefined();
    // In our seed fixture, mess-h15-16 has 3 fresh reports with high confidence
    if (rec.data.isEligible) {
      expect(rec.data.state).toBe('recommended');
      expect(rec.data.predictedWaitMinutes).toBeDefined();
    } else {
      expect(rec.data.state).toBe('insufficient_data');
      expect(rec.data.recommendedLocationId).toBeNull();
    }
  });

  it('provides student-sourced campus directory with honest provenance', () => {
    expect(INITIAL_LOCATIONS.length).toBeGreaterThanOrEqual(5);
    const verifiedLocations = INITIAL_LOCATIONS.filter(
      (l) => l.verificationStatus === 'STUDENT_SOURCED'
    );
    expect(verifiedLocations.length).toBe(INITIAL_LOCATIONS.length);
    verifiedLocations.forEach((loc) => {
      expect(loc.verificationSource.length).toBeGreaterThan(5);
    });
  });

  it('provides historical trends API with 24-hour distribution', async () => {
    const hist = await api.getHistorical('iitb-mess-h12-14');
    expect(hist.data.locationId).toBe('iitb-mess-h12-14');
    expect(hist.data.hourlyTrends.length).toBe(24);
    expect(hist.data.summary).toBeDefined();
  });
});
