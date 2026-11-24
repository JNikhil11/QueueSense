export type CongestionLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH' | 'UNKNOWN';

export type FreshnessState = 'LIVE' | 'RECENT' | 'STALE' | 'NO RECENT DATA';

export type ConfidenceLabel = 'HIGH' | 'MODERATE' | 'LIMITED' | 'VERY LOW' | 'NO DATA' | 'INSUFFICIENT DATA';

export type DataMode = 'production' | 'demo' | 'development';

export interface QueueEstimate {
  predictedWaitMinutes: number | null;
  predictedQueueLength: number | null;
  congestion: CongestionLevel;
  confidence: number;
  confidenceLabel: ConfidenceLabel;
  confidenceScoreType?: string;
  freshness: FreshnessState;
  reportCount: number;
  recentReportCount: number;
  distinctDevicesCount?: number;
  newestReportAgeMinutes: number | null;
  newestReportTimestamp: string | null;
  disagreementMinutes: number;
  outliersExcluded: number;
  evidenceExplanation: string;
  updatedAt: string;
}

export interface CampusLocation {
  id: string;
  name: string;
  category: 'MESS' | 'CANTEEN';
  description: string;
  landmarkLocation: string;
  verificationStatus: 'VERIFIED' | 'VERIFIED_CAMPUS_DIRECTORY' | 'UNVERIFIED' | string;
  sourceType?: string;
  sourceAttribution?: string;
  verificationSource?: string;
  openHours: string;
  capacity?: number;
  capacityEstimate?: string;
  active: boolean;
  estimate?: QueueEstimate;
}

export interface QueueReport {
  reportId: string;
  locationId: string;
  reportedWaitMinutes: number;
  queueLength: number;
  note?: string;
  timestamp: string;
  isOutlier?: boolean;
}

export interface SmartRecommendation {
  recommendedLocationId: string | null;
  recommendedLocationName: string | null;
  predictedWaitMinutes?: number;
  congestion?: CongestionLevel;
  confidence?: number;
  confidenceLabel?: ConfidenceLabel;
  reason: string;
  isEligible: boolean;
  state?: 'recommended' | 'insufficient_data' | 'stale_data' | 'no_active_outlets';
  minReportsRequired?: number;
  minConfidenceRequired?: number;
  candidateCount: number;
  eligibleCount: number;
}

export interface ReportSubmissionPayload {
  reportedWaitMinutes: number;
  queueLength: number;
  note?: string;
  idempotencyKey?: string;
}

export interface HistoricalHourlyBucket {
  hour: number;
  label: string;
  historicalAverageWaitMinutes?: number | null;
  historicalAverageQueueLength?: number | null;
  sampleCount?: number;
  averageWaitMinutes: number | null;
  averageQueueLength: number | null;
  observationCount: number;
}

export interface HistoricalData {
  locationId: string;
  locationName?: string;
  status: 'available' | 'insufficient_history';
  timezone?: string;
  metricType?: string;
  minSamplesRequiredForPeak?: number;
  disclaimer?: string;
  totalObservations: number;
  hourlyTrends: HistoricalHourlyBucket[];
  busiestHour: {
    hour: number;
    label: string;
    historicalAverageWaitMinutes?: number;
    averageWaitMinutes: number;
    sampleCount?: number;
  } | null;
  quietestHour: {
    hour: number;
    label: string;
    historicalAverageWaitMinutes?: number;
    averageWaitMinutes: number;
    sampleCount?: number;
  } | null;
  summary: string;
}
