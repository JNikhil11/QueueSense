import React, { useEffect, useState } from 'react';
import { CampusLocation, QueueEstimate, QueueReport } from '../types';
import { api } from '../services/api';
import { CongestionBadge, FreshnessBadge, ConfidenceMeter } from './StatusBadge';
import { X, Clock, Users, PlusCircle, AlertCircle, History, RefreshCw } from 'lucide-react';

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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-2xl max-h-[90vh] rounded-2xl bg-surface-card border border-surface-border shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-surface-border flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] uppercase font-mono font-bold tracking-wider px-2 py-0.5 rounded bg-surface-elevated border border-surface-border text-neon-blue">
                {location?.category || 'OUTLET'}
              </span>
              {estimate && <FreshnessBadge state={estimate.freshness} />}
              {estimate && <CongestionBadge level={estimate.congestion} />}
            </div>
            <h2 className="font-display text-xl sm:text-2xl font-bold text-white tracking-tight">
              {location?.name || 'Loading outlet...'}
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-lg">
              {location?.description}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-surface-elevated transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto space-y-6 flex-1">
          {loading ? (
            <div className="py-12 flex flex-col items-center justify-center text-slate-400 gap-3">
              <RefreshCw className="w-6 h-6 animate-spin text-neon-green" />
              <span className="text-xs font-mono">Fetching real-time observations...</span>
            </div>
          ) : (
            <>
              {/* Primary Estimation Box */}
              <div className="p-5 rounded-xl bg-surface-base border border-surface-border grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div>
                  <div className="text-[10px] uppercase font-mono tracking-wider text-slate-400">
                    Estimated Wait
                  </div>
                  <div className="font-mono text-2xl font-bold text-neon-green mt-0.5">
                    {estimate?.predictedWaitMinutes !== null && estimate?.predictedWaitMinutes !== undefined
                      ? `~${estimate.predictedWaitMinutes}m`
                      : '--'}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] uppercase font-mono tracking-wider text-slate-400">
                    Queue Ahead
                  </div>
                  <div className="font-mono text-2xl font-bold text-neon-blue mt-0.5">
                    {estimate?.predictedQueueLength !== null && estimate?.predictedQueueLength !== undefined
                      ? `~${estimate.predictedQueueLength} ppl`
                      : '--'}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] uppercase font-mono tracking-wider text-slate-400">
                    Confidence
                  </div>
                  <div className="mt-1">
                    {estimate && (
                      <ConfidenceMeter
                        confidence={estimate.confidence}
                        label={estimate.confidenceLabel}
                      />
                    )}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] uppercase font-mono tracking-wider text-slate-400">
                    Disagreement
                  </div>
                  <div className="font-mono text-base font-semibold text-slate-300 mt-1">
                    {estimate ? `±${estimate.disagreementMinutes}m` : '--'}
                  </div>
                </div>
              </div>

              {/* Evidence Explanation Alert */}
              {estimate && (
                <div className="p-3.5 rounded-xl bg-surface-elevated/70 border border-surface-border text-xs text-slate-300 flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 text-neon-blue shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-white">Algorithm Rationale: </span>
                    {estimate.evidenceExplanation}
                  </div>
                </div>
              )}

              {/* Operating Specs */}
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-surface-elevated border border-surface-border flex items-center gap-2">
                  <Clock className="w-4 h-4 text-slate-400" />
                  <div>
                    <div className="text-[10px] uppercase font-mono text-slate-400">Hours</div>
                    <div className="text-white font-medium">{location?.openHours}</div>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-surface-elevated border border-surface-border flex items-center gap-2">
                  <Users className="w-4 h-4 text-slate-400" />
                  <div>
                    <div className="text-[10px] uppercase font-mono text-slate-400">Capacity</div>
                    <div className="text-white font-medium">{location?.capacity} seating</div>
                  </div>
                </div>
              </div>

              {/* Recent Observations Feed */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-display text-sm font-bold text-white flex items-center gap-2">
                    <History className="w-4 h-4 text-neon-green" />
                    <span>Recent Observations ({reports.length})</span>
                  </h4>
                  <span className="text-[11px] font-mono text-slate-400">
                    Max age 60 minutes
                  </span>
                </div>

                {reports.length === 0 ? (
                  <div className="py-8 text-center border border-dashed border-surface-border rounded-xl text-slate-400 text-xs">
                    No observations recorded recently. Be the first to submit a report!
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
                          className="p-3 rounded-xl bg-surface-base border border-surface-border flex items-start justify-between gap-3 text-xs"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <span className="font-mono font-bold text-neon-green">
                                {r.reportedWaitMinutes} min wait
                              </span>
                              <span className="text-slate-500">•</span>
                              <span className="font-mono text-slate-300">
                                {r.queueLength} in line
                              </span>
                              <span className="text-slate-500">•</span>
                              <span className="font-mono text-[11px] text-slate-400">
                                {timeStr}
                              </span>
                            </div>
                            {r.note && (
                              <p className="text-slate-300 italic">"{r.note}"</p>
                            )}
                          </div>
                          <span className="text-[10px] font-mono text-slate-500 shrink-0">
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
        <div className="p-4 border-t border-surface-border bg-surface-card flex items-center justify-between gap-3">
          <span className="text-[11px] text-slate-400 font-mono">
            {isLive ? 'Connected to live AWS API' : 'Viewing local mock fixtures'}
          </span>
          <button
            onClick={() => onOpenReportModal(locationId)}
            className="flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-semibold rounded-xl bg-neon-green hover:bg-[#2fe07c] text-slate-950 shadow-glow-green transition-all"
          >
            <PlusCircle className="w-4 h-4" />
            <span>Add Observation</span>
          </button>
        </div>
      </div>
    </div>
  );
};
