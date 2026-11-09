"use client";

import React, { useState } from "react";
import { Plus, Upload, Trash2, FileText, CheckCircle2, AlertCircle } from "lucide-react";
import { useCatalog } from "@/hooks/useCatalog";
import { useLinkClicks } from "@/hooks/useAnalytics";
import ClickAttributionBanner from "./ClickAttributionBanner";

export default function BenableClicksSection() {
  const { products } = useCatalog();
  const {
    data: clicksData,
    isLoading,
    createClick,
    isCreating,
    deleteClick,
    previewCsv,
    isPreviewing,
    importCsv,
    isImporting,
  } = useLinkClicks();

  const [showManualForm, setShowManualForm] = useState(false);
  const [showCsvModal, setShowCsvModal] = useState(false);

  // Manual Form State
  const [productId, setProductId] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [clicksCount, setClicksCount] = useState(0);
  const [note, setNote] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  // CSV Modal State
  const [csvText, setCsvText] = useState("");
  const [previewResult, setPreviewResult] = useState<any>(null);
  const [csvError, setCsvError] = useState<string | null>(null);

  const activeProducts = products.filter((p) => p.status !== "archived");

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!periodStart || !periodEnd) {
      setFormError("Periode mulai dan selesai wajib diisi.");
      return;
    }
    if (periodStart > periodEnd) {
      setFormError("Periode mulai tidak boleh lebih besar dari periode selesai.");
      return;
    }
    if (clicksCount < 0) {
      setFormError("Jumlah klik tidak boleh negatif.");
      return;
    }

    try {
      await createClick({
        product_id: productId || null,
        period_start: periodStart,
        period_end: periodEnd,
        clicks: clicksCount,
        note: note.trim() || null,
        source: "benable_manual",
      });
      setShowManualForm(false);
      setClicksCount(0);
      setNote("");
    } catch (err: any) {
      setFormError(err?.message || "Gagal menyimpan data klik.");
    }
  };

  const handlePreviewCsv = async () => {
    setCsvError(null);
    if (!csvText.trim()) {
      setCsvError("Konten CSV tidak boleh kosong.");
      return;
    }

    try {
      const res = await previewCsv(csvText);
      setPreviewResult(res);
    } catch (err: any) {
      setCsvError(err?.message || "Gagal memproses pratinjau CSV.");
    }
  };

  const handleCommitCsv = async () => {
    setCsvError(null);
    try {
      await importCsv(csvText);
      setShowCsvModal(false);
      setCsvText("");
      setPreviewResult(null);
    } catch (err: any) {
      setCsvError(err?.message || "Gagal mengimpor CSV.");
    }
  };

  const handleDelete = async (clickId: string) => {
    if (!confirm("Hapus catatan klik ini?")) return;
    try {
      await deleteClick(clickId);
    } catch (err: any) {
      alert(err?.message || "Gagal menghapus.");
    }
  };

  return (
    <div className="space-y-6">
      {/* Mandatory Caveat Banner */}
      <ClickAttributionBanner />

      {/* Header and Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Pencatatan Klik Benable
          </h2>
          <p className="text-xs text-slate-500">
            Total tercatat: <strong>{clicksData?.total_clicks || 0}</strong> klik di seluruh produk.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowManualForm(!showManualForm)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-300 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>{showManualForm ? "Tutup Form" : "Entri Manual"}</span>
          </button>
          <button
            onClick={() => {
              setShowCsvModal(true);
              setPreviewResult(null);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-colors"
          >
            <Upload className="w-3.5 h-3.5" />
            <span>Impor CSV Benable</span>
          </button>
        </div>
      </div>

      {/* Manual Input Form */}
      {showManualForm && (
        <form
          onSubmit={handleManualSubmit}
          className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-4 text-xs animate-in fade-in duration-200"
        >
          <h3 className="font-bold text-slate-900 dark:text-slate-100">Catat Klik Manual</h3>

          {formError && (
            <div className="p-2.5 rounded-md bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300">
              {formError}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block font-semibold text-slate-600 dark:text-slate-400 mb-1">
                Tautkan ke Produk
              </label>
              <select
                value={productId}
                onChange={(e) => setProductId(e.target.value)}
                className="w-full px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              >
                <option value="">Pilih Produk (Opsional)...</option>
                {activeProducts.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-semibold text-slate-600 dark:text-slate-400 mb-1">
                Jumlah Klik
              </label>
              <input
                type="number"
                min={0}
                value={clicksCount}
                onChange={(e) => setClicksCount(parseInt(e.target.value) || 0)}
                className="w-full px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-600 dark:text-slate-400 mb-1">
                Periode Mulai
              </label>
              <input
                type="date"
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
                className="w-full px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-600 dark:text-slate-400 mb-1">
                Periode Selesai
              </label>
              <input
                type="date"
                value={periodEnd}
                onChange={(e) => setPeriodEnd(e.target.value)}
                className="w-full px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              />
            </div>
          </div>

          <div>
            <label className="block font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Catatan (Opsional)
            </label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Contoh: Batch review mingguan Benable dashboard"
              className="w-full px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setShowManualForm(false)}
              className="px-3 py-1.5 rounded-md border border-slate-300 text-slate-600"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={isCreating}
              className="px-3 py-1.5 rounded-md bg-indigo-600 text-white font-semibold disabled:opacity-50"
            >
              {isCreating ? "Menyimpan..." : "Simpan Catatan Klik"}
            </button>
          </div>
        </form>
      )}

      {/* Recorded Clicks Table */}
      <div className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-4">
        <h3 className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
          Riwayat Klik Terhubung
        </h3>

        {isLoading ? (
          <div className="py-8 text-center text-xs text-slate-400">Memuat data klik...</div>
        ) : (clicksData?.items || []).length === 0 ? (
          <div className="py-8 text-center text-xs text-slate-400">
            Belum ada catatan klik dari Benable. Gunakan tombol "Entri Manual" atau "Impor CSV".
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 font-semibold">
                  <th className="py-2 px-3">Produk</th>
                  <th className="py-2 px-3">Rentang Periode</th>
                  <th className="py-2 px-3 text-right">Klik</th>
                  <th className="py-2 px-3">Sumber</th>
                  <th className="py-2 px-3">Catatan</th>
                  <th className="py-2 px-3 text-center">Aksi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {(clicksData?.items || []).map((c) => (
                  <tr key={c.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40">
                    <td className="py-2 px-3 font-medium text-slate-900 dark:text-slate-100">
                      {c.product_title || "—"}
                    </td>
                    <td className="py-2 px-3 font-mono text-[11px] text-slate-600 dark:text-slate-400">
                      {c.period_start.slice(0, 10)} s/d {c.period_end.slice(0, 10)}
                    </td>
                    <td className="py-2 px-3 text-right font-mono font-bold text-indigo-600 dark:text-indigo-400">
                      {c.clicks.toLocaleString()}
                    </td>
                    <td className="py-2 px-3">
                      <span className="px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-[10px] font-mono">
                        {c.source}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-slate-500 max-w-xs truncate">{c.note || "—"}</td>
                    <td className="py-2 px-3 text-center">
                      <button
                        onClick={() => handleDelete(c.id)}
                        className="p-1 rounded text-slate-400 hover:text-rose-600"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* CSV Import Modal */}
      {showCsvModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-2xl w-full max-w-xl overflow-hidden p-6 space-y-4 text-xs">
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <Upload className="w-4 h-4 text-indigo-600" />
              <span>Impor CSV Klik Benable</span>
            </h3>

            <p className="text-slate-500 leading-relaxed">
              Format header yang didukung: <code>product, period_start, period_end, clicks, note</code>.
              Validasi baris demi baris akan memeriksa kecocokan produk, tanggal valid, dan klik non-negatif.
            </p>

            {csvError && (
              <div className="p-2.5 rounded-md bg-rose-50 border border-rose-200 text-rose-700">
                {csvError}
              </div>
            )}

            <textarea
              rows={6}
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
              placeholder="product,period_start,period_end,clicks,note&#10;Ergonomic Keyboard,2026-11-01,2026-11-07,45,Batch 1"
              className="w-full p-3 rounded-md font-mono border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none"
            />

            {previewResult && (
              <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800 space-y-2">
                <div className="flex items-center justify-between font-bold">
                  <span>Hasil Pratinjau:</span>
                  <span className="text-emerald-600">
                    {previewResult.imported_count} baris valid / {previewResult.total_rows} total
                  </span>
                </div>
                {previewResult.errors?.length > 0 && (
                  <div className="space-y-1 text-rose-600 text-[11px]">
                    <span className="font-semibold">Galat ditemukan:</span>
                    {previewResult.errors.map((e: any, idx: number) => (
                      <div key={idx}>
                        Baris {e.row}: {e.reason}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setShowCsvModal(false)}
                className="px-3 py-1.5 rounded-md border border-slate-300 text-slate-600"
              >
                Tutup
              </button>
              {!previewResult ? (
                <button
                  type="button"
                  onClick={handlePreviewCsv}
                  disabled={isPreviewing}
                  className="px-3 py-1.5 rounded-md bg-indigo-600 text-white font-semibold disabled:opacity-50"
                >
                  {isPreviewing ? "Memeriksa..." : "Pratinjau Validasi"}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleCommitCsv}
                  disabled={isImporting || previewResult.imported_count === 0}
                  className="px-3 py-1.5 rounded-md bg-emerald-600 text-white font-semibold disabled:opacity-50"
                >
                  {isImporting ? "Mengimpor..." : `Komit ${previewResult.imported_count} Baris`}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
