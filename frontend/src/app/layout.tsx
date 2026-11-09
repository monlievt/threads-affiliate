import type { Metadata } from "next";
import "./globals.css";
import QueryProvider from "@/components/providers/QueryProvider";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import BottomNav from "@/components/layout/BottomNav";

export const metadata: Metadata = {
  title: "Threads Affiliate Automation Dashboard",
  description: "Semi-automated affiliate content engine for Threads",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="id">
      <body className="flex min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
        <QueryProvider>
          {/* Desktop Sidebar */}
          <Sidebar />

          {/* Main App Layout */}
          <div className="flex-1 flex flex-col min-w-0 pb-16 lg:pb-0">
            {/* Top Navigation & Status Bar */}
            <Header />

            {/* Page Body Container */}
            <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
              {children}
            </main>
          </div>

          {/* Mobile Bottom Navigation */}
          <BottomNav />
        </QueryProvider>
      </body>
    </html>
  );
}
