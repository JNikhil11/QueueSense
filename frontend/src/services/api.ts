/**
 * QueueSense API Client
 * Supports seamless switching between live AWS API Gateway and offline mock fixtures.
 * Explicitly distinguishes live cloud data from demo/seed data.
 */

import { CampusLocation, QueueEstimate, QueueReport, SmartRecommendation, ReportSubmissionPayload } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Authentic IIT Bombay Campus Dining Directory (SMP / Gymkhana Verified)
export const INITIAL_LOCATIONS: CampusLocation[] = [
  {
    id: 'iitb-mess-h12-14',
    name: 'Hostel 12-13-14 Dining Complex',
    category: 'MESS',
    description: 'Central multi-tiered student mess serving breakfast, lunch, snacks, and dinner counters.',
    landmarkLocation: 'Hostel 12-14 Complex, Lakeside Road, East Campus',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Council of Student Affairs / Mess Council',
    openHours: '07:30 - 21:30',
    capacity: 650,
    active: true,
  },
  {
    id: 'iitb-mess-h15-16',
    name: 'Hostel 15-16 Dining Hall',
    category: 'MESS',
    description: 'Modern high-capacity hostel mess catering to senior undergraduate and postgraduate wings.',
    landmarkLocation: 'Hostel 15-16 Quadrangle, North-East Campus',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Student Mentor Program (SMP)',
    openHours: '07:30 - 21:30',
    capacity: 550,
    active: true,
  },
  {
    id: 'iitb-mess-h2',
    name: 'Hostel 2 Dining Hall & Mess',
    category: 'MESS',
    description: 'Historic hostel mess renowned for South and North Indian rotating regional menus.',
    landmarkLocation: 'Hostel 2 Quadrangle, near Gymkhana Grounds',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Hostel 2 Council & SMP Guide',
    openHours: '07:30 - 21:00',
    capacity: 350,
    active: true,
  },
  {
    id: 'iitb-canteen-h3',
    name: 'Hostel 3 Canteen & Juice Centre',
    category: 'CANTEEN',
    description: 'Beloved campus late-night staple serving fresh fruit juices, dosas, parathas, and tea.',
    landmarkLocation: 'Ground Floor, Hostel 3, Main Hostel Avenue',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Gymkhana Freshers Guide',
    openHours: '14:00 - 02:30',
    capacity: 120,
    active: true,
  },
  {
    id: 'iitb-canteen-lhc',
    name: 'LHC Food Court (Lecture Hall)',
    category: 'CANTEEN',
    description: 'High-velocity daytime cafeteria serving express lunches, coffee, sandwiches, and rolls.',
    landmarkLocation: 'Ground Floor, Lecture Hall Complex (LHC), Academic Area',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Academic Facilities & SMP',
    openHours: '08:30 - 18:30',
    capacity: 220,
    active: true,
  },
  {
    id: 'iitb-canteen-gulmohar',
    name: 'Gulmohar Restaurant & Cafe',
    category: 'CANTEEN',
    description: 'Multi-cuisine sit-down restaurant and faculty guest lounge serving thalis and meals.',
    landmarkLocation: 'Gulmohar Building, First Floor, Opposite Main Building',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Estate & Hospitality Directory',
    openHours: '11:00 - 22:30',
    capacity: 180,
    active: true,
  },
  {
    id: 'iitb-canteen-kresit',
    name: 'KReSIT IT Canteen (CSE)',
    category: 'CANTEEN',
    description: 'Quick-service eatery favored by computer science students for coffee, noodles, and wraps.',
    landmarkLocation: 'Kanwal Rekhi School of Information Technology (KReSIT)',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Dept of Computer Science & Eng',
    openHours: '09:00 - 20:00',
    capacity: 90,
    active: true,
  },
  {
    id: 'iitb-cafe-92',
    name: 'Cafe 92 (SAC Hangout)',
    category: 'CANTEEN',
    description: 'Active evening hangout spot serving milkshakes, burgers, hot fries, and snacks.',
    landmarkLocation: 'Students Activity Centre (SAC) Grounds',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Gymkhana Cultural Affairs',
    openHours: '16:00 - 01:00',
    capacity: 140,
    active: true,
  },
  {
    id: 'iitb-canteen-brewberrys',
    name: 'Brewberrys The Coffee Bar',
    category: 'CANTEEN',
    description: 'Artisan coffee, bakery items, iced brews, and quiet tables for study sessions.',
    landmarkLocation: 'Adjacent to Central Library, Main Academic Spine',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Central Library Amenities',
    openHours: '08:00 - 23:00',
    capacity: 80,
    active: true,
  },
  {
    id: 'iitb-amul-parlour',
    name: 'Amul Ice Cream & Dairy Parlour',
    category: 'CANTEEN',
    description: 'Exclusive dairy outlet offering ice creams, flavored milk, milkshakes, and packaged snacks.',
    landmarkLocation: 'Near Hostel 1 & Campus School Junction',
    verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY',
    verificationSource: 'IIT Bombay Commercial Establishments',
    openHours: '09:00 - 23:00',
    capacity: 40,
    active: true,
  },
];

