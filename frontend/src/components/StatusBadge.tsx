import React from 'react';
import { CongestionLevel, FreshnessState, ConfidenceLabel } from '../types';

interface CongestionBadgeProps {
  level: CongestionLevel;
}

export const CongestionBadge: React.FC<CongestionBadgeProps> = ({ level }) => {
  const configs: Record<CongestionLevel, { text: string; bg: string; border: string; textCol: string }> = {
    LOW: {
      text: 'Low Wait',
      bg: 'bg-emerald-950/60',
      border: 'border-emerald-500/40',
      textCol: 'text-emerald-400',
    },
    MODERATE: {
      text: 'Moderate Wait',
      bg: 'bg-cyan-950/60',
      border: 'border-cyan-500/40',
      textCol: 'text-cyan-400',
    },
    HIGH: {
      text: 'High Wait',
      bg: 'bg-amber-950/60',
      border: 'border-amber-500/40',
      textCol: 'text-amber-400',
    },
    VERY_HIGH: {
      text: 'Heavy Congestion',
      bg: 'bg-rose-950/60',
      border: 'border-rose-500/40',
      textCol: 'text-rose-400',
    },
    UNKNOWN: {
      text: 'Unknown Wait',
      bg: 'bg-slate-900/60',
      border: 'border-slate-700/40',
      textCol: 'text-slate-400',
    },
  };

  const c = configs[level] || configs.UNKNOWN;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border ${c.bg} ${c.border} ${c.textCol}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${level === 'LOW' ? 'bg-emerald-400' : level === 'MODERATE' ? 'bg-cyan-400' : level === 'HIGH' ? 'bg-amber-400' : level === 'VERY_HIGH' ? 'bg-rose-400' : 'bg-slate-500'}`} />
      {c.text}
    </span>
  );
};

interface FreshnessBadgeProps {
  state: FreshnessState;
}

export const FreshnessBadge: React.FC<FreshnessBadgeProps> = ({ state }) => {
  switch (state) {
    case 'LIVE':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-semibold rounded-full bg-neon-green/10 border border-neon-green/30 text-neon-green">
          <span className="w-2 h-2 rounded-full bg-neon-green animate-pulse-live" />
          LIVE (&lt;7m)
        </span>
      );
    case 'RECENT':
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 text-xs font-medium rounded-full bg-neon-blue/10 border border-neon-blue/30 text-neon-blue">
          RECENT (&lt;20m)
        </span>
      );
    case 'STALE':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400">
          AGING DATA
        </span>
      );
    case 'NO RECENT DATA':
    default:
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-slate-800 border border-slate-700 text-slate-400">
          NO RECENT DATA
        </span>
      );
  }
};

interface ConfidenceMeterProps {
  confidence: number;
  label: ConfidenceLabel;
}

export const ConfidenceMeter: React.FC<ConfidenceMeterProps> = ({ confidence, label }) => {
  const percent = Math.round(confidence * 100);

  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden flex">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            confidence >= 0.7
              ? 'bg-neon-green'
              : confidence >= 0.4
              ? 'bg-neon-blue'
              : confidence >= 0.2
              ? 'bg-amber-400'
              : 'bg-slate-600'
          }`}
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className="font-mono text-slate-400 text-[11px] font-medium">
        {label} ({percent}%)
      </span>
    </div>
  );
};
