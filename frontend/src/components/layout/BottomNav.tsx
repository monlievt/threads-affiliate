"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Inbox,
  FolderKanban,
  CalendarDays,
  Settings,
} from "lucide-react";

const MOBILE_NAV = [
  { label: "Beranda", href: "/", icon: LayoutDashboard },
  { label: "Review", href: "/review", icon: Inbox },
  { label: "Katalog", href: "/catalog", icon: FolderKanban },
  { label: "Jadwal", href: "/schedule", icon: CalendarDays },
  { label: "Pengaturan", href: "/settings", icon: Settings },
];

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-40 bg-white/95 dark:bg-slate-900/95 border-t border-slate-200 dark:border-slate-800 backdrop-blur-xs">
      <div className="grid grid-cols-5 h-14">
        {MOBILE_NAV.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center justify-center gap-1 text-[10px] font-medium transition-colors ${
                isActive
                  ? "text-slate-950 dark:text-white font-bold"
                  : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? "stroke-[2.5]" : "stroke-[1.75]"}`} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
