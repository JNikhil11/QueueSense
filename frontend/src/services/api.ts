/**
 * QueueSense API Client
 * Supports seamless switching between live AWS API Gateway and offline mock fixtures.
 * Explicitly distinguishes live cloud data from demo/seed data.
 */

import { CampusLocation, QueueEstimate, QueueReport, SmartRecommendation, ReportSubmissionPayload } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Configurable campus outlets (VIT-AP campus context)
const INITIAL_LOCATIONS: CampusLocation[] = [
  {
    id: 'mess-a-central',
    name: 'Central Mess A (North Dining)',
    category: 'MESS',
    description: 'Primary multi-story student dining hall serving breakfast, lunch, and dinner counters.',
    openHours: '07:30 - 21:30',
    capacity: 450,
    active: true,
  },
  {
    id: 'mess-b-south',
    name: 'South Mess B (Annex Dining)',
    category: 'MESS',
    description: 'South block student dining hall featuring traditional and vegetarian meal counters.',
    openHours: '07:30 - 21:00',
    capacity: 350,
    active: true,
  },
  {
    id: 'canteen-rock-plaza',
    name: 'Rock Plaza Food Court',
    category: 'CANTEEN',
    description: 'Open-air plaza offering quick snacks, fresh juices, hot beverages, and rolls.',
    openHours: '10:00 - 23:00',
    capacity: 180,
    active: true,
  },
  {
    id: 'canteen-academic-block',
    name: 'CB Academic Bistro',
    category: 'CANTEEN',
    description: 'Fast-counter canteen situated near lecture halls for express lunch and coffee.',
    openHours: '08:30 - 18:00',
    capacity: 120,
    active: true,
  },
  {
    id: 'canteen-night-cafeteria',
    name: 'Midnight Fuel Canteen',
    category: 'CANTEEN',
    description: 'Late-evening campus outlet popular during exam periods and project deadlines.',
    openHours: '17:00 - 02:00',
    capacity: 150,
    active: true,
  },
];

// Offline In-Memory Mock Store with Seed Observations
// Clearly labeled as SEED/DEMO data when active
const mockReports: Record<string, QueueReport[]> = {
  'mess-a-central': [
    {
      reportId: 'rep_seed_01',
      locationId: 'mess-a-central',
      reportedWaitMinutes: 14,
      queueLength: 22,
      note: 'Lunch rush, main counter packed',
      timestamp: new Date(Date.now() - 3 * 60 * 1000).toISOString(), // 3m ago
    },
    {
      reportId: 'rep_seed_02',
      locationId: 'mess-a-central',
      reportedWaitMinutes: 12,
      queueLength: 20,
      note: 'Both lines moving steady',
      timestamp: new Date(Date.now() - 6 * 60 * 1000).toISOString(), // 6m ago
    },
    {
      reportId: 'rep_seed_03',
      locationId: 'mess-a-central',
      reportedWaitMinutes: 15,
      queueLength: 25,
      note: '',
      timestamp: new Date(Date.now() - 11 * 60 * 1000).toISOString(), // 11m ago
    },
  ],
  'mess-b-south': [
    {
      reportId: 'rep_seed_04',
      locationId: 'mess-b-south',
      reportedWaitMinutes: 5,
      queueLength: 6,
      note: 'Very short queue today, fast service',
      timestamp: new Date(Date.now() - 2 * 60 * 1000).toISOString(), // 2m ago
    },
    {
      reportId: 'rep_seed_05',
      locationId: 'mess-b-south',
      reportedWaitMinutes: 6,
      queueLength: 8,
      note: 'Smooth flow at veg counter',
      timestamp: new Date(Date.now() - 8 * 60 * 1000).toISOString(), // 8m ago
    },
  ],
  'canteen-rock-plaza': [
    {
      reportId: 'rep_seed_06',
      locationId: 'canteen-rock-plaza',
      reportedWaitMinutes: 9,
      queueLength: 12,
      note: 'Chai and sandwich counter busy',
      timestamp: new Date(Date.now() - 15 * 60 * 1000).toISOString(), // 15m ago
    },
  ],
  'canteen-academic-block': [
    {
      reportId: 'rep_seed_07',
      locationId: 'canteen-academic-block',
      reportedWaitMinutes: 4,
      queueLength: 5,
      note: 'Quiet afternoon',
      timestamp: new Date(Date.now() - 52 * 60 * 1000).toISOString(), // 52m ago -> STALE
    },
  ],
  'canteen-night-cafeteria': [], // NO DATA
};

