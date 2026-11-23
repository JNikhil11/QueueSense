import React from 'react';
import { CampusLocation } from '../types';
import { Clock, Users, UtensilsCrossed, Activity, ArrowUpRight } from 'lucide-react';

interface HeroProps {
  locations: CampusLocation[];
}

export const Hero: React.FC<HeroProps> = ({ locations }) => {
  // Aggregate real stats from loaded data (never fabricate)
  const activeCount = locations.filter((l) => l.active).length;
  const totalReports = locations.reduce((acc, l) => acc + (l.estimate?.reportCount || 0), 0);

  const validWaits = locations
    .map((l) => l.estimate?.predictedWaitMinutes)
    .filter((w): w is number => typeof w === 'number');

  const avgWait =
    validWaits.length > 0
      ? Math.round((validWaits.reduce((a, b) => a + b, 0) / validWaits.length) * 10) / 10
      : null;

  const minWait = validWaits.length > 0 ? Math.min(...validWaits) : null;

  return (
    <section className="relative pt-8 sm:pt-12 pb-10 overflow-hidden">
      {/* Background Ambient Green Energy Glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-radial-ambient pointer-events-none blur-3xl opacity-80" />
      <div className="absolute top-10 right-10 w-[400px] h-[250px] bg-radial-cyan-ambient pointer-events-none blur-3xl opacity-50" />

      {/* Abstract Background Queue Flow Lines Graphic */}
      <div className="absolute inset-0 pointer-events-none opacity-20 overflow-hidden">
        <svg
          className="w-full h-full"
          viewBox="0 0 1200 400"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M -100 120 C 300 80, 500 280, 900 160 C 1100 100, 1300 220, 1400 180"
            stroke="url(#hero-flow-1)"
            strokeWidth="1.5"
            strokeDasharray="6 8"
          />
          <path
            d="M -50 200 C 350 140, 550 340, 950 220 C 1150 160, 1350 280, 1450 240"
            stroke="url(#hero-flow-2)"
            strokeWidth="2"
          />
          <defs>
            <linearGradient id="hero-flow-1" x1="0" y1="0" x2="1200" y2="0" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#39FF14" stopOpacity="0" />
              <stop offset="50%" stopColor="#39FF14" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#7DF9FF" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="hero-flow-2" x1="0" y1="0" x2="1200" y2="0" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#7DF9FF" stopOpacity="0" />
              <stop offset="60%" stopColor="#39FF14" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#39FF14" stopOpacity="0" />
            </linearGradient>
          </defs>
        </svg>
      </div>

      <div className="relative z-10 max-w-7xl mx-auto">
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-8">
          {/* Hero Typography */}
          <div className="max-w-2xl space-y-3.5 sm:space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full glass-pill border border-[#39FF14]/30 text-[#39FF14] text-xs font-mono font-medium tracking-wide shadow-[0_0_15px_-4px_rgba(57,255,20,0.3)]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#39FF14] animate-pulse-live" />
              <span>Campus Food-Service Intelligence • IIT Bombay</span>
            </div>

            <h1 className="font-display text-3xl sm:text-4xl md:text-5xl lg:text-6xl font-extrabold tracking-tight text-white leading-[1.12]">
              Skip the wait.{' '}
              <br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#39FF14] via-[#7DF9FF] to-white">
                Find your next meal.
              </span>
            </h1>

            <p className="text-xs sm:text-sm md:text-base text-[#8E9E93] leading-relaxed max-w-xl font-normal">
              Continuous queue velocity, statistical outlier filtering, and verified peer observations.
              Know exact dining congestion across campus before leaving your lab, hostel, or lecture hall.
            </p>
          </div>

          {/* Differentiated Cohesive Statistics Capsule Group with Focused Dimming */}
          <div className="stats-grid grid grid-cols-2 sm:grid-cols-4 gap-2.5 sm:gap-3 w-full lg:w-auto">
            {/* Stat 1: Outlets */}
            <div className="stat-card group rounded-2xl glass-panel p-3.5 sm:p-4 flex flex-col justify-between transition-all duration-300 hover:border-[#7DF9FF]/40 glass-specular-edge">
              <div className="flex items-center justify-between text-[#8E9E93] text-xs mb-2">
                <span className="font-mono uppercase tracking-wider text-[10px]">Active Outlets</span>
                <UtensilsCrossed className="w-3.5 h-3.5 text-[#7DF9FF]" />
              </div>
              <div className="font-mono text-2xl sm:text-3xl font-bold text-white tracking-tight">
                {activeCount}
              </div>
              <span className="text-[10px] text-[#5A695F] font-mono mt-1">Messes & Cafes</span>
            </div>

            {/* Stat 2: Shortest Wait (Highlighted in Electric Neon Green) */}
            <div className="stat-card group rounded-2xl glass-panel p-3.5 sm:p-4 flex flex-col justify-between border-[#39FF14]/35 shadow-[0_0_20px_-6px_rgba(57,255,20,0.25)] transition-all duration-300 hover:border-[#39FF14]/60 glass-specular-edge">
              <div className="flex items-center justify-between text-[#39FF14] text-xs mb-2">
                <span className="font-mono uppercase tracking-wider text-[10px] font-semibold">Fastest Meal</span>
                <Clock className="w-3.5 h-3.5 text-[#39FF14]" />
              </div>
              <div className="font-mono text-2xl sm:text-3xl font-extrabold text-[#39FF14] tracking-tight">
                {minWait !== null ? `${minWait}m` : '--'}
              </div>
              <span className="text-[10px] text-[#39FF14]/70 font-mono mt-1 flex items-center gap-1">
                <span>Minimum queue</span>
                <ArrowUpRight className="w-2.5 h-2.5" />
              </span>
            </div>

            {/* Stat 3: Campus Avg */}
            <div className="stat-card group rounded-2xl glass-panel p-3.5 sm:p-4 flex flex-col justify-between transition-all duration-300 hover:border-[#7DF9FF]/40 glass-specular-edge">
              <div className="flex items-center justify-between text-[#8E9E93] text-xs mb-2">
                <span className="font-mono uppercase tracking-wider text-[10px]">Campus Avg</span>
                <Activity className="w-3.5 h-3.5 text-[#7DF9FF]" />
              </div>
              <div className="font-mono text-2xl sm:text-3xl font-bold text-[#F4F7F5] tracking-tight">
                {avgWait !== null ? `${avgWait}m` : '--'}
              </div>
              <span className="text-[10px] text-[#5A695F] font-mono mt-1">Mean campus wait</span>
            </div>

            {/* Stat 4: Observations */}
            <div className="stat-card group rounded-2xl glass-panel p-3.5 sm:p-4 flex flex-col justify-between transition-all duration-300 hover:border-[#39FF14]/40 glass-specular-edge">
              <div className="flex items-center justify-between text-[#8E9E93] text-xs mb-2">
                <span className="font-mono uppercase tracking-wider text-[10px]">Observations</span>
                <Users className="w-3.5 h-3.5 text-[#8E9E93]" />
              </div>
              <div className="font-mono text-2xl sm:text-3xl font-bold text-white tracking-tight">
                {totalReports}
              </div>
              <span className="text-[10px] text-[#5A695F] font-mono mt-1">Peer reports</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
