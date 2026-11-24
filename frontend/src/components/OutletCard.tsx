import React from 'react';
import { CampusLocation } from '../types';
import { CongestionBadge, FreshnessBadge, ConfidenceMeter } from './StatusBadge';
import { Clock, Users, ArrowUpRight, Plus, AlertCircle, MapPin, CheckCircle2 } from 'lucide-react';

interface OutletCardProps {
  location: CampusLocation;
  onSelect: (id: string) => void;
  onReport: (id: string) => void;
}

export const OutletCard: React.FC<OutletCardProps> = ({ location, onSelect, onReport }) => {
  const est = location.estimate;
  const hasWait = est?.predictedWaitMinutes !== null && est?.predictedWaitMinutes !== undefined;
  const isNoData = !est || est.freshness === 'NO RECENT DATA' || !hasWait;

  const newestAge = est?.newestReportAgeMinutes;
  const newestAgeStr =
    newestAge !== null && newestAge !== undefined
      ? newestAge <= 1
        ? 'just now'
        : `${Math.round(newestAge)}m ago`
      : null;

  return (
    <div className="outlet-card group relative rounded-3xl glass-panel glass-card-ambient p-5 sm:p-6 flex flex-col justify-between glass-specular-edge border-[#39FF14]/30 hover:border-[#39FF14]/60 min-w-0">
      {/* Top Meta Header */}
      <div>
        <div className="flex items-start justify-between gap-3 mb-2.5">
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <span
              className={`text-[10px] uppercase font-mono font-bold tracking-wider px-2.5 py-0.5 rounded-full border shrink-0 ${
                location.category === 'MESS'
                  ? 'bg-[#7DF9FF]/10 text-[#7DF9FF] border-[#7DF9FF]/30'
                  : 'bg-[#39FF14]/10 text-[#39FF14] border-[#39FF14]/30'
              }`}
            >
              {location.category}
            </span>
            {location.verificationStatus === 'STUDENT_SOURCED' && (
              <span
                className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/[0.04] text-[#8E9E93] border border-white/10 shrink-0"
                title={location.verificationSource}
              >
                <CheckCircle2 className="w-3 h-3 text-[#39FF14] shrink-0" />
                <span>Student Sourced</span>
              </span>
            )}
            {location.verificationStatus === 'COMMUNITY_LISTING' && (
              <span
                className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/[0.04] text-[#8E9E93] border border-white/10 shrink-0"
                title={location.verificationSource}
              >
                <span>Community Listing</span>
              </span>
            )}
            {est && <FreshnessBadge state={est.freshness} />}
          </div>
          {est && (
            <div className="shrink-0">
              <CongestionBadge level={est.congestion} />
            </div>
          )}
        </div>

        {/* Title & Landmark */}
        <h3 className="font-display text-xl font-bold text-white group-hover:text-[#39FF14] transition-colors tracking-tight line-clamp-1">
          {location.name}
        </h3>
        {location.landmarkLocation && (
          <div className="flex items-center gap-1.5 text-[11px] text-[#7DF9FF]/80 font-mono mt-1">
            <MapPin className="w-3 h-3 text-[#7DF9FF] shrink-0" />
            <span className="line-clamp-1">{location.landmarkLocation}</span>
          </div>
        )}
        <p className="text-xs text-[#8E9E93] mt-1.5 line-clamp-2 leading-relaxed">
          {location.description}
        </p>
      </div>

      {/* Main Aggregated Estimate Box */}
      <div className="my-5 p-4 rounded-2xl bg-[#090E0B]/70 border border-white/[0.06] backdrop-blur-md">
        <div className="flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase font-mono tracking-widest text-[#8E9E93] flex items-center gap-1.5">
              <span>Aggregated Wait</span>
              <span className="text-[9px] text-[#5A695F] font-normal">(time-decayed)</span>
            </div>
            <div className="flex items-baseline gap-1 mt-1">
              {isNoData ? (
                <div className="font-mono text-2xl font-bold text-[#5A695F]">
                  --
                  <span className="text-xs font-sans text-[#5A695F] ml-1.5 font-normal">
                    (awaiting reports)
                  </span>
                </div>
              ) : (
                <div
                  className={`font-mono text-3xl sm:text-4xl font-extrabold tracking-tight flex items-baseline gap-1.5 ${
                    est.congestion === 'LOW'
                      ? 'text-[#39FF14] drop-shadow-[0_0_12px_rgba(57,255,20,0.4)]'
                      : est.congestion === 'MODERATE'
                      ? 'text-[#7DF9FF] drop-shadow-[0_0_12px_rgba(125,249,255,0.4)]'
                      : est.congestion === 'HIGH'
                      ? 'text-[#FFA028]'
                      : 'text-[#FF4A60] drop-shadow-[0_0_12px_rgba(204,22,45,0.5)]'
                  }`}
                >
                  ~{est.predictedWaitMinutes}
                  <span className="text-xs font-sans font-normal text-[#8E9E93]">min</span>
                </div>
              )}
            </div>
          </div>

          <div className="text-right">
            <div className="text-[10px] uppercase font-mono tracking-widest text-[#8E9E93]">
              Queue Ahead
            </div>
            <div className="font-mono text-lg font-bold text-[#F4F7F5] mt-1">
              {isNoData || est.predictedQueueLength === null
                ? '--'
                : `~${est.predictedQueueLength} ppl`}
            </div>
          </div>
        </div>

        {/* Evidence & Latest Observation Indicator */}
        <div className="mt-3.5 pt-3 border-t border-white/[0.06]">
          {est && est.confidence > 0 ? (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-[#8E9E93] font-mono text-[10px] uppercase">
                  Evidence ({est.recentReportCount} obs)
                </span>
                <ConfidenceMeter confidence={est.confidence} label={est.confidenceLabel} />
              </div>
              <p className="text-[11px] text-[#8E9E93] line-clamp-1 italic">
                {est.evidenceExplanation}
              </p>
              {newestAgeStr && (
                <div className="text-[10px] font-mono text-[#7DF9FF]/80 flex items-center justify-between pt-1">
                  <span>Latest observation recorded:</span>
                  <span className="text-white font-semibold">{newestAgeStr}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-[11px] text-[#8E9E93]">
              <AlertCircle className="w-3.5 h-3.5 text-[#5A695F] shrink-0" />
              <span>No observations in 60m. Community report needed.</span>
            </div>
          )}
        </div>
      </div>

      {/* Footer Specs & Actions: Robust Responsive Containment */}
      <div className="pt-3 border-t border-white/[0.06] flex flex-wrap items-center justify-between gap-x-3 gap-y-2.5">
        {/* Left Secondary Metadata: Truncates cleanly without displacing actions */}
        <div className="flex items-center gap-2 text-[#8E9E93] min-w-0 flex-1 basis-[150px]">
          <span
            className="inline-flex items-center gap-1 text-[11px] font-mono min-w-0 shrink"
            title={location.openHours}
          >
            <Clock className="w-3 h-3 text-[#7DF9FF] shrink-0" />
            <span className="truncate">{location.openHours}</span>
          </span>
          {(location.capacityEstimate || location.capacity) && (
            <>
              <span className="text-[#5A695F] text-[10px] shrink-0 select-none">•</span>
              <span
                className="inline-flex items-center gap-1 text-[11px] font-mono min-w-0 shrink"
                title={location.capacityEstimate || `${location.capacity} cap`}
              >
                <Users className="w-3 h-3 text-[#5A695F] shrink-0" />
                <span className="truncate">{location.capacityEstimate || `${location.capacity} cap`}</span>
              </span>
            </>
          )}
        </div>

        {/* Right Action Buttons: Predictable dimensions (min 44x44px touch targets), strictly contained */}
        <div className="flex items-center gap-2 shrink-0 ml-auto">
          <button
            onClick={() => onReport(location.id)}
            className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-xl btn-glass hover:border-[#39FF14]/50 hover:text-white text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#39FF14] transition-all min-h-[44px]"
            title="Submit a queue observation"
            aria-label={`Submit observation for ${location.name}`}
          >
            <Plus className="w-3.5 h-3.5 text-[#39FF14] shrink-0" />
            <span>Report</span>
          </button>

          <button
            onClick={() => onSelect(location.id)}
            className="inline-flex items-center justify-center w-11 h-11 rounded-xl btn-glass hover:border-[#7DF9FF]/50 hover:text-[#7DF9FF] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7DF9FF] transition-all shrink-0 min-h-[44px] min-w-[44px]"
            title="View details and history"
            aria-label={`View details and history for ${location.name}`}
          >
            <ArrowUpRight className="w-4 h-4 shrink-0" />
          </button>
        </div>
      </div>
    </div>
  );
};
