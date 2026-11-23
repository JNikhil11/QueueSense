import React from 'react';

interface BrandLogoProps {
  size?: 'sm' | 'md' | 'lg';
  showWordmark?: boolean;
  className?: string;
}

export const BrandLogo: React.FC<BrandLogoProps> = ({
  size = 'md',
  showWordmark = true,
  className = '',
}) => {
  const dimensions = {
    sm: { icon: 28, text: 'text-base', sub: 'text-[9px]' },
    md: { icon: 36, text: 'text-lg', sub: 'text-[10px]' },
    lg: { icon: 48, text: 'text-2xl', sub: 'text-xs' },
  }[size];

  return (
    <div className={`flex items-center gap-3 select-none ${className}`}>
      {/* Liquid Glass App Icon Container */}
      <div
        className="relative flex items-center justify-center rounded-xl bg-gradient-to-b from-[#1E2E22] via-[#0E1610] to-[#080D0A] p-2 border border-[#39FF14]/30 shadow-[0_0_20px_-3px_rgba(57,255,20,0.3),inset_0_1px_1px_0_rgba(255,255,255,0.25)] transition-all duration-300 hover:border-[#39FF14]/60 hover:shadow-[0_0_25px_0_rgba(57,255,20,0.45)] group"
        style={{ width: dimensions.icon + 10, height: dimensions.icon + 10 }}
      >
        {/* Subtle Ambient Specular Rim */}
        <div className="absolute inset-x-1.5 top-0.5 h-[1px] bg-gradient-to-r from-transparent via-white/40 to-transparent pointer-events-none" />

        {/* Custom QueueSense Geometric Flow Symbol */}
        <svg
          width={dimensions.icon}
          height={dimensions.icon}
          viewBox="0 0 40 40"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="transition-transform duration-300 group-hover:scale-105"
        >
          <defs>
            {/* Primary Neon Green Gradient */}
            <linearGradient id="qs-neon-flow" x1="4" y1="4" x2="36" y2="36" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#7DF9FF" />
              <stop offset="45%" stopColor="#39FF14" />
              <stop offset="100%" stopColor="#25B80C" />
            </linearGradient>

            {/* Cyan Accent Stream */}
            <linearGradient id="qs-cyan-stream" x1="10" y1="28" x2="32" y2="10" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#39FF14" stopOpacity="0.4" />
              <stop offset="70%" stopColor="#7DF9FF" />
              <stop offset="100%" stopColor="#E0FFFF" />
            </linearGradient>

            {/* Glowing Drop Filter */}
            <filter id="qs-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="1.5" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Stream 1: Outer continuous loop representing campus queue circulatory flow */}
          <path
            d="M 12 28 C 6 22 7 12 15 7 C 23 2 33 6 34 16 C 34.8 24 28 32 18 33"
            stroke="url(#qs-neon-flow)"
            strokeWidth="3.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            filter="url(#qs-glow)"
          />

          {/* Stream 2: Inner accelerated forward vector (The directional flow through the line) */}
          <path
            d="M 15 20 C 14 15 18 11 23 12 C 27 13 29 17 27 21 C 25 25 21 27 18 26"
            stroke="url(#qs-cyan-stream)"
            strokeWidth="2.5"
            strokeLinecap="round"
          />

          {/* Dynamic Queue Nodes: 3 progressive queue checkpoints */}
          <circle cx="12" cy="28" r="2.2" fill="#39FF14" />
          <circle cx="27" cy="13" r="2" fill="#7DF9FF" />
          
          {/* Leading Intelligence Arrow: Fast exit vector */}
          <path
            d="M 23 29 L 33 33 L 29 23"
            stroke="#39FF14"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M 33 33 L 21 21"
            stroke="#7DF9FF"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
        </svg>
      </div>

      {/* Typography Wordmark */}
      {showWordmark && (
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5 leading-none">
            <span className={`font-display font-extrabold tracking-tight text-white ${dimensions.text}`}>
              Queue<span className="text-[#39FF14]">Sense</span>
            </span>
          </div>
          <span className={`font-mono uppercase tracking-[0.2em] text-[#8E9E93] mt-0.5 ${dimensions.sub}`}>
            Campus Intelligence
          </span>
        </div>
      )}
    </div>
  );
};

