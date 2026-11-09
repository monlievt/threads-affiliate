"use client";

import React, { useState } from "react";
import { History, Search, FileJson, AlertCircle } from "lucide-react";
import { useAuditLogs } from "@/hooks/useSettings";
import { AuditLogItem } from "@/types";

export default function AuditTrailTab() {
  const [actionFilter, setActionFilter] = useState<string>("");
  const [selectedDetailLog, setSelectedDetailLog] = useState<AuditLogItem | null>(null);

  const { data: logs = [], isLoading, error } = useAuditLogs(100, 0, actionFilter || undefined);

  return (
    <div className="space-y-6">
      {/* Header & Filter */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Riwayat Jejak Audit (Audit Trail)
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Log mutasi append-only permanen untuk menjamin akuntabilitas seluruh aksi operator dan sistem.
          </p>
        </div>

        {/* Action Filter */}
        <div className="flex items-center gap-2">
          <select
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="px-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 focus:outline-hidden"
          >
            <option value="">Semua Aksi</option>
            <option value="approve_draft">approve_draft</option>
            <option value="reject_draft">reject_draft</option>
            <option value="edit_draft">edit_draft</option>
            <option value="reschedule_draft">reschedule_draft</option>
            <option value="batch_approve_drafts">batch_approve_drafts</option>
            <option value="update_account_settings">update_account_settings</option>
            <option value="resolve_incident">resolve_incident</option>
            <option value="toggle_kill_switch">toggle_kill_switch</option>
            <option value="import_csv">import_csv</option>
          </select>
        </div>
      </div>

      {isLoading && (
        <div className="p-8 text-center text-sm text-slate-500 animate-pulse">
          Memuat riwayat audit...
        </div>
      )}

      {error && (
        <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Gagal memuat log audit: {(error as any).message}</span>
        </div>
      )}

      {/* Audit Log Table */}
      {!isLoading && !error && (
        <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xs">
          <table className="w-full text-left text-xs text-slate-600 dark:text-slate-300">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 font-semibold border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="py-3 px-4">Waktu (UTC)</th>
                <th className="py-3 px-4">Aktor</th>
                <th className="py-3 px-4">Aksi</th>
                <th className="py-3 px-4">Entitas</th>
                <th className="py-3 px-4">Detail Mutasi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-400">
                    Belum ada riwayat audit log.
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                      {log.at.replace("T", " ").slice(0, 19)}
                    </td>
                    <td className="py-3 px-4 font-medium text-slate-900 dark:text-slate-100">
                      <span className="px-2 py-0.5 rounded-sm bg-slate-100 dark:bg-slate-800 text-[10px] font-mono">
                        {log.actor}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-800 dark:text-slate-200">
                      {log.action}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-500">
                      {log.entity ? `${log.entity}${log.entity_id ? `:${log.entity_id.slice(0, 8)}` : ""}` : "—"}
                    </td>
                    <td className="py-3 px-4 max-w-xs truncate font-mono text-[11px]">
                      {log.detail ? (
                        <button
                          onClick={() => setSelectedDetailLog(log)}
                          className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          <FileJson className="w-3.5 h-3.5" />
                          <span className="truncate max-w-[200px]">{log.detail}</span>
                        </button>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail JSON Modal */}
      {selectedDetailLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                Detail Log: {selectedDetailLog.action}
              </h3>
              <button
                onClick={() => setSelectedDetailLog(null)}
                className="text-slate-400 hover:text-slate-600 text-xs"
              >
                Tutup
              </button>
            </div>
            <div className="p-6 space-y-3">
              <div className="flex items-center gap-4 text-xs text-slate-500 font-mono">
                <span>Aktor: {selectedDetailLog.actor}</span>
                <span>Waktu: {selectedDetailLog.at}</span>
              </div>
              <pre className="p-4 rounded-xl bg-slate-950 text-slate-100 font-mono text-xs overflow-x-auto max-h-80">
                {(() => {
                  try {
                    return JSON.stringify(JSON.parse(selectedDetailLog.detail || "{}"), null, 2);
                  } catch {
                    return selectedDetailLog.detail;
                  }
                })()}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
