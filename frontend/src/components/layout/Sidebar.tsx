"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Inbox,
  FolderKanban,
  CalendarDays,
  BarChart3,
  MessageSquareShare,
  Settings,
  Sparkles,
  ExternalLink,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Beranda", href: "/", icon: LayoutDashboard },
  { label: "Antrean Review", href: "/review", icon: Inbox },
  { label: "Katalog Konten", href: "/catalog", icon: FolderKanban },
  { label: "Jadwal Kalender", href: "/schedule", icon: CalendarDays },
  { label: "Analytics & Uji", href: "/analytics", icon: BarChart3 },
  { label: "Komentar F10", href: "/comments", icon: MessageSquareShare },
  { label: "Pengaturan & Audit", href: "/settings", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden lg:flex flex-col w-64 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 h-screen sticky top-0 shrink-0">
      {/* Brand Header */}
      <div className="flex items-center gap-2.5 px-6 h-14 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center justify-center w-7 h-7 rounded-md bg-slate-900 text-white dark:bg-white dark:text-slate-900 font-black text-sm">
          @
        </div>
        <div>
          <span className="text-sm font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Threads Affiliate
          </span>
          <span className="block text-[10px] text-slate-400 font-mono">v1.0-alpha · Gerbang B</span>
        </div>
      </div>

      {/* Nav Menu */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center justify-between px-3 py-2 text-xs font-medium rounded-md transition-colors ${
                isActive
                  ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 font-semibold"
                  : "text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-slate-100 dark:hover:bg-slate-800/60"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Icon className={`w-4 h-4 ${isActive ? "text-white dark:text-slate-900" : "text-slate-400"}`} />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-rose-500 text-white">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="p-4 border-t border-slate-200 dark:border-slate-800 text-[11px] text-slate-500 space-y-1">
        <div className="flex items-center justify-between">
          <span>Engine</span>
          <span className="font-mono font-medium text-slate-700 dark:text-slate-300">FastAPI + WAL</span>
        </div>
        <div className="flex items-center justify-between">
          <span>Target Audience</span>
          <span className="font-medium text-slate-700 dark:text-slate-300">US (EST)</span>
        </div>
        <div className="flex items-center justify-between">
          <span>LLM Provider</span>
          <span className="font-medium text-slate-700 dark:text-slate-300">Gemini Pro</span>
        </div>
      </div>
    </aside>
  );
}
