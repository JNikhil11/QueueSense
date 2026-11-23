import React from 'react';
import { RefreshCw, Plus, ShieldCheck, Wifi, Database } from 'lucide-react';
import { BrandLogo } from './BrandLogo';

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
    <header className="sticky top-0 z-40 w-full pt-3 px-4 sm:px-6 lg:px-8">
      {/* Floating Liquid-Glass Island Control Surface */}
      <div className="max-w-7xl mx-auto h-16 rounded-2xl glass-panel-elevated px-4 sm:px-6 flex items-center justify-between transition-all duration-300">
        {/* Specular Top Reflection Ridge */}
        <div className="absolute inset-x-6 top-0 h-[1px] bg-gradient-to-r from-transparent via-white/35 to-transparent pointer-events-none" />

        {/* Brand Lockup */}
        <div className="flex items-center gap-3">
          <BrandLogo size="md" showWordmark={true} />
          <span className="hidden xl:inline-block text-[10px] uppercase font-mono tracking-wider px-2 py-0.5 rounded-full bg-white/[0.05] border border-white/10 text-[#8E9E93]">
            v2.0 • AWS Sydney
          </span>
        </div>

        {/* Environment State Indicator (Pill Island) */}
        <div className="hidden md:flex items-center gap-2 px-3.5 py-1.5 rounded-full glass-pill text-xs border border-white/10">
          {isLiveApi ? (
            <>
              <Wifi className="w-3.5 h-3.5 text-[#39FF14]" />
              <span className="text-[#F4F7F5] font-medium tracking-tight">AWS API Gateway</span>
              <span className="w-1.5 h-1.5 rounded-full bg-[#39FF14] animate-pulse-live ml-1" />
            </>
          ) : (
            <>
              <Database className="w-3.5 h-3.5 text-[#FFA028]" />
              <span className="text-[#F4F7F5] font-medium tracking-tight">Offline Simulation</span>
              <span className="text-[10px] text-[#FFA028] uppercase font-mono tracking-wider font-semibold px-2 py-0.5 bg-[#FFA028]/15 rounded-full border border-[#FFA028]/35 ml-1">
                Demo Fixtures
              </span>
            </>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Refresh Action */}
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            title="Refresh queue estimates"
            className="p-2.5 rounded-xl btn-glass flex items-center justify-center disabled:opacity-50 transition-transform active:scale-95"
            aria-label="Refresh data"
          >
            <RefreshCw
              className={`w-4 h-4 text-[#7DF9FF] ${isRefreshing ? 'animate-spin' : ''}`}
            />
          </button>

          {/* Audit Feed Modal Trigger */}
          <button
            onClick={onOpenAdminModal}
            className="hidden sm:flex items-center gap-2 px-3.5 py-2 text-xs font-mono uppercase tracking-wider rounded-xl btn-glass hover:border-[#7DF9FF]/40 transition-colors"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-[#7DF9FF]" />
            <span className="text-[#F4F7F5]">Audit Stream</span>
          </button>

          {/* Primary Report CTA */}
          <button
            onClick={onOpenReportModal}
            className="flex items-center gap-2 px-4 sm:px-5 py-2.5 text-xs sm:text-sm btn-electric"
          >
            <Plus className="w-4 h-4 stroke-[2.5]" />
            <span className="font-semibold tracking-tight">Report Queue</span>
          </button>
        </div>
      </div>
    </header>
  );
};
