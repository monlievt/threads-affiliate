"use client";

import React, { useState } from "react";
import {
  KeyRound,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Lock,
  Sparkles,
  Info,
} from "lucide-react";
import {
  useAccountSettings,
  useFullAutoEligibility,
  useUpdateAccountSettings,
} from "@/hooks/useSettings";

export default function AccountTab() {
  const { data: account, isLoading: isAccLoading } = useAccountSettings();
  const { data: eligibility, isLoading: isEligLoading } = useFullAutoEligibility();
  const updateMutation = useUpdateAccountSettings();

  const [selectedMode, setSelectedMode] = useState<"manual_approve" | "auto_sampled" | "full_auto">("manual_approve");
  const [modeChanged, setModeChanged] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Sync mode with loaded data
  React.useEffect(() => {
    if (account?.automation_mode && !modeChanged) {
      setSelectedMode(account.automation_mode);
    }
  }, [account, modeChanged]);

  const handleModeSelect = (mode: "manual_approve" | "auto_sampled" | "full_auto") => {
    if (mode === "full_auto" && !eligibility?.eligible) {
      return; // Locked
    }
    setSelectedMode(mode);
    setModeChanged(true);
    setSaveSuccess(false);
    setSaveError(null);
  };

  const handleSaveMode = async () => {
    setSaveError(null);
    try {
      await updateMutation.mutateAsync({
        automation_mode: selectedMode,
      });
      setSaveSuccess(true);
      setModeChanged(false);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      setSaveError(err.message || "Gagal memperbarui mode otomasi.");
    }
  };

  if (isAccLoading || isEligLoading) {
    return (
      <div className="p-8 text-center text-sm text-slate-500 animate-pulse">
        Memuat informasi akun dan syarat kelayakan...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 1. OAuth Connection & Token Health Card */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 shadow-xs">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
              <KeyRound className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                Koneksi Threads OAuth &amp; Token
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Status otorisasi akun Threads resmi dan masa berlaku access token.
              </p>
            </div>
          </div>

          {account?.token_valid ? (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 border border-emerald-200/50">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Token Aktif</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-400 border border-red-200/50">
              <XCircle className="w-3.5 h-3.5" />
              <span>Token Tidak Valid</span>
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-xs">
          <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Username</span>
            <span className="font-semibold text-slate-800 dark:text-slate-200">
              @{account?.username || "threads_user"}
            </span>
          </div>

          <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Target Negara</span>
            <span className="font-semibold text-slate-800 dark:text-slate-200">
              🇺🇸 {account?.country_code} ({account?.timezone})
            </span>
          </div>

          <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Usia Warm-up</span>
            <span className="font-semibold text-slate-800 dark:text-slate-200">
              {account?.warmup_age_days} hari
            </span>
          </div>

          <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Masa Berlaku Token</span>
            <span className={`font-semibold ${
              (account?.days_until_token_expiry || 0) < 15
                ? "text-amber-600 dark:text-amber-400"
                : "text-slate-800 dark:text-slate-200"
            }`}>
              {account?.days_until_token_expiry !== null
                ? `${account?.days_until_token_expiry} hari tersisa`
                : "Tidak ada data"}
            </span>
          </div>
        </div>

        {/* Warning if token < 15 days */}
        {account?.days_until_token_expiry !== null && (account?.days_until_token_expiry || 0) < 15 && (
          <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>
              Token akan kedaluwarsa dalam {account?.days_until_token_expiry} hari. Refresh token otomatis aktif oleh background worker setiap 6 jam.
            </span>
          </div>
        )}
      </div>

      {/* 2. Automation Mode Selector */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
            Mode Otomasi Penerbitan
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Tingkat otonomi penerbitan draf postingan Threads.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* Option 1: manual_approve */}
          <div
            onClick={() => handleModeSelect("manual_approve")}
            className={`cursor-pointer p-4 rounded-xl border text-xs space-y-2 transition-all ${
              selectedMode === "manual_approve"
                ? "border-slate-900 dark:border-white bg-slate-50 dark:bg-slate-800/80 shadow-xs"
                : "border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900 dark:text-slate-100">Manual Approve</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded-sm bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 font-semibold">
                Default
              </span>
            </div>
            <p className="text-slate-500 dark:text-slate-400 text-[11px] leading-relaxed">
              100% human-in-the-loop. Setiap draf wajib disetujui operator melalui dashboard atau Telegram bot sebelum diterbitkan.
            </p>
          </div>

          {/* Option 2: auto_sampled */}
          <div
            onClick={() => handleModeSelect("auto_sampled")}
            className={`cursor-pointer p-4 rounded-xl border text-xs space-y-2 transition-all ${
              selectedMode === "auto_sampled"
                ? "border-slate-900 dark:border-white bg-slate-50 dark:bg-slate-800/80 shadow-xs"
                : "border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900 dark:text-slate-100">Auto Sampled</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded-sm bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 font-semibold">
                Semi-Auto
              </span>
            </div>
            <p className="text-slate-500 dark:text-slate-400 text-[11px] leading-relaxed">
              Penerbitan otomatis dengan sampling acak review ({account?.sample_review_pct || 30}% draf acak tetap wajib di-review manual).
            </p>
          </div>

          {/* Option 3: full_auto */}
          <div
            onClick={() => handleModeSelect("full_auto")}
            className={`p-4 rounded-xl border text-xs space-y-2 transition-all ${
              !eligibility?.eligible
                ? "opacity-60 bg-slate-50/50 dark:bg-slate-900/50 border-dashed border-slate-300 dark:border-slate-800 cursor-not-allowed"
                : selectedMode === "full_auto"
                ? "cursor-pointer border-slate-900 dark:border-white bg-slate-50 dark:bg-slate-800/80 shadow-xs"
                : "cursor-pointer border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700"
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-slate-900 dark:text-slate-100">Full Auto</span>
                {!eligibility?.eligible && <Lock className="w-3.5 h-3.5 text-slate-400" />}
              </div>
              <span className={`text-[10px] px-1.5 py-0.5 rounded-sm font-semibold ${
                eligibility?.eligible
                  ? "bg-purple-100 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300"
                  : "bg-slate-200 text-slate-500 dark:bg-slate-800"
              }`}>
                Otonom
              </span>
            </div>
            <p className="text-slate-500 dark:text-slate-400 text-[11px] leading-relaxed">
              Penerbitan otonom penuh tanpa review manual. Hanya dapat diaktifkan jika telah memenuhi seluruh 5 kriteria kelayakan.
            </p>
          </div>
        </div>

        {/* Save button if mode was changed */}
        {modeChanged && (
          <div className="pt-2 flex items-center justify-end gap-2">
            <button
              onClick={() => {
                setSelectedMode(account?.automation_mode || "manual_approve");
                setModeChanged(false);
              }}
              className="px-3.5 py-2 text-xs font-medium rounded-lg text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
            >
              Batal
            </button>
            <button
              onClick={handleSaveMode}
              disabled={updateMutation.isPending}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100 transition-colors disabled:opacity-50"
            >
              {updateMutation.isPending ? "Menyimpan..." : "Simpan Perubahan Mode"}
            </button>
          </div>
        )}

        {saveSuccess && (
          <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>Mode otomasi berhasil diperbarui dan dicatat ke audit trail.</span>
          </div>
        )}

        {saveError && (
          <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{saveError}</span>
          </div>
        )}
      </div>

      {/* 3. Full-Auto Eligibility Checklist Card */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-slate-700 dark:text-slate-300" />
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              Syarat Kelayakan Mode Full-Auto (docs/06 §6)
            </h3>
          </div>
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
              eligibility?.eligible
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 border border-emerald-200/50"
                : "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 border border-amber-200/50"
            }`}
          >
            {eligibility?.eligible ? (
              <>
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Memenuhi Syarat (Eligible)</span>
              </>
            ) : (
              <>
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Belum Memenuhi Syarat</span>
              </>
            )}
          </span>
        </div>

        <p className="text-xs text-slate-500 dark:text-slate-400">
          {eligibility?.summary_reason}
        </p>

        {/* Criteria Checklist */}
        <div className="divide-y divide-slate-100 dark:divide-slate-800 border-t border-slate-100 dark:border-slate-800 pt-2">
          {eligibility?.criteria &&
            Object.entries(eligibility.criteria).map(([key, crit]) => (
              <div key={key} className="py-2.5 flex items-center justify-between text-xs gap-4">
                <div className="flex items-center gap-2.5">
                  {crit.passed ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                  ) : (
                    <XCircle className="w-4 h-4 text-red-500 shrink-0" />
                  )}
                  <span className={crit.passed ? "text-slate-800 dark:text-slate-200" : "text-slate-500 dark:text-slate-400"}>
                    {crit.label}
                  </span>
                </div>
                <div className="flex items-center gap-3 shrink-0 font-mono text-[11px]">
                  <span className="text-slate-400">Target: {crit.required}</span>
                  <span className={`font-semibold ${crit.passed ? "text-emerald-600 dark:text-emerald-400" : "text-red-500"}`}>
                    ({crit.current})
                  </span>
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
