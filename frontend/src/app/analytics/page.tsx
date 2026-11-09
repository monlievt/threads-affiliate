"use client";

import React, { useState } from "react";
import {
  BarChart3,
  FlaskConical,
  MousePointerClick,
  FileSpreadsheet,
} from "lucide-react";
import ExperimentsTab from "@/components/analytics/ExperimentsTab";
import PerformanceTab from "@/components/analytics/PerformanceTab";
import BenableClicksSection from "@/components/analytics/BenableClicksSection";
import WeeklyReportTab from "@/components/analytics/WeeklyReportTab";

type ActiveTab = "experiments" | "performance" | "clicks" | "weekly";

export default function AnalyticsPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("experiments");

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
          Analytics & Eksperimen Konten
        </h1>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Uji ilmiah A/B (niche & gaya) berbasis formula <code>rule_v1</code>, pelacakan metrik bucket Threads, dan rekonsiliasi klik Benable.
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="flex border-b border-slate-200 dark:border-slate-800 space-x-1 sm:space-x-2 overflow-x-auto text-xs">
        <button
          onClick={() => setActiveTab("experiments")}
          className={`flex items-center gap-2 px-3 py-2.5 font-semibold border-b-2 transition-colors whitespace-nowrap ${
            activeTab === "experiments"
              ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
              : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
          }`}
        >
          <FlaskConical className="w-4 h-4" />
          <span>Eksperimen & Uji (rule_v1)</span>
        </button>

        <button
          onClick={() => setActiveTab("performance")}
          className={`flex items-center gap-2 px-3 py-2.5 font-semibold border-b-2 transition-colors whitespace-nowrap ${
            activeTab === "performance"
              ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
              : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
          }`}
        >
          <BarChart3 className="w-4 h-4" />
          <span>Performa & Postingan</span>
        </button>

        <button
          onClick={() => setActiveTab("clicks")}
          className={`flex items-center gap-2 px-3 py-2.5 font-semibold border-b-2 transition-colors whitespace-nowrap ${
            activeTab === "clicks"
              ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
              : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
          }`}
        >
          <MousePointerClick className="w-4 h-4" />
          <span>Klik Benable & Atribusi</span>
        </button>

        <button
          onClick={() => setActiveTab("weekly")}
          className={`flex items-center gap-2 px-3 py-2.5 font-semibold border-b-2 transition-colors whitespace-nowrap ${
            activeTab === "weekly"
              ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
              : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
          }`}
        >
          <FileSpreadsheet className="w-4 h-4" />
          <span>Laporan Mingguan</span>
        </button>
      </div>

      {/* Tab Panels */}
      <div>
        {activeTab === "experiments" && <ExperimentsTab />}
        {activeTab === "performance" && <PerformanceTab />}
        {activeTab === "clicks" && <BenableClicksSection />}
        {activeTab === "weekly" && <WeeklyReportTab />}
      </div>
    </div>
  );
}
