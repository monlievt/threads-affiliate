"use client";

import React, { useState } from "react";
import { Clock, Tag, ExternalLink, Calendar as CalendarIcon, CheckCircle2, AlertTriangle, ShieldAlert } from "lucide-react";
import { CalendarDay, CalendarSlot } from "@/types";
import RescheduleModal from "./RescheduleModal";

interface CalendarWeekViewProps {
  days: CalendarDay[];
  onRefresh: () => void;
}

export default function CalendarWeekView({ days, onRefresh }: CalendarWeekViewProps) {
  const [selectedSlotForMove, setSelectedSlotForMove] = useState<CalendarSlot | null>(null);

  return (
    <div className="space-y-4">
      {/* 7-Day Responsive Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-7 gap-3">
        {days.map((day) => {
          const quotaPercent = Math.min(100, (day.scheduled_count + day.published_count) / day.max_posts * 100);

          return (
            <div
              key={day.date}
              className={`flex flex-col rounded-xl border transition-colors ${
                day.is_today
                  ? "border-blue-400 dark:border-blue-500 bg-blue-50/20 dark:bg-blue-950/10 shadow-xs"
                  : "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900"
              }`}
            >
              {/* Day Header */}
              <div className="p-3 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold text-slate-900 dark:text-slate-100">
                      {day.day_name.slice(0, 3)}
                    </span>
                    {day.is_today && (
                      <span className="text-[9px] font-bold px-1.5 py-0.2 rounded-sm bg-blue-600 text-white uppercase tracking-wider">
                        Hari Ini
                      </span>
                    )}
                  </div>
                  <span className="text-[11px] text-slate-400 block mt-0.5 font-mono">
                    {day.date.slice(5)}
                  </span>
                </div>

                {/* Quota Badge */}
                <div
                  className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                    day.is_quota_full
                      ? "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-400 border border-red-200/50"
                      : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 border border-emerald-200/50"
                  }`}
                  title={`Kuota: ${day.scheduled_count + day.published_count} dari ${day.max_posts} post`}
                >
                  {day.scheduled_count + day.published_count}/{day.max_posts} Kuota
                </div>
              </div>

              {/* Day Content Area */}
              <div className="p-2.5 flex-1 flex flex-col justify-between space-y-3 min-h-[220px]">
                {/* Scheduled Slots List */}
                <div className="space-y-2">
                  {day.slots.length === 0 ? (
                    <div className="py-6 text-center text-[11px] text-slate-400 italic">
                      Slot kosong
                    </div>
                  ) : (
                    day.slots.map((slot) => (
                      <div
                        key={slot.id}
                        className={`group relative p-2.5 rounded-lg border text-xs space-y-1.5 transition-all shadow-2xs ${
                          slot.status === "published"
                            ? "bg-emerald-50/40 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800/40"
                            : "bg-slate-50 dark:bg-slate-800/60 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600"
                        }`}
                      >
                        {/* Dual Time Badges */}
                        <div className="flex items-center justify-between text-[10px] font-mono font-medium">
                          <span className="text-blue-700 dark:text-blue-300 bg-blue-100/60 dark:bg-blue-950/60 px-1.5 py-0.5 rounded-sm">
                            {slot.scheduled_at_target}
                          </span>
                          <span className="text-slate-500 dark:text-slate-400">
                            {slot.scheduled_at_operator}
                          </span>
                        </div>

                        {/* Text / Title */}
                        <div className="font-medium text-slate-800 dark:text-slate-200 line-clamp-2 leading-tight">
                          {slot.product_title || slot.text_snippet}
                        </div>

                        {/* Context Tag & Status */}
                        <div className="flex items-center justify-between pt-1 border-t border-slate-100 dark:border-slate-700/60 text-[10px]">
                          <span className="truncate max-w-[90px] text-slate-500 dark:text-slate-400">
                            {slot.niche_name || "Niche"}
                          </span>

                          {slot.status === "published" ? (
                            <span className="inline-flex items-center gap-0.5 text-emerald-600 dark:text-emerald-400 font-semibold">
                              <CheckCircle2 className="w-2.5 h-2.5" />
                              <span>Terbit</span>
                            </span>
                          ) : (
                            <button
                              onClick={() => setSelectedSlotForMove(slot)}
                              className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
                            >
                              Ubah Jam
                            </button>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>

                {/* Forbidden Hours Notice for this day */}
                <div className="p-2 rounded-lg bg-slate-100/80 dark:bg-slate-800/40 border border-dashed border-slate-200 dark:border-slate-700/60 text-[10px] text-slate-400 space-y-0.5 select-none">
                  <div className="flex items-center gap-1 font-semibold text-slate-500 dark:text-slate-400">
                    <ShieldAlert className="w-3 h-3" />
                    <span>Zona Terlarang</span>
                  </div>
                  <p className="text-[9px] leading-tight">
                    21:00 - 09:00 EST (di luar jam aktif US) dilarang oleh governor.
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Reschedule Modal */}
      {selectedSlotForMove && (
        <RescheduleModal
          slot={selectedSlotForMove}
          onClose={() => setSelectedSlotForMove(null)}
          onSuccess={() => {
            setSelectedSlotForMove(null);
            onRefresh();
          }}
        />
      )}
    </div>
  );
}
