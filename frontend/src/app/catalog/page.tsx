"use client";

import React, { useState } from "react";
import { Package, Tag, PenTool, UserCheck } from "lucide-react";
import ProductTab from "@/components/catalog/ProductTab";
import NicheTab from "@/components/catalog/NicheTab";
import StyleTab from "@/components/catalog/StyleTab";
import PersonaTab from "@/components/catalog/PersonaTab";

type TabKey = "products" | "niches" | "styles" | "personas";

const TABS: { key: TabKey; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: "products", label: "Produk Afiliasi", icon: Package },
  { key: "niches", label: "Niche", icon: Tag },
  { key: "styles", label: "Gaya Penulisan", icon: PenTool },
  { key: "personas", label: "Persona Akun", icon: UserCheck },
];

export default function CatalogPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("products");

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Title & Context Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
          Katalog &amp; Konten
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-1">
          Pusat kurasi materi konten: kelola produk Benable, segmentasi niche, gaya persona, dan impor massal CSV.
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

      {/* Active Tab Content */}
      <div className="pt-2">
        {activeTab === "products" && <ProductTab />}
        {activeTab === "niches" && <NicheTab />}
        {activeTab === "styles" && <StyleTab />}
        {activeTab === "personas" && <PersonaTab />}
      </div>
    </div>
  );
}
