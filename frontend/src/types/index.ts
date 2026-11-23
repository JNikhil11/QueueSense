export type CongestionLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH' | 'UNKNOWN';

export type FreshnessState = 'LIVE' | 'RECENT' | 'STALE' | 'NO RECENT DATA';

export type ConfidenceLabel = 'HIGH' | 'MODERATE' | 'LIMITED' | 'VERY LOW' | 'NO DATA';

export interface QueueEstimate {
  predictedWaitMinutes: number | null;
  predictedQueueLength: number | null;
  congestion: CongestionLevel;
  confidence: number;
  confidenceLabel: ConfidenceLabel;
  freshness: FreshnessState;
  reportCount: number;
  recentReportCount: number;
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
  verificationStatus: 'VERIFIED_CAMPUS_DIRECTORY' | 'COMMUNITY_LISTING';
  verificationSource: string;
  openHours: string;
  capacity: number;
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
  candidateCount: number;
  eligibleCount: number;
}

export interface ReportSubmissionPayload {
  reportedWaitMinutes: number;
  queueLength: number;
  note?: string;
}

