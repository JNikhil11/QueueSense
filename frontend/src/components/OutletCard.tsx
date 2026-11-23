import React from 'react';
import { CampusLocation } from '../types';
import { CongestionBadge, FreshnessBadge, ConfidenceMeter } from './StatusBadge';
import { Clock, Users, ArrowUpRight, PlusCircle, AlertCircle } from 'lucide-react';

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
    <div className="group relative rounded-2xl bg-surface-card hover:bg-surface-elevated/70 border border-surface-border hover:border-surface-subtle transition-all duration-200 flex flex-col justify-between overflow-hidden shadow-sm hover:shadow-md">
      {/* Top Banner & Tags */}
      <div className="p-5 pb-3">
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`text-[10px] uppercase font-mono font-bold tracking-wider px-2 py-0.5 rounded ${
                location.category === 'MESS'
                  ? 'bg-neon-blue/10 text-neon-blue border border-neon-blue/30'
                  : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
              }`}
            >
              {location.category}
            </span>
            {est && <FreshnessBadge state={est.freshness} />}
          </div>
          {est && <CongestionBadge level={est.congestion} />}
        </div>

        <h3 className="font-display text-lg font-bold text-white group-hover:text-neon-green transition-colors tracking-tight line-clamp-1">
          {location.name}
        </h3>
        <p className="text-xs text-slate-400 mt-1 line-clamp-2 leading-relaxed">
          {location.description}
        </p>
      </div>

      {/* Main Wait Metric Display */}
      <div className="px-5 py-3 border-y border-surface-border/50 bg-surface-base/30">
        <div className="flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase font-mono tracking-wider text-slate-400">
              Estimated Wait
            </div>
            <div className="flex items-baseline gap-1 mt-0.5">
              {isNoData ? (
                <div className="font-mono text-2xl font-bold text-slate-500">
                  --
                  <span className="text-xs font-sans text-slate-500 ml-1 font-normal">
                    (insufficient data)
                  </span>
                </div>
              ) : (
                <div
                  className={`font-mono text-3xl font-extrabold flex items-baseline gap-1 ${
                    est.congestion === 'LOW'
                      ? 'text-neon-green'
                      : est.congestion === 'MODERATE'
                      ? 'text-neon-blue'
                      : est.congestion === 'HIGH'
                      ? 'text-amber-400'
                      : 'text-rose-400'
                  }`}
                >
                  ~{est.predictedWaitMinutes}
                  <span className="text-xs font-sans font-normal text-slate-400">min</span>
                </div>
              )}
            </div>
          </div>

          <div className="text-right">
            <div className="text-[10px] uppercase font-mono tracking-wider text-slate-400">
              Queue Length
            </div>
            <div className="font-mono text-lg font-semibold text-slate-200 mt-0.5">
              {isNoData || est.predictedQueueLength === null
                ? '--'
                : `~${est.predictedQueueLength} ppl`}
            </div>
          </div>
        </div>

        {/* Evidence & Explanation */}
        <div className="mt-3 pt-2.5 border-t border-surface-border/30">
          {est && est.confidence > 0 ? (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400">Evidence Quality</span>
                <ConfidenceMeter confidence={est.confidence} label={est.confidenceLabel} />
              </div>
              <p className="text-[11px] text-slate-400 line-clamp-1 italic">
                {est.evidenceExplanation}
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <AlertCircle className="w-3.5 h-3.5 text-slate-500 shrink-0" />
              <span>No observations in past 60 mins. First report needed.</span>
            </div>
          )}
        </div>
      </div>

      {/* Footer Info & Actions */}
      <div className="p-4 bg-surface-card/60 flex items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-3 text-slate-400">
          <span className="flex items-center gap-1 text-[11px] font-mono">
            <Clock className="w-3 h-3 text-slate-400" />
            {location.openHours}
          </span>
          <span className="flex items-center gap-1 text-[11px] font-mono">
            <Users className="w-3 h-3 text-slate-400" />
            {location.capacity} cap
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onReport(location.id)}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-surface-elevated hover:bg-surface-subtle border border-surface-border text-slate-200 hover:text-white transition-colors"
            title="Submit a queue observation"
          >
            <PlusCircle className="w-3.5 h-3.5 text-neon-green" />
            <span className="font-medium">Report</span>
          </button>

          <button
            onClick={() => onSelect(location.id)}
            className="p-1.5 rounded-lg bg-surface-elevated hover:bg-surface-subtle border border-surface-border text-slate-300 hover:text-neon-blue transition-colors"
            title="View details and history"
          >
            <ArrowUpRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
