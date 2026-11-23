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

    // Validation
    if (!selectedLocationId) {
      setErrorMsg('Please select a campus outlet.');
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

      setSuccessMsg('Thank you! Observation recorded and queue estimate updated.');
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-lg rounded-2xl bg-surface-card border border-surface-border shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-surface-border flex items-center justify-between">
          <div>
            <h3 className="font-display text-lg font-bold text-white">
              Report Current Queue
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Help campus peers know the wait before walking over.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-surface-elevated transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-5 space-y-5">
          {errorMsg && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {successMsg && (
            <div className="p-3 rounded-xl bg-neon-green/10 border border-neon-green/30 text-neon-green text-xs flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* Location Selector */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
              Campus Outlet
            </label>
            <select
              value={selectedLocationId}
              onChange={(e) => setSelectedLocationId(e.target.value)}
              className="w-full px-3 py-2.5 rounded-xl bg-surface-elevated border border-surface-border text-sm text-white focus:outline-none focus:border-neon-green transition-colors"
            >
              {locations.map((loc) => (
                <option key={loc.id} value={loc.id} className="bg-surface-card text-white">
                  {loc.name} ({loc.category})
                </option>
              ))}
            </select>
            {selectedLoc && (
              <div className="flex items-center gap-3 text-[11px] text-slate-400 font-mono mt-1">
                <span>{selectedLoc.openHours}</span>
                <span>•</span>
                <span>{selectedLoc.capacity} seating capacity</span>
              </div>
            )}
          </div>

          {/* Observed Wait Time */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-neon-green" />
                <span>Observed Wait Time</span>
              </label>
              <span className="font-mono text-sm font-bold text-neon-green">
                {waitMinutes} min
              </span>
            </div>

            {/* Quick Presets */}
            <div className="grid grid-cols-6 gap-1.5 mb-2">
              {quickWaits.map((val) => (
                <button
                  type="button"
                  key={val}
                  onClick={() => setWaitMinutes(val)}
                  className={`py-1.5 text-xs font-mono font-medium rounded-lg border transition-all ${
                    waitMinutes === val
                      ? 'bg-neon-green text-slate-950 border-neon-green font-bold shadow-sm'
                      : 'bg-surface-elevated text-slate-300 border-surface-border hover:bg-surface-subtle'
                  }`}
                >
                  {val}m
                </button>
              ))}
            </div>

            {/* Range Slider for granular control */}
            <input
              type="range"
              min="0"
              max="45"
              step="1"
              value={waitMinutes}
              onChange={(e) => setWaitMinutes(Number(e.target.value))}
              className="w-full accent-neon-green cursor-pointer h-1.5 bg-slate-800 rounded-lg"
            />
          </div>

          {/* Queue Length */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5 text-neon-blue" />
                <span>Approximate People Ahead</span>
              </label>
              <span className="font-mono text-sm font-bold text-neon-blue">
                {queueLength} {queueLength === 1 ? 'person' : 'people'}
              </span>
            </div>

            {/* Quick Presets */}
            <div className="grid grid-cols-6 gap-1.5 mb-2">
              {quickQueues.map((val) => (
                <button
                  type="button"
                  key={val}
                  onClick={() => setQueueLength(val)}
                  className={`py-1.5 text-xs font-mono font-medium rounded-lg border transition-all ${
                    queueLength === val
                      ? 'bg-neon-blue text-slate-950 border-neon-blue font-bold shadow-sm'
                      : 'bg-surface-elevated text-slate-300 border-surface-border hover:bg-surface-subtle'
                  }`}
                >
                  {val}
                </button>
              ))}
            </div>

            <input
              type="range"
              min="0"
              max="60"
              step="1"
              value={queueLength}
              onChange={(e) => setQueueLength(Number(e.target.value))}
              className="w-full accent-neon-blue cursor-pointer h-1.5 bg-slate-800 rounded-lg"
            />
          </div>

          {/* Optional Note */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Optional Note
              </label>
              <span className="text-[10px] font-mono text-slate-500">
                {note.length}/140
              </span>
            </div>
            <input
              type="text"
              maxLength={140}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Counter 2 is fast, veg meal line moving quick"
              className="w-full px-3 py-2 rounded-xl bg-surface-elevated border border-surface-border text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-neon-green transition-colors"
            />
          </div>

          {/* Submit Action */}
          <div className="pt-2 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 text-xs font-medium rounded-xl border border-surface-border text-slate-300 hover:text-white hover:bg-surface-elevated transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-2 px-5 py-2 text-xs sm:text-sm font-semibold rounded-xl bg-neon-green hover:bg-[#2fe07c] text-slate-950 shadow-glow-green transition-all disabled:opacity-50"
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
