"use client";

import React, { useState, useEffect } from "react";
import {
  CheckCheck,
  Filter,
  Inbox,
  Keyboard,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useBatchApproveDrafts, useDrafts } from "@/hooks/useDrafts";
import DraftCard from "@/components/review/DraftCard";

export default function ReviewQueuePage() {
  const [statusFilter, setStatusFilter] = useState<string>("pending_review");
  const [activeIndex, setActiveIndex] = useState<number>(0);
  const [showBatchModal, setShowBatchModal] = useState(false);

  const { data: drafts, isLoading, refetch, isRefetching } = useDrafts({
    status: statusFilter === "all" ? undefined : statusFilter,
  });

  const batchApproveMutation = useBatchApproveDrafts();

  const draftList = drafts || [];
  const pendingCount = draftList.filter((d) => d.status === "pending_review").length;

  // Keyboard navigation shortcuts: J/K to move, A to approve, R to reject
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in input or textarea
      if (
        ["INPUT", "TEXTAREA"].includes((e.target as HTMLElement)?.tagName || "")
      ) {
        return;
      }

      if (e.key === "j" || e.key === "J") {
        setActiveIndex((prev) => Math.min(prev + 1, draftList.length - 1));
      } else if (e.key === "k" || e.key === "K") {
        setActiveIndex((prev) => Math.max(prev - 1, 0));
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [draftList.length]);

  const handleConfirmBatchApprove = async () => {
    try {
      const res = await batchApproveMutation.mutateAsync();
      alert(`Berhasil menyetujui ${res.approved_count} draf yang lolos semua validator!`);
      setShowBatchModal(false);
    } catch (err: any) {
      alert(err?.message || "Gagal melakukan persetujuan massal");
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2.5">
            <span>Antrean Review</span>
            {pendingCount > 0 && (
              <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-amber-500 text-white">
                {pendingCount}
              </span>
            )}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Tinjau kepatuhan konten terhadap 10 aturan keselamatan sebelum dijadwalkan terbit ke Threads
          </p>
        </div>

        {/* Action Buttons: Batch Approve & Refresh */}
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isRefetching}
            className="p-2 text-xs font-medium border rounded-md border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition"
            title="Muat ulang antrean"
          >
            <RefreshCw className={`w-4 h-4 ${isRefetching ? "animate-spin" : ""}`} />
          </button>

          {pendingCount > 0 && (
            <button
              type="button"
              onClick={() => setShowBatchModal(true)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-bold rounded-md bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs transition"
            >
              <CheckCheck className="w-4 h-4" />
              <span>Setujui Semua yang Lolos</span>
            </button>
          )}
        </div>
      </div>

      {/* 2. Filter Bar & Keyboard Hint Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <span className="text-xs font-semibold text-slate-600 dark:text-slate-400">Filter Status:</span>
          <div className="flex items-center gap-1">
            {[
              { label: "Menunggu Review", val: "pending_review" },
              { label: "Disetujui / Jadwal", val: "approved" },
              { label: "Ditolak", val: "rejected" },
              { label: "Semua", val: "all" },
            ].map((f) => (
              <button
                key={f.val}
                type="button"
                onClick={() => {
                  setStatusFilter(f.val);
                  setActiveIndex(0);
                }}
                className={`px-2.5 py-1 text-xs rounded transition ${
                  statusFilter === f.val
                    ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 font-bold"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Keyboard shortcut reminder (docs/08 §4.2) */}
        <div className="hidden lg:flex items-center gap-2 text-[11px] text-slate-400">
          <Keyboard className="w-3.5 h-3.5" />
          <span>
            Pintasan: <kbd className="px-1 py-0.5 bg-slate-100 dark:bg-slate-800 rounded border font-mono">J</kbd> / <kbd className="px-1 py-0.5 bg-slate-100 dark:bg-slate-800 rounded border font-mono">K</kbd> pindah kartu
          </span>
        </div>
      </div>

      {/* 3. Draft List */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center p-16 text-slate-400">
          <Loader2 className="w-8 h-8 animate-spin mb-3" />
          <span className="text-xs font-medium">Memuat antrean draf...</span>
        </div>
      ) : draftList.length === 0 ? (
        /* Empty State (docs/08 §6) */
        <div className="flex flex-col items-center justify-center p-16 text-center bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800">
          <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-400 mb-4">
            <Inbox className="w-6 h-6" />
          </div>
          <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
            Antrean Review Bersih
          </h3>
          <p className="text-xs text-slate-500 max-w-sm mt-1 mb-4">
            Tidak ada draf dalam status ini. Sistem akan menghasilkan varian baru secara otomatis sesuai jadwal.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {draftList.map((draft, idx) => (
            <div
              key={draft.id}
              className={`rounded-lg transition-all ${
                idx === activeIndex ? "ring-2 ring-slate-900 dark:ring-slate-100" : ""
              }`}
            >
              <DraftCard draft={draft} />
            </div>
          ))}
        </div>
      )}

      {/* Batch Approval Confirmation Modal */}
      {showBatchModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="w-full max-w-md p-6 bg-white dark:bg-slate-900 rounded-lg shadow-xl border border-slate-200 dark:border-slate-800">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
                <CheckCheck className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                  Konfirmasi Persetujuan Massal
                </h3>
                <p className="text-xs text-slate-500">
                  Semua draf berstatus 'pending_review' yang lolos 100% aturan validator akan disetujui sekaligus.
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-400 mb-5 p-3 rounded bg-slate-50 dark:bg-slate-800/50">
              Draf yang disetujui akan dialokasikan slot terbitnya oleh scheduler dalam batas jam aktif (09:00 - 21:00 EST).
            </p>

            <div className="flex justify-end gap-2.5">
              <button
                type="button"
                onClick={() => setShowBatchModal(false)}
                disabled={batchApproveMutation.isPending}
                className="px-3.5 py-1.5 text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded"
              >
                Batal
              </button>
              <button
                type="button"
                onClick={handleConfirmBatchApprove}
                disabled={batchApproveMutation.isPending}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded shadow-xs"
              >
                {batchApproveMutation.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                <span>Ya, Setujui Semua</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
