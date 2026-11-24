/**
 * QueueSense API Client
 * Strict Separation: Production (Live AWS API) vs. Demo (Local Simulated Data)
 * Enforces server-side idempotency, rate-limiting handling, and durable persistence.
 */

import {
  CampusLocation,
  QueueEstimate,
  QueueReport,
  SmartRecommendation,
  ReportSubmissionPayload,
  HistoricalData,
  DataMode,
} from '../types';
import {
  getOrGenerateDeviceId,
  rotateDeviceId,
  resetDeviceId,
  DEVICE_ID_STORAGE_KEY,
} from './deviceId';

export {
  getOrGenerateDeviceId,
  rotateDeviceId,
  resetDeviceId,
  DEVICE_ID_STORAGE_KEY,
};

export const API_BASE_URL =
  (typeof window !== 'undefined' && (window as any).__QUEUESENSE_API_URL__) ||
  import.meta.env.VITE_API_URL ||
  '';

export const DATA_MODE: DataMode = (
  (typeof window !== 'undefined' && (window as any).__QUEUESENSE_DATA_MODE__) ||
  import.meta.env.VITE_DATA_MODE ||
  (import.meta.env.PROD ? 'production' : 'demo')
) as DataMode;

export const CAMPUS_ID =
  (typeof window !== 'undefined' && (window as any).__QUEUESENSE_CAMPUS_ID__) ||
  import.meta.env.VITE_CAMPUS_ID ||
  'iitb';

// Student-Sourced IIT Bombay Dining Directory
export const IITB_LOCATIONS: CampusLocation[] = [
  {
    id: 'iitb-mess-h12-14',
    name: 'Hostel 12-13-14 Dining Complex',
    category: 'MESS',
    description: 'Central multi-tiered student mess serving breakfast, lunch, snacks, and dinner counters.',
    landmarkLocation: 'Hostel 12-14 Complex, Lakeside Road, East Campus',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'IIT Bombay Student Mentorship Guide & Techfest Ambassador Sourced',
    openHours: 'Breakfast (07:30-09:30), Lunch (12:00-14:15), Dinner (19:30-21:30)',
    capacityEstimate: 'Large Dining Complex (~500-650 approx.)',
    capacity: 600,
    active: true,
  },
  {
    id: 'iitb-mess-h15-16',
    name: 'Hostel 15-16 Dining Hall',
    category: 'MESS',
    description: 'Modern high-capacity hostel mess catering to senior undergraduate and postgraduate wings.',
    landmarkLocation: 'Hostel 15-16 Quadrangle, North-East Campus',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'IIT Bombay Student Mentor Program (SMP) Guide',
    openHours: 'Breakfast (07:30-09:30), Lunch (12:00-14:15), Dinner (19:30-21:30)',
    capacityEstimate: 'Large Modern Dining Hall (~450-550 approx.)',
    capacity: 500,
    active: true,
  },
  {
    id: 'iitb-mess-h2',
    name: 'Hostel 2 Dining Hall & Mess',
    category: 'MESS',
    description: 'Historic hostel mess renowned for South and North Indian rotating regional menus.',
    landmarkLocation: 'Hostel 2 Quadrangle, near Gymkhana Grounds',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'IIT Bombay Hostel 2 Council & SMP Guide',
    openHours: 'Breakfast (07:30-09:30), Lunch (12:00-14:00), Dinner (19:30-21:15)',
    capacityEstimate: 'Hostel Dining Hall (~300-380 approx.)',
    capacity: 350,
    active: true,
  },
  {
    id: 'iitb-canteen-h3',
    name: 'Hostel 3 Canteen & Juice Centre',
    category: 'CANTEEN',
    description: 'Beloved campus late-night staple serving fresh fruit juices, dosas, parathas, and tea.',
    landmarkLocation: 'Ground Floor, Hostel 3, Main Hostel Avenue',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'IIT Bombay Gymkhana Freshers Guide',
    openHours: '14:00 - 02:30 (Late Night Canteen)',
    capacityEstimate: 'Hostel Canteen Counter (~80-120 approx.)',
    capacity: 100,
    active: true,
  },
  {
    id: 'iitb-canteen-lhc',
    name: 'LHC Food Court (Lecture Hall)',
    category: 'CANTEEN',
    description: 'High-velocity daytime cafeteria serving express lunches, coffee, sandwiches, and rolls.',
    landmarkLocation: 'Ground Floor, Lecture Hall Complex (LHC), Academic Area',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'IIT Bombay Academic Facilities & SMP Guide',
    openHours: '08:30 - 18:30 (Academic Class Hours)',
    capacityEstimate: 'Academic Cafeteria (~180-240 approx.)',
    capacity: 200,
    active: true,
  },
  {
    id: 'iitb-canteen-gulmohar',
    name: 'Gulmohar Restaurant & Cafe',
    category: 'CANTEEN',
    description: 'Multi-cuisine sit-down restaurant and faculty guest lounge serving thalis and meals.',
    landmarkLocation: 'Gulmohar Building, First Floor, Opposite Main Building',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'IIT Bombay Estate & Hospitality Directory',
    openHours: 'Lunch (11:30-15:00), Dinner (19:00-22:30)',
    capacityEstimate: 'Restaurant & Lounge (~140-180 approx.)',
    capacity: 160,
    active: true,
  },
  {
    id: 'iitb-canteen-kresit',
    name: 'KReSIT IT Canteen (CSE)',
    category: 'CANTEEN',
    description: 'Quick-service eatery favored by computer science students for coffee, noodles, and wraps.',
    landmarkLocation: 'Kanwal Rekhi School of Information Technology (KReSIT)',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'IIT Bombay Dept of Computer Science & Eng',
    openHours: '09:00 - 20:00 (Department Hours)',
    capacityEstimate: 'Quick-Service Counter (~70-100 approx.)',
    capacity: 85,
    active: true,
  },
  {
    id: 'iitb-cafe-92',
    name: 'Cafe 92 (SAC Hangout)',
    category: 'CANTEEN',
    description: 'Active evening hangout spot serving milkshakes, burgers, hot fries, and snacks.',
    landmarkLocation: 'Students Activity Centre (SAC) Grounds',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'IIT Bombay Gymkhana Cultural Affairs',
    openHours: '16:00 - 01:00 (Evening / Night)',
    capacityEstimate: 'Student Activity Cafe (~100-150 approx.)',
    capacity: 120,
    active: true,
  },
  {
    id: 'iitb-canteen-brewberrys',
    name: 'Brewberrys The Coffee Bar',
    category: 'CANTEEN',
    description: 'Artisan coffee, bakery items, iced brews, and quiet tables for study sessions.',
    landmarkLocation: 'Adjacent to Central Library, Main Academic Spine',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'IIT Bombay Central Library Amenities',
    openHours: '08:00 - 23:00 (Library Hours)',
    capacityEstimate: 'Coffee Lounge (~60-80 approx.)',
    capacity: 70,
    active: true,
  },
  {
    id: 'iitb-amul-parlour',
    name: 'Amul Ice Cream & Dairy Parlour',
    category: 'CANTEEN',
    description: 'Exclusive dairy outlet offering ice creams, flavored milk, milkshakes, and packaged snacks.',
    landmarkLocation: 'Near Hostel 1 & Campus School Junction',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'IIT Bombay Commercial Establishments',
    openHours: '09:00 - 23:00',
    capacityEstimate: 'Dairy Kiosk & Takeaway (~30-50 approx.)',
    capacity: 40,
    active: true,
  },
];

