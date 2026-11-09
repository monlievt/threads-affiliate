"use client";

import React, { useState } from "react";
import { AlertTriangle, CheckCircle2, ShieldAlert, Clock, Check, X, FileText } from "lucide-react";
import { useIncidents, useResolveIncident } from "@/hooks/useSettings";
import { IncidentItem } from "@/types";

export default function IncidentsTab() {
  const [filterResolved, setFilterResolved] = useState<boolean | undefined>(undefined);
  const { data: incidents = [], isLoading, error, refetch } = useIncidents(filterResolved);
  const resolveMutation = useResolveIncident();

  const [resolvingIncident, setResolvingIncident] = useState<IncidentItem | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [resolveError, setResolveError] = useState<string | null>(null);

  const handleOpenResolve = (inc: IncidentItem) => {
    setResolvingIncident(inc);
    setResolutionNotes("");
    setResolveError(null);
  };

  const handleConfirmResolve = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resolvingIncident || !resolutionNotes.trim()) return;
    setResolveError(null);

    try {
      await resolveMutation.mutateAsync({
        incidentId: resolvingIncident.id,
        notes: resolutionNotes.trim(),
      });
      setResolvingIncident(null);
      refetch();
    } catch (err: any) {
      setResolveError(err.message || "Gagal menyelesaikan insiden.");
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Filter Controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Daftar Insiden Sistem &amp; Safety
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Log insiden keamanan, galat API beruntun, pemicu kill switch, dan rate limit.
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 p-0.5 text-xs">
          <button
            onClick={() => setFilterResolved(undefined)}
            className={`px-3 py-1 rounded-md font-medium transition-colors ${
              filterResolved === undefined
                ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
            }`}
          >
            Semua
          </button>
          <button
            onClick={() => setFilterResolved(false)}
            className={`px-3 py-1 rounded-md font-medium transition-colors ${
              filterResolved === false
                ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
            }`}
          >
            Aktif (Perlu Ditangani)
          </button>
          <button
            onClick={() => setFilterResolved(true)}
            className={`px-3 py-1 rounded-md font-medium transition-colors ${
              filterResolved === true
                ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
            }`}
          >
            Selesai
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="p-8 text-center text-sm text-slate-500 animate-pulse">
          Memuat daftar insiden...
        </div>
      )}

      {error && (
        <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
          Gagal memuat insiden: {(error as any).message}
        </div>
      )}

      {/* Incidents List */}
      {!isLoading && !error && (
        <div className="space-y-3">
          {incidents.length === 0 ? (
            <div className="p-10 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-center space-y-2">
              <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-500" />
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                Tidak Ada Insiden
              </div>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                Semua sistem berjalan lancar tanpa pemicu darurat atau galat keamanan.
              </p>
            </div>
          ) : (
            incidents.map((inc) => (
              <div
                key={inc.id}
                className={`p-4 rounded-xl border transition-all ${
                  inc.resolved_at
                    ? "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 opacity-80"
                    : inc.severity === "critical"
                    ? "border-red-300 dark:border-red-800 bg-red-50/20 dark:bg-red-950/20 shadow-xs"
                    : "border-amber-300 dark:border-amber-800 bg-amber-50/20 dark:bg-amber-950/20 shadow-xs"
                }`}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                        inc.severity === "critical"
                          ? "bg-red-100 text-red-700 dark:bg-red-950/60 dark:text-red-400"
                          : inc.severity === "warning"
                          ? "bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-400"
                          : "bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-400"
                      }`}
                    >
                      {inc.severity}
                    </span>
                    <span className="font-mono font-bold text-xs text-slate-900 dark:text-slate-100">
                      {inc.code}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-[11px] text-slate-400 font-mono">
                      {inc.created_at.replace("T", " ").slice(0, 19)} UTC
                    </span>
                    {inc.resolved_at ? (
                      <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 text-[11px] font-medium">
                        <Check className="w-3.5 h-3.5" />
                        <span>Diselesaikan</span>
                      </span>
                    ) : (
                      <button
                        onClick={() => handleOpenResolve(inc)}
                        className="px-2.5 py-1 text-xs font-medium rounded-md bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100 transition-colors"
                      >
                        Tandai Selesai
                      </button>
                    )}
                  </div>
                </div>

                {inc.detail && (
                  <div className="mt-2.5 p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 font-mono text-[11px] text-slate-700 dark:text-slate-300 whitespace-pre-wrap break-all">
                    {inc.detail}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Modal: Tandai Selesai Insiden */}
      {resolvingIncident && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                Selesaikan Insiden: {resolvingIncident.code}
              </h3>
            </div>
            <form onSubmit={handleConfirmResolve} className="p-6 space-y-4">
              {resolveError && (
                <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
                  {resolveError}
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Catatan Investigasi &amp; Resolusi <span className="text-red-500">*</span>
                </label>
                <textarea
                  rows={3}
                  required
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  placeholder="Jelaskan akar penyebab masalah dan tindakan perbaikan yang telah diambil..."
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setResolvingIncident(null)}
                  className="px-3.5 py-2 text-xs font-medium rounded-lg text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={resolveMutation.isPending || !resolutionNotes.trim()}
                  className="px-4 py-2 text-xs font-medium rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition-colors disabled:opacity-50"
                >
                  {resolveMutation.isPending ? "Menyimpan..." : "Konfirmasi Selesai"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
