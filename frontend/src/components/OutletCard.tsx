import React from 'react';
import { CampusLocation } from '../types';
import { CongestionBadge, FreshnessBadge, ConfidenceMeter } from './StatusBadge';
import { Clock, Users, ArrowUpRight, Plus, AlertCircle } from 'lucide-react';

interface OutletCardProps {
  location: CampusLocation;
  onSelect: (id: string) => void;
  onReport: (id: string) => void;
}

export const OutletCard: React.FC<OutletCardProps> = ({ location, onSelect, onReport }) => {
  const est = location.estimate;
  const hasWait = est?.predictedWaitMinutes !== null && est?.predictedWaitMinutes !== undefined;
  const isNoData = !est || est.freshness === 'NO RECENT DATA' || !hasWait;

  return (
    <div className="group relative rounded-3xl glass-panel p-6 flex flex-col justify-between transition-all duration-300 hover:-translate-y-1 glass-specular-edge hover:border-[#39FF14]/40 hover:shadow-[0_16px_40px_-10px_rgba(0,0,0,0.7),0_0_25px_-5px_rgba(57,255,20,0.2)]">
      {/* Top Meta Header */}
      <div>
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`text-[10px] uppercase font-mono font-bold tracking-wider px-2.5 py-0.5 rounded-full border ${
                location.category === 'MESS'
                  ? 'bg-[#7DF9FF]/10 text-[#7DF9FF] border-[#7DF9FF]/30'
                  : 'bg-[#39FF14]/10 text-[#39FF14] border-[#39FF14]/30'
              }`}
            >
              {location.category}
            </span>
            {est && <FreshnessBadge state={est.freshness} />}
          </div>
          {est && <CongestionBadge level={est.congestion} />}
        </div>

        {/* Title & Description */}
        <h3 className="font-display text-xl font-bold text-white group-hover:text-[#39FF14] transition-colors tracking-tight line-clamp-1">
          {location.name}
        </h3>
        <p className="text-xs text-[#8E9E93] mt-1.5 line-clamp-2 leading-relaxed">
          {location.description}
        </p>
      </div>

      {/* Main Wait Time & Queue Status Box */}
      <div className="my-5 p-4 rounded-2xl bg-[#090E0B]/60 border border-white/[0.06] backdrop-blur-md">
        <div className="flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase font-mono tracking-widest text-[#8E9E93]">
              Estimated Wait
            </div>
            <div className="flex items-baseline gap-1 mt-1">
              {isNoData ? (
                <div className="font-mono text-2xl font-bold text-[#5A695F]">
                  --
                  <span className="text-xs font-sans text-[#5A695F] ml-1.5 font-normal">
                    (insufficient data)
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

        {/* Evidence & Rationale */}
        <div className="mt-3.5 pt-3 border-t border-white/[0.06]">
          {est && est.confidence > 0 ? (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-[#8E9E93] font-mono text-[10px] uppercase">Evidence Index</span>
                <ConfidenceMeter confidence={est.confidence} label={est.confidenceLabel} />
              </div>
              <p className="text-[11px] text-[#8E9E93] line-clamp-1 italic">
                {est.evidenceExplanation}
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-[11px] text-[#8E9E93]">
              <AlertCircle className="w-3.5 h-3.5 text-[#5A695F] shrink-0" />
              <span>No observations in 60m. First report needed.</span>
            </div>
          )}
        </div>
      </div>

      {/* Footer Specs & Actions */}
      <div className="pt-2 flex items-center justify-between gap-3 text-xs border-t border-white/[0.04]">
        <div className="flex items-center gap-3 text-[#8E9E93]">
          <span className="flex items-center gap-1 text-[11px] font-mono">
            <Clock className="w-3 h-3 text-[#7DF9FF]" />
            {location.openHours}
          </span>
          <span className="flex items-center gap-1 text-[11px] font-mono">
            <Users className="w-3 h-3 text-[#5A695F]" />
            {location.capacity} cap
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onReport(location.id)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl btn-glass hover:border-[#39FF14]/40 text-xs font-semibold"
            title="Submit a queue observation"
          >
            <Plus className="w-3.5 h-3.5 text-[#39FF14]" />
            <span>Report</span>
          </button>

          <button
            onClick={() => onSelect(location.id)}
            className="p-2 rounded-xl btn-glass hover:border-[#7DF9FF]/40 hover:text-[#7DF9FF] transition-colors"
            title="View details and history"
          >
            <ArrowUpRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
