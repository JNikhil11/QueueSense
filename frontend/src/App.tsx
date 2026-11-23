import React, { useState, useEffect, useMemo } from 'react';
import { CampusLocation, SmartRecommendation, ReportSubmissionPayload } from './types';
import { api } from './services/api';
import { Navbar } from './components/Navbar';
import { Hero } from './components/Hero';
import { RecommendationBanner } from './components/RecommendationBanner';
import { FilterBar } from './components/FilterBar';
import { OutletCard } from './components/OutletCard';
import { ReportModal } from './components/ReportModal';
import { OutletDetailModal } from './components/OutletDetailModal';
import { AdminAuditModal } from './components/AdminAuditModal';
import { BrandLogo } from './components/BrandLogo';
import { Utensils, AlertCircle, RefreshCw, CheckCircle2 } from 'lucide-react';

export const App: React.FC = () => {
  const [locations, setLocations] = useState<CampusLocation[]>([]);
  const [recommendation, setRecommendation] = useState<SmartRecommendation | null>(null);
  const [isLiveApi, setIsLiveApi] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Filters & Search
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('wait-asc');

  // Modals state
  const [isReportModalOpen, setIsReportModalOpen] = useState<boolean>(false);
  const [activeReportOutletId, setActiveReportOutletId] = useState<string | undefined>(undefined);
  const [detailOutletId, setDetailOutletId] = useState<string | null>(null);
  const [isAdminModalOpen, setIsAdminModalOpen] = useState<boolean>(false);
  const [detailRefreshTrigger, setDetailRefreshTrigger] = useState<number>(0);

  // Toast notification
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  // Container ref for subtle pointer ambient lighting
  const containerRef = React.useRef<HTMLDivElement>(null);

  // Subtle cursor ambient light tracking (only for fine pointer desktop, zero React re-renders)
  useEffect(() => {
    const isFinePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!isFinePointer || prefersReducedMotion || !containerRef.current) return;

    let rafId: number | null = null;
    const handlePointerMove = (e: PointerEvent) => {
      if (rafId) return;
      rafId = requestAnimationFrame(() => {
        if (containerRef.current) {
          const rect = containerRef.current.getBoundingClientRect();
          const xPercent = Math.max(0, Math.min(100, Math.round(((e.clientX - rect.left) / rect.width) * 100)));
          const yPercent = Math.max(0, Math.min(100, Math.round(((e.clientY - rect.top) / rect.height) * 100)));
          containerRef.current.style.setProperty('--mouse-x', `${xPercent}%`);
          containerRef.current.style.setProperty('--mouse-y', `${yPercent}%`);
        }
        rafId = null;
      });
    };

    window.addEventListener('pointermove', handlePointerMove, { passive: true });
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, []);

  // Prevent background scroll when any modal is open
  useEffect(() => {
    if (isReportModalOpen || detailOutletId || isAdminModalOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isReportModalOpen, detailOutletId, isAdminModalOpen]);

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3500);
  };

  const loadData = async (isManualRefresh = false) => {
    try {
      if (isManualRefresh) setIsRefreshing(true);
      else setLoading(true);

      const [locResult, recResult] = await Promise.all([
        api.getLocations(),
        api.getRecommendations(),
      ]);

      setLocations(locResult.data);
      setRecommendation(recResult.data);
      setIsLiveApi(locResult.isLive);
      setErrorMsg(null);

      if (isManualRefresh) {
        showToast('Queue estimates and observations refreshed.');
      }
    } catch (err: any) {
      console.error('Error fetching data:', err);
      setErrorMsg('Failed to sync queue data with server.');
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  // Initial fetch and automatic refresh interval (every 30s)
  useEffect(() => {
    loadData();
    const interval = setInterval(() => {
      loadData(true);
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // Filtered & Sorted Outlets
  const filteredLocations = useMemo(() => {
    let result = [...locations];

    // Category Filter
    if (selectedCategory !== 'ALL') {
      result = result.filter((l) => l.category === selectedCategory);
    }

    // Search Query Filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (l) =>
          l.name.toLowerCase().includes(q) ||
          l.description.toLowerCase().includes(q) ||
          l.category.toLowerCase().includes(q)
      );
    }

    // Sorting
    result.sort((a, b) => {
      const waitA = a.estimate?.predictedWaitMinutes ?? 999;
      const waitB = b.estimate?.predictedWaitMinutes ?? 999;

      if (sortBy === 'wait-asc') {
        return waitA - waitB;
      }
      if (sortBy === 'freshness') {
        const timeA = a.estimate?.newestReportTimestamp
          ? new Date(a.estimate.newestReportTimestamp).getTime()
          : 0;
        const timeB = b.estimate?.newestReportTimestamp
          ? new Date(b.estimate.newestReportTimestamp).getTime()
          : 0;
        return timeB - timeA;
      }
      if (sortBy === 'reports-desc') {
        return (b.estimate?.reportCount || 0) - (a.estimate?.reportCount || 0);
      }
      return a.name.localeCompare(b.name);
    });

    return result;
  }, [locations, selectedCategory, searchQuery, sortBy]);

  const handleOpenReportModal = (outletId?: string) => {
    setActiveReportOutletId(outletId);
    setIsReportModalOpen(true);
  };

  const handleReportSubmit = async (locationId: string, payload: ReportSubmissionPayload) => {
    await api.submitReport(locationId, payload);
    setDetailRefreshTrigger((prev) => prev + 1);
    showToast(`Recorded report: ~${payload.reportedWaitMinutes}m wait at outlet.`);
    await loadData(true);
  };

  return (
    <div
      ref={containerRef}
      className="min-h-screen flex flex-col bg-[#070A08] text-[#F4F7F5] relative selection:bg-[#39FF14] selection:text-[#070A08] overflow-x-hidden"
    >
      {/* Subtle Living Pointer Ambient Field */}
      <div
        className="fixed inset-0 pointer-events-none transition-opacity duration-700"
        style={{
          background: 'radial-gradient(900px circle at var(--mouse-x, 50%) var(--mouse-y, 25%), rgba(0, 150, 255, 0.038), transparent 70%)',
        }}
      />

      {/* Global Ambient Glow Nodes */}
      <div className="fixed top-0 left-1/4 w-[600px] h-[300px] bg-[#39FF14]/[0.06] rounded-full blur-[140px] pointer-events-none" />
      <div className="fixed top-1/3 right-10 w-[500px] h-[350px] bg-[#7DF9FF]/[0.04] rounded-full blur-[160px] pointer-events-none" />

      {/* Toast Notification */}
      {toastMsg && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3.5 rounded-2xl glass-panel-elevated border-[#39FF14]/40 shadow-[0_10px_35px_-5px_rgba(0,0,0,0.8),0_0_25px_rgba(57,255,20,0.3)] text-xs font-mono font-medium text-white animate-bounce-subtle">
          <CheckCircle2 className="w-4 h-4 text-[#39FF14]" />
          <span>{toastMsg}</span>
        </div>
      )}

      {/* Navigation */}
      <Navbar
        isLiveApi={isLiveApi}
        isRefreshing={isRefreshing}
        onRefresh={() => loadData(true)}
        onOpenReportModal={() => handleOpenReportModal()}
        onOpenAdminModal={() => setIsAdminModalOpen(true)}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 pb-20">
        {/* Hero Section */}
        <Hero locations={locations} />

        {/* Global Error Notice if any */}
        {errorMsg && (
          <div className="my-4 p-4 rounded-2xl bg-[#CC162D]/15 border border-[#CC162D]/40 text-[#FF4A60] text-xs flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 shrink-0 text-[#FF4A60]" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Smart Recommendation Banner */}
        <RecommendationBanner
          recommendation={recommendation}
          onSelectOutlet={(id) => setDetailOutletId(id)}
          onOpenReportModal={handleOpenReportModal}
        />

        {/* Filter Bar */}
        <FilterBar
          selectedCategory={selectedCategory}
          onSelectCategory={setSelectedCategory}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          sortBy={sortBy}
          onSortChange={setSortBy}
          totalCount={filteredLocations.length}
        />

        {/* Outlets Grid with Focused Hover Dimming */}
        {loading ? (
          <div className="py-24 flex flex-col items-center justify-center text-[#8E9E93] gap-3">
            <RefreshCw className="w-8 h-8 animate-spin text-[#39FF14]" />
            <span className="text-xs font-mono tracking-widest uppercase">
              Synchronizing Campus Queue Intelligence...
            </span>
          </div>
        ) : filteredLocations.length === 0 ? (
          <div className="py-24 text-center rounded-3xl glass-panel border-dashed border-white/10">
            <Utensils className="w-10 h-10 text-[#5A695F] mx-auto mb-3" />
            <h3 className="text-base font-display font-bold text-white">No dining outlets match your query</h3>
            <p className="text-xs text-[#8E9E93] mt-1 font-mono">
              Try adjusting your category filter or search keywords.
            </p>
          </div>
        ) : (
          <div className="cards-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-4">
            {filteredLocations.map((loc) => (
              <OutletCard
                key={loc.id}
                location={loc}
                onSelect={(id) => setDetailOutletId(id)}
                onReport={(id) => handleOpenReportModal(id)}
              />
            ))}
          </div>
        )}
      </main>

      {/* Footer & Truthful Data Source Disclosure */}
      <footer className="border-t border-white/[0.08] bg-[#050806]/80 backdrop-blur-xl py-10 text-xs text-[#8E9E93]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-3">
              <BrandLogo size="sm" showWordmark={true} />
              <span className="text-[#5A695F]">•</span>
              <span className="font-mono text-[11px] text-[#8E9E93]">IIT Bombay Campus Food Services</span>
            </div>

            <div className="flex items-center gap-4 text-[11px] font-mono text-[#5A695F]">
              <span>Techfest, IIT Bombay × AWS ShipIt Challenge</span>
              <span>•</span>
              <span className="text-[#8E9E93]">Built by J Nikhil</span>
            </div>
          </div>

          {/* Truthful Data Status Bar */}
          <div className="pt-4 border-t border-white/[0.04] flex flex-col sm:flex-row items-center justify-between gap-3 text-[11px] font-mono">
            <div className="flex items-center gap-2">
              {isLiveApi ? (
                <>
                  <span className="w-1.5 h-1.5 rounded-full bg-[#39FF14] animate-pulse" />
                  <span className="text-[#39FF14] font-medium">Live AWS API Gateway</span>
                  <span className="text-[#5A695F]">| Synchronized with DynamoDB ap-southeast-2</span>
                </>
              ) : (
                <>
                  <span className="w-1.5 h-1.5 rounded-full bg-[#FFA028]" />
                  <span className="text-[#FFA028] font-medium">Offline Simulation Fixture</span>
                  <span className="text-[#5A695F]">| Demonstrating real-time decay & statistical aggregation. Observations persist in browser storage.</span>
                </>
              )}
            </div>
            <span className="text-[#5A695F]">
              {locations.length} dining locations indexed • Verified Directory
            </span>
          </div>
        </div>
      </footer>

      {/* Modals */}
      <ReportModal
        isOpen={isReportModalOpen}
        onClose={() => setIsReportModalOpen(false)}
        locations={locations}
        initialLocationId={activeReportOutletId}
        onSubmit={handleReportSubmit}
      />

      <OutletDetailModal
        locationId={detailOutletId}
        refreshTrigger={detailRefreshTrigger}
        onClose={() => setDetailOutletId(null)}
        onOpenReportModal={(id) => {
          setDetailOutletId(null);
          handleOpenReportModal(id);
        }}
      />

      <AdminAuditModal
        isOpen={isAdminModalOpen}
        onClose={() => setIsAdminModalOpen(false)}
      />

      <AdminAuditModal
        isOpen={isAdminModalOpen}
        onClose={() => setIsAdminModalOpen(false)}
      />
    </div>
  );
};

export default App;
