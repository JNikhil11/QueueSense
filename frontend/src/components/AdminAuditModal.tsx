import React, { useEffect, useState } from 'react';
import { QueueReport } from '../types';
import { api } from '../services/api';
import { X, ShieldAlert, RefreshCw } from 'lucide-react';

interface AdminAuditModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AdminAuditModal: React.FC<AdminAuditModalProps> = ({ isOpen, onClose }) => {
  const [reports, setReports] = useState<QueueReport[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isLive, setIsLive] = useState<boolean>(false);

  const fetchReports = async () => {
    try {
      setLoading(true);
      const res = await api.getAdminReports();
      setReports(res.reports);
      setIsLive(res.isLive);
    } catch (err) {
      console.error('Failed to load admin audit feed:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchReports();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-3xl max-h-[85vh] rounded-2xl bg-surface-card border border-surface-border shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-surface-border flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-neon-blue/10 border border-neon-blue/30 text-neon-blue">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-display text-lg font-bold text-white flex items-center gap-2">
                <span>Campus Queue Audit Feed</span>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-surface-elevated text-neon-blue border border-neon-blue/30">
                  Read-Only Audit
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Centralized stream of crowdsourced observations across campus dining halls.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-surface-elevated transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Audit Stats Banner */}
        <div className="px-5 py-3 bg-surface-base border-b border-surface-border flex items-center justify-between text-xs">
          <div className="flex items-center gap-4">
            <span className="text-slate-400">
              Total Observations: <strong className="text-white font-mono">{reports.length}</strong>
            </span>
            <span className="text-slate-400 flex items-center gap-1.5">
              Source:{' '}
              {isLive ? (
                <span className="text-neon-green font-mono">Live DynamoDB Table</span>
              ) : (
                <span className="text-amber-400 font-mono">In-Memory Mock Store</span>
              )}
            </span>
          </div>

          <button
            onClick={fetchReports}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-surface-elevated hover:bg-surface-subtle text-slate-300 hover:text-white border border-surface-border transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>

        {/* Feed Table */}
        <div className="p-5 overflow-y-auto space-y-2 flex-1">
          {loading ? (
            <div className="py-12 flex flex-col items-center justify-center text-slate-400 gap-2">
              <RefreshCw className="w-5 h-5 animate-spin text-neon-blue" />
              <span className="text-xs font-mono">Loading campus report log...</span>
            </div>
          ) : reports.length === 0 ? (
            <div className="py-12 text-center text-slate-400 text-xs font-mono">
              No reports currently recorded in database.
            </div>
          ) : (
            reports.map((r) => {
              const dateObj = new Date(r.timestamp);
              const formattedTime = dateObj.toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              });

              return (
                <div
                  key={r.reportId}
                  className="p-3 rounded-xl bg-surface-base border border-surface-border flex items-center justify-between gap-3 text-xs"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-surface-elevated text-slate-300 border border-surface-border">
                      {r.locationId}
                    </span>
                    <span className="font-mono font-bold text-neon-green">
                      {r.reportedWaitMinutes} min
                    </span>
                    <span className="text-slate-500">•</span>
                    <span className="font-mono text-slate-300">{r.queueLength} people</span>
                    {r.note && (
                      <>
                        <span className="text-slate-500">•</span>
                        <span className="text-slate-400 italic truncate max-w-xs">
                          "{r.note}"
                        </span>
                      </>
                    )}
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[11px] font-mono text-slate-400">
                      {formattedTime}
                    </span>
                    <span className="text-[10px] font-mono text-slate-500 bg-surface-elevated px-1.5 py-0.5 rounded">
                      {r.reportId.slice(0, 10)}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-surface-border bg-surface-card flex items-center justify-between text-xs text-slate-400">
          <span>Protected operations view. No personal data collected or stored.</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-surface-elevated hover:bg-surface-subtle text-slate-200 border border-surface-border"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
