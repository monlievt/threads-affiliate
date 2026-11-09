"use client";

import React, { useState } from "react";
import { UserCog, Sliders, ShieldAlert, History } from "lucide-react";
import AccountTab from "@/components/settings/AccountTab";
import OperationalLimitsTab from "@/components/settings/OperationalLimitsTab";
import IncidentsTab from "@/components/settings/IncidentsTab";
import AuditTrailTab from "@/components/settings/AuditTrailTab";

type TabKey = "account" | "limits" | "incidents" | "audit";

const TABS: { key: TabKey; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: "account", label: "Akun & Otomasi", icon: UserCog },
  { key: "limits", label: "Batas Operasional", icon: Sliders },
  { key: "incidents", label: "Insiden Safety", icon: ShieldAlert },
  { key: "audit", label: "Audit Trail", icon: History },
];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("account");

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
          Pengaturan, Batas &amp; Audit
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-1">
          Konfigurasi mode otonomi, kriteria kelayakan full-auto, batas keras operasional, dan riwayat audit trail.
        </p>
      </div>

      {/* Tabs Switcher */}
      <div className="border-b border-slate-200 dark:border-slate-800">
        <nav className="flex space-x-2 sm:space-x-4 overflow-x-auto" aria-label="Tabs">
          {TABS.map((tab) => {
            const isActive = activeTab === tab.key;
            const Icon = tab.icon;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`inline-flex items-center gap-2 py-3 px-3 sm:px-4 text-xs sm:text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                  isActive
                    ? "border-slate-900 text-slate-900 dark:border-white dark:text-white font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300 dark:text-slate-400 dark:hover:text-slate-200"
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? "stroke-[2.5]" : "stroke-[1.75]"}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Active Tab View */}
      <div className="pt-2">
        {activeTab === "account" && <AccountTab />}
        {activeTab === "limits" && <OperationalLimitsTab />}
        {activeTab === "incidents" && <IncidentsTab />}
        {activeTab === "audit" && <AuditTrailTab />}
      </div>
    </div>
  );
}
