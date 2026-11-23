import React, { useEffect, useState } from 'react';
import { QueueReport } from '../types';
import { api } from '../services/api';
import { X, ShieldCheck, RefreshCw, Key, AlertCircle, Lock } from 'lucide-react';

interface AdminAuditModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AdminAuditModal: React.FC<AdminAuditModalProps> = ({ isOpen, onClose }) => {
  const [reports, setReports] = useState<QueueReport[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isLive, setIsLive] = useState<boolean>(false);
  const [isUnauthorized, setIsUnauthorized] = useState<boolean>(false);
  const [adminKey, setAdminKey] = useState<string>(() => {
    return (
      (typeof localStorage !== 'undefined' ? localStorage.getItem('queuesense_admin_key') : '') ||
      ''
    );
  });
  const [authError, setAuthError] = useState<string | null>(null);

  const fetchReports = async (keyToUse?: string) => {
    try {
      setLoading(true);
      setIsUnauthorized(false);
      setAuthError(null);
      const res = await api.getAdminReports(keyToUse || adminKey);
      setReports(res.reports);
      setIsLive(res.isLive);
    } catch (err: any) {
      if (err.message === 'UNAUTHORIZED') {
        setIsUnauthorized(true);
      } else {
        setAuthError(err.message || 'Failed to load admin audit feed.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleKeySubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!adminKey.trim()) return;
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('queuesense_admin_key', adminKey.trim());
    }
    fetchReports(adminKey.trim());
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
                  Protected Admin View
                </span>
              </div>
              <p className="text-xs text-[#8E9E93] mt-0.5">
                Centralized operational stream of crowdsourced observations across campus dining halls.
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

          {!isUnauthorized && (
            <button
              onClick={() => fetchReports()}
              className="flex items-center gap-1.5 px-3 py-1 rounded-xl btn-glass hover:border-[#7DF9FF]/40 text-xs text-[#7DF9FF] transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Sync</span>
            </button>
          )}
        </div>

        {/* Feed Timeline or Auth Screen */}
        <div className="p-6 overflow-y-auto space-y-2.5 flex-1">
          {isUnauthorized ? (
            <div className="py-12 flex flex-col items-center justify-center max-w-md mx-auto text-center space-y-4">
              <div className="p-3.5 rounded-2xl bg-[#CC162D]/15 border border-[#CC162D]/40 text-[#FF4A60] shadow-[0_0_15px_rgba(204,22,45,0.3)]">
                <Lock className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-bold text-white font-display">
                  Admin Authorization Required
                </h4>
                <p className="text-xs text-[#8E9E93] mt-1 leading-relaxed">
                  The <code className="text-[#7DF9FF]">GET /admin/reports</code> endpoint is secured. Enter your admin API key to unlock the audit feed.
                </p>
              </div>

              <form onSubmit={handleKeySubmit} className="w-full space-y-3 pt-2">
                <div className="relative">
                  <Key className="w-4 h-4 text-[#8E9E93] absolute left-3 top-3" />
                  <input
                    type="password"
                    placeholder="Enter Admin API Key..."
                    value={adminKey}
                    onChange={(e) => setAdminKey(e.target.value)}
                    className="w-full pl-9 pr-3 py-2.5 bg-black/50 border border-white/15 rounded-xl text-white font-mono text-xs focus:outline-none focus:border-[#7DF9FF]"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full py-2.5 px-4 rounded-xl bg-[#7DF9FF] text-black font-mono text-xs font-bold uppercase tracking-wider hover:bg-[#68e0e6] transition-colors shadow-[0_0_15px_rgba(125,249,255,0.3)]"
                >
                  Authenticate & Unlock
                </button>
              </form>
            </div>
          ) : authError ? (
            <div className="py-12 text-center text-[#FF4A60] text-xs font-mono space-y-2">
              <AlertCircle className="w-6 h-6 mx-auto text-[#FF4A60]" />
              <div>{authError}</div>
              <button
                onClick={() => fetchReports()}
                className="mt-3 px-4 py-1.5 rounded-xl btn-glass text-white text-xs"
              >
                Retry
              </button>
            </div>
          ) : loading ? (
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
                    <span className="font-mono text-[#39FF14] font-bold">
                      {r.reportedWaitMinutes}m wait
                    </span>
                    <span className="text-[#7DF9FF] font-mono">
                      {r.queueLength} queue
                    </span>
                    {r.note && (
                      <span className="text-[#8E9E93] italic font-sans max-w-xs truncate">
                        "{r.note}"
                      </span>
                    )}
                    {r.isOutlier && (
                      <span className="text-[9px] uppercase font-mono px-2 py-0.5 rounded bg-[#CC162D]/20 text-[#FF4A60] border border-[#CC162D]/40">
                        Outlier Filtered
                      </span>
                    )}
                  </div>

                  <div className="text-right shrink-0">
                    <div className="text-[10px] font-mono text-[#5A695F]">{formattedTime}</div>
                    <div className="text-[9px] font-mono text-[#3D4740]">{r.reportId}</div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
