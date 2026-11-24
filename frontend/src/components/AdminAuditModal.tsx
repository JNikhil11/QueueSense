import React, { useEffect, useState } from 'react';
import { QueueReport } from '../types';
import { api } from '../services/api';
import { X, ShieldCheck, RefreshCw, Key, AlertCircle, Lock } from 'lucide-react';
import { useFocusTrap } from '../hooks/useFocusTrap';

interface AdminAuditModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AdminAuditModal: React.FC<AdminAuditModalProps> = ({ isOpen, onClose }) => {
  const [reports, setReports] = useState<QueueReport[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isLive, setIsLive] = useState<boolean>(false);
  const [isUnauthorized, setIsUnauthorized] = useState<boolean>(false);
  const [adminToken, setAdminToken] = useState<string>(() => {
    try {
      if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
        return localStorage.getItem('queuesense_admin_token') || '';
      }
    } catch {
      // Storage access blocked or throws SecurityError
    }
    return '';
  });
  const [authError, setAuthError] = useState<string | null>(null);

  // WCAG 2.2 AA Focus Trapping & Restoration
  const containerRef = useFocusTrap<HTMLDivElement>({
    isOpen,
    onClose,
    autoFocusSelector: 'input[type="password"], button[aria-label="Close dialog"]',
  });

  const fetchReports = async (tokenToUse?: string) => {
    try {
      setLoading(true);
      setIsUnauthorized(false);
      setAuthError(null);
      const res = await api.getAdminReports(tokenToUse || adminToken);
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

  const handleTokenSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!adminToken.trim()) return;
    try {
      if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
        localStorage.setItem('queuesense_admin_token', adminToken.trim());
      }
    } catch {
      // Safe fallback if storage throws SecurityError
    }
    fetchReports(adminToken.trim());
  };

  useEffect(() => {
    if (isOpen) {
      fetchReports();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      ref={containerRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="admin-audit-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#070A08]/85 backdrop-blur-md animate-fade-in"
    >
      <div className="w-full max-w-3xl max-h-[85vh] rounded-3xl glass-panel-elevated shadow-2xl flex flex-col overflow-hidden glass-specular-edge border-[#7DF9FF]/30 animate-modal-in">
        {/* Header */}
        <div className="p-6 border-b border-white/[0.08] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-[#7DF9FF]/10 border border-[#7DF9FF]/30 text-[#7DF9FF] shadow-[0_0_15px_rgba(125,249,255,0.25)]">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 id="admin-audit-title" className="font-display text-xl font-extrabold text-white tracking-tight">
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
            className="p-2.5 rounded-xl text-[#8E9E93] hover:text-white hover:bg-white/[0.06] transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
            aria-label="Close dialog"
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
              className="flex items-center gap-1.5 px-3 py-1 rounded-xl btn-glass hover:border-[#7DF9FF]/40 text-xs text-[#7DF9FF] transition-colors min-h-[44px]"
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
                  Cognito Admin Authorization Required
                </h4>
                <p className="text-xs text-[#8E9E93] mt-1 leading-relaxed">
                  The <code className="text-[#7DF9FF]">GET /admin/reports</code> endpoint is protected by AWS Cognito User Pool with an <code className="text-[#7DF9FF]">Admins</code> group policy. Enter your authenticated operator JWT token to unlock the live audit stream.
                </p>
              </div>

              <form onSubmit={handleTokenSubmit} className="w-full space-y-3 pt-2">
                <div className="relative">
                  <Key className="w-4 h-4 text-[#8E9E93] absolute left-3 top-3.5" />
                  <input
                    type="password"
                    aria-label="Cognito Operator Bearer Token"
                    placeholder="Enter Cognito Operator Bearer Token..."
                    value={adminToken}
                    onChange={(e) => setAdminToken(e.target.value)}
                    className="w-full pl-9 pr-3 py-2.5 bg-black/50 border border-white/15 rounded-xl text-white font-mono text-xs focus:outline-none focus:border-[#7DF9FF] min-h-[44px]"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full py-2.5 px-4 rounded-xl bg-[#7DF9FF] text-black font-mono text-xs font-bold uppercase tracking-wider hover:bg-[#68e0e6] transition-colors shadow-[0_0_15px_rgba(125,249,255,0.3)] min-h-[44px] flex items-center justify-center"
                >
                  Verify Cognito Token & Unlock
                </button>
              </form>
            </div>
          ) : authError ? (
            <div role="alert" className="py-12 text-center text-[#FF4A60] text-xs font-mono space-y-2">
              <AlertCircle className="w-6 h-6 mx-auto text-[#FF4A60]" />
              <div>{authError}</div>
              <button
                onClick={() => fetchReports()}
                className="mt-3 px-4 py-2 rounded-xl btn-glass text-white text-xs min-h-[44px]"
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
