"use client";

import React from "react";
import { ShieldCheck, ShieldAlert, Cpu, Activity, Clock, LogOut } from "lucide-react";
import { useSystemHealth, useKillSwitch } from "@/hooks/useSystemStatus";
import { logoutApi } from "@/lib/api";
import KillSwitchButton from "@/components/safety/KillSwitchModal";

export default function Header() {
  const { data: health, isLoading: healthLoading } = useSystemHealth();
  const { data: killSwitch } = useKillSwitch();

  const handleLogout = async () => {
    try {
      await logoutApi();
    } catch {
      // ignore
    }
    window.location.href = "/login";
  };

  const isPaused = killSwitch?.active ?? (health?.kill_switch === "on");
  const isHealthy = health?.status === "ok" && !isPaused;
  const isDegraded = health?.status === "degraded";

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xs">
      <div className="flex flex-wrap items-center justify-between px-4 py-2.5 sm:px-6 gap-3">
        {/* Left: Account & System Status Badges */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
            <span className="w-2 h-2 rounded-full bg-slate-400" />
            <span>@threads_curator</span>
            <span className="text-slate-400 font-normal">(US/Eastern)</span>
          </div>

          <div className="h-4 w-px bg-slate-200 dark:bg-slate-800 hidden sm:block" />

          {/* System Status Badge */}
          <div
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
              isPaused
                ? "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-400 dark:border-rose-900"
                : isDegraded
                ? "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-900"
                : "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-900"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isPaused
                  ? "bg-rose-500 animate-ping"
                  : isDegraded
                  ? "bg-amber-500"
                  : "bg-emerald-500"
              }`}
            />
            <span>{isPaused ? "Sistem Dijeda (Kill Switch)" : isDegraded ? "Degraded" : "Sistem Aktif"}</span>
          </div>

          {/* Automation Mode Badge */}
          <div className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
            <Cpu className="w-3.5 h-3.5 text-slate-500" />
            <span>Mode: <b>Manual Review</b></span>
          </div>
        </div>

        {/* Right: Daily Quota & Emergency Kill Switch Button */}
        <div className="flex items-center gap-3">
          {/* Daily Quota Pill */}
          <div className="hidden sm:flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400 font-medium px-2.5 py-1 bg-slate-50 dark:bg-slate-800/60 rounded border border-slate-200 dark:border-slate-800">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>Kuota Hari Ini:</span>
            <span className="font-bold text-slate-900 dark:text-slate-100">0 / 1</span>
            <span className="text-[10px] text-slate-400">(W1)</span>
          </div>

          {/* Emergency Kill Switch Button (always visible, <= 5s effective) */}
          <KillSwitchButton />

          {/* Logout Button */}
          <button
            onClick={handleLogout}
            title="Keluar dari akun admin"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:text-rose-600 hover:border-rose-300 dark:hover:text-rose-400 dark:hover:border-rose-900 transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Keluar</span>
          </button>
        </div>
      </div>
    </header>
  );
}
