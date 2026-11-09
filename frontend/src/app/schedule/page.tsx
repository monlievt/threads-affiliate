"use client";

import React, { useState } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { useScheduleCalendar } from "@/hooks/useSchedule";
import CalendarHeader from "@/components/schedule/CalendarHeader";
import CalendarWeekView from "@/components/schedule/CalendarWeekView";

export default function SchedulePage() {
  const [startDate, setStartDate] = useState<string | undefined>(undefined);
  const { data, isLoading, error, refetch, isFetching } = useScheduleCalendar(startDate);

  const handlePrevWeek = () => {
    if (!data?.start_date) return;
    const d = new Date(data.start_date + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - 7);
    setStartDate(d.toISOString().slice(0, 10));
  };

  const handleNextWeek = () => {
    if (!data?.start_date) return;
    const d = new Date(data.start_date + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + 7);
    setStartDate(d.toISOString().slice(0, 10));
  };

  const handleToday = () => {
    setStartDate(undefined);
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header with Navigation and Dual Timezone / Governor Status */}
      {data && (
        <CalendarHeader
          startDate={data.start_date}
          endDate={data.end_date}
          governor={data.governor}
          onPrevWeek={handlePrevWeek}
          onNextWeek={handleNextWeek}
          onToday={handleToday}
        />
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="p-12 text-center text-sm text-slate-500 animate-pulse space-y-2">
          <RefreshCw className="w-5 h-5 mx-auto animate-spin text-slate-400" />
          <p>Memuat kalender jadwal mingguan...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>Gagal memuat kalender: {(error as any).message}</span>
          </div>
          <button
            onClick={() => refetch()}
            className="px-2.5 py-1 text-[11px] font-medium rounded-md bg-red-100 hover:bg-red-200 text-red-800 transition-colors"
          >
            Coba Lagi
          </button>
        </div>
      )}

      {/* Main Weekly View */}
      {!isLoading && !error && data && (
        <CalendarWeekView days={data.days} onRefresh={() => refetch()} />
      )}
    </div>
  );
}
