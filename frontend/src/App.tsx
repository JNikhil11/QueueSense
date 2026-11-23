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

  // Toast notification
  const [toastMsg, setToastMsg] = useState<string | null>(null);

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
    showToast(`Recorded report: ~${payload.reportedWaitMinutes}m wait at outlet.`);
    // Refresh to update estimates and recommendation
    await loadData(true);
  };

  return (
    <div className="min-h-screen flex flex-col bg-surface-base text-slate-100">
      {/* Toast Notification */}
      {toastMsg && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-4 py-3 rounded-xl bg-surface-card border border-neon-green/40 shadow-glow-green text-xs font-medium text-white animate-bounce-subtle">
          <CheckCircle2 className="w-4 h-4 text-neon-green" />
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
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 pb-16">
        {/* Hero Section */}
        <Hero locations={locations} />

        {/* Global Error Notice if any */}
        {errorMsg && (
          <div className="my-4 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
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

        {/* Outlets Grid */}
        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center text-slate-400 gap-3">
            <RefreshCw className="w-8 h-8 animate-spin text-neon-green" />
            <span className="text-sm font-mono tracking-wider">
              Syncing Campus Food Queue Estimates...
            </span>
          </div>
        ) : filteredLocations.length === 0 ? (
          <div className="py-20 text-center rounded-2xl bg-surface-card/40 border border-dashed border-surface-border">
            <Utensils className="w-10 h-10 text-slate-500 mx-auto mb-2" />
            <h3 className="text-base font-semibold text-white">No food outlets found</h3>
            <p className="text-xs text-slate-400 mt-1">
              Try adjusting your search query or category filters.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mt-2">
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

      {/* Footer */}
      <footer className="border-t border-surface-border/60 bg-surface-card/40 py-8 text-xs text-slate-400">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-display font-bold text-white tracking-tight">
              Queue<span className="text-neon-green">Sense</span>
            </span>
            <span>—</span>
            <span>Know the queue before you join it.</span>
          </div>

          <div className="flex items-center gap-4 text-[11px] font-mono">
            <span>Techfest, IIT Bombay × AWS ShipIt Challenge</span>
            <span>•</span>
            <span>Built by J Nikhil</span>
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
    </div>
  );
};

export default App;
