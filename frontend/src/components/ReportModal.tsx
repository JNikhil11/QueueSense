import React, { useState, useEffect } from 'react';
import { CampusLocation, ReportSubmissionPayload } from '../types';
import { X, Send, AlertTriangle, CheckCircle2, Clock, Users } from 'lucide-react';

interface ReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  locations: CampusLocation[];
  initialLocationId?: string;
  onSubmit: (locationId: string, payload: ReportSubmissionPayload) => Promise<void>;
}

export const ReportModal: React.FC<ReportModalProps> = ({
  isOpen,
  onClose,
  locations,
  initialLocationId,
  onSubmit,
}) => {
  const [selectedLocationId, setSelectedLocationId] = useState(
    initialLocationId || (locations[0]?.id || '')
  );
  const [waitMinutes, setWaitMinutes] = useState<number>(5);
  const [queueLength, setQueueLength] = useState<number>(8);
  const [note, setNote] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    if (initialLocationId) {
      setSelectedLocationId(initialLocationId);
    } else if (locations.length > 0 && !selectedLocationId) {
      setSelectedLocationId(locations[0].id);
    }
  }, [initialLocationId, locations]);

  if (!isOpen) return null;

  const quickWaits = [2, 5, 8, 12, 15, 20];
  const quickQueues = [0, 5, 10, 15, 25, 40];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!selectedLocationId) {
      setErrorMsg('Please select a campus dining outlet.');
      return;
    }
    if (waitMinutes < 0 || waitMinutes > 120) {
      setErrorMsg('Wait time must be between 0 and 120 minutes.');
      return;
    }
    if (queueLength < 0 || queueLength > 300) {
      setErrorMsg('Queue length must be between 0 and 300 people.');
      return;
    }

    try {
      setIsSubmitting(true);
      await onSubmit(selectedLocationId, {
        reportedWaitMinutes: waitMinutes,
        queueLength: queueLength,
        note: note.trim() || undefined,
      });

      setSuccessMsg('Thank you! Observation verified and queue estimate updated.');
      setTimeout(() => {
        setSuccessMsg(null);
        onClose();
      }, 1500);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to submit report. Please check connection.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedLoc = locations.find((l) => l.id === selectedLocationId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#070A08]/85 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-lg rounded-3xl glass-panel-elevated shadow-2xl overflow-hidden glass-specular-edge border-[#39FF14]/25">
        {/* Header */}
        <div className="p-6 border-b border-white/[0.08] flex items-center justify-between">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-[#39FF14]/10 text-[#39FF14] border border-[#39FF14]/30 text-[10px] font-mono uppercase tracking-wider mb-1">
              <span>Peer Observation Stream</span>
            </div>
            <h3 className="font-display text-xl font-extrabold text-white tracking-tight">
              Report Current Queue
            </h3>
            <p className="text-xs text-[#8E9E93] mt-0.5">
              Empower campus peers with live queue intelligence.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-[#8E9E93] hover:text-white hover:bg-white/[0.06] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {errorMsg && (
            <div className="p-3.5 rounded-2xl bg-[#CC162D]/15 border border-[#CC162D]/40 text-[#FF4A60] text-xs flex items-center gap-2.5">
              <AlertTriangle className="w-4 h-4 shrink-0 text-[#FF4A60]" />
              <span>{errorMsg}</span>
            </div>
          )}

          {successMsg && (
            <div className="p-3.5 rounded-2xl bg-[#39FF14]/15 border border-[#39FF14]/40 text-[#39FF14] text-xs flex items-center gap-2.5 shadow-[0_0_15px_rgba(57,255,20,0.25)]">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-[#39FF14]" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* Location Selector */}
          <div>
            <label className="block text-xs font-mono font-semibold uppercase tracking-wider text-[#8E9E93] mb-2">
              Campus Outlet
            </label>
            <select
              value={selectedLocationId}
              onChange={(e) => setSelectedLocationId(e.target.value)}
              className="w-full px-4 py-3 rounded-2xl bg-[#090E0B] border border-white/[0.1] text-sm text-white focus:outline-none focus:border-[#39FF14]/60 transition-colors cursor-pointer"
            >
              {locations.map((loc) => (
                <option key={loc.id} value={loc.id} className="bg-[#090E0B] text-white">
                  {loc.name} ({loc.category})
                </option>
              ))}
            </select>
            {selectedLoc && (
              <div className="flex items-center gap-3 text-[11px] text-[#5A695F] font-mono mt-1.5 px-1">
                <span>{selectedLoc.openHours}</span>
                <span>•</span>
                <span>{selectedLoc.capacity} seating capacity</span>
              </div>
            )}
          </div>

          {/* Observed Wait Time */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-mono font-semibold uppercase tracking-wider text-[#8E9E93] flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-[#39FF14]" />
                <span>Observed Wait Time</span>
              </label>
              <span className="font-mono text-base font-extrabold text-[#39FF14]">
                {waitMinutes} min
              </span>
            </div>

            {/* Segmented Quick Presets */}
            <div className="grid grid-cols-6 gap-1.5 mb-3">
              {quickWaits.map((val) => {
                const isSelected = waitMinutes === val;
                return (
                  <button
                    type="button"
                    key={val}
                    onClick={() => setWaitMinutes(val)}
                    className={`py-2 text-xs font-mono rounded-xl border transition-all ${
                      isSelected
                        ? 'bg-[#39FF14] text-[#070A08] border-[#39FF14] font-bold shadow-[0_0_15px_rgba(57,255,20,0.4)]'
                        : 'bg-[#090E0B]/80 text-[#8E9E93] border-white/[0.08] hover:border-white/20 hover:text-white'
                    }`}
                  >
                    {val}m
                  </button>
                );
              })}
            </div>

            <input
              type="range"
              min="0"
              max="45"
              step="1"
              value={waitMinutes}
              onChange={(e) => setWaitMinutes(Number(e.target.value))}
              className="w-full accent-[#39FF14] cursor-pointer h-1.5 bg-[#17221A] rounded-lg"
            />
          </div>

          {/* Queue Length Ahead */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-mono font-semibold uppercase tracking-wider text-[#8E9E93] flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5 text-[#7DF9FF]" />
                <span>People in Line Ahead</span>
              </label>
              <span className="font-mono text-base font-bold text-[#7DF9FF]">
                {queueLength} {queueLength === 1 ? 'person' : 'people'}
              </span>
            </div>

            {/* Segmented Quick Presets */}
            <div className="grid grid-cols-6 gap-1.5 mb-3">
              {quickQueues.map((val) => {
                const isSelected = queueLength === val;
                return (
                  <button
                    type="button"
                    key={val}
                    onClick={() => setQueueLength(val)}
                    className={`py-2 text-xs font-mono rounded-xl border transition-all ${
                      isSelected
                        ? 'bg-[#7DF9FF] text-[#070A08] border-[#7DF9FF] font-bold shadow-[0_0_15px_rgba(125,249,255,0.4)]'
                        : 'bg-[#090E0B]/80 text-[#8E9E93] border-white/[0.08] hover:border-white/20 hover:text-white'
                    }`}
                  >
                    {val}
                  </button>
                );
              })}
            </div>

            <input
              type="range"
              min="0"
              max="60"
              step="1"
              value={queueLength}
              onChange={(e) => setQueueLength(Number(e.target.value))}
              className="w-full accent-[#7DF9FF] cursor-pointer h-1.5 bg-[#17221A] rounded-lg"
            />
          </div>

          {/* Optional Short Note */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-mono font-semibold uppercase tracking-wider text-[#8E9E93]">
                Operational Note (Optional)
              </label>
              <span className="text-[10px] font-mono text-[#5A695F]">
                {note.length}/140
              </span>
            </div>
            <input
              type="text"
              maxLength={140}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Counter 2 moving briskly, main line surging"
              className="w-full px-4 py-2.5 rounded-2xl bg-[#090E0B] border border-white/[0.08] text-xs sm:text-sm text-[#F4F7F5] placeholder-[#5A695F] focus:outline-none focus:border-[#39FF14]/60 transition-colors"
            />
          </div>

          {/* Actions */}
          <div className="pt-2 flex items-center justify-end gap-3 border-t border-white/[0.06]">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-5 py-2.5 text-xs font-mono uppercase tracking-wider rounded-xl btn-glass"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-2 px-6 py-2.5 text-xs sm:text-sm btn-electric disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
              <span>{isSubmitting ? 'Recording...' : 'Submit Observation'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
