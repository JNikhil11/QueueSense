import React from 'react';
import { SmartRecommendation } from '../types';
import { CongestionBadge, ConfidenceMeter } from './StatusBadge';
import { Sparkles, ArrowRight, AlertCircle, Clock } from 'lucide-react';

interface RecommendationBannerProps {
  recommendation: SmartRecommendation | null;
  onSelectOutlet: (outletId: string) => void;
  onOpenReportModal: (outletId?: string) => void;
}

export const RecommendationBanner: React.FC<RecommendationBannerProps> = ({
  recommendation,
  onSelectOutlet,
  onOpenReportModal,
}) => {
  if (!recommendation) return null;

  if (!recommendation.isEligible || !recommendation.recommendedLocationId) {
    return (
      <div className="rounded-2xl bg-surface-card/60 border border-surface-border p-4 sm:p-5 my-6 flex items-start gap-3.5">
        <div className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 shrink-0 mt-0.5">
          <AlertCircle className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase font-mono tracking-wider font-semibold text-amber-400">
              No High-Confidence Recommendation
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-300">
            {recommendation.reason}
          </p>
        </div>
        <button
          onClick={() => onOpenReportModal()}
          className="shrink-0 hidden sm:flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg bg-surface-elevated hover:bg-surface-border border border-surface-border text-slate-200 transition-colors"
        >
          <span>Be the first to report</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="relative rounded-2xl overflow-hidden bg-gradient-to-r from-surface-card via-surface-elevated to-surface-card border border-neon-green/40 shadow-glow-green/20 p-5 sm:p-6 my-6">
      {/* Decorative ambient gradient */}
      <div className="absolute -top-12 -right-12 w-48 h-48 bg-neon-green/10 rounded-full blur-3xl pointer-events-none" />

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-5 relative z-10">
        <div className="space-y-2 max-w-xl">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-neon-green/20 text-neon-green border border-neon-green/40 text-xs font-semibold uppercase tracking-wider">
              <Sparkles className="w-3 h-3" />
              Smart Recommendation
            </span>
            {recommendation.congestion && (
              <CongestionBadge level={recommendation.congestion} />
            )}
          </div>

          <h2 className="font-display text-xl sm:text-2xl font-bold text-white tracking-tight">
            {recommendation.recommendedLocationName}
          </h2>

          <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
            {recommendation.reason}
          </p>

          {recommendation.confidence !== undefined && recommendation.confidenceLabel && (
            <div className="pt-1 flex items-center gap-3">
              <span className="text-xs text-slate-400">Evidence Quality:</span>
              <ConfidenceMeter
                confidence={recommendation.confidence}
                label={recommendation.confidenceLabel}
              />
            </div>
          )}
        </div>

        {/* Highlighted Metric & CTA */}
        <div className="flex items-center md:flex-col md:items-end justify-between border-t md:border-t-0 pt-4 md:pt-0 border-surface-border/60 gap-4">
          <div className="text-left md:text-right">
            <div className="text-[11px] uppercase tracking-wider text-slate-400 font-mono">
              Estimated Wait
            </div>
            <div className="font-mono text-3xl sm:text-4xl font-extrabold text-neon-green flex items-baseline md:justify-end gap-1">
              <Clock className="w-5 h-5 text-neon-green self-center hidden sm:block" />
              ~{recommendation.predictedWaitMinutes}
              <span className="text-sm font-sans font-normal text-slate-400">min</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onSelectOutlet(recommendation.recommendedLocationId!)}
              className="flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg bg-neon-green text-slate-950 hover:bg-[#2fe07c] shadow-glow-green transition-all"
            >
              <span>View Outlet</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
