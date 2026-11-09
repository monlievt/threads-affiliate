"use client";

import React, { useState } from "react";
import {
  FileText,
  Copy,
  Check,
  Calendar,
  AlertTriangle,
  CheckCircle2,
  TrendingUp,
  UserCheck,
  ShieldAlert,
} from "lucide-react";
import { useWeeklyReport } from "@/hooks/useAnalytics";

export default function WeeklyReportTab() {
  const { data: report, isLoading } = useWeeklyReport(7);
  const [copied, setCopied] = useState(false);

  const handleCopyTelegram = () => {
    if (!report) return;

    const lines = [
      `📅 <b>Laporan Mingguan Threads</b> (${report.period_start} s/d ${report.period_end})`,
      "",
      `🚀 <b>Publikasi & Performa:</b>`,
      `• Postingan Terbit: <b>${report.total_posts_published}</b>`,
      `• Total Views: <b>${report.total_views.toLocaleString()}</b>`,
      `• Rata-rata ER: <b>${report.average_er_pct.toFixed(2)}%</b>`,
      "",
      `👨‍💻 <b>Beban Review Operator:</b>`,
      `• Disetujui: <b>${report.operator_workload.approved}</b>`,
      `• Ditolak: <b>${report.operator_workload.rejected}</b>`,
      `• Antrean Saat Ini: <b>${report.operator_workload.current_pending_queue} draf</b>`,
      "",
      `🧪 <b>Evaluasi Eksperimen (rule_v1):</b>`,
    ];

    for (const exp of report.experiments || []) {
      lines.push(`• <b>Fase: ${exp.phase}</b> (${exp.status})`);
      for (const a of exp.arms || []) {
        const tag = a.insufficient_data ? " [data kurang]" : ` [Rank #${a.rank}]`;
        lines.push(`  - ${a.label} (n=${a.n}${tag}): ER=${a.median_er_72}%, Views=${a.median_views_72}`);
      }
      lines.push(`  💡 <i>${exp.explanation}</i>`);
    }

    if (report.incidents?.unresolved_count > 0) {
      lines.push(`\n⚠️ <b>Insiden:</b> ${report.incidents.unresolved_count} insiden aktif!`);
    }

    lines.push(`\n🎯 <b>Rekomendasi Tindakan:</b>`);
    for (const act of report.suggested_actions || []) {
      lines.push(`• ${act}`);
    }

    navigator.clipboard.writeText(lines.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12 text-slate-400 text-xs">
        Memuat laporan mingguan...
      </div>
    );
  }

  if (!report) {
    return (
      <div className="py-12 text-center text-xs text-slate-400">
        Belum ada laporan mingguan yang dihasilkan.
      </div>
    );
  }

  return (
    <div className="space-y-6 text-xs">
      {/* Header and Copy Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-indigo-600" />
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              Laporan Mingguan & Evaluasi rule_v1
            </h2>
          </div>
          <p className="text-slate-500 mt-0.5">
            Periode: <strong>{report.period_start}</strong> s/d <strong>{report.period_end}</strong>
          </p>
        </div>

        <button
          onClick={handleCopyTelegram}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white font-semibold transition-colors self-start sm:self-auto"
        >
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          <span>{copied ? "Tersalin ke Clipboard!" : "Salin Format Telegram"}</span>
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-1">
          <span className="text-slate-500 text-[11px]">Post Terbit 7 Hari</span>
          <div className="text-xl font-black text-slate-900 dark:text-slate-100">
            {report.total_posts_published}
          </div>
        </div>
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-1">
          <span className="text-slate-500 text-[11px]">Total Views</span>
          <div className="text-xl font-black text-slate-900 dark:text-slate-100">
            {report.total_views.toLocaleString()}
          </div>
        </div>
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-1">
          <span className="text-slate-500 text-[11px]">Rata-rata ER</span>
          <div className="text-xl font-black text-emerald-600">
            {report.average_er_pct.toFixed(2)}%
          </div>
        </div>
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-1">
          <span className="text-slate-500 text-[11px]">Antrean Review Saat Ini</span>
          <div className="text-xl font-black text-amber-600">
            {report.operator_workload.current_pending_queue} draf
          </div>
        </div>
      </div>

      {/* Suggested Actions Checklist */}
      <div className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-3">
        <h3 className="font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
          <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          <span>Rekomendasi Tindakan Operator</span>
        </h3>
        <div className="space-y-2">
          {report.suggested_actions.map((act: string, idx: number) => (
            <div
              key={idx}
              className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 text-slate-700 dark:text-slate-300 font-medium leading-relaxed"
            >
              {act}
            </div>
          ))}
        </div>
      </div>

      {/* Operator Review Workload & Incidents Breakdown */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-3">
          <h3 className="font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
            <UserCheck className="w-4 h-4 text-blue-500" />
            <span>Beban Kerja Review Operator</span>
          </h3>
          <div className="space-y-2">
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
              <span className="text-slate-500">Draf Dibuat Periode Ini:</span>
              <span className="font-bold">{report.operator_workload.drafts_created_this_period}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
              <span className="text-slate-500">Disetujui / Terbit:</span>
              <span className="font-bold text-emerald-600">{report.operator_workload.approved}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-500">Ditolak Operator:</span>
              <span className="font-bold text-rose-600">{report.operator_workload.rejected}</span>
            </div>
          </div>
        </div>

        <div className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-3">
          <h3 className="font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
            <ShieldAlert className="w-4 h-4 text-rose-500" />
            <span>Kesehatan Sistem & Insiden</span>
          </h3>
          <div className="space-y-2">
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
              <span className="text-slate-500">Total Insiden Tercatat:</span>
              <span className="font-bold">{report.incidents.total_incidents}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
              <span className="text-slate-500">Insiden Kritis:</span>
              <span className="font-bold text-rose-600">{report.incidents.critical_count}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-500">Insiden Belum Selesai:</span>
              <span className="font-bold text-amber-600">{report.incidents.unresolved_count}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
