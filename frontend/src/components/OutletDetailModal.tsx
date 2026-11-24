import React, { useEffect, useState } from 'react';
import { CampusLocation, QueueEstimate, QueueReport, HistoricalData, AppSyncState } from '../types';
import { api } from '../services/api';
import { CongestionBadge, FreshnessBadge, ConfidenceMeter } from './StatusBadge';
import { X, Clock, Users, Plus, AlertCircle, AlertTriangle, History, RefreshCw, MapPin, CheckCircle2, TrendingUp } from 'lucide-react';
import { useFocusTrap } from '../hooks/useFocusTrap';

interface OutletDetailModalProps {
  locationId: string | null;
  refreshTrigger?: number;
  syncState?: AppSyncState;
  lastSuccessfulSyncStr?: string | null;
  onClose: () => void;
  onOpenReportModal: (locationId: string) => void;
}

export const OutletDetailModal: React.FC<OutletDetailModalProps> = ({
  locationId,
  refreshTrigger,
  syncState,
  lastSuccessfulSyncStr,
  onClose,
  onOpenReportModal,
}) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [location, setLocation] = useState<CampusLocation | null>(null);
  const [estimate, setEstimate] = useState<QueueEstimate | null>(null);
  const [reports, setReports] = useState<QueueReport[]>([]);
  const [historical, setHistorical] = useState<HistoricalData | null>(null);
  const [isLive, setIsLive] = useState<boolean>(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const isStale = syncState === 'STALE' || Boolean(fetchError);

  // WCAG 2.2 AA Focus Trapping & Robust Lifecycle Restoration
  const containerRef = useFocusTrap<HTMLDivElement>({
    isOpen: Boolean(locationId),
    onClose,
    autoFocusSelector: 'button[aria-label="Close dialog"]',
  });

  const fetchData = async () => {
    if (!locationId) return;
    try {
      setLoading(true);
      setFetchError(null);
      const [queueRes, histRes] = await Promise.allSettled([
        api.getLocationQueue(locationId),
        api.getHistorical(locationId),
      ]);

      if (queueRes.status === 'fulfilled') {
        setLocation(queueRes.value.location);
        setEstimate(queueRes.value.estimate);
        setReports(queueRes.value.reports);
        setIsLive(queueRes.value.isLive);
      } else {
        setFetchError('Live queue sync failed');
      }
      if (histRes.status === 'fulfilled') {
        setHistorical(histRes.value.data);
      }
    } catch (err: any) {
      console.error('Failed to load outlet details:', err);
      setFetchError(err.message || 'Live queue sync failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [locationId, refreshTrigger]);

  if (!locationId) return null;

  const latestReport = reports.length > 0 ? reports[0] : null;
  const latestAgeMin = latestReport
    ? Math.round((Date.now() - new Date(latestReport.timestamp).getTime()) / (60 * 1000))
    : null;
  const latestAgeStr =
    latestAgeMin !== null
      ? latestAgeMin <= 1
        ? 'Just now'
        : `${latestAgeMin}m ago`
      : '';

  // Filter daytime operating hours (8:00 to 22:00) for historical display
  const daytimeTrends = (historical?.hourlyTrends || []).filter(
    (h) => h.hour >= 8 && h.hour <= 22
  );
  const maxWaitInTrends = Math.max(
    ...daytimeTrends.map((h) => h.averageWaitMinutes || 0),
    1
  );

  return (
    <div
      ref={containerRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="outlet-detail-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#070A08]/85 backdrop-blur-md animate-fade-in"
    >
      <div className={`w-full max-w-2xl max-h-[90vh] rounded-3xl glass-panel-elevated shadow-2xl flex flex-col overflow-hidden glass-specular-edge animate-modal-in border ${
        isStale ? 'border-[#FFA028]/40' : 'border-[#39FF14]/30'
      }`}>
        {/* Header */}
        <div className="p-6 border-b border-white/[0.08] flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="text-[10px] uppercase font-mono font-bold tracking-wider px-2.5 py-0.5 rounded-full bg-[#7DF9FF]/10 text-[#7DF9FF] border border-[#7DF9FF]/30">
                {location?.category || 'OUTLET'}
              </span>
              {isStale && (
                <span
                  data-testid="detail-stale-badge"
                  className="text-[10px] uppercase font-mono font-bold tracking-wider px-2.5 py-0.5 rounded-full bg-[#FFA028]/20 text-[#FFA028] border border-[#FFA028]/45"
                >
                  STALE DATA
                </span>
              )}
              {location?.verificationStatus === 'STUDENT_SOURCED' && (
                <span
                  className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/[0.04] text-[#8E9E93] border border-white/10"
                  title={location?.verificationSource}
                >
                  <CheckCircle2 className="w-3 h-3 text-[#39FF14]" />
                  <span>Student Sourced</span>
                </span>
              )}
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/[0.04] text-[#5A695F] border border-white/10">
                {isLive ? 'AWS Cloud' : 'Local Demo'}
              </span>
              {estimate && !isStale && <FreshnessBadge state={estimate.freshness} />}
              {estimate && <CongestionBadge level={estimate.congestion} />}
            </div>
            <h2 id="outlet-detail-title" className="font-display text-2xl font-extrabold text-white tracking-tight">
              {location?.name || 'Loading outlet...'}
            </h2>
            {location?.landmarkLocation && (
              <div className="flex items-center gap-1.5 text-xs text-[#7DF9FF] font-mono mt-1">
                <MapPin className="w-3.5 h-3.5 shrink-0" />
                <span>{location.landmarkLocation}</span>
              </div>
            )}
            <p className="text-xs text-[#8E9E93] mt-1.5 max-w-lg leading-relaxed">
              {location?.description}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2.5 rounded-xl text-[#8E9E93] hover:text-white hover:bg-white/[0.06] transition-colors min-h-[44px] min-w-[44px] h-11 w-11 shrink-0 flex items-center justify-center"
            style={{ minHeight: '44px', minWidth: '44px' }}
            aria-label="Close dialog"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1">
          {/* Stale Warning Banner inside Detail Modal */}
          {isStale && (
            <div data-testid="detail-stale-banner" className="p-3.5 rounded-2xl bg-[#FFA028]/15 border border-[#FFA028]/40 text-[#FFA028] text-xs font-mono flex items-center justify-between gap-2.5">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 text-[#FFA028]" />
                <span>
                  STALE OBSERVATIONS: Server sync failed. Displaying cached data from {lastSuccessfulSyncStr || 'prior observation window'}.
                </span>
              </div>
              <button
                onClick={fetchData}
                className="px-3 py-1 rounded-xl bg-[#FFA028] text-black text-[11px] font-bold uppercase tracking-wider hover:bg-[#e68f20] transition-colors shrink-0"
              >
                Retry
              </button>
            </div>
          )}

          {loading ? (
            <div className="py-16 flex flex-col items-center justify-center text-[#8E9E93] gap-3">
              <RefreshCw className="w-6 h-6 animate-spin text-[#39FF14]" />
              <span className="text-xs font-mono">Fetching real-time observations...</span>
            </div>
          ) : (
            <>
              {/* Primary Estimation Box */}
              <div className={`p-5 rounded-2xl border grid grid-cols-2 sm:grid-cols-4 gap-4 backdrop-blur-md ${
                isStale ? 'bg-[#14100A]/80 border-[#FFA028]/30' : 'bg-[#090E0B]/70 border-white/[0.08]'
              }`}>
                <div>
                  <div className="text-[10px] uppercase font-mono tracking-widest text-[#8E9E93]">
                    Aggregated Wait
                  </div>
                  <div className={`font-mono text-3xl font-extrabold mt-0.5 ${
                    isStale ? 'text-[#FFA028]' : 'text-[#39FF14] drop-shadow-[0_0_12px_rgba(57,255,20,0.4)]'
                  }`}>
                    {estimate?.predictedWaitMinutes !== null && estimate?.predictedWaitMinutes !== undefined
                      ? `~${estimate.predictedWaitMinutes}m`
                      : '--'}
                  </div>
                  <div className="text-[9px] text-[#5A695F] font-mono mt-0.5">
                    {isStale ? 'Stale Estimate' : 'Statistical Estimate'}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] uppercase font-mono tracking-widest text-[#8E9E93]">
                    Queue Ahead
                  </div>
                  <div className={`font-mono text-3xl font-bold mt-0.5 ${
                    isStale ? 'text-[#FFA028]/90' : 'text-[#7DF9FF] drop-shadow-[0_0_12px_rgba(125,249,255,0.4)]'
                  }`}>
                    {estimate?.predictedQueueLength !== null && estimate?.predictedQueueLength !== undefined
                      ? `~${estimate.predictedQueueLength} ppl`
                      : '--'}
                  </div>
                  <div className="text-[9px] text-[#5A695F] font-mono mt-0.5">Calculated Load</div>
                </div>

                <div>
                  <div className="text-[10px] uppercase font-mono tracking-widest text-[#8E9E93]">
                    Confidence
                  </div>
                  <div className="mt-1.5">
                    {estimate && (
                      <ConfidenceMeter
                        confidence={estimate.confidence}
                        label={estimate.confidenceLabel}
                      />
                    )}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] uppercase font-mono tracking-widest text-[#8E9E93]">
                    Spread
                  </div>
                  <div className="font-mono text-base font-bold text-[#F4F7F5] mt-1.5">
                    {estimate ? `±${estimate.disagreementMinutes}m` : '--'}
                  </div>
                  <div className="text-[9px] text-[#5A695F] font-mono mt-0.5">Report Variation</div>
                </div>
              </div>

              {/* Latest Verified Crowdsourced Observation Section */}
              {latestReport && (
                <div className={`p-4 rounded-2xl border space-y-2 ${
                  isStale ? 'bg-[#14100A] border-[#FFA028]/35' : 'bg-[#0D1811] border-[#39FF14]/40 shadow-[0_0_20px_rgba(57,255,20,0.12)]'
                }`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] uppercase font-mono font-bold tracking-wider px-2.5 py-0.5 rounded-full ${
                        isStale ? 'bg-[#FFA028]/20 text-[#FFA028] border border-[#FFA028]/40' : 'bg-[#39FF14]/15 text-[#39FF14] border border-[#39FF14]/35'
                      }`}>
                        Latest Observation Record
                      </span>
                      <span className="text-[11px] font-mono text-[#8E9E93]">
                        {latestAgeStr}
                      </span>
                    </div>
                    <span className="text-[10px] font-mono text-[#5A695F] bg-white/[0.04] px-2 py-0.5 rounded">
                      ID: {latestReport.reportId}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-sm font-mono pt-1">
                    <div>
                      <span className="text-xs text-[#8E9E93] mr-1.5 font-sans">Observed wait:</span>
                      <strong className={`font-extrabold text-base ${isStale ? 'text-[#FFA028]' : 'text-[#39FF14]'}`}>
                        {latestReport.reportedWaitMinutes} min
                      </strong>
                    </div>
                    <span className="text-[#5A695F]">•</span>
                    <div>
                      <span className="text-xs text-[#8E9E93] mr-1.5 font-sans">Queue ahead:</span>
                      <strong className={`font-bold text-base ${isStale ? 'text-[#FFA028]/90' : 'text-[#7DF9FF]'}`}>
                        {latestReport.queueLength} people
                      </strong>
                    </div>
                  </div>
                  {latestReport.note && (
                    <div className="text-xs text-white bg-black/40 px-3 py-1.5 rounded-xl border border-white/10 italic">
                      "{latestReport.note}"
                    </div>
                  )}
                  <p className="text-[11px] text-[#8E9E93] pt-0.5 leading-relaxed">
                    This observation was saved in the database. The aggregated estimate above weights observations using time-decay (τ = 15m).
                  </p>
                </div>
              )}

              {/* Historical Best-Time-To-Go / Rush Hours */}
              {historical && (
                <div className="p-4 rounded-2xl bg-[#090E0B]/70 border border-white/[0.08] space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-[#7DF9FF]" />
                      <h4 className="font-display text-sm font-bold text-white">
                        Typical Wait Times by Hour
                      </h4>
                    </div>
                    <span className="text-[10px] font-mono text-[#5A695F]">
                      Past 14 Days (Asia/Kolkata)
                    </span>
                  </div>

                  {historical.status === 'insufficient_history' ? (
                    <div className="py-4 text-center text-xs font-mono text-[#8E9E93] bg-white/[0.02] rounded-xl border border-dashed border-white/10">
                      {historical.summary}
                    </div>
                  ) : (
                    <>
                      {/* Quietest & Busiest Badges */}
                      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                        {historical.quietestHour && (
                          <div className="p-2.5 rounded-xl bg-[#39FF14]/10 border border-[#39FF14]/30 flex items-center justify-between">
                            <span className="text-[#8E9E93]">Best time to go:</span>
                            <span className="text-[#39FF14] font-bold">
                              {historical.quietestHour.label} (~{historical.quietestHour.historicalAverageWaitMinutes ?? historical.quietestHour.averageWaitMinutes}m)
                            </span>
                          </div>
                        )}
                        {historical.busiestHour && (
                          <div className="p-2.5 rounded-xl bg-[#FFA028]/10 border border-[#FFA028]/30 flex items-center justify-between">
                            <span className="text-[#8E9E93]">Peak rush:</span>
                            <span className="text-[#FFA028] font-bold">
                              {historical.busiestHour.label} (~{historical.busiestHour.historicalAverageWaitMinutes ?? historical.busiestHour.averageWaitMinutes}m)
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Hourly Mini Histogram */}
                      <div className="pt-2">
                        <div className="flex items-end gap-1 h-20 w-full px-1">
                          {daytimeTrends.map((bucket) => {
                            const val = bucket.averageWaitMinutes || 0;
                            const heightPct = Math.max(10, Math.round((val / maxWaitInTrends) * 100));
                            const isPeak = historical.busiestHour?.hour === bucket.hour;
                            const isQuiet = historical.quietestHour?.hour === bucket.hour;

                            return (
                              <div
                                key={bucket.hour}
                                className="flex-1 flex flex-col items-center gap-1 group relative cursor-pointer"
                                title={`${bucket.label}: ~${val}m wait (${bucket.observationCount} reports)`}
                              >
                                <div
                                  className={`w-full rounded-t-sm transition-all duration-300 ${
                                    isPeak
                                      ? 'bg-[#FFA028]'
                                      : isQuiet
                                      ? 'bg-[#39FF14]'
                                      : val > 0
                                      ? 'bg-[#7DF9FF]/60 group-hover:bg-[#7DF9FF]'
                                      : 'bg-white/10'
                                  }`}
                                  style={{ height: `${heightPct}%` }}
                                />
                                <span className="text-[8px] font-mono text-[#5A695F]">
                                  {bucket.hour % 3 === 0 ? bucket.hour : ''}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                        <div className="flex justify-between text-[9px] font-mono text-[#5A695F] pt-1 px-1">
                          <span>08:00</span>
                          <span>14:00</span>
                          <span>22:00</span>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Algorithm Rationale Notice */}
              {estimate && (
                <div className="p-4 rounded-2xl bg-[#131C15]/70 border border-white/[0.08] text-xs text-[#8E9E93] flex items-start gap-3">
                  <AlertCircle className="w-4 h-4 text-[#7DF9FF] shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-white font-mono uppercase tracking-wide">
                      Statistical Aggregation:{' '}
                    </span>
                    <span>{estimate.evidenceExplanation}</span>
                  </div>
                </div>
              )}

              {/* Operating Specs */}
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3.5 rounded-2xl bg-[#090E0B]/60 border border-white/[0.06] flex items-center gap-2.5">
                  <Clock className="w-4 h-4 text-[#7DF9FF]" />
                  <div>
                    <div className="text-[10px] uppercase font-mono text-[#5A695F]">Operating Hours</div>
                    <div className="text-white font-mono font-medium">{location?.openHours}</div>
                  </div>
                </div>

                <div className="p-3.5 rounded-2xl bg-[#090E0B]/60 border border-white/[0.06] flex items-center gap-2.5">
                  <Users className="w-4 h-4 text-[#39FF14]" />
                  <div>
                    <div className="text-[10px] uppercase font-mono text-[#5A695F]">Capacity Estimate</div>
                    <div className="text-white font-mono font-medium">{location?.capacityEstimate || `${location?.capacity} students approx.`}</div>
                  </div>
                </div>
              </div>

              {/* Recent Observations Feed */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-display text-sm font-bold text-white flex items-center gap-2">
                    <History className="w-4 h-4 text-[#39FF14]" />
                    <span>Observation History ({reports.length})</span>
                  </h4>
                  <span className="text-[11px] font-mono text-[#5A695F]">
                    Decay window: 60m max
                  </span>
                </div>

                {reports.length === 0 ? (
                  <div className="py-10 text-center border border-dashed border-white/10 rounded-2xl text-[#8E9E93] text-xs font-mono">
                    No active observations within 60 minutes.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {reports.map((r) => {
                      const ageMin = Math.round(
                        (Date.now() - new Date(r.timestamp).getTime()) / (60 * 1000)
                      );
                      const ageText = ageMin <= 1 ? 'Just now' : `${ageMin}m ago`;

                      return (
                        <div
                          key={r.reportId}
                          className="p-3.5 rounded-2xl bg-[#090E0B]/50 border border-white/[0.06] flex items-center justify-between gap-4 text-xs font-mono hover:border-white/20 transition-colors"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-3">
                              <span className="text-[#39FF14] font-bold text-sm">
                                {r.reportedWaitMinutes}m wait
                              </span>
                              <span className="text-[#7DF9FF]">
                                {r.queueLength} in queue
                              </span>
                              <span className="text-[10px] text-[#5A695F]">
                                ({ageText})
                              </span>
                            </div>
                            {r.note && (
                              <div className="text-[11px] text-[#8E9E93] font-sans italic">
                                "{r.note}"
                              </div>
                            )}
                          </div>
                          <span className="text-[9px] text-[#5A695F] shrink-0">
                            {r.reportId}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-4 border-t border-white/[0.08] bg-[#070A08]/90 flex items-center justify-between">
          <button
            onClick={fetchData}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-mono text-[#8E9E93] hover:text-white hover:bg-white/[0.04] transition-colors min-h-[44px]"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>

          <button
            onClick={() => {
              onClose();
              onOpenReportModal(locationId);
            }}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-mono text-xs uppercase tracking-wider font-bold bg-[#39FF14] text-black shadow-[0_0_20px_rgba(57,255,20,0.4)] hover:bg-[#32e012] transition-colors min-h-[44px]"
          >
            <Plus className="w-4 h-4" />
            <span>Submit Observation</span>
          </button>
        </div>
      </div>
    </div>
  );
};
