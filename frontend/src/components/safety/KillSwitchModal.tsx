"use client";

import React, { useState } from "react";
import { AlertOctagon, CheckCircle2, Loader2, PauseCircle, PlayCircle, ShieldAlert } from "lucide-react";
import { useKillSwitch } from "@/hooks/useSystemStatus";

export default function KillSwitchButton() {
  const { data: ksStatus, toggle, isToggling } = useKillSwitch();
  const [isOpen, setIsOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isPaused = ksStatus?.active ?? true;

  const handleOpenModal = () => {
    setReason(
      isPaused
        ? "Operator manual resume via dashboard button"
        : "Operator emergency stop via dashboard button"
    );
    setError(null);
    setIsOpen(true);
  };

  const handleConfirmToggle = async () => {
    if (!reason.trim()) {
      setError("Alasan tindakan wajib diisi untuk audit log.");
      return;
    }

    try {
      setError(null);
      await toggle({ active: !isPaused, reason: reason.trim() });
      setIsOpen(false);
    } catch (err: any) {
      setError(err?.message || "Gagal mengubah status Kill Switch");
    }
  };

  return (
    <>
      {/* Prominent Header Action Button */}
      <button
        type="button"
        onClick={handleOpenModal}
        disabled={isToggling}
        className={`inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-md transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 ${
          isPaused
            ? "bg-emerald-600 hover:bg-emerald-700 text-white focus:ring-emerald-500"
            : "bg-rose-600 hover:bg-rose-700 text-white focus:ring-rose-500 animate-pulse hover:animate-none"
        }`}
        title={isPaused ? "Klik untuk mengaktifkan kembali publikasi" : "Klik untuk menghentikan semua publikasi seketika (<= 5 detik)"}
      >
        {isToggling ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : isPaused ? (
          <PlayCircle className="w-4 h-4" />
        ) : (
          <AlertOctagon className="w-4 h-4" />
        )}
        <span>{isPaused ? "Aktifkan Publikasi" : "Jeda Semua (Kill Switch)"}</span>
      </button>

      {/* Confirmation Modal */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="w-full max-w-md p-6 bg-white dark:bg-slate-900 rounded-lg shadow-xl border border-slate-200 dark:border-slate-800">
            <div className="flex items-center gap-3 mb-4">
              <div
                className={`p-2.5 rounded-full ${
                  isPaused ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400" : "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-400"
                }`}
              >
                {isPaused ? <CheckCircle2 className="w-6 h-6" /> : <ShieldAlert className="w-6 h-6" />}
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                  {isPaused ? "Konfirmasi Pengaktifan Publikasi" : "Konfirmasi Darurat Jeda Semua"}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {isPaused
                    ? "Sistem akan kembali menerbitkan postingan sesuai jadwal yang ditentukan."
                    : "Semua proses penerbitan dan API call akan dihentikan secara instan (≤ 5 detik)."}
                </p>
              </div>
            </div>

            {error && (
              <div className="p-3 mb-4 text-xs text-rose-700 bg-rose-50 dark:bg-rose-950/50 dark:text-rose-400 border border-rose-200 dark:border-rose-900 rounded">
                {error}
              </div>
            )}

            <div className="mb-5">
              <label className="block mb-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                Alasan Tindakan <span className="text-rose-500">*</span>
              </label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Tuliskan alasan perubahan status untuk catatan audit..."
                rows={3}
                className="w-full px-3 py-2 text-xs border rounded-md border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-500"
              />
            </div>

            <div className="flex items-center justify-end gap-2.5">
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                disabled={isToggling}
                className="px-3.5 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-md transition"
              >
                Batal
              </button>
              <button
                type="button"
                onClick={handleConfirmToggle}
                disabled={isToggling}
                className={`inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold rounded-md text-white shadow-sm transition ${
                  isPaused ? "bg-emerald-600 hover:bg-emerald-700" : "bg-rose-600 hover:bg-rose-700"
                }`}
              >
                {isToggling && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                <span>{isPaused ? "Ya, Aktifkan Kembali" : "Ya, Hentikan Semua"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
