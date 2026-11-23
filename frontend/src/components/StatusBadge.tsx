import React from 'react';
import { CongestionLevel, FreshnessState, ConfidenceLabel } from '../types';

interface CongestionBadgeProps {
  level: CongestionLevel;
  className?: string;
}

export const CongestionBadge: React.FC<CongestionBadgeProps> = ({ level, className = '' }) => {
  const configs: Record<
    CongestionLevel,
    { text: string; bg: string; border: string; textCol: string; dot: string; glow: string }
  > = {
    LOW: {
      text: 'Low Wait',
      bg: 'bg-[#39FF14]/10',
      border: 'border-[#39FF14]/35',
      textCol: 'text-[#39FF14]',
      dot: 'bg-[#39FF14]',
      glow: 'shadow-[0_0_10px_rgba(57,255,20,0.35)]',
    },
    MODERATE: {
      text: 'Moderate Wait',
      bg: 'bg-[#7DF9FF]/10',
      border: 'border-[#7DF9FF]/35',
      textCol: 'text-[#7DF9FF]',
      dot: 'bg-[#7DF9FF]',
      glow: 'shadow-[0_0_10px_rgba(125,249,255,0.35)]',
    },
    HIGH: {
      text: 'High Wait',
      bg: 'bg-[#FFA028]/10',
      border: 'border-[#FFA028]/35',
      textCol: 'text-[#FFA028]',
      dot: 'bg-[#FFA028]',
      glow: 'shadow-[0_0_10px_rgba(255,160,40,0.35)]',
    },
    VERY_HIGH: {
      text: 'Heavy Bottleneck',
      bg: 'bg-[#CC162D]/15',
      border: 'border-[#CC162D]/50',
      textCol: 'text-[#FF4A60]',
      dot: 'bg-[#CC162D]',
      glow: 'shadow-[0_0_12px_rgba(204,22,45,0.5)]',
    },
    UNKNOWN: {
      text: 'Unknown Wait',
      bg: 'bg-white/[0.04]',
      border: 'border-white/10',
      textCol: 'text-[#8E9E93]',
      dot: 'bg-[#5A695F]',
      glow: '',
    },
  };

  const c = configs[level] || configs.UNKNOWN;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono uppercase tracking-wider font-semibold rounded-full border backdrop-blur-md ${c.bg} ${c.border} ${c.textCol} ${c.glow} ${className}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {c.text}
    </span>
  );
};

interface FreshnessBadgeProps {
  state: FreshnessState;
  className?: string;
}

export const FreshnessBadge: React.FC<FreshnessBadgeProps> = ({ state, className = '' }) => {
  switch (state) {
    case 'LIVE':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-mono font-bold uppercase tracking-wider rounded-full bg-[#39FF14]/15 border border-[#39FF14]/40 text-[#39FF14] shadow-[0_0_15px_-3px_rgba(57,255,20,0.4)] backdrop-blur-md ${className}`}
        >
          <span className="w-2 h-2 rounded-full bg-[#39FF14] animate-pulse-live" />
          LIVE (&lt;7m)
        </span>
      );
    case 'RECENT':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-mono font-semibold uppercase tracking-wider rounded-full bg-[#7DF9FF]/10 border border-[#7DF9FF]/35 text-[#7DF9FF] shadow-[0_0_12px_-3px_rgba(125,249,255,0.3)] backdrop-blur-md ${className}`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-[#7DF9FF]" />
          RECENT (&lt;20m)
        </span>
      );
    case 'STALE':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-mono font-medium uppercase tracking-wider rounded-full bg-[#FFA028]/10 border border-[#FFA028]/35 text-[#FFA028] backdrop-blur-md ${className}`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-[#FFA028]" />
          AGING DATA
        </span>
      );
    case 'NO RECENT DATA':
    default:
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-mono font-medium uppercase tracking-wider rounded-full bg-white/[0.04] border border-white/10 text-[#8E9E93] backdrop-blur-md ${className}`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-[#5A695F]" />
          NO RECENT DATA
        </span>
      );
  }
};

interface ConfidenceMeterProps {
  confidence: number;
  label: ConfidenceLabel;
  className?: string;
}

export const ConfidenceMeter: React.FC<ConfidenceMeterProps> = ({ confidence, label, className = '' }) => {
  const percent = Math.round(confidence * 100);

  return (
    <div className={`flex items-center gap-2.5 text-xs ${className}`}>
      <div className="w-16 h-1.5 bg-[#121A14] rounded-full overflow-hidden border border-white/10 flex p-[0.5px]">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            confidence >= 0.7
              ? 'bg-[#39FF14] shadow-[0_0_8px_#39FF14]'
              : confidence >= 0.4
              ? 'bg-[#7DF9FF] shadow-[0_0_8px_#7DF9FF]'
              : confidence >= 0.2
              ? 'bg-[#FFA028]'
              : 'bg-[#5A695F]'
          }`}
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className="font-mono text-[#8E9E93] text-[11px] font-medium tracking-tight">
        {label} <span className="text-[#F4F7F5]/60 font-normal">({percent}%)</span>
      </span>
    </div>
  );
};