// Student-Sourced VIT-AP Dining Directory
export const VITAP_LOCATIONS: CampusLocation[] = [
  {
    id: 'vitap-mess-a',
    name: 'North Mess A (Central Dining)',
    category: 'MESS',
    description: 'Central dining complex with multi-cuisine counters for undergraduate students.',
    landmarkLocation: 'North Student Block, Ground Floor',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'VIT-AP Student Dining Guide (Community Sourced)',
    openHours: 'Breakfast (07:30-09:30), Lunch (12:00-14:15), Dinner (19:30-21:30)',
    capacityEstimate: 'Central Dining Complex (~350-450 approx.)',
    capacity: 400,
    active: true,
  },
  {
    id: 'vitap-mess-b',
    name: 'South Mess B (Annex Dining)',
    category: 'MESS',
    description: 'South dining hall featuring vegetarian and regional dining counters.',
    landmarkLocation: 'South Student Block, Near LH-1',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'VIT-AP Student Dining Guide (Community Sourced)',
    openHours: 'Breakfast (07:30-09:30), Lunch (12:00-14:15), Dinner (19:30-21:00)',
    capacityEstimate: 'Medium Dining Hall (~250-350 approx.)',
    capacity: 300,
    active: true,
  },
  {
    id: 'vitap-rock-plaza',
    name: 'Rock Plaza Food Court',
    category: 'CANTEEN',
    description: 'Open-air food court offering quick snacks, fruit juices, and meals.',
    landmarkLocation: 'Central Plaza, Between Academic & Hostel Blocks',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'VIT-AP Student Dining Guide (Community Sourced)',
    openHours: '10:00 - 23:00',
    capacityEstimate: 'Open Plaza Seating (~120-180 approx.)',
    capacity: 150,
    active: true,
  },
  {
    id: 'vitap-academic-bistro',
    name: 'Academic Bistro',
    category: 'CANTEEN',
    description: 'Express counter near lecture halls for sandwiches, rolls, and coffee.',
    landmarkLocation: 'Central Block (CB), Ground Floor',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'VIT-AP Student Dining Guide (Community Sourced)',
    openHours: '08:30 - 18:00 (Class Hours)',
    capacityEstimate: 'Express Counter (~80-120 approx.)',
    capacity: 100,
    active: true,
  },
  {
    id: 'vitap-midnight-fuel',
    name: 'Midnight Fuel Canteen',
    category: 'CANTEEN',
    description: 'Late-evening campus eatery active during study and project hours.',
    landmarkLocation: 'Hostel Avenue Commercial Area',
    verificationStatus: 'UNVERIFIED',
    verificationSource: 'VIT-AP Student Dining Guide (Community Sourced)',
    openHours: '17:00 - 02:00 (Late Night)',
    capacityEstimate: 'Late Night Counter (~100-150 approx.)',
    capacity: 120,
    active: true,
  },
];

export const INITIAL_LOCATIONS: CampusLocation[] =
  CAMPUS_ID === 'vitap' ? VITAP_LOCATIONS : IITB_LOCATIONS;

// Demo / Simulated Seed Reports (only used in demo/dev mode)
const DEFAULT_SEED_REPORTS: Record<string, QueueReport[]> = {
  'iitb-mess-h12-14': [
    {
      reportId: 'rep_seed_101',
      locationId: 'iitb-mess-h12-14',
      reportedWaitMinutes: 14,
      queueLength: 22,
      note: 'Dinner rush, both South & North counters active',
      timestamp: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
    },
    {
      reportId: 'rep_seed_102',
      locationId: 'iitb-mess-h12-14',
      reportedWaitMinutes: 12,
      queueLength: 19,
      note: 'Line moving steadily',
      timestamp: new Date(Date.now() - 7 * 60 * 1000).toISOString(),
    },
    {
      reportId: 'rep_seed_103',
      locationId: 'iitb-mess-h12-14',
      reportedWaitMinutes: 15,
      queueLength: 24,
      note: 'Heavy arrival from Hostel 13',
      timestamp: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
    },
  ],
  'iitb-mess-h15-16': [
    {
      reportId: 'rep_seed_104',
      locationId: 'iitb-mess-h15-16',
      reportedWaitMinutes: 5,
      queueLength: 6,
      note: 'Very short queue right now, swift service',
      timestamp: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
    },
    {
      reportId: 'rep_seed_105',
      locationId: 'iitb-mess-h15-16',
      reportedWaitMinutes: 6,
      queueLength: 8,
      note: 'Veg meal counter clear',
      timestamp: new Date(Date.now() - 8 * 60 * 1000).toISOString(),
    },
    {
      reportId: 'rep_seed_105b',
      locationId: 'iitb-mess-h15-16',
      reportedWaitMinutes: 5.5,
      queueLength: 7,
      note: 'Smooth flow at counter 2',
      timestamp: new Date(Date.now() - 14 * 60 * 1000).toISOString(),
    },
  ],
  'iitb-mess-h2': [
    {
      reportId: 'rep_seed_106',
      locationId: 'iitb-mess-h2',
      reportedWaitMinutes: 8,
      queueLength: 11,
      note: 'Moderate crowd for special dinner',
      timestamp: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    },
  ],
  'iitb-canteen-h3': [
    {
      reportId: 'rep_seed_107',
      locationId: 'iitb-canteen-h3',
      reportedWaitMinutes: 4,
      queueLength: 5,
      note: 'Fast juice token queue',
      timestamp: new Date(Date.now() - 4 * 60 * 1000).toISOString(),
    },
  ],
  'iitb-canteen-lhc': [
    {
      reportId: 'rep_seed_108',
      locationId: 'iitb-canteen-lhc',
      reportedWaitMinutes: 18,
      queueLength: 28,
      note: 'Post-lecture crowd at sandwich counter',
      timestamp: new Date(Date.now() - 9 * 60 * 1000).toISOString(),
    },
  ],
  'iitb-canteen-gulmohar': [
    {
      reportId: 'rep_seed_109',
      locationId: 'iitb-canteen-gulmohar',
      reportedWaitMinutes: 7,
      queueLength: 9,
      note: 'Thali tokens moving fast',
      timestamp: new Date(Date.now() - 14 * 60 * 1000).toISOString(),
    },
  ],
  'iitb-canteen-kresit': [
    {
      reportId: 'rep_seed_110',
      locationId: 'iitb-canteen-kresit',
      reportedWaitMinutes: 3,
      queueLength: 4,
      note: 'Quiet lab break',
      timestamp: new Date(Date.now() - 6 * 60 * 1000).toISOString(),
    },
  ],
  'iitb-cafe-92': [],
  'iitb-canteen-brewberrys': [],
  'iitb-amul-parlour': [],
};

const STORAGE_KEY = `queuesense_${CAMPUS_ID}_observations_v2`;

function loadReportsStore(): Record<string, QueueReport[]> {
  try {
    if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        const store: Record<string, QueueReport[]> = {};
        INITIAL_LOCATIONS.forEach((l) => {
          store[l.id] = parsed[l.id] || DEFAULT_SEED_REPORTS[l.id] || [];
        });
        return store;
      }
    }
  } catch (e) {
    // Ignore fallback
  }
  const initialStore: Record<string, QueueReport[]> = {};
  INITIAL_LOCATIONS.forEach((l) => {
    initialStore[l.id] = [...(DEFAULT_SEED_REPORTS[l.id] || [])];
  });
  return initialStore;
}

