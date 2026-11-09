"use client";

import React, { useState, useEffect } from "react";
import { Clock, AlertCircle, CheckCircle2, Calendar as CalendarIcon, ArrowRight } from "lucide-react";
import { useMoveScheduleSlot, useValidateScheduleSlot } from "@/hooks/useSchedule";
import { CalendarSlot } from "@/types";

interface RescheduleModalProps {
  slot: CalendarSlot;
  onClose: () => void;
  onSuccess: () => void;
}

export default function RescheduleModal({ slot, onClose, onSuccess }: RescheduleModalProps) {
  const moveMutation = useMoveScheduleSlot();
  const validateMutation = useValidateScheduleSlot();

  // Extract initial date and time
  const initialDate = slot.scheduled_at_utc.slice(0, 10);
  const initialTime = slot.scheduled_at_utc.slice(11, 16);

  const [dateVal, setDateVal] = useState(initialDate);
  const [timeVal, setTimeVal] = useState(initialTime);
  const [validationResult, setValidationResult] = useState<{
    valid: boolean;
    reason?: string | null;
    target_time?: string;
    operator_time?: string;
  } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Re-run validation whenever dateVal or timeVal changes
  useEffect(() => {
    if (!dateVal || !timeVal) return;
    const candidateUtcIso = `${dateVal}T${timeVal}:00Z`;

    const timer = setTimeout(async () => {
      try {
        const res = await validateMutation.mutateAsync({
          draftId: slot.draft_id,
          candidateScheduledAt: candidateUtcIso,
        });
        setValidationResult({
          valid: res.valid,
          reason: res.reason,
          target_time: res.target_time_formatted,
          operator_time: res.operator_time_formatted,
        });
      } catch (err: any) {
        setValidationResult(null);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [dateVal, timeVal, slot.draft_id]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validationResult?.valid) return;
    setErrorMsg(null);

    const newScheduledAt = `${dateVal}T${timeVal}:00Z`;
    try {
      await moveMutation.mutateAsync({
        draftId: slot.draft_id,
        newScheduledAt,
      });
      onSuccess();
      onClose();
    } catch (err: any) {
      setErrorMsg(err.message || "Gagal memindahkan jadwal slot.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-700 dark:text-slate-300" />
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Pindahkan Jadwal Penerbitan
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xs"
          >
            Tutup
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {errorMsg && (
            <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Current Slot Info */}
          <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 text-xs space-y-1">
            <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">
              Draf yang dipilih:
            </span>
            <div className="font-medium text-slate-900 dark:text-slate-100 line-clamp-1">
              {slot.product_title || slot.text_snippet}
            </div>
            <div className="text-[11px] text-slate-500 flex items-center gap-2 pt-0.5 font-mono">
              <span>{slot.scheduled_at_target}</span>
              <span>·</span>
              <span>{slot.scheduled_at_operator}</span>
            </div>
          </div>

          {/* Date & Time Picker */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                Pilih Tanggal
              </label>
              <input
                type="date"
                required
                value={dateVal}
                onChange={(e) => setDateVal(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                Waktu UTC (Jam:Mnt)
              </label>
              <input
                type="time"
                required
                value={timeVal}
                onChange={(e) => setTimeVal(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
              />
            </div>
          </div>

          {/* Dual Timezone Preview & Validation Feedback */}
          {validationResult && (
            <div className="space-y-2 pt-1">
              <div className="p-3 rounded-xl border text-xs space-y-1.5 transition-all">
                {validationResult.valid ? (
                  <div className="flex items-start gap-2 text-emerald-700 dark:text-emerald-400">
                    <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold">Jadwal Sesuai Aturan Governor</div>
                      <div className="text-[11px] text-slate-600 dark:text-slate-400 mt-0.5">
                        US: {validationResult.target_time} ↔ WIB: {validationResult.operator_time}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start gap-2 text-red-600 dark:text-red-400">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold">Pelanggaran Aturan Governor</div>
                      <div className="text-[11px] text-red-700 dark:text-red-300 mt-0.5">
                        {validationResult.reason}
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1">
                        US: {validationResult.target_time} ↔ WIB: {validationResult.operator_time}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Bottom Actions */}
          <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-2 text-xs font-medium rounded-lg text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={moveMutation.isPending || !validationResult?.valid}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100 transition-colors disabled:opacity-50 flex items-center gap-1.5"
            >
              {moveMutation.isPending ? "Memindahkan..." : "Simpan Jadwal Baru"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