// Client-side pure estimation calculation (mirrors backend Python prediction module)
export function computeClientEstimate(reports: QueueReport[]): QueueEstimate {
  const now = Date.now();
  const TAU_MS = 15 * 60 * 1000;
  const MAX_AGE_MS = 60 * 60 * 1000;

  if (!reports || reports.length === 0) {
    return {
      predictedWaitMinutes: null,
      predictedQueueLength: null,
      congestion: 'UNKNOWN',
      confidence: 0,
      confidenceLabel: 'NO DATA',
      freshness: 'NO RECENT DATA',
      reportCount: 0,
      recentReportCount: 0,
      newestReportAgeMinutes: null,
      newestReportTimestamp: null,
      disagreementMinutes: 0,
      outliersExcluded: 0,
      evidenceExplanation: 'No recent observations recorded for this outlet.',
      updatedAt: new Date().toISOString(),
    };
  }

  let weightedWaitSum = 0;
  let weightedQueueSum = 0;
  let totalWeight = 0;
  let newestAgeMinutes: number | null = null;
  let newestTimestamp: string | null = null;
  const recentReports: QueueReport[] = [];

  for (const r of reports) {
    const ageMs = Math.max(0, now - new Date(r.timestamp).getTime());
    const ageMin = ageMs / (60 * 1000);

    if (newestAgeMinutes === null || ageMin < newestAgeMinutes) {
      newestAgeMinutes = ageMin;
      newestTimestamp = r.timestamp;
    }

    if (ageMs <= MAX_AGE_MS) {
      const weight = Math.exp(-ageMs / TAU_MS);
      if (weight > 0.001) {
        weightedWaitSum += weight * r.reportedWaitMinutes;
        weightedQueueSum += weight * r.queueLength;
        totalWeight += weight;
        recentReports.push(r);
      }
    }
  }

  if (totalWeight < 0.01 || recentReports.length === 0) {
    return {
      predictedWaitMinutes: null,
      predictedQueueLength: null,
      congestion: 'UNKNOWN',
      confidence: 0,
      confidenceLabel: 'NO DATA',
      freshness: 'NO RECENT DATA',
      reportCount: reports.length,
      recentReportCount: 0,
      newestReportAgeMinutes: newestAgeMinutes ? Math.round(newestAgeMinutes) : null,
      newestReportTimestamp: newestTimestamp,
      disagreementMinutes: 0,
      outliersExcluded: 0,
      evidenceExplanation: 'Past reports are over 60 minutes old and no longer reflect current conditions.',
      updatedAt: new Date().toISOString(),
    };
  }

  const estimatedWait = Math.round((weightedWaitSum / totalWeight) * 10) / 10;
  const estimatedQueue = Math.round(weightedQueueSum / totalWeight);

  // Congestion
  let congestion: QueueEstimate['congestion'] = 'LOW';
  if (estimatedWait >= 15.5) congestion = 'VERY_HIGH';
  else if (estimatedWait >= 8.5) congestion = 'HIGH';
  else if (estimatedWait >= 3.5) congestion = 'MODERATE';

  // Freshness
  let freshness: QueueEstimate['freshness'] = 'NO RECENT DATA';
  if (newestAgeMinutes !== null) {
    if (newestAgeMinutes <= 7) freshness = 'LIVE';
    else if (newestAgeMinutes <= 20) freshness = 'RECENT';
    else if (newestAgeMinutes <= 60) freshness = 'STALE';
  }

  // Disagreement
  const waits = recentReports.map((r) => r.reportedWaitMinutes);
  const disagreement = waits.length > 1 ? Math.round((Math.max(...waits) - Math.min(...waits)) * 10) / 10 : 0;

  // Confidence
  const volumeScore = Math.min(recentReports.length / 4, 1.0) * 0.45;
  const recencyFactor = Math.max(0, 1.0 - (newestAgeMinutes || 0) / 25) * 0.35;
  const agreementFactor = waits.length > 1 ? Math.max(0, 1.0 - disagreement / 15) * 0.2 : 0.08;
  const confidence = Math.round(Math.min(1.0, volumeScore + recencyFactor + agreementFactor) * 100) / 100;

  let confidenceLabel: QueueEstimate['confidenceLabel'] = 'VERY LOW';
  if (confidence >= 0.7) confidenceLabel = 'HIGH';
  else if (confidence >= 0.4) confidenceLabel = 'MODERATE';
  else if (confidence >= 0.2) confidenceLabel = 'LIMITED';

  const countStr = `${recentReports.length} recent report${recentReports.length === 1 ? '' : 's'}`;
  const ageStr = newestAgeMinutes && newestAgeMinutes >= 1 ? `${Math.round(newestAgeMinutes)}m ago` : 'just now';

  let explanation = '';
  if (confidenceLabel === 'HIGH') {
    explanation = `Strong agreement across ${countStr}; latest report from ${ageStr}.`;
  } else if (confidenceLabel === 'MODERATE') {
    explanation = `Solid estimate based on ${countStr}; updated ${ageStr}.`;
  } else if (confidenceLabel === 'LIMITED') {
    explanation = `Based on a single observation from ${ageStr}. More reports will improve accuracy.`;
  } else {
    explanation = `Observations are aging (${ageStr}); estimate may not reflect sudden rushes.`;
  }

  return {
    predictedWaitMinutes: estimatedWait,
    predictedQueueLength: estimatedQueue,
    congestion,
    confidence,
    confidenceLabel,
    freshness,
    reportCount: reports.length,
    recentReportCount: recentReports.length,
    newestReportAgeMinutes: newestAgeMinutes !== null ? Math.round(newestAgeMinutes * 10) / 10 : null,
    newestReportTimestamp: newestTimestamp,
    disagreementMinutes: disagreement,
    outliersExcluded: 0,
    evidenceExplanation: explanation,
    updatedAt: new Date().toISOString(),
  };
}