function persistReportsStore(store: Record<string, QueueReport[]>): void {
  try {
    if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    }
  } catch (e) {
    // Ignore fallback
  }
}

const mockReports: Record<string, QueueReport[]> = loadReportsStore();

function extractClientIdentifier(r: any): string | null {
  const rawId = r.deviceId || r.clientHash || r.reporterId;
  if (!rawId || typeof rawId !== 'string') return null;
  const trimmed = rawId.trim();
  if (trimmed.length < 8 || trimmed.length > 128) return null;
  return trimmed;
}

export function computeClientEstimate(reports: QueueReport[]): QueueEstimate {
  const now = Date.now();
  const TAU_MS = 15 * 60 * 1000;
  const MAX_AGE_MS = 60 * 60 * 1000;
  const TAPER_START_MS = 50 * 60 * 1000;

  if (!reports || reports.length === 0) {
    return {
      predictedWaitMinutes: null,
      predictedQueueLength: null,
      congestion: 'UNKNOWN',
      confidence: 0,
      confidenceLabel: 'NO DATA',
      confidenceScoreType: 'HEURISTIC_COMPOSITE',
      freshness: 'NO RECENT DATA',
      reportCount: 0,
      recentReportCount: 0,
      distinctDevicesCount: 0,
      newestReportAgeMinutes: null,
      newestReportTimestamp: null,
      disagreementMinutes: 0,
      outliersExcluded: 0,
      evidenceExplanation: 'No recent observations recorded for this outlet.',
      updatedAt: new Date().toISOString(),
    };
  }

  // First pass: Physical plausibility & numerical validation
  const plausible: QueueReport[] = [];
  let physicalOutliers = 0;
  for (const r of reports) {
    const w = Number(r.reportedWaitMinutes);
    const q = Number(r.queueLength);
    if (!Number.isFinite(w) || !Number.isFinite(q) || w < 0 || w > 120 || q < 0 || q > 300) {
      physicalOutliers++;
    } else {
      plausible.push(r);
    }
  }

  // Statistical outlier filtering with Corroborated Surge Detection
  let validReports: QueueReport[] = plausible;
  let statisticalOutliers = 0;

  if (plausible.length >= 5) {
    const waits = plausible.map((r) => Number(r.reportedWaitMinutes)).sort((a, b) => a - b);
    const n = waits.length;
    const medianWait = n % 2 !== 0 ? waits[Math.floor(n / 2)] : (waits[n / 2 - 1] + waits[n / 2]) / 2;
    const absDevs = waits.map((w) => Math.abs(w - medianWait)).sort((a, b) => a - b);
    const mad = n % 2 !== 0 ? absDevs[Math.floor(n / 2)] : (absDevs[n / 2 - 1] + absDevs[n / 2]) / 2;
    const cutoff = Math.max(3.5 * mad, 25.0);

    const normal: QueueReport[] = [];
    const candidateSpikes: QueueReport[] = [];
    const candidateDrops: QueueReport[] = [];

    for (const r of plausible) {
      const w = Number(r.reportedWaitMinutes);
      if (w - medianWait > cutoff) {
        candidateSpikes.push(r);
      } else if (medianWait - w > cutoff) {
        candidateDrops.push(r);
      } else {
        normal.push(r);
      }
    }

    // Corroborate spikes: require at least 2 reports agreeing on elevated condition
    // Strict temporal (within 30m) and distinct device corroboration
    const corroboratedSpikes: QueueReport[] = [];
    for (const r of candidateSpikes) {
      const w = Number(r.reportedWaitMinutes);
      const reportTime = new Date(r.timestamp).getTime();
      const devR = extractClientIdentifier(r);

      if (isNaN(reportTime)) {
        statisticalOutliers++;
        continue;
      }

      // Missing identity is NOT evidence of distinct client instances
      if (!devR) {
        statisticalOutliers++;
        continue;
      }

      let peerMatches = 0;
      for (const peer of candidateSpikes) {
        if (peer === r) continue;
        const peerTime = new Date(peer.timestamp).getTime();
        if (isNaN(peerTime)) continue;

        // Temporal proximity within 30 minutes
        if (Math.abs(reportTime - peerTime) > 30 * 60 * 1000) continue;

        // Distinct device identifiers
        const devPeer = extractClientIdentifier(peer);
        if (!devPeer || devR === devPeer) continue;

        // Value consistency within 20m
        if (Math.abs(w - Number(peer.reportedWaitMinutes)) <= 20.0) {
          peerMatches++;
        }
      }

      if (peerMatches >= 1) {
        corroboratedSpikes.push(r);
      } else {
        statisticalOutliers++;
      }
    }

    // Corroborate drops: require at least 2 reports agreeing on low condition within 30m from distinct devices
    const corroboratedDrops: QueueReport[] = [];
    for (const r of candidateDrops) {
      const w = Number(r.reportedWaitMinutes);
      const reportTime = new Date(r.timestamp).getTime();
      const devR = extractClientIdentifier(r);

      if (isNaN(reportTime)) {
        statisticalOutliers++;
        continue;
      }

      if (!devR) {
        statisticalOutliers++;
        continue;
      }

      let peerMatches = 0;
      for (const peer of candidateDrops) {
        if (peer === r) continue;
        const peerTime = new Date(peer.timestamp).getTime();
        if (isNaN(peerTime)) continue;

        if (Math.abs(reportTime - peerTime) > 30 * 60 * 1000) continue;

        const devPeer = extractClientIdentifier(peer);
        if (!devPeer || devR === devPeer) continue;

        if (Math.abs(w - Number(peer.reportedWaitMinutes)) <= 20.0) {
          peerMatches++;
        }
      }

      if (peerMatches >= 1) {
        corroboratedDrops.push(r);
      } else {
        statisticalOutliers++;
      }
    }

    validReports = [...normal, ...corroboratedSpikes, ...corroboratedDrops];
  }

  const outliersExcluded = physicalOutliers + statisticalOutliers;

  let weightedWaitSum = 0;
  let weightedQueueSum = 0;
  let totalWeight = 0;
  let newestAgeMinutes: number | null = null;
  let newestTimestamp: string | null = null;
  const recentReports: QueueReport[] = [];
  const observedDevices = new Set<string>();
  const timestampsMs: number[] = [];

  for (const r of validReports) {
    const reportTime = new Date(r.timestamp).getTime();
    if (isNaN(reportTime)) continue;

    const ageMs = now - reportTime;

    // Reject future reports (> 30s ahead)
    if (ageMs < -30000) continue;
    const clampedAgeMs = Math.max(0, ageMs);
    const clampedAgeMin = clampedAgeMs / (60 * 1000);

    if (newestAgeMinutes === null || clampedAgeMin < newestAgeMinutes) {
      newestAgeMinutes = clampedAgeMin;
      newestTimestamp = r.timestamp;
    }

    if (clampedAgeMs <= MAX_AGE_MS) {
      const baseWeight = Math.exp(-clampedAgeMs / TAU_MS);
      let weight = baseWeight;
      // Smooth cosine tapering between 50m and 60m
      if (clampedAgeMs > TAPER_START_MS) {
        const taperFraction = (clampedAgeMs - TAPER_START_MS) / (MAX_AGE_MS - TAPER_START_MS);
        const taperWeight = 0.5 * (1.0 + Math.cos(Math.PI * taperFraction));
        weight = baseWeight * taperWeight;
      }

      if (weight > 0.0001) {
        weightedWaitSum += weight * Number(r.reportedWaitMinutes);
        weightedQueueSum += weight * Number(r.queueLength);
        totalWeight += weight;
        recentReports.push(r);

        const devId = extractClientIdentifier(r);
        if (devId) observedDevices.add(devId);
        timestampsMs.push(reportTime);
      }
    }
  }

  if (totalWeight < 0.001 || recentReports.length === 0) {
    return {
      predictedWaitMinutes: null,
      predictedQueueLength: null,
      congestion: 'UNKNOWN',
      confidence: 0,
      confidenceLabel: 'NO DATA',
      confidenceScoreType: 'HEURISTIC_COMPOSITE',
      freshness: 'NO RECENT DATA',
      reportCount: reports.length,
      recentReportCount: 0,
      distinctDevicesCount: 0,
      newestReportAgeMinutes: newestAgeMinutes !== null ? Math.round(newestAgeMinutes) : null,
      newestReportTimestamp: newestTimestamp,
      disagreementMinutes: 0,
      outliersExcluded,
      evidenceExplanation: 'Past reports are over 60 minutes old and no longer reflect current conditions.',
      updatedAt: new Date().toISOString(),
    };
  }

  // Calculate distinct devices count (strictly distinct client instance identifiers)
  const distinctDevicesCount = observedDevices.size;

  const estimatedWait = Math.round((weightedWaitSum / totalWeight) * 10) / 10;
  const estimatedQueue = Math.round(weightedQueueSum / totalWeight);

  let congestion: QueueEstimate['congestion'] = 'LOW';
  if (estimatedWait >= 15.5) congestion = 'VERY_HIGH';
  else if (estimatedWait >= 8.5) congestion = 'HIGH';
  else if (estimatedWait >= 3.5) congestion = 'MODERATE';

  let freshness: QueueEstimate['freshness'] = 'NO RECENT DATA';
  if (newestAgeMinutes !== null) {
    if (newestAgeMinutes <= 7) freshness = 'LIVE';
    else if (newestAgeMinutes <= 20) freshness = 'RECENT';
    else if (newestAgeMinutes <= 60) freshness = 'STALE';
  }

  const waits = recentReports.map((r) => Number(r.reportedWaitMinutes));
  const disagreement = waits.length > 1 ? Math.round((Math.max(...waits) - Math.min(...waits)) * 10) / 10 : 0;

  // Dynamic Evidence-Weighting Normalization (P1.15)
  const volumeRaw = Math.min(recentReports.length / 4, 1.0);
  const recencyRaw = Math.max(0, 1.0 - (newestAgeMinutes || 0) / 25);
  let confidence = 0;

  if (recentReports.length > 1) {
    const agreementRaw = Math.max(0, 1.0 - disagreement / 15);
    confidence = Math.round(Math.min(1.0, 0.45 * volumeRaw + 0.35 * recencyRaw + 0.20 * agreementRaw) * 100) / 100;
  } else {
    // Dynamic renormalization for single report: agreement undefined
    const renormalizedScore = (0.45 * volumeRaw + 0.35 * recencyRaw) / 0.80;
    confidence = Math.round(Math.min(0.40, renormalizedScore * 0.70) * 100) / 100;
  }

  let confidenceLabel: QueueEstimate['confidenceLabel'] = 'VERY LOW';
  if (confidence >= 0.7) confidenceLabel = 'HIGH';
  else if (confidence > 0.4 && recentReports.length >= 2) confidenceLabel = 'MODERATE';
  else if (confidence >= 0.2) confidenceLabel = 'LIMITED';

  const countStr = `${recentReports.length} recent report${recentReports.length === 1 ? '' : 's'}`;
  const ageStr = newestAgeMinutes && newestAgeMinutes >= 1 ? `${Math.round(newestAgeMinutes)}m ago` : 'just now';

  let explanation = '';
  if (confidenceLabel === 'HIGH') {
    explanation = `Strong agreement across ${countStr}; latest report from ${ageStr}.`;
  } else if (confidenceLabel === 'MODERATE') {
    explanation = `Moderate consensus based on ${countStr}; updated ${ageStr}.`;
  } else if (confidenceLabel === 'LIMITED') {
    if (recentReports.length === 1) {
      explanation = `Based on a single observation from ${ageStr}. More reports will improve accuracy.`;
    } else {
      explanation = `Limited evidence based on ${countStr}; updated ${ageStr}.`;
    }
  } else {
    explanation = `Observations are aging (${ageStr}); estimate may not reflect sudden rushes.`;
  }

  return {
    predictedWaitMinutes: estimatedWait,
    predictedQueueLength: estimatedQueue,
    congestion,
    confidence,
    confidenceLabel,
    confidenceScoreType: 'HEURISTIC_COMPOSITE',
    freshness,
    reportCount: reports.length,
    recentReportCount: recentReports.length,
    distinctDevicesCount,
    newestReportAgeMinutes: newestAgeMinutes !== null ? Math.round(newestAgeMinutes * 10) / 10 : null,
    newestReportTimestamp: newestTimestamp,
    disagreementMinutes: disagreement,
    outliersExcluded,
    evidenceExplanation: explanation,
    updatedAt: new Date().toISOString(),
  };
}

