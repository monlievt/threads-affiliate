"use client";

import React from "react";
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, Clock, ShieldCheck, Zap } from "lucide-react";
import { GovernorRulesSummary } from "@/types";

interface CalendarHeaderProps {
  startDate: string;
  endDate: string;
  governor: GovernorRulesSummary;
  onPrevWeek: () => void;
  onNextWeek: () => void;
  onToday: () => void;
}

export default function CalendarHeader({
  startDate,
  endDate,
  governor,
  onPrevWeek,
  onNextWeek,
  onToday,
}: CalendarHeaderProps) {
  // Format readable range
  const formatHeaderRange = (start: string, end: string) => {
    try {
      const s = new Date(start + "T00:00:00Z");
      const e = new Date(end + "T00:00:00Z");
      const sStr = s.toLocaleDateString("id-ID", { day: "numeric", month: "short", timeZone: "UTC" });
      const eStr = e.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
      return `${sStr} – ${eStr}`;
    } catch {
      return `${startDate} – ${endDate}`;
    }
  };

  return (
    <div className="space-y-4">
      {/* Title & Navigation Controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Jadwal Kalender Mingguan
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Manajemen slot penerbitan dengan pembatasan jam aktif audiens US dan rate governor.
          </p>
        </div>

        {/* Date Navigation Buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={onToday}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors shadow-2xs"
          >
            Hari Ini
          </button>
          <div className="flex items-center rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-2xs overflow-hidden">
            <button
              onClick={onPrevWeek}
              className="p-1.5 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
              title="Minggu Sebelumnya"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-3 py-1 text-xs font-semibold text-slate-800 dark:text-slate-200 border-x border-slate-200 dark:border-slate-700 select-none">
              {formatHeaderRange(startDate, endDate)}
            </span>
            <button
              onClick={onNextWeek}
              className="p-1.5 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
              title="Minggu Berikutnya"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Dual Timezone & Warmup Governor Rules Banner */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 text-xs">
        {/* Dual Timezone Pill */}
        <div className="flex items-start gap-2.5">
          <div className="p-1.5 rounded-md bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 shrink-0">
            <Clock className="w-4 h-4" />
          </div>
          <div>
            <div className="font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
              <span>Zona Waktu Berdampingan</span>
              <span className="font-mono text-[10px] px-1.5 py-0.2 rounded-sm bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 border border-blue-200/50">
                Dual TZ
              </span>
            </div>
            <div className="text-[11px] text-slate-600 dark:text-slate-400 mt-0.5 space-y-0.5">
              <div>
                🎯 <strong>Target Audiens US:</strong> {governor.active_hours_label} ({governor.target_timezone})
              </div>
              <div>
                🇮🇩 <strong>Waktu Lokal Operator:</strong> {governor.operator_active_hours_label} ({governor.operator_timezone})
              </div>
            </div>
          </div>
        </div>

        {/* Warm-up Tier & Rate Governor Info */}
        <div className="flex items-start gap-2.5">
          <div className="p-1.5 rounded-md bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 shrink-0">
            <Zap className="w-4 h-4" />
          </div>
          <div>
            <div className="font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
              <span>Aturan Rate Governor</span>
              <span className="font-mono text-[10px] px-1.5 py-0.2 rounded-sm bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200/50">
                {governor.warmup_tier_label}
              </span>
            </div>
            <div className="text-[11px] text-slate-600 dark:text-slate-400 mt-0.5 space-y-0.5">
              <div>
                📊 <strong>Batas Kuota:</strong> Maks {governor.max_posts_per_day} post/hari (peningkatan bertahap)
              </div>
              <div>
                ⏱️ <strong>Jeda Minimum:</strong> {governor.min_interval_minutes} menit antar posting (±15 mnt jitter)
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
