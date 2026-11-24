import React from 'react';
import { SmartRecommendation, AppSyncState } from '../types';
import { CongestionBadge, ConfidenceMeter } from './StatusBadge';
import { ArrowRight, AlertTriangle, Compass } from 'lucide-react';

interface RecommendationBannerProps {
  recommendation: SmartRecommendation | null;
  syncState?: AppSyncState;
  lastSuccessfulSyncStr?: string | null;
  onSelectOutlet: (outletId: string) => void;
  onOpenReportModal: (outletId?: string) => void;
}

export const RecommendationBanner: React.FC<RecommendationBannerProps> = ({
  recommendation,
  syncState,
  lastSuccessfulSyncStr,
  onSelectOutlet,
  onOpenReportModal,
}) => {
  if (!recommendation) return null;

  const isStale = syncState === 'STALE';

  // Honest Sparse-Data Fallback
  if (!recommendation.isEligible || !recommendation.recommendedLocationId) {
    return (
      <div className="rounded-2xl glass-panel p-5 sm:p-6 my-6 border-white/10 glass-specular-edge transition-all">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <div className="p-2.5 rounded-xl bg-[#FFA028]/10 border border-[#FFA028]/25 text-[#FFA028] shrink-0 mt-0.5">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono uppercase tracking-wider font-semibold text-[#FFA028]">
                  Sparse Observation Window
                </span>
                {isStale && (
                  <span className="text-[10px] uppercase font-mono font-bold tracking-wider px-2 py-0.5 rounded-full bg-[#FFA028]/20 text-[#FFA028] border border-[#FFA028]/40">
                    Sync Offline
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-[#8E9E93] leading-relaxed max-w-2xl">
                {isStale
                  ? `Server synchronization is currently offline. Retaining previous queue evaluation from ${lastSuccessfulSyncStr || 'earlier'}. ${recommendation.reason}`
                  : recommendation.reason}
              </p>
            </div>
          </div>

          <button
            onClick={() => onOpenReportModal()}
            className="shrink-0 flex items-center gap-2 px-4 py-2.5 text-xs font-mono uppercase tracking-wider rounded-xl btn-glass hover:border-[#39FF14]/40 min-h-[44px]"
            aria-label="Be the first to submit a queue observation"
          >
            <span>Be first to submit</span>
            <ArrowRight className="w-3.5 h-3.5 text-[#39FF14]" />
          </button>
        </div>
      </div>
    );
  }

  // Active Centerpiece Recommendation
  return (
    <div className={`recommendation-card relative rounded-3xl overflow-hidden glass-panel-centerpiece p-6 sm:p-8 my-6 transition-all duration-300 ${
      isStale ? 'border-[#FFA028]/50 shadow-[0_16px_45px_-10px_rgba(0,0,0,0.8),0_0_35px_-5px_rgba(255,160,40,0.25)]' : ''
    }`}>
      {/* Specular Top Reflection Accent Line */}
      <div className={`absolute inset-x-8 top-0 h-[1.5px] bg-gradient-to-r from-transparent pointer-events-none ${
        isStale ? 'via-[#FFA028]/80' : 'via-[#39FF14]/70'
      } to-transparent`} />

      {/* Internal Atmospheric Light Cone */}
      <div className={`absolute -top-24 -right-24 w-80 h-80 rounded-full blur-3xl pointer-events-none ${
        isStale ? 'bg-gradient-to-br from-[#FFA028]/20 via-[#FFA028]/5 to-transparent' : 'bg-gradient-to-br from-[#39FF14]/20 via-[#7DF9FF]/10 to-transparent'
      }`} />
      <div className={`absolute -bottom-24 -left-24 w-80 h-80 rounded-full blur-3xl pointer-events-none ${
        isStale ? 'bg-gradient-to-tr from-[#FFA028]/15 to-transparent' : 'bg-gradient-to-tr from-[#39FF14]/15 to-transparent'
      }`} />

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
        {/* Left Information Stack */}
        <div className="space-y-3 max-w-xl">
          <div className="flex items-center gap-2.5 flex-wrap">
            {isStale ? (
              <span
                data-testid="stale-recommendation-badge"
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#FFA028]/25 text-[#FFA028] border border-[#FFA028]/50 text-xs font-mono font-bold uppercase tracking-wider shadow-[0_0_15px_rgba(255,160,40,0.35)]"
              >
                <AlertTriangle className="w-3.5 h-3.5 text-[#FFA028]" />
                Cached Recommendation (Stale Data)
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#39FF14]/20 text-[#39FF14] border border-[#39FF14]/50 text-xs font-mono font-bold uppercase tracking-wider shadow-[0_0_15px_rgba(57,255,20,0.35)]">
                <Compass className="w-3.5 h-3.5 animate-spin text-[#39FF14]" style={{ animationDuration: '8s' }} />
                Recommended Right Now
              </span>
            )}
            {recommendation.congestion && (
              <CongestionBadge level={recommendation.congestion} />
            )}
          </div>

          <div>
            <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              {recommendation.recommendedLocationName}
            </h2>
            <p className="text-xs sm:text-sm text-[#8E9E93] mt-1.5 leading-relaxed">
              {isStale
                ? `WARNING: Live campus sync failed. Recommendation is based on cached observations from ${lastSuccessfulSyncStr || 'earlier'} and may not reflect current surge conditions.`
                : recommendation.reason}
            </p>
          </div>

          {recommendation.confidence !== undefined && recommendation.confidenceLabel && (
            <div className="pt-1 flex items-center gap-3">
              <span className="text-xs font-mono text-[#8E9E93] uppercase tracking-wider">
                Evidence Reliability:
              </span>
              <ConfidenceMeter
                confidence={recommendation.confidence}
                label={recommendation.confidenceLabel}
              />
            </div>
          )}
        </div>

        {/* Right Wait Metric & Action */}
        <div className="flex items-center md:flex-col md:items-end justify-between border-t md:border-t-0 pt-4 md:pt-0 border-white/10 gap-5 shrink-0">
          <div className="text-left md:text-right">
            <div className="text-[10px] uppercase tracking-widest text-[#8E9E93] font-mono">
              {isStale ? 'Cached Wait (Stale)' : 'Calculated Wait'}
            </div>
            <div className={`font-mono text-4xl sm:text-5xl font-extrabold tracking-tight flex items-baseline md:justify-end gap-1.5 mt-0.5 ${
              isStale ? 'text-[#FFA028]' : 'text-[#39FF14]'
            }`}>
              ~{recommendation.predictedWaitMinutes}
              <span className="text-sm font-sans font-medium text-[#8E9E93]">min</span>
            </div>
          </div>

          <button
            onClick={() => onSelectOutlet(recommendation.recommendedLocationId!)}
            className={`flex items-center gap-2 px-5 py-3 text-xs sm:text-sm font-semibold rounded-xl transition-all min-h-[44px] ${
              isStale
                ? 'bg-[#FFA028] text-black hover:bg-[#e68f20] font-bold shadow-[0_0_20px_rgba(255,160,40,0.35)]'
                : 'btn-electric'
            }`}
            aria-label={`View details for recommended outlet ${recommendation.recommendedLocationName}`}
          >
            <span>View Outlet</span>
            <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
          </button>
        </div>
      </div>
    </div>
  );
};