// =========================================================================
// Strict Field-Level API Validation Helpers
// =========================================================================

export function isNonEmptyString(val: unknown): val is string {
  return typeof val === 'string' && val.trim().length > 0;
}

export function isValidNumber(val: unknown, min = -Infinity, max = Infinity): val is number {
  return typeof val === 'number' && Number.isFinite(val) && !Number.isNaN(val) && val >= min && val <= max;
}

export function isValidInteger(val: unknown, min = -Infinity, max = Infinity): val is number {
  return isValidNumber(val, min, max) && Number.isInteger(val);
}

export function isValidIsoDate(val: unknown): boolean {
  if (typeof val !== 'string' || !val.trim()) return false;
  const str = val.trim();
  const match = /^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])T([01]\d|2[0-3]):([0-5]\d):([0-5]\d)(?:\.(\d+))?(Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.exec(str);
  if (!match) return false;
  const d = new Date(str);
  if (Number.isNaN(d.getTime())) return false;
  const year = parseInt(match[1], 10);
  const month = parseInt(match[2], 10);
  const day = parseInt(match[3], 10);
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  if (day > daysInMonth) return false;
  return true;
}

export const VALID_CONGESTION_LEVELS = new Set(['LOW', 'MODERATE', 'HIGH', 'VERY_HIGH', 'SURGE', 'UNKNOWN']);
export const VALID_FRESHNESS_STATES = new Set(['LIVE', 'RECENT', 'STALE', 'NO RECENT DATA', 'INSUFFICIENT DATA']);
export const VALID_LOCATION_CATEGORIES = new Set([
  'MESS',
  'CANTEEN',
  'CAFE',
  'RESTAURANT',
  'HOSTEL_MESS',
  'mess',
  'canteen',
  'cafe',
  'restaurant',
  'hostel_mess',
]);
export const VALID_RECOMMENDATION_STATES = new Set(['recommended', 'insufficient_data', 'stale_data', 'no_active_outlets']);
export const VALID_HISTORICAL_STATUSES = new Set(['available', 'insufficient_history']);

