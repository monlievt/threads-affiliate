"use client";

import React, { useState, useEffect } from "react";
import { Sliders, ShieldAlert, CheckCircle2, AlertCircle, Lock } from "lucide-react";
import { useAccountSettings, useUpdateAccountSettings } from "@/hooks/useSettings";

export default function OperationalLimitsTab() {
  const { data: account, isLoading } = useAccountSettings();
  const updateMutation = useUpdateAccountSettings();

  const [startHour, setStartHour] = useState(9);
  const [endHour, setEndHour] = useState(21);
  const [samplePct, setSamplePct] = useState(30);
  const [timezone, setTimezone] = useState("America/New_York");
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (account) {
      setStartHour(account.active_hours_start);
      setEndHour(account.active_hours_end);
      setSamplePct(account.sample_review_pct);
      setTimezone(account.timezone || "America/New_York");
    }
  }, [account]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError(null);
    setSaveSuccess(false);

    if (startHour >= endHour) {
      setSaveError("Jam mulai aktif harus lebih kecil dari jam selesai.");
      return;
    }

    try {
      await updateMutation.mutateAsync({
        active_hours_start: startHour,
        active_hours_end: endHour,
        sample_review_pct: samplePct,
        timezone,
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      setSaveError(err.message || "Gagal menyimpan batas operasional.");
    }
  };

  if (isLoading) {
    return (
      <div className="p-8 text-center text-sm text-slate-500 animate-pulse">
        Memuat konfigurasi batas operasional...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Form Card */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 shadow-xs">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
            <Sliders className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              Pengaturan Jam Aktif &amp; Batas Governor
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Konfigurasi rentang jam aktif postingan pada zona waktu audiens target.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          {saveSuccess && (
            <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>Batas operasional berhasil diperbarui dan dicatat ke audit log.</span>
            </div>
          )}

          {saveError && (
            <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{saveError}</span>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                Jam Mulai Aktif (Format 24 Jam)
              </label>
              <select
                value={startHour}
                onChange={(e) => setStartHour(parseInt(e.target.value))}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              >
                {Array.from({ length: 24 }).map((_, i) => (
                  <option key={i} value={i}>
                    {i.toString().padStart(2, "0")}:00 ({i <= 12 ? `${i} AM` : `${i - 12} PM`})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                Jam Selesai Aktif (Format 24 Jam)
              </label>
              <select
                value={endHour}
                onChange={(e) => setEndHour(parseInt(e.target.value))}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              >
                {Array.from({ length: 24 }).map((_, i) => (
                  <option key={i + 1} value={i + 1}>
                    {(i + 1).toString().padStart(2, "0")}:00 ({(i + 1) <= 12 ? `${i + 1} AM` : `${(i + 1) - 12} PM`})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
              Zona Waktu Target Akun
            </label>
            <select
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            >
              <option value="America/New_York">America/New_York (US Eastern Time - Rekomendasi)</option>
              <option value="America/Chicago">America/Chicago (US Central Time)</option>
              <option value="America/Denver">America/Denver (US Mountain Time)</option>
              <option value="America/Los_Angeles">America/Los_Angeles (US Pacific Time)</option>
            </select>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
                Persentase Sampling Review Manual (untuk mode Auto-Sampled)
              </label>
              <span className="font-mono font-bold text-xs text-slate-900 dark:text-slate-100">
                {samplePct}%
              </span>
            </div>
            <input
              type="range"
              min={10}
              max={100}
              step={5}
              value={samplePct}
              onChange={(e) => setSamplePct(parseInt(e.target.value))}
              className="w-full accent-slate-900 dark:accent-white"
            />
            <p className="text-[10px] text-slate-400 mt-1">
              Dalam mode semi-otomatis, {samplePct}% dari seluruh draf acak akan dialihkan ke antrean review manual.
            </p>
          </div>

          <div className="pt-2 flex justify-end">
            <button
              type="submit"
              disabled={updateMutation.isPending}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100 transition-colors disabled:opacity-50"
            >
              {updateMutation.isPending ? "Menyimpan..." : "Simpan Batas Operasional"}
            </button>
          </div>
        </form>
      </div>

      {/* Hard Limits Failsafe Banner */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/40 p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Lock className="w-4 h-4 text-slate-600 dark:text-slate-400" />
          <h4 className="text-xs font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wider">
            Batas Keras Sistem (Hard Limits — Tidak Dapat Dilewati)
          </h4>
        </div>

        <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
          Batas berikut dikonfigurasi permanen pada level environment container (<code>.env</code>). Apapun konfigurasi di atas, sistem rate governor tidak akan pernah mengizinkan penerbitan melebihi batas ini:
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1 text-xs">
          <div className="p-3 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block">HARD_MAX_POSTS_PER_DAY</span>
            <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
              {account?.hard_max_posts_per_day} post/hari
            </span>
          </div>

          <div className="p-3 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block">HARD_MAX_REPLIES_PER_DAY</span>
            <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
              {account?.hard_max_replies_per_day} komentar/hari
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
