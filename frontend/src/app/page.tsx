"use client";

import React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Cpu,
  Flame,
  Inbox,
  Layers,
  PlayCircle,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useSystemHealth, useKillSwitch } from "@/hooks/useSystemStatus";

export default function DashboardHomePage() {
  const { data: health } = useSystemHealth();
  const { data: killSwitch } = useKillSwitch();

  const isPaused = killSwitch?.active ?? (health?.kill_switch === "on");
  const heartbeatAge = health?.worker_heartbeat_age_sec;
  const isWorkerStale = heartbeatAge !== null && heartbeatAge !== undefined && heartbeatAge > 120;

  return (
    <div className="space-y-6">
      {/* Page Title & Breadcrumb */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Beranda Operasional
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Pusat kendali otomatisasi konten afiliasi Threads & pemantauan keselamatan
          </p>
        </div>

        {/* Quick Review Link */}
        <Link
          href="/review"
          className="inline-flex items-center justify-center gap-2 px-4 py-2 text-xs font-semibold rounded-md bg-slate-900 text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200 transition shadow-xs self-start sm:self-auto"
        >
          <Inbox className="w-4 h-4" />
          <span>Buka Antrean Review</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {/* Emergency Kill Switch Banner (if paused) */}
      {isPaused && (
        <div className="p-4 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-800 dark:text-rose-300">
          <div className="flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <h4 className="text-sm font-bold">Kill Switch Sedang Aktif (Publishing Dijeda)</h4>
              <p className="text-xs mt-1 text-rose-700 dark:text-rose-300">
                Alasan: <span className="font-semibold">{killSwitch?.reason || "Default ON saat startup"}</span>
              </p>
              <p className="text-[11px] text-rose-600/80 dark:text-rose-400/80 mt-1">
                Seluruh proses penerbitan ke Threads dihentikan. Anda dapat mengaktifkan kembali melalui tombol di header setelah memastikan kondisi aman.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Worker Stale Warning (if degraded) */}
      {isWorkerStale && (
        <div className="p-3.5 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 text-amber-800 dark:text-amber-300">
          <div className="flex items-center gap-2.5 text-xs font-medium">
            <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
            <span>
              Worker background tidak mengirim denyut heartbeat selama {Math.round(heartbeatAge || 0)} detik. Periksa proses worker.
            </span>
          </div>
        </div>
      )}

      {/* 4 Core Metric & State Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Status Sistem & Gerbang */}
        <div className="p-4 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-medium">Gerbang Keselamatan</span>
            {isPaused ? (
              <ShieldAlert className="w-4 h-4 text-rose-500" />
            ) : (
              <ShieldCheck className="w-4 h-4 text-emerald-500" />
            )}
          </div>
          <div className="text-lg font-bold text-slate-900 dark:text-slate-100">
            {isPaused ? "Dijeda" : "Aktif"}
          </div>
          <div className="mt-2 text-[11px] text-slate-500 flex items-center justify-between">
            <span>PublishGuard:</span>
            <span className="font-semibold text-emerald-600 dark:text-emerald-400">10 Cek Ketat</span>
          </div>
        </div>

        {/* Card 2: Warmup & Kuota */}
        <div className="p-4 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-medium">Warmup Schedule</span>
            <Flame className="w-4 h-4 text-amber-500" />
          </div>
          <div className="text-lg font-bold text-slate-900 dark:text-slate-100">
            Minggu 1 <span className="text-xs font-normal text-slate-400">(Maks 1/hari)</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-500 flex items-center justify-between">
            <span>Interval Minimum:</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300">240 Menit</span>
          </div>
        </div>

        {/* Card 3: Status Heartbeat & Database */}
        <div className="p-4 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-medium">Koneksi & Worker</span>
            <Cpu className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-lg font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <span>DB: {health?.db === "ok" ? "OK" : "Error"}</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-500 flex items-center justify-between">
            <span>Heartbeat:</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300">
              {heartbeatAge !== null && heartbeatAge !== undefined ? `${Math.round(heartbeatAge)}s lalu` : "Belum aktif"}
            </span>
          </div>
        </div>

        {/* Card 4: Token Threads */}
        <div className="p-4 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-medium">Token OAuth Threads</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-lg font-bold text-slate-900 dark:text-slate-100">
            {health?.token_valid ? "Valid" : "Tersambung"}
          </div>
          <div className="mt-2 text-[11px] text-slate-500 flex items-center justify-between">
            <span>Enkripsi:</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300">Fernet AES</span>
          </div>
        </div>
      </div>

      {/* Quick Action Panels */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
        <Link
          href="/review"
          className="group p-5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-400 dark:hover:border-slate-600 transition shadow-2xs flex flex-col justify-between"
        >
          <div>
            <div className="w-8 h-8 rounded-md bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-700 dark:text-slate-300 mb-3 group-hover:scale-105 transition-transform">
              <Inbox className="w-4 h-4" />
            </div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">Antrean Review Draf</h3>
            <p className="text-xs text-slate-500 mt-1">
              Tinjau draf hasil generator AI, periksa validator V-LEN s/d V-MISC, dan setujui untuk jadwal.
            </p>
          </div>
          <div className="mt-4 flex items-center text-xs font-semibold text-slate-900 dark:text-slate-100 group-hover:translate-x-1 transition-transform">
            <span>Buka Antrean</span>
            <ArrowRight className="w-3.5 h-3.5 ml-1" />
          </div>
        </Link>

        <Link
          href="/catalog"
          className="group p-5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-400 dark:hover:border-slate-600 transition shadow-2xs flex flex-col justify-between"
        >
          <div>
            <div className="w-8 h-8 rounded-md bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-700 dark:text-slate-300 mb-3 group-hover:scale-105 transition-transform">
              <Layers className="w-4 h-4" />
            </div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">Katalog & Impor CSV</h3>
            <p className="text-xs text-slate-500 mt-1">
              Kelola niche, produk afiliasi Benable terverifikasi, gaya penulisan, dan persona akun.
            </p>
          </div>
          <div className="mt-4 flex items-center text-xs font-semibold text-slate-900 dark:text-slate-100 group-hover:translate-x-1 transition-transform">
            <span>Kelola Katalog</span>
            <ArrowRight className="w-3.5 h-3.5 ml-1" />
          </div>
        </Link>

        <Link
          href="/schedule"
          className="group p-5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-400 dark:hover:border-slate-600 transition shadow-2xs flex flex-col justify-between"
        >
          <div>
            <div className="w-8 h-8 rounded-md bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-700 dark:text-slate-300 mb-3 group-hover:scale-105 transition-transform">
              <Clock className="w-4 h-4" />
            </div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">Jadwal Kalender</h3>
            <p className="text-xs text-slate-500 mt-1">
              Visualisasi slot posting 24 jam ke depan di dalam jam aktif 09:00 - 21:00 EST dengan jitter.
            </p>
          </div>
          <div className="mt-4 flex items-center text-xs font-semibold text-slate-900 dark:text-slate-100 group-hover:translate-x-1 transition-transform">
            <span>Lihat Jadwal</span>
            <ArrowRight className="w-3.5 h-3.5 ml-1" />
          </div>
        </Link>
      </div>
    </div>
  );
}