/**
 * Validates a QueueEstimate object with strict type and boundary checking.
 */
export function validateQueueEstimate(est: unknown, context = 'estimate'): QueueEstimate {
  if (!est || typeof est !== 'object' || Array.isArray(est)) {
    throw new Error(`Malformed API response: ${context} must be an object`);
  }
  const e = est as Record<string, any>;

  // confidence: number [0, 1]
  if (!isValidNumber(e.confidence, 0, 1)) {
    throw new Error(`Malformed API response: ${context}.confidence must be a number between 0 and 1, got ${e.confidence}`);
  }

  // congestion: valid enum
  if (typeof e.congestion !== 'string' || !VALID_CONGESTION_LEVELS.has(e.congestion)) {
    throw new Error(`Malformed API response: ${context}.congestion has invalid value '${e.congestion}'`);
  }

  // freshness: non-empty string in VALID_FRESHNESS_STATES
  if (typeof e.freshness !== 'string' || !VALID_FRESHNESS_STATES.has(e.freshness)) {
    throw new Error(`Malformed API response: ${context}.freshness has invalid value '${e.freshness}'`);
  }

  // predictedWaitMinutes: null or number [0, 120]
  if (e.predictedWaitMinutes !== null && e.predictedWaitMinutes !== undefined && !isValidNumber(e.predictedWaitMinutes, 0, 120)) {
    throw new Error(`Malformed API response: ${context}.predictedWaitMinutes must be null or number between 0 and 120, got ${e.predictedWaitMinutes}`);
  }

  // predictedQueueLength: null or integer [0, 300]
  if (e.predictedQueueLength !== null && e.predictedQueueLength !== undefined && !isValidInteger(e.predictedQueueLength, 0, 300)) {
    throw new Error(`Malformed API response: ${context}.predictedQueueLength must be null or integer between 0 and 300, got ${e.predictedQueueLength}`);
  }

  // Optional counts
  if (e.reportCount !== undefined && !isValidInteger(e.reportCount, 0)) {
    throw new Error(`Malformed API response: ${context}.reportCount must be a non-negative integer`);
  }
  if (e.recentReportCount !== undefined && !isValidInteger(e.recentReportCount, 0)) {
    throw new Error(`Malformed API response: ${context}.recentReportCount must be a non-negative integer`);
  }

  return e as QueueEstimate;
}

/**
 * Validates a CampusLocation object with strict field-level checking.
 */
export function validateCampusLocation(loc: unknown, context = 'location'): CampusLocation {
  if (!loc || typeof loc !== 'object' || Array.isArray(loc)) {
    throw new Error(`Malformed API response: ${context} must be an object`);
  }
  const l = loc as Record<string, any>;

  if (!isNonEmptyString(l.id)) {
    throw new Error(`Malformed API response: ${context}.id must be a non-empty string`);
  }
  if (!isNonEmptyString(l.name)) {
    throw new Error(`Malformed API response: ${context}.name must be a non-empty string`);
  }
  if (!isNonEmptyString(l.category) || (!VALID_LOCATION_CATEGORIES.has(l.category) && !VALID_LOCATION_CATEGORIES.has(l.category.toUpperCase()))) {
    throw new Error(`Malformed API response: ${context}.category has invalid value '${l.category}'`);
  }
  if (typeof l.active !== 'boolean') {
    throw new Error(`Malformed API response: ${context}.active must be a boolean, got ${typeof l.active}`);
  }
  if (!isNonEmptyString(l.openHours)) {
    throw new Error(`Malformed API response: ${context}.openHours must be a non-empty string`);
  }

  if (l.estimate !== undefined && l.estimate !== null) {
    validateQueueEstimate(l.estimate, `${context}.estimate`);
  }

  return l as CampusLocation;
}

/**
 * Validates a QueueReport object with strict field-level and boundary checking.
 */
export function validateQueueReport(rep: unknown, context = 'report'): QueueReport {
  if (!rep || typeof rep !== 'object' || Array.isArray(rep)) {
    throw new Error(`Malformed API response: ${context} must be an object`);
  }
  const r = rep as Record<string, any>;

  if (!isNonEmptyString(r.reportId) && !isNonEmptyString(r.id)) {
    throw new Error(`Malformed API response: ${context}.reportId must be a non-empty string`);
  }
  // Standardize reportId
  if (!r.reportId && r.id) {
    r.reportId = r.id;
  }

  if (!isNonEmptyString(r.locationId)) {
    throw new Error(`Malformed API response: ${context}.locationId must be a non-empty string`);
  }

  if (!isValidNumber(r.reportedWaitMinutes, 0, 120)) {
    throw new Error(`Malformed API response: ${context}.reportedWaitMinutes must be a number between 0 and 120, got ${r.reportedWaitMinutes}`);
  }
  if (!isValidInteger(r.queueLength, 0, 300)) {
    throw new Error(`Malformed API response: ${context}.queueLength must be an integer between 0 and 300, got ${r.queueLength}`);
  }
  if (!isValidIsoDate(r.timestamp)) {
    throw new Error(`Malformed API response: ${context}.timestamp must be a valid ISO date string, got '${r.timestamp}'`);
  }

  return r as QueueReport;
}

/**
 * Generates a cryptographically secure random idempotency key.
 * Strictly uses crypto.randomUUID() or crypto.getRandomValues().
 * If neither CSPRNG API is available, throws an explicit Error.
 * NEVER falls back to Math.random(), timestamps, or performance.now().
 */
export function generateSecureIdempotencyKey(): string {
  if (typeof crypto !== 'undefined') {
    if (typeof crypto.randomUUID === 'function') {
      try {
        return 'idem_' + crypto.randomUUID();
      } catch {
        // Fall through to getRandomValues
      }
    }
    if (typeof crypto.getRandomValues === 'function') {
      try {
        const bytes = new Uint8Array(16);
        crypto.getRandomValues(bytes);
        const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
        return 'idem_' + hex;
      } catch {
        // Fall through to error throw
      }
    }
  }
  throw new Error('Cryptographically secure randomness is unavailable. Cannot generate a secure idempotency key.');
}

export interface ApiClientConfig {
  apiBaseUrl?: string;
  dataMode?: DataMode;
}