export const api = {
  isLiveApiConfigured(): boolean {
    return Boolean(API_BASE_URL && API_BASE_URL.startsWith('http'));
  },

  async getLocations(): Promise<{ data: CampusLocation[]; isLive: boolean }> {
    if (this.isLiveApiConfigured()) {
      try {
        const res = await fetch(`${API_BASE_URL}/locations`);
        if (res.ok) {
          const json = await res.json();
          return { data: json.data, isLive: true };
        }
      } catch (err) {
        console.warn('API Gateway unreachable, falling back to mock fixtures:', err);
      }
    }

    // Offline / Mock fallback
    const locationsWithEstimates = INITIAL_LOCATIONS.map((loc) => ({
      ...loc,
      estimate: computeClientEstimate(mockReports[loc.id] || []),
    }));

    return { data: locationsWithEstimates, isLive: false };
  },

  async getLocationQueue(locationId: string): Promise<{
    location: CampusLocation;
    estimate: QueueEstimate;
    reports: QueueReport[];
    isLive: boolean;
  }> {
    if (this.isLiveApiConfigured()) {
      try {
        const res = await fetch(`${API_BASE_URL}/locations/${locationId}/queue`);
        if (res.ok) {
          const json = await res.json();
          return { ...json.data, isLive: true };
        }
      } catch (err) {
        console.warn('API Gateway unreachable, falling back to mock fixtures:', err);
      }
    }

    const loc = INITIAL_LOCATIONS.find((l) => l.id === locationId) || INITIAL_LOCATIONS[0];
    const reports = [...(mockReports[locationId] || [])].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
    const estimate = computeClientEstimate(reports);

    return {
      location: loc,
      estimate,
      reports,
      isLive: false,
    };
  },

  async submitReport(
    locationId: string,
    payload: ReportSubmissionPayload
  ): Promise<{ report: QueueReport; updatedEstimate: QueueEstimate; isLive: boolean }> {
    if (this.isLiveApiConfigured()) {
      try {
        const res = await fetch(`${API_BASE_URL}/locations/${locationId}/reports`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          const json = await res.json();
          return { ...json.data, isLive: true };
        }
        const errJson = await res.json();
        throw new Error(errJson.error || 'Failed to submit report to server');
      } catch (err: any) {
        if (!err.message?.includes('Failed to submit')) {
          console.warn('API Gateway unreachable, storing report locally:', err);
        } else {
          throw err;
        }
      }
    }

    // Mock fallback submission
    const newReport: QueueReport = {
      reportId: `rep_local_${Date.now()}`,
      locationId,
      reportedWaitMinutes: payload.reportedWaitMinutes,
      queueLength: payload.queueLength,
      note: payload.note,
      timestamp: new Date().toISOString(),
    };

    if (!mockReports[locationId]) {
      mockReports[locationId] = [];
    }
    mockReports[locationId].unshift(newReport);
    const updatedEstimate = computeClientEstimate(mockReports[locationId]);

    return {
      report: newReport,
      updatedEstimate,
      isLive: false,
    };
  },

  async getRecommendations(): Promise<{ data: SmartRecommendation; isLive: boolean }> {
    if (this.isLiveApiConfigured()) {
      try {
        const res = await fetch(`${API_BASE_URL}/recommendations`);
        if (res.ok) {
          const json = await res.json();
          return { data: json.data, isLive: true };
        }
      } catch (err) {
        console.warn('API Gateway unreachable, calculating recommendations locally:', err);
      }
    }

    // Calculate recommendation across mock outlets
    const candidates = INITIAL_LOCATIONS.map((loc) => ({
      ...loc,
      estimate: computeClientEstimate(mockReports[loc.id] || []),
    }));

    const eligible = candidates.filter(
      (c) =>
        c.estimate &&
        c.estimate.predictedWaitMinutes !== null &&
        ['LIVE', 'RECENT'].includes(c.estimate.freshness) &&
        c.estimate.confidence >= 0.25
    );

    if (eligible.length === 0) {
      return {
        data: {
          recommendedLocationId: null,
          recommendedLocationName: null,
          reason: 'Not enough recent queue reports across campus to make a reliable recommendation yet.',
          isEligible: false,
          candidateCount: candidates.length,
          eligibleCount: 0,
        },
        isLive: false,
      };
    }

    eligible.sort((a, b) => {
      const waitA = a.estimate!.predictedWaitMinutes!;
      const waitB = b.estimate!.predictedWaitMinutes!;
      if (waitA !== waitB) return waitA - waitB;
      return b.estimate!.confidence - a.estimate!.confidence;
    });

    const winner = eligible[0];
    const wEst = winner.estimate!;
    const ageText =
      wEst.newestReportAgeMinutes && wEst.newestReportAgeMinutes >= 1
        ? `${Math.round(wEst.newestReportAgeMinutes)}m ago`
        : 'just now';

    return {
      data: {
        recommendedLocationId: winner.id,
        recommendedLocationName: winner.name,
        predictedWaitMinutes: wEst.predictedWaitMinutes!,
        congestion: wEst.congestion,
        confidence: wEst.confidence,
        confidenceLabel: wEst.confidenceLabel,
        reason: `Shortest estimated wait (~${wEst.predictedWaitMinutes} min) with ${wEst.confidenceLabel.toLowerCase()} evidence; verified by ${wEst.recentReportCount} report${wEst.recentReportCount === 1 ? '' : 's'} updated ${ageText}.`,
        isEligible: true,
        candidateCount: candidates.length,
        eligibleCount: eligible.length,
      },
      isLive: false,
    };
  },

  async getAdminReports(): Promise<{ reports: QueueReport[]; isLive: boolean }> {
    if (this.isLiveApiConfigured()) {
      try {
        const res = await fetch(`${API_BASE_URL}/admin/reports`);
        if (res.ok) {
          const json = await res.json();
          return { reports: json.data.reports, isLive: true };
        }
      } catch (err) {
        console.warn('API Gateway unreachable, returning mock admin audit feed:', err);
      }
    }

    const allReports: QueueReport[] = [];
    Object.values(mockReports).forEach((reps) => {
      allReports.push(...reps);
    });
    allReports.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

    return { reports: allReports, isLive: false };
  },
};

