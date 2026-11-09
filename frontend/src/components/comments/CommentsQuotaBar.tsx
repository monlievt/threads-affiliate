"use client";

import React, { useState } from "react";
import { MessageSquare, ShieldCheck, AlertTriangle, ChevronDown, ChevronUp, Info } from "lucide-react";
import { useCommentsQuota } from "@/hooks/useComments";

export default function CommentsQuotaBar() {
  const { data: quota, isLoading } = useCommentsQuota();
  const [showAvoidList, setShowAvoidList] = useState(false);

  if (isLoading || !quota) {
    return (
      <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 animate-pulse text-xs text-slate-500 text-center">
        Memuat batas kuota komentar harian...
      </div>
    );
  }

  const quotaPercent = Math.min(100, (quota.replies_today / quota.max_replies_today) * 100);

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3 shadow-xs">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Title & Philosophy */}
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300">
            <MessageSquare className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold text-slate-900 dark:text-slate-100">
                Kuota Komentar Bernilai (F10)
              </h3>
              <span className="text-[10px] px-1.5 py-0.2 rounded-sm bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 font-semibold font-mono">
                Selalu Manual
              </span>
            </div>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              Interaksi autentik untuk membangun otoritas profil tanpa pemicu spam Threads.
            </p>
          </div>
        </div>

        {/* Quota Counter Pill */}
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-xs font-bold text-slate-900 dark:text-slate-100">
              {quota.replies_today} / {quota.max_replies_today} Komentar
            </div>
            <div className="text-[10px] text-slate-400">
              {quota.remaining_today} sisa hari ini (Batas Keras: {quota.hard_max_replies})
            </div>
          </div>
          <div className="w-16 h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
            <div
              className={`h-full transition-all ${
                quota.is_quota_full ? "bg-red-500" : quotaPercent > 70 ? "bg-amber-500" : "bg-emerald-500"
              }`}
              style={{ width: `${quotaPercent}%` }}
            />
          </div>
        </div>
      </div>

      {/* Quota Full Alert */}
      {quota.is_quota_full && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-xs text-red-700 dark:text-red-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>
            <strong>Batas Kuota Tercapai:</strong> Anda telah mencapai batas {quota.max_replies_today} komentar hari ini. Istirahatkan aktivitas komentar sampai reset harian untuk menjaga trust score akun Threads.
          </span>
        </div>
      )}

      {/* Expandable Avoid List */}
      <div className="pt-1 border-t border-slate-100 dark:border-slate-800">
        <button
          onClick={() => setShowAvoidList(!showAvoidList)}
          className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
        >
          <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
          <span>Daftar yang Dihindari Sistem (Avoid List)</span>
          {showAvoidList ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>

        {showAvoidList && (
          <div className="mt-2 p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 space-y-1 animate-in fade-in duration-150">
            <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">
              Dilarang keras disertakan dalam balasan komentar:
            </p>
            <div className="flex flex-wrap gap-1 pt-1">
              {quota.avoid_list.map((item, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 rounded-sm bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-400 text-[10px] border border-red-200/50"
                >
                  ✕ {item}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
