import React, { useEffect, useState } from 'react';
import { CampusLocation, QueueEstimate, QueueReport } from '../types';
import { api } from '../services/api';
import { CongestionBadge, FreshnessBadge, ConfidenceMeter } from './StatusBadge';
import { X, Clock, Users, Plus, AlertCircle, History, RefreshCw, MapPin, CheckCircle2 } from 'lucide-react';

interface OutletDetailModalProps {
  locationId: string | null;
  refreshTrigger?: number;
  onClose: () => void;
  onOpenReportModal: (locationId: string) => void;
}

export const OutletDetailModal: React.FC<OutletDetailModalProps> = ({
  locationId,
  refreshTrigger,
  onClose,
  onOpenReportModal,
}) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [location, setLocation] = useState<CampusLocation | null>(null);
  const [estimate, setEstimate] = useState<QueueEstimate | null>(null);
  const [reports, setReports] = useState<QueueReport[]>([]);
  const [isLive, setIsLive] = useState<boolean>(false);

  const fetchData = async () => {
    if (!locationId) return;
    try {
      setLoading(true);
      const res = await api.getLocationQueue(locationId);
      setLocation(res.location);
      setEstimate(res.estimate);
      setReports(res.reports);
      setIsLive(res.isLive);
    } catch (err) {
      console.error('Failed to load outlet details:', err);
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#070A08]/85 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-2xl max-h-[90vh] rounded-3xl glass-panel-elevated shadow-2xl flex flex-col overflow-hidden glass-specular-edge border-[#39FF14]/30">
        {/* Header */}
        <div className="p-6 border-b border-white/[0.08] flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="text-[10px] uppercase font-mono font-bold tracking-wider px-2.5 py-0.5 rounded-full bg-[#7DF9FF]/10 text-[#7DF9FF] border border-[#7DF9FF]/30">
                {location?.category || 'OUTLET'}
              </span>
              {location?.verificationStatus === 'VERIFIED_CAMPUS_DIRECTORY' && (
                <span className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/[0.04] text-[#8E9E93] border border-white/10" title={location?.verificationSource}>
                  <CheckCircle2 className="w-3 h-3 text-[#39FF14]" />
                  <span>Verified Campus Directory</span>
                </span>
              )}
              {estimate && <FreshnessBadge state={estimate.freshness} />}
              {estimate && <CongestionBadge level={estimate.congestion} />}
            </div>
            <h2 className="font-display text-2xl font-extrabold text-white tracking-tight">
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
            className="p-2 rounded-xl text-[#8E9E93] hover:text-white hover:bg-white/[0.06] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1">
          {loading ? (
            <div className="py-16 flex flex-col items-center justify-center text-[#8E9E93] gap-3">
              <RefreshCw className="w-6 h-6 animate-spin text-[#39FF14]" />
              <span className="text-xs font-mono">Fetching real-time observations...</span>
            </div>
          ) : (
            <>
              {/* Primary Estimation Box */}
              <div className="p-5 rounded-2xl bg-[#090E0B]/70 border border-white/[0.08] grid grid-cols-2 sm:grid-cols-4 gap-4 backdrop-blur-md">
                <div>
                  <div className="text-[10px] uppercase font-mono tracking-widest text-[#8E9E93]">
                    Aggregated Wait
                  </div>
                  <div className="font-mono text-3xl font-extrabold text-[#39FF14] mt-0.5 drop-shadow-[0_0_12px_rgba(57,255,20,0.4)]">
                    {estimate?.predictedWaitMinutes !== null && estimate?.predictedWaitMinutes !== undefined
                      ? `~${estimate.predictedWaitMinutes}m`
                      : '--'}
                  </div>
                  <div className="text-[9px] text-[#5A695F] font-mono mt-0.5">Statistical Estimate</div>
                </div>

                <div>
                  <div className="text-[10px] uppercase font-mono tracking-widest text-[#8E9E93]">
                    Queue Ahead
                  </div>
                  <div className="font-mono text-3xl font-bold text-[#7DF9FF] mt-0.5 drop-shadow-[0_0_12px_rgba(125,249,255,0.4)]">
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
                <div className="p-4 rounded-2xl bg-[#0D1811] border border-[#39FF14]/40 space-y-2 shadow-[0_0_20px_rgba(57,255,20,0.12)]">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] uppercase font-mono font-bold tracking-wider px-2.5 py-0.5 rounded-full bg-[#39FF14]/15 text-[#39FF14] border border-[#39FF14]/35">
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
                      <strong className="text-[#39FF14] font-extrabold text-base">{latestReport.reportedWaitMinutes} min</strong>
                    </div>
                    <span className="text-[#5A695F]">•</span>
                    <div>
                      <span className="text-xs text-[#8E9E93] mr-1.5 font-sans">Queue ahead:</span>
                      <strong className="text-[#7DF9FF] font-bold text-base">{latestReport.queueLength} people</strong>
                    </div>
                  </div>
                  {latestReport.note && (
                    <div className="text-xs text-white bg-black/40 px-3 py-1.5 rounded-xl border border-white/10 italic">
                      "{latestReport.note}"
                    </div>
                  )}
                  <p className="text-[11px] text-[#8E9E93] pt-0.5 leading-relaxed">
                    This exact observation is saved in the database. The aggregated estimate above weights this alongside previous observations using time-decay (τ = 15m).
                  </p>
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
                    <div className="text-[10px] uppercase font-mono text-[#5A695F]">Seating Capacity</div>
                    <div className="text-white font-mono font-medium">{location?.capacity} students</div>
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
                    {reports.map((r, index) => {
                      const ageMin = Math.round(
                        (Date.now() - new Date(r.timestamp).getTime()) / (60 * 1000)
                      );
                      const timeStr = ageMin <= 1 ? 'Just now' : `${ageMin}m ago`;
                      const isFirst = index === 0;

                      return (
                        <div
                          key={r.reportId}
                          className={`p-3.5 rounded-2xl bg-[#090E0B]/80 border ${
                            isFirst ? 'border-[#39FF14]/40 bg-[#0C150E]/90' : 'border-white/[0.06]'
                          } flex items-start justify-between gap-3 text-xs hover:border-[#39FF14]/30 transition-colors`}
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              {isFirst && (
                                <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-[#39FF14]/20 text-[#39FF14] font-bold">
                                  Latest
                                </span>
                              )}
                              <span className="font-mono font-bold text-[#39FF14]">
                                {r.reportedWaitMinutes}m wait
                              </span>
                              <span className="text-[#5A695F]">•</span>
                              <span className="font-mono text-[#F4F7F5]">
                                {r.queueLength} in line
                              </span>
                              <span className="text-[#5A695F]">•</span>
                              <span className="font-mono text-[11px] text-[#8E9E93]">
                                {timeStr}
                              </span>
                            </div>
                            {r.note && (
                              <p className="text-[#8E9E93] italic">"{r.note}"</p>
                            )}
                          </div>
                          <span className="text-[10px] font-mono text-[#5A695F] shrink-0 px-2 py-0.5 rounded bg-white/[0.03]">
                            {r.reportId.slice(0, 10)}
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
        <div className="p-5 border-t border-white/[0.08] bg-[#090E0B]/80 flex items-center justify-between gap-3">
          <span className="text-[11px] text-[#5A695F] font-mono">
            {isLive ? 'AWS Cloud Synchronized' : 'Offline Simulation Fixture'}
          </span>
          <button
            onClick={() => onOpenReportModal(locationId)}
            className="flex items-center gap-2 px-5 py-2.5 text-xs sm:text-sm btn-electric"
          >
            <Plus className="w-4 h-4 stroke-[2.5]" />
            <span>Add Observation</span>
          </button>
        </div>
      </div>
    </div>
  );
};
