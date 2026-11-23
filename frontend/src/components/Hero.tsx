import React from 'react';
import { CampusLocation } from '../types';
import { Clock, Users, UtensilsCrossed, Sparkles } from 'lucide-react';

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

  const avgWait = validWaits.length > 0 
    ? Math.round((validWaits.reduce((a, b) => a + b, 0) / validWaits.length) * 10) / 10 
    : null;

  const minWait = validWaits.length > 0 ? Math.min(...validWaits) : null;

  return (
    <section className="relative pt-6 pb-8 border-b border-surface-border/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-neon-green/10 border border-neon-green/30 text-neon-green text-xs font-semibold mb-3">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Campus Queue Intelligence • VIT-AP</span>
            </div>
            <h1 className="font-display text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-white">
              Skip the wait. <br className="hidden sm:block" />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-neon-green via-neon-blue to-teal-300">
                Find your next meal.
              </span>
            </h1>
            <p className="mt-3 text-sm sm:text-base text-slate-300 leading-relaxed max-w-xl">
              Live, crowdsourced queue estimates for campus messes and canteens. Powered by mathematical time-decay, statistical outlier rejection, and transparent evidence scoring.
            </p>
          </div>

          {/* Genuine Real-Time Metrics Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 w-full md:w-auto">
            <div className="p-3 rounded-xl bg-surface-card border border-surface-border">
              <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
                <UtensilsCrossed className="w-3.5 h-3.5 text-neon-blue" />
                <span>Active Outlets</span>
              </div>
              <div className="font-mono text-xl sm:text-2xl font-bold text-white">
                {activeCount}
              </div>
            </div>

            <div className="p-3 rounded-xl bg-surface-card border border-surface-border">
              <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
                <Clock className="w-3.5 h-3.5 text-neon-green" />
                <span>Shortest Wait</span>
              </div>
              <div className="font-mono text-xl sm:text-2xl font-bold text-neon-green">
                {minWait !== null ? `${minWait}m` : '--'}
              </div>
            </div>

            <div className="p-3 rounded-xl bg-surface-card border border-surface-border">
              <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
                <Clock className="w-3.5 h-3.5 text-cyan-400" />
                <span>Campus Avg</span>
              </div>
              <div className="font-mono text-xl sm:text-2xl font-bold text-slate-200">
                {avgWait !== null ? `${avgWait}m` : '--'}
              </div>
            </div>

            <div className="p-3 rounded-xl bg-surface-card border border-surface-border">
              <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
                <Users className="w-3.5 h-3.5 text-amber-400" />
                <span>Observations</span>
              </div>
              <div className="font-mono text-xl sm:text-2xl font-bold text-white">
                {totalReports}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