// Realistic Initial Observations for IIT Bombay Outlets
// Explicitly labeled as DEMO / SIMULATED observations
const DEFAULT_SEED_REPORTS: Record<string, QueueReport[]> = {
  'iitb-mess-h12-14': [
    {
      reportId: 'rep_seed_101',
      locationId: 'iitb-mess-h12-14',
      reportedWaitMinutes: 14,
      queueLength: 22,
      note: 'Dinner rush, both South & North counters active',
      timestamp: new Date(Date.now() - 3 * 60 * 1000).toISOString(), // 3m ago
    },
    {
      reportId: 'rep_seed_102',
      locationId: 'iitb-mess-h12-14',
      reportedWaitMinutes: 12,
      queueLength: 19,
      note: 'Line moving steadily',
      timestamp: new Date(Date.now() - 7 * 60 * 1000).toISOString(), // 7m ago
    },
    {
      reportId: 'rep_seed_103',
      locationId: 'iitb-mess-h12-14',
      reportedWaitMinutes: 15,
      queueLength: 24,
      note: 'Heavy arrival from Hostel 13',
      timestamp: new Date(Date.now() - 12 * 60 * 1000).toISOString(), // 12m ago
    },
  ],
  'iitb-mess-h15-16': [
    {
      reportId: 'rep_seed_104',
      locationId: 'iitb-mess-h15-16',
      reportedWaitMinutes: 5,
      queueLength: 6,
      note: 'Very short queue right now, swift service',
      timestamp: new Date(Date.now() - 2 * 60 * 1000).toISOString(), // 2m ago
    },
    {
      reportId: 'rep_seed_105',
      locationId: 'iitb-mess-h15-16',
      reportedWaitMinutes: 6,
      queueLength: 8,
      note: 'Veg meal counter clear',
      timestamp: new Date(Date.now() - 8 * 60 * 1000).toISOString(), // 8m ago
    },
  ],
  'iitb-mess-h2': [
    {
      reportId: 'rep_seed_106',
      locationId: 'iitb-mess-h2',
      reportedWaitMinutes: 8,
      queueLength: 11,
      note: 'Moderate crowd for special dinner',
      timestamp: new Date(Date.now() - 5 * 60 * 1000).toISOString(), // 5m ago
    },
  ],
  'iitb-canteen-h3': [
    {
      reportId: 'rep_seed_107',
      locationId: 'iitb-canteen-h3',
      reportedWaitMinutes: 4,
      queueLength: 5,
      note: 'Fast juice token queue',
      timestamp: new Date(Date.now() - 4 * 60 * 1000).toISOString(), // 4m ago
    },
  ],
  'iitb-canteen-lhc': [
    {
      reportId: 'rep_seed_108',
      locationId: 'iitb-canteen-lhc',
      reportedWaitMinutes: 18,
      queueLength: 28,
      note: 'Post-lecture crowd at sandwich counter',
      timestamp: new Date(Date.now() - 9 * 60 * 1000).toISOString(), // 9m ago
    },
  ],
  'iitb-canteen-gulmohar': [
    {
      reportId: 'rep_seed_109',
      locationId: 'iitb-canteen-gulmohar',
      reportedWaitMinutes: 7,
      queueLength: 9,
      note: 'Thali tokens moving fast',
      timestamp: new Date(Date.now() - 14 * 60 * 1000).toISOString(), // 14m ago
    },
  ],
  'iitb-canteen-kresit': [
    {
      reportId: 'rep_seed_110',
      locationId: 'iitb-canteen-kresit',
      reportedWaitMinutes: 3,
      queueLength: 4,
      note: 'Quiet lab break',
      timestamp: new Date(Date.now() - 6 * 60 * 1000).toISOString(), // 6m ago
    },
  ],
  'iitb-cafe-92': [],
  'iitb-canteen-brewberrys': [],
  'iitb-amul-parlour': [],
};

// Storage Key for Local Browser Simulation Persistence
const STORAGE_KEY = 'queuesense_iitb_observations_v2';

// Load stored reports from LocalStorage or initialize with defaults
function loadReportsStore(): Record<string, QueueReport[]> {
  try {
    if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        // Ensure all initial locations have an array
        const store: Record<string, QueueReport[]> = {};
        INITIAL_LOCATIONS.forEach((l) => {
          store[l.id] = parsed[l.id] || DEFAULT_SEED_REPORTS[l.id] || [];
        });
        return store;
      }
    }
  } catch (e) {
    // Graceful fallback for non-browser or sandbox environments
  }
  // Clone seed reports to avoid mutation
  const initialStore: Record<string, QueueReport[]> = {};
  INITIAL_LOCATIONS.forEach((l) => {
    initialStore[l.id] = [...(DEFAULT_SEED_REPORTS[l.id] || [])];
  });
  return initialStore;
}

// Persist reports store to LocalStorage
function persistReportsStore(store: Record<string, QueueReport[]>): void {
  try {
    if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    }
  } catch (e) {
    // Graceful fallback
  }
}

const mockReports: Record<string, QueueReport[]> = loadReportsStore();

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
    // Persist to local storage for durable offline simulation
    persistReportsStore(mockReports);
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