export function createApiClient(config: ApiClientConfig = {}) {
  const getBaseUrl = () => {
    if (config.apiBaseUrl !== undefined) return config.apiBaseUrl;
    if (typeof window !== 'undefined' && (window as any).__QUEUESENSE_API_URL__ !== undefined) {
      return (window as any).__QUEUESENSE_API_URL__;
    }
    return API_BASE_URL;
  };

  const getDataMode = () => {
    if (config.dataMode !== undefined) return config.dataMode;
    if (typeof window !== 'undefined' && (window as any).__QUEUESENSE_DATA_MODE__ !== undefined) {
      return (window as any).__QUEUESENSE_DATA_MODE__;
    }
    return DATA_MODE;
  };

  return {
    isLiveApiConfigured(): boolean {
      const url = getBaseUrl();
      return Boolean(url && (url.startsWith('http') || url.startsWith('/')));
    },

    getDataMode(): DataMode {
      return getDataMode();
    },

    async getLocations(): Promise<{ data: CampusLocation[]; isLive: boolean; isPartial?: boolean }> {
      const mode = getDataMode();
      const baseUrl = getBaseUrl();
      if (this.isLiveApiConfigured()) {
        try {
          const res = await fetch(`${baseUrl}/locations`);
          if (res.ok) {
            const json = await res.json();
            if (!json || typeof json !== 'object' || !Array.isArray(json.data)) {
              throw new Error('Malformed API response: expected locations array');
            }
            // Strict field and type validation on every location item
            for (let i = 0; i < json.data.length; i++) {
              validateCampusLocation(json.data[i], `locations[${i}]`);
              if (!json.data[i].estimate) {
                throw new Error(`Malformed API response: locations[${i}].estimate is required`);
              }
              validateQueueEstimate(json.data[i].estimate, `locations[${i}].estimate`);
            }
            return { data: json.data, isLive: true, isPartial: json.isPartial ?? false };
          }
          if (mode === 'production') {
            throw new Error(`API returned status ${res.status}`);
          }
        } catch (err: any) {
          if (mode === 'production') {
            throw new Error(`Live data temporarily unavailable: ${err.message || 'API unreachable'}`);
          }
          console.warn('API Gateway unreachable, falling back to demo fixtures:', err);
        }
      } else if (mode === 'production') {
        throw new Error('Production mode active: Live API URL (VITE_API_URL) is not configured.');
      }

      // Demo Mode Fixtures
      const locationsWithEstimates = INITIAL_LOCATIONS.map((loc) => ({
        ...loc,
        estimate: computeClientEstimate(mockReports[loc.id] || []),
      }));

      return { data: locationsWithEstimates, isLive: false, isPartial: false };
    },

    async getLocationQueue(locationId: string): Promise<{
      location: CampusLocation;
      estimate: QueueEstimate;
      reports: QueueReport[];
      isLive: boolean;
    }> {
      const mode = getDataMode();
      const baseUrl = getBaseUrl();
      if (this.isLiveApiConfigured()) {
        try {
          const res = await fetch(`${baseUrl}/locations/${locationId}/queue`);
          if (res.ok) {
            const json = await res.json();
            if (
              !json ||
              typeof json !== 'object' ||
              !json.data ||
              typeof json.data !== 'object' ||
              Array.isArray(json.data) ||
              !json.data.location ||
              !json.data.estimate ||
              !Array.isArray(json.data.reports)
            ) {
              throw new Error('Malformed API response: expected queue data object with location, estimate, and reports');
            }
            if (json.data.location.id !== locationId) {
              throw new Error(`Malformed API response: location id mismatch, expected '${locationId}' but got '${json.data.location.id}'`);
            }
            validateCampusLocation(json.data.location, 'queue.location');
            validateQueueEstimate(json.data.estimate, 'queue.estimate');
            for (let i = 0; i < json.data.reports.length; i++) {
              validateQueueReport(json.data.reports[i], `queue.reports[${i}]`);
              if (json.data.reports[i].locationId !== locationId) {
                throw new Error(`Malformed API response: queue.reports[${i}].locationId mismatch, expected '${locationId}' but got '${json.data.reports[i].locationId}'`);
              }
            }
            return { ...json.data, isLive: true };
          }
          if (mode === 'production') {
            throw new Error(`API returned status ${res.status}`);
          }
        } catch (err: any) {
          if (mode === 'production') {
            throw new Error(`Live queue data temporarily unavailable: ${err.message || 'API unreachable'}`);
          }
          console.warn('API Gateway unreachable, falling back to demo fixtures:', err);
        }
      } else if (mode === 'production') {
        throw new Error('Production mode active: Live API URL is not configured.');
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
      const mode = getDataMode();
      const baseUrl = getBaseUrl();

      // Secure Idempotency Key Handling
      // 1. Caller-supplied key: validated against safe format and reused
      // 2. Auto-generated key: generated strictly using CSPRNG; fails safely if crypto is unavailable
      let idempotencyKey = payload.idempotencyKey;
      if (!idempotencyKey) {
        idempotencyKey = generateSecureIdempotencyKey();
      } else {
        if (typeof idempotencyKey !== 'string' || !/^[a-zA-Z0-9_-]{8,64}$/.test(idempotencyKey.trim())) {
          throw new Error('Invalid idempotency key format: must be 8-64 alphanumeric, hyphen, or underscore characters.');
        }
        idempotencyKey = idempotencyKey.trim();
      }

      if (this.isLiveApiConfigured()) {
        try {
          const deviceId = getOrGenerateDeviceId();
          const headers: Record<string, string> = {
            'Content-Type': 'application/json',
            'X-Idempotency-Key': idempotencyKey,
          };
          // Only attach X-Device-ID if a valid, non-fabricated device ID was returned.
          // When null (e.g. storage disabled and crypto unavailable), header is strictly omitted
          // allowing the backend to fall back gracefully to IP-level rate limiting.
          if (deviceId) {
            headers['X-Device-ID'] = deviceId;
          }

          const res = await fetch(`${baseUrl}/locations/${locationId}/reports`, {
            method: 'POST',
            headers,
            body: JSON.stringify({ ...payload, idempotencyKey }),
          });

          if (res.status === 200 || res.status === 201) {
            const json = await res.json();
            if (
              !json ||
              typeof json !== 'object' ||
              !json.data ||
              typeof json.data !== 'object' ||
              Array.isArray(json.data) ||
              !json.data.report ||
              !json.data.updatedEstimate
            ) {
              throw new Error('Malformed API response: expected report and updatedEstimate');
            }
            validateQueueReport(json.data.report, 'submitReport.report');
            if (json.data.report.locationId !== locationId) {
              throw new Error(`Malformed API response: submitted report locationId mismatch, expected '${locationId}' but got '${json.data.report.locationId}'`);
            }
            validateQueueEstimate(json.data.updatedEstimate, 'submitReport.updatedEstimate');
            return { ...json.data, isLive: true };
          }

          const errJson = await res.json().catch(() => ({}));
          if (res.status === 429) {
            throw new Error(
              errJson.error || 'Submission rate limit reached. Please wait a few minutes before reporting again.'
            );
          }
          if (res.status === 500 && errJson.errorCode === 'PERSISTENCE_FAILED') {
            throw new Error('Database persistence failed. Observation could not be durably recorded. Please retry.');
          }
          throw new Error(errJson.error || `Server rejected report with status ${res.status}`);
        } catch (err: any) {
          if (mode === 'production') {
            throw err;
          }
          console.warn('API Gateway unreachable, storing report locally (demo mode):', err);
        }
      } else if (mode === 'production') {
        throw new Error('Production mode active: Cannot submit observation without configured live API endpoint.');
      }

      // Demo fallback submission
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
      persistReportsStore(mockReports);
      const updatedEstimate = computeClientEstimate(mockReports[locationId]);

      return {
        report: newReport,
        updatedEstimate,
        isLive: false,
      };
    },

    async getRecommendations(): Promise<{ data: SmartRecommendation; isLive: boolean }> {
      const mode = getDataMode();
      const baseUrl = getBaseUrl();
      if (this.isLiveApiConfigured()) {
        try {
          const res = await fetch(`${baseUrl}/recommendations`);
          if (res.ok) {
            const json = await res.json();
            if (
              !json ||
              typeof json !== 'object' ||
              !json.data ||
              typeof json.data !== 'object' ||
              Array.isArray(json.data) ||
              typeof json.data.isEligible !== 'boolean' ||
              typeof json.data.reason !== 'string' ||
              !isNonEmptyString(json.data.reason) ||
              !isValidNumber(json.data.confidence, 0, 1)
            ) {
              throw new Error('Malformed API response: expected recommendation object with isEligible, reason, and confidence');
            }

            const rec = json.data;
            if (typeof rec.state !== 'string' || !VALID_RECOMMENDATION_STATES.has(rec.state)) {
              throw new Error(`Malformed API response: recommendations.state has invalid value '${rec.state}'`);
            }

            if (rec.isEligible === true) {
              if (!isNonEmptyString(rec.recommendedLocationId)) {
                throw new Error('Malformed API response: eligible recommendation must have non-empty recommendedLocationId');
              }
              if (!isNonEmptyString(rec.recommendedLocationName)) {
                throw new Error('Malformed API response: eligible recommendation must have non-empty recommendedLocationName');
              }
              if (!isValidNumber(rec.predictedWaitMinutes, 0, 120)) {
                throw new Error(`Malformed API response: eligible recommendation predictedWaitMinutes must be between 0 and 120, got ${rec.predictedWaitMinutes}`);
              }
              if (typeof rec.congestion !== 'string' || !VALID_CONGESTION_LEVELS.has(rec.congestion)) {
                throw new Error(`Malformed API response: eligible recommendation congestion has invalid value '${rec.congestion}'`);
              }
            } else {
              if (rec.recommendedLocationId !== null && rec.recommendedLocationId !== undefined && !isNonEmptyString(rec.recommendedLocationId)) {
                throw new Error('Malformed API response: ineligible recommendation recommendedLocationId must be null or non-empty string');
              }
              if (rec.predictedWaitMinutes !== null && rec.predictedWaitMinutes !== undefined && !isValidNumber(rec.predictedWaitMinutes, 0, 120)) {
                throw new Error(`Malformed API response: ineligible recommendation predictedWaitMinutes must be null or number between 0 and 120, got ${rec.predictedWaitMinutes}`);
              }
            }

            return { data: rec, isLive: true };
          }
          if (mode === 'production') {
            throw new Error(`API returned status ${res.status}`);
          }
        } catch (err: any) {
          if (mode === 'production') {
            throw new Error(`Live recommendations temporarily unavailable: ${err.message || 'API unreachable'}`);
          }
          console.warn('API Gateway unreachable, calculating recommendations locally:', err);
        }
      } else if (mode === 'production') {
        throw new Error('Production mode active: Live API URL is not configured.');
      }

      // Cold-Start Protected Demo Recommendation Calculation
      const candidates = INITIAL_LOCATIONS.map((loc) => ({
        ...loc,
        estimate: computeClientEstimate(mockReports[loc.id] || []),
      }));

      const hasActiveLocations = candidates.some((c) => c.active);
      const hasFreshReports = candidates.some(
        (c) => c.estimate && ['LIVE', 'RECENT'].includes(c.estimate.freshness)
      );

      const VERIFIED_STATUSES = new Set([
        'VERIFIED',
        'VERIFIED_CAMPUS_DIRECTORY',
      ]);

      // Must be active, verified, have at least 3 fresh reports, >= 50% confidence, and >= 2 distinct devices
      const eligible = candidates.filter((c) => {
        if (!c.active) return false;
        if (!c.verificationStatus || !VERIFIED_STATUSES.has(c.verificationStatus)) return false;
        if (!c.estimate) return false;
        if (c.estimate.predictedWaitMinutes === null) return false;
        if (!['LIVE', 'RECENT'].includes(c.estimate.freshness)) return false;
        if (c.estimate.recentReportCount < 3) return false;
        if (c.estimate.confidence < 0.50) return false;
        const devCount = c.estimate.distinctDevicesCount;
        if (typeof devCount !== 'number' || isNaN(devCount) || devCount < 2) return false;
        return true;
      });

      if (eligible.length === 0) {
        let state: SmartRecommendation['state'] = 'insufficient_data';
        let reason =
          'Not enough recent queue reports across campus to make a reliable recommendation yet. At least 3 fresh observations (within 20 minutes), 50%+ confidence, and corroboration from multiple distinct client devices are required.';

        if (!hasActiveLocations) {
          state = 'no_active_outlets';
          reason = 'No campus food outlets are currently open or active.';
        } else if (!hasFreshReports) {
          state = 'stale_data';
          reason =
            'Not enough recent queue reports across campus to make a reliable recommendation yet. All campus queue observations are over 20 minutes old and considered stale. Fresh student reports are needed before making a recommendation.';
        }

        return {
          data: {
            recommendedLocationId: null,
            recommendedLocationName: null,
            reason,
            isEligible: false,
            state,
            minReportsRequired: 3,
            minConfidenceRequired: 0.50,
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
          reason: `Shortest estimated wait (~${wEst.predictedWaitMinutes} min) with ${wEst.confidenceLabel.toLowerCase()} evidence; verified by ${wEst.recentReportCount} fresh reports updated ${ageText}.`,
          isEligible: true,
          state: 'recommended',
          candidateCount: candidates.length,
          eligibleCount: eligible.length,
        },
        isLive: false,
      };
    },

    async getHistorical(locationId: string): Promise<{ data: HistoricalData; isLive: boolean }> {
      const mode = getDataMode();
      const baseUrl = getBaseUrl();
      if (this.isLiveApiConfigured()) {
        try {
          const res = await fetch(`${baseUrl}/locations/${locationId}/historical`);
          if (res.ok) {
            const json = await res.json();
            if (
              !json ||
              typeof json !== 'object' ||
              !json.data ||
              typeof json.data !== 'object' ||
              Array.isArray(json.data) ||
              !isNonEmptyString(json.data.locationId) ||
              typeof json.data.status !== 'string' ||
              !VALID_HISTORICAL_STATUSES.has(json.data.status) ||
              !Array.isArray(json.data.hourlyTrends)
            ) {
              throw new Error('Malformed API response: expected historical data object with hourly trends');
            }

            if (json.data.locationId !== locationId) {
              throw new Error(`Malformed API response: historical locationId mismatch, expected '${locationId}' but got '${json.data.locationId}'`);
            }

            const hData = json.data;
            if (!isValidInteger(hData.totalObservations, 0)) {
              throw new Error('Malformed API response: historical totalObservations must be a non-negative integer');
            }

            for (let i = 0; i < hData.hourlyTrends.length; i++) {
              const trend = hData.hourlyTrends[i];
              if (!trend || typeof trend !== 'object' || Array.isArray(trend)) {
                throw new Error(`Malformed API response: hourlyTrends[${i}] must be an object`);
              }
              if (!isValidInteger(trend.hour, 0, 23)) {
                throw new Error(`Malformed API response: hourlyTrends[${i}].hour must be an integer between 0 and 23, got ${trend.hour}`);
              }
              if (!isNonEmptyString(trend.label)) {
                throw new Error(`Malformed API response: hourlyTrends[${i}].label must be a non-empty string`);
              }
              const wait = trend.averageWaitMinutes !== undefined ? trend.averageWaitMinutes : trend.historicalAverageWaitMinutes;
              if (wait !== null && wait !== undefined && !isValidNumber(wait, 0, 120)) {
                throw new Error(`Malformed API response: hourlyTrends[${i}].averageWaitMinutes must be null or number between 0 and 120, got ${wait}`);
              }
              const qLen = trend.averageQueueLength !== undefined ? trend.averageQueueLength : trend.historicalAverageQueueLength;
              if (qLen !== null && qLen !== undefined && !isValidNumber(qLen, 0, 300)) {
                throw new Error(`Malformed API response: hourlyTrends[${i}].averageQueueLength must be null or number between 0 and 300, got ${qLen}`);
              }
              const count = trend.observationCount !== undefined ? trend.observationCount : trend.sampleCount;
              if (count !== undefined && !isValidInteger(count, 0)) {
                throw new Error(`Malformed API response: hourlyTrends[${i}].observationCount must be a non-negative integer`);
              }
            }

            const validatePeakHour = (peak: any, fieldName: string) => {
              if (peak === null || peak === undefined) return;
              if (typeof peak !== 'object' || Array.isArray(peak)) {
                throw new Error(`Malformed API response: ${fieldName} must be an object or null`);
              }
              if (!isValidInteger(peak.hour, 0, 23)) {
                throw new Error(`Malformed API response: ${fieldName}.hour must be an integer between 0 and 23, got ${peak.hour}`);
              }
              if (!isNonEmptyString(peak.label)) {
                throw new Error(`Malformed API response: ${fieldName}.label must be a non-empty string`);
              }
              const wait = peak.averageWaitMinutes !== undefined ? peak.averageWaitMinutes : peak.historicalAverageWaitMinutes;
              if (wait === null || wait === undefined || !isValidNumber(wait, 0, 120)) {
                throw new Error(`Malformed API response: ${fieldName}.averageWaitMinutes must be a number between 0 and 120, got ${wait}`);
              }
              const count = peak.sampleCount !== undefined ? peak.sampleCount : peak.observationCount;
              if (count !== undefined && !isValidInteger(count, 0)) {
                throw new Error(`Malformed API response: ${fieldName}.sampleCount must be a non-negative integer`);
              }
            };

            validatePeakHour(hData.busiestHour, 'busiestHour');
            validatePeakHour(hData.quietestHour, 'quietestHour');

            return { data: json.data, isLive: true };
          }
          if (mode === 'production') {
            throw new Error(`Historical API returned status ${res.status}`);
          }
        } catch (err: any) {
          if (mode === 'production') {
            throw new Error(`Historical queue patterns temporarily unavailable: ${err.message || 'API unreachable'}`);
          }
        }
      } else if (mode === 'production') {
        throw new Error('Production mode active: Live API URL is not configured.');
      }

      // Demo Mode Simulated Historical Curve
      const hourlyTrends = Array.from({ length: 24 }, (_, h) => {
        // Meal rush simulation: lunch (12-14) and dinner (19-21)
        let avgWait: number | null = null;
        let count = 0;
        if (h >= 8 && h <= 22) {
          if (h >= 12 && h <= 14) {
            avgWait = Math.round((14 + Math.sin(h) * 4) * 10) / 10;
            count = 12;
          } else if (h >= 19 && h <= 21) {
            avgWait = Math.round((16 + Math.cos(h) * 5) * 10) / 10;
            count = 16;
          } else {
            avgWait = Math.round((4 + (h % 3)) * 10) / 10;
            count = 6;
          }
        }
        return {
          hour: h,
          label: `${h.toString().padStart(2, '0')}:00`,
          historicalAverageWaitMinutes: avgWait,
          historicalAverageQueueLength: avgWait ? Math.round(avgWait * 1.5) : null,
          sampleCount: count,
          averageWaitMinutes: avgWait,
          averageQueueLength: avgWait ? Math.round(avgWait * 1.5) : null,
          observationCount: count,
        };
      });

      return {
        data: {
          locationId,
          status: 'available',
          timezone: 'Asia/Kolkata',
          metricType: 'HISTORICAL_AVERAGES',
          minSamplesRequiredForPeak: 3,
          totalObservations: 42,
          disclaimer: 'Historical averages reflect empirical crowdsourced observations in Indian Standard Time (IST, UTC+05:30) and should not be treated as deterministic real-time forecasts.',
          hourlyTrends,
          busiestHour: {
            hour: 20,
            label: '20:00',
            historicalAverageWaitMinutes: 18.5,
            averageWaitMinutes: 18.5,
            sampleCount: 16,
          },
          quietestHour: {
            hour: 16,
            label: '16:00',
            historicalAverageWaitMinutes: 3.5,
            averageWaitMinutes: 3.5,
            sampleCount: 6,
          },
          summary: 'Demo historical average curve aggregated from 42 campus observations over past 14 days (Campus Timezone: Asia/Kolkata).',
        },
        isLive: false,
      };
    },

    async getAdminReports(bearerToken?: string): Promise<{
      reports: QueueReport[];
      isLive: boolean;
      metadata?: {
        totalReportsReturned?: number;
        outlierCount?: number;
        isPartial?: boolean;
        isTruncated?: boolean;
        retrievalSource?: string;
        operatorIdentity?: string | null;
      };
    }> {
      const mode = getDataMode();
      const baseUrl = getBaseUrl();
      let token = bearerToken || '';
      if (!token) {
        try {
          if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
            token = localStorage.getItem('queuesense_admin_token') || '';
          }
        } catch {
          // Graceful fallback if storage throws SecurityError
        }
      }

      if (this.isLiveApiConfigured()) {
        if (!token || !token.trim()) {
          throw new Error('UNAUTHORIZED');
        }
        try {
          const res = await fetch(`${baseUrl}/admin/reports`, {
            headers: {
              Authorization: `Bearer ${token.trim()}`,
            },
          });
          if (res.ok) {
            const json = await res.json();
            if (
              !json ||
              typeof json !== 'object' ||
              !json.data ||
              typeof json.data !== 'object' ||
              Array.isArray(json.data) ||
              !Array.isArray(json.data.reports)
            ) {
              throw new Error('Malformed API response: expected admin reports array');
            }
            for (let i = 0; i < json.data.reports.length; i++) {
              validateQueueReport(json.data.reports[i], `adminReports[${i}]`);
            }
            return {
              reports: json.data.reports,
              isLive: true,
              metadata: {
                totalReportsReturned: json.data.totalReportsReturned ?? json.data.reports.length,
                outlierCount: json.data.outlierCount ?? 0,
                isPartial: json.data.isPartial ?? false,
                isTruncated: json.data.isTruncated ?? false,
                retrievalSource: json.data.retrievalSource,
                operatorIdentity: json.data.operatorIdentity,
              },
            };
          }
          if (res.status === 401 || res.status === 403) {
            throw new Error('UNAUTHORIZED');
          }
          if (mode === 'production') {
            throw new Error(`Admin audit API returned status ${res.status}`);
          }
        } catch (err: any) {
          if (err.message === 'UNAUTHORIZED' || mode === 'production') {
            throw err;
          }
          console.warn('API Gateway unreachable, returning demo admin audit feed:', err);
        }
      } else if (mode === 'production') {
        throw new Error('Production mode active: Live API URL is not configured.');
      }

      const allReports: QueueReport[] = [];
      Object.values(mockReports).forEach((reps) => {
        allReports.push(...reps);
      });
      allReports.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

      return {
        reports: allReports,
        isLive: false,
        metadata: {
          totalReportsReturned: allReports.length,
          outlierCount: 0,
          isPartial: false,
          isTruncated: false,
          retrievalSource: 'LOCAL_FIXTURES',
          operatorIdentity: 'demo-local',
        },
      };
    },
  };
}

export const api = createApiClient();
