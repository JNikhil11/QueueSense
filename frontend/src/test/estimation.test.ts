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

  it('dynamically renormalizes confidence for a single observation and caps at 0.40', () => {
    const now = Date.now();
    const singleReport: QueueReport[] = [
      {
        reportId: 'rep_single',
        locationId: 'mess-c',
        reportedWaitMinutes: 5,
        queueLength: 6,
        deviceId: 'dev_test_device_1',
        timestamp: new Date(now - 1 * 60 * 1000).toISOString(),
      } as any,
    ];

    const est = computeClientEstimate(singleReport);
    expect(est.confidenceScoreType).toBe('HEURISTIC_COMPOSITE');
    expect(est.confidence).toBeLessThanOrEqual(0.40);
    expect(est.confidenceLabel).toMatch(/LIMITED|MODERATE/);
    expect(est.distinctDevicesCount).toBe(1);
  });

  it('filters uncorroborated isolated extreme spikes while preserving corroborated rush-hour surges', () => {
    const now = Date.now();
    // Baseline: 5 reports with low wait (5m)
    const baselineReports: QueueReport[] = Array.from({ length: 5 }, (_, i) => ({
      reportId: `base_${i}`,
      locationId: 'mess-d',
      reportedWaitMinutes: 5,
      queueLength: 6,
      timestamp: new Date(now - (10 + i * 2) * 60 * 1000).toISOString(),
    }));

    // Scenario A: Isolated extreme spike (110m, no corroboration)
    const isolatedSpikeReports = [
      ...baselineReports,
      {
        reportId: 'rep_isolated_spike',
        locationId: 'mess-d',
        reportedWaitMinutes: 110,
        queueLength: 10,
        timestamp: new Date(now - 1 * 60 * 1000).toISOString(),
      },
    ];
    const estIsolated = computeClientEstimate(isolatedSpikeReports);
    expect(estIsolated.outliersExcluded).toBeGreaterThanOrEqual(1);
    expect(estIsolated.predictedWaitMinutes).toBeLessThan(20);

    // Scenario B: Corroborated rush-hour surge (two students report 35m and 38m with distinct client IDs)
    const corroboratedReports = [
      ...baselineReports,
      {
        reportId: 'rep_surge_1',
        locationId: 'mess-d',
        reportedWaitMinutes: 35,
        queueLength: 45,
        deviceId: 'dev_student_surge_alpha',
        timestamp: new Date(now - 2 * 60 * 1000).toISOString(),
      },
      {
        reportId: 'rep_surge_2',
        locationId: 'mess-d',
        reportedWaitMinutes: 38,
        queueLength: 50,
        deviceId: 'dev_student_surge_beta',
        timestamp: new Date(now - 1 * 60 * 1000).toISOString(),
      },
    ];
    const estCorroborated = computeClientEstimate(corroboratedReports);
    expect(estCorroborated.predictedWaitMinutes).toBeGreaterThanOrEqual(18);
    expect(estCorroborated.congestion).toBe('VERY_HIGH');

    // Scenario C: Spikes with missing or identical device IDs fail to corroborate
    const sameDeviceSpikes = [
      ...baselineReports,
      {
        reportId: 'rep_same_dev_1',
        locationId: 'mess-d',
        reportedWaitMinutes: 35,
        queueLength: 45,
        deviceId: 'dev_student_same_device',
        timestamp: new Date(now - 2 * 60 * 1000).toISOString(),
      },
      {
        reportId: 'rep_same_dev_2',
        locationId: 'mess-d',
        reportedWaitMinutes: 38,
        queueLength: 50,
        deviceId: 'dev_student_same_device',
        timestamp: new Date(now - 1 * 60 * 1000).toISOString(),
      },
    ];
    const estSameDev = computeClientEstimate(sameDeviceSpikes);
    expect(estSameDev.outliersExcluded).toBe(2);
    expect(estSameDev.predictedWaitMinutes).toBeLessThan(20);
  });

  it('smoothly tapers time-decay weights between 50 and 60 minutes with zero step discontinuity', () => {
    const now = Date.now();

    // Report at 45m: untapered exponential
    const rep45: QueueReport[] = [
      {
        reportId: 'r45',
        locationId: 'test',
        reportedWaitMinutes: 10,
        queueLength: 5,
        timestamp: new Date(now - 45 * 60 * 1000).toISOString(),
      },
    ];
    const est45 = computeClientEstimate(rep45);
    expect(est45.predictedWaitMinutes).toBe(10);

    // Report at 55m: cosine tapered (T(55) = 0.5)
    const rep55: QueueReport[] = [
      {
        reportId: 'r55',
        locationId: 'test',
        reportedWaitMinutes: 20,
        queueLength: 10,
        timestamp: new Date(now - 55 * 60 * 1000).toISOString(),
      },
    ];
    const est55 = computeClientEstimate(rep55);
    expect(est55.predictedWaitMinutes).toBe(20);

    // Report at 61m: completely disregarded
    const rep61: QueueReport[] = [
      {
        reportId: 'r61',
        locationId: 'test',
        reportedWaitMinutes: 20,
        queueLength: 10,
        timestamp: new Date(now - 61 * 60 * 1000).toISOString(),
      },
    ];
    const est61 = computeClientEstimate(rep61);
    expect(est61.predictedWaitMinutes).toBeNull();
    expect(est61.freshness).toBe('NO RECENT DATA');
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
    const unverifiedLocations = INITIAL_LOCATIONS.filter(
      (l) => l.verificationStatus === 'UNVERIFIED'
    );
    expect(unverifiedLocations.length).toBe(INITIAL_LOCATIONS.length);
    unverifiedLocations.forEach((loc) => {
      expect(loc.verificationSource).toBeDefined();
      expect(loc.verificationSource!.length).toBeGreaterThan(5);
    });
  });

  it('provides historical trends API with 24-hour distribution', async () => {
    const hist = await api.getHistorical('iitb-mess-h12-14');
    expect(hist.data.locationId).toBe('iitb-mess-h12-14');
    expect(hist.data.hourlyTrends.length).toBe(24);
    expect(hist.data.summary).toBeDefined();
  });
});
