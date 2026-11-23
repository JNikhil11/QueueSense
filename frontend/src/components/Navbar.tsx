import React from 'react';
import { RefreshCw, PlusCircle, ShieldAlert, Wifi, Database } from 'lucide-react';

interface NavbarProps {
  isLiveApi: boolean;
  isRefreshing: boolean;
  onRefresh: () => void;
  onOpenReportModal: () => void;
  onOpenAdminModal: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  isLiveApi,
  isRefreshing,
  onRefresh,
  onOpenReportModal,
  onOpenAdminModal,
}) => {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-surface-border/80 bg-surface-base/90 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand Lockup */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-neon-green/20 via-neon-blue/10 to-surface-card border border-neon-green/40 flex items-center justify-center shadow-glow-green/30">
            <svg
              className="w-5 h-5 text-neon-green"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-display font-bold text-xl tracking-tight text-white">
                Queue<span className="text-neon-green">Sense</span>
              </span>
              <span className="hidden sm:inline-block text-[10px] uppercase font-mono tracking-wider px-2 py-0.5 rounded bg-surface-elevated border border-surface-border text-slate-300">
                v1.0 • AWS
              </span>
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">Campus Queue Intelligence</p>
          </div>
        </div>

        {/* Center / Cloud Status Pill */}
        <div className="hidden md:flex items-center gap-2 px-3 py-1 rounded-full bg-surface-card border border-surface-border text-xs">
          {isLiveApi ? (
            <>
              <Wifi className="w-3.5 h-3.5 text-neon-green" />
              <span className="text-slate-300 font-medium">AWS API Gateway</span>
              <span className="w-1.5 h-1.5 rounded-full bg-neon-green animate-pulse-live" />
            </>
          ) : (
            <>
              <Database className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-slate-300 font-medium">Offline Simulation</span>
              <span className="text-[10px] text-amber-400 uppercase font-mono tracking-wide px-1.5 py-0.2 bg-amber-950/60 rounded border border-amber-500/30">
                Demo Fixtures
              </span>
            </>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            title="Refresh queue observations"
            className="p-2 rounded-lg bg-surface-card hover:bg-surface-elevated border border-surface-border text-slate-300 hover:text-white transition-all duration-150 disabled:opacity-50"
            aria-label="Refresh data"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-neon-blue' : ''}`} />
          </button>

          <button
            onClick={onOpenAdminModal}
            className="hidden sm:flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-surface-card hover:bg-surface-elevated border border-surface-border text-slate-300 hover:text-white transition-colors"
          >
            <ShieldAlert className="w-3.5 h-3.5 text-neon-blue" />
            <span>Audit Feed</span>
          </button>

          <button
            onClick={onOpenReportModal}
            className="flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg bg-neon-green hover:bg-[#2fe07c] text-slate-950 shadow-glow-green transition-all duration-150 hover:shadow-lg active:scale-95"
          >
            <PlusCircle className="w-4 h-4" />
            <span>Report Queue</span>
          </button>
        </div>
      </div>
    </header>
  );
};
