import React, { useEffect, useState } from 'react';
import { QueueReport } from '../types';
import { api } from '../services/api';
import { X, ShieldCheck, RefreshCw } from 'lucide-react';

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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#070A08]/85 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-3xl max-h-[85vh] rounded-3xl glass-panel-elevated shadow-2xl flex flex-col overflow-hidden glass-specular-edge border-[#7DF9FF]/30">
        {/* Header */}
        <div className="p-6 border-b border-white/[0.08] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-[#7DF9FF]/10 border border-[#7DF9FF]/30 text-[#7DF9FF] shadow-[0_0_15px_rgba(125,249,255,0.25)]">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-display text-xl font-extrabold text-white tracking-tight">
                  Campus Queue Audit Stream
                </h3>
                <span className="text-[10px] font-mono uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-[#7DF9FF]/15 text-[#7DF9FF] border border-[#7DF9FF]/40">
                  Read-Only
                </span>
              </div>
              <p className="text-xs text-[#8E9E93] mt-0.5">
                Centralized stream of crowdsourced observations across campus dining halls.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-[#8E9E93] hover:text-white hover:bg-white/[0.06] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Audit Stats Banner */}
        <div className="px-6 py-3.5 bg-[#090E0B]/80 border-b border-white/[0.08] flex items-center justify-between text-xs font-mono">
          <div className="flex items-center gap-4">
            <span className="text-[#8E9E93]">
              Indexed Observations: <strong className="text-white">{reports.length}</strong>
            </span>
            <span className="text-[#8E9E93] flex items-center gap-1.5">
              Storage Source:{' '}
              {isLive ? (
                <span className="text-[#39FF14]">DynamoDB Single-Table</span>
              ) : (
                <span className="text-[#FFA028]">In-Memory Mock Store</span>
              )}
            </span>
          </div>

          <button
            onClick={fetchReports}
            className="flex items-center gap-1.5 px-3 py-1 rounded-xl btn-glass hover:border-[#7DF9FF]/40 text-xs text-[#7DF9FF] transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Sync</span>
          </button>
        </div>

        {/* Feed Timeline */}
        <div className="p-6 overflow-y-auto space-y-2.5 flex-1">
          {loading ? (
            <div className="py-16 flex flex-col items-center justify-center text-[#8E9E93] gap-2">
              <RefreshCw className="w-5 h-5 animate-spin text-[#7DF9FF]" />
              <span className="text-xs font-mono">Streaming queue audit entries...</span>
            </div>
          ) : reports.length === 0 ? (
            <div className="py-16 text-center text-[#5A695F] text-xs font-mono">
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
                  className="p-3.5 rounded-2xl bg-[#090E0B]/70 border border-white/[0.06] flex items-center justify-between gap-3 text-xs hover:border-white/20 transition-colors"
                >
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="text-[10px] uppercase font-mono px-2.5 py-0.5 rounded-md bg-white/[0.05] text-[#8E9E93] border border-white/10">
                      {r.locationId}
                    </span>
                    <span className="font-mono font-bold text-[#39FF14]">
                      {r.reportedWaitMinutes}m wait
                    </span>
                    <span className="text-[#5A695F]">•</span>
                    <span className="font-mono text-[#F4F7F5]">{r.queueLength} in queue</span>
                    {r.note && (
                      <>
                        <span className="text-[#5A695F]">•</span>
                        <span className="text-[#8E9E93] italic truncate max-w-xs">
                          "{r.note}"
                        </span>
                      </>
                    )}
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-[11px] font-mono text-[#8E9E93]">
                      {formattedTime}
                    </span>
                    <span className="text-[10px] font-mono text-[#5A695F] bg-white/[0.03] px-2 py-0.5 rounded">
                      {r.reportId.slice(0, 10)}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="p-4 px-6 border-t border-white/[0.08] bg-[#090E0B]/80 flex items-center justify-between text-xs text-[#8E9E93] font-mono">
          <span>Protected operations view. No personal data collected or stored.</span>
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl btn-glass"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
