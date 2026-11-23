import React, { useEffect, useState } from 'react';
import { CampusLocation, QueueEstimate, QueueReport } from '../types';
import { api } from '../services/api';
import { CongestionBadge, FreshnessBadge, ConfidenceMeter } from './StatusBadge';
import { X, Clock, Users, Plus, AlertCircle, History, RefreshCw } from 'lucide-react';

interface OutletDetailModalProps {
  locationId: string | null;
  onClose: () => void;
  onOpenReportModal: (locationId: string) => void;
}

export const OutletDetailModal: React.FC<OutletDetailModalProps> = ({
  locationId,
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
  }, [locationId]);

  if (!locationId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#070A08]/85 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-2xl max-h-[90vh] rounded-3xl glass-panel-elevated shadow-2xl flex flex-col overflow-hidden glass-specular-edge border-[#39FF14]/25">
        {/* Header */}
        <div className="p-6 border-b border-white/[0.08] flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[10px] uppercase font-mono font-bold tracking-wider px-2.5 py-0.5 rounded-full bg-[#7DF9FF]/10 text-[#7DF9FF] border border-[#7DF9FF]/30">
                {location?.category || 'OUTLET'}
              </span>
              {estimate && <FreshnessBadge state={estimate.freshness} />}
              {estimate && <CongestionBadge level={estimate.congestion} />}
            </div>
            <h2 className="font-display text-2xl font-extrabold text-white tracking-tight">
              {location?.name || 'Loading outlet...'}
            </h2>
            <p className="text-xs text-[#8E9E93] mt-1 max-w-lg leading-relaxed">
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
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
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
                    Estimated Wait
                  </div>
                  <div className="font-mono text-3xl font-extrabold text-[#39FF14] mt-0.5 drop-shadow-[0_0_12px_rgba(57,255,20,0.4)]">
                    {estimate?.predictedWaitMinutes !== null && estimate?.predictedWaitMinutes !== undefined
                      ? `~${estimate.predictedWaitMinutes}m`
                      : '--'}
                  </div>
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
                </div>
              </div>

              {/* Algorithm Rationale Notice */}
              {estimate && (
                <div className="p-4 rounded-2xl bg-[#131C15]/70 border border-white/[0.08] text-xs text-[#8E9E93] flex items-start gap-3">
                  <AlertCircle className="w-4 h-4 text-[#7DF9FF] shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-white font-mono uppercase tracking-wide">
                      Algorithm Rationale:{' '}
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
                    <span>Recent Observations ({reports.length})</span>
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
                      const timeStr = ageMin <= 1 ? 'Just now' : `${ageMin}m ago`;

                      return (
                        <div
                          key={r.reportId}
                          className="p-3.5 rounded-2xl bg-[#090E0B]/80 border border-white/[0.06] flex items-start justify-between gap-3 text-xs hover:border-[#39FF14]/30 transition-colors"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
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
