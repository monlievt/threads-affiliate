"use client";

import React, { useState } from "react";
import { Plus, Tag, Archive, Edit2, AlertCircle, CheckCircle2 } from "lucide-react";
import { useNiches, useCreateNiche, useUpdateNiche, useArchiveNiche } from "@/hooks/useCatalog";
import { NicheItem } from "@/types";

export default function NicheTab() {
  const { data: niches = [], isLoading, error } = useNiches(true);
  const createMutation = useCreateNiche();
  const updateMutation = useUpdateNiche();
  const archiveMutation = useArchiveNiche();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingNiche, setEditingNiche] = useState<NicheItem | null>(null);
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formKeywords, setFormKeywords] = useState("");
  const [formStatus, setFormStatus] = useState<"active" | "paused" | "archived">("active");
  const [formError, setFormError] = useState<string | null>(null);

  const handleOpenCreate = () => {
    setEditingNiche(null);
    setFormName("");
    setFormDesc("");
    setFormKeywords("");
    setFormStatus("active");
    setFormError(null);
    setModalOpen(true);
  };

  const handleOpenEdit = (niche: NicheItem) => {
    setEditingNiche(niche);
    setFormName(niche.name);
    setFormDesc(niche.description || "");
    setFormKeywords(niche.keywords.join(", "));
    setFormStatus(niche.status);
    setFormError(null);
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const keywordsList = formKeywords
      .split(/[,;\n]/)
      .map((k) => k.trim())
      .filter(Boolean);

    try {
      if (editingNiche) {
        await updateMutation.mutateAsync({
          id: editingNiche.id,
          data: {
            name: formName.trim(),
            description: formDesc.trim() || undefined,
            keywords: keywordsList,
            status: formStatus,
          },
        });
      } else {
        await createMutation.mutateAsync({
          name: formName.trim(),
          description: formDesc.trim() || undefined,
          keywords: keywordsList,
        });
      }
      setModalOpen(false);
    } catch (err: any) {
      setFormError(err.message || "Gagal menyimpan niche.");
    }
  };

  const handleArchive = async (niche: NicheItem) => {
    if (confirm(`Arsipkan niche "${niche.name}"? Produk dalam niche ini tidak akan dihapus permanen.`)) {
      try {
        await archiveMutation.mutateAsync(niche.id);
      } catch (err: any) {
        alert(err.message || "Gagal mengarsipkan niche.");
      }
    }
  };

  return (
    <div className="space-y-6">
      {/* Action Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Manajemen Niche
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Kategori tema postingan Threads untuk penyesuaian audiens AS dan kurasi Benable.
          </p>
        </div>
        <button
          onClick={handleOpenCreate}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium rounded-lg bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100 transition-colors shadow-xs"
        >
          <Plus className="w-4 h-4" />
          <span>Tambah Niche</span>
        </button>
      </div>

      {/* Loading & Error States */}
      {isLoading && (
        <div className="p-8 text-center text-sm text-slate-500 animate-pulse">
          Memuat data niche...
        </div>
      )}

      {error && (
        <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Gagal memuat niche: {(error as any).message}</span>
        </div>
      )}

      {/* Niches Table */}
      {!isLoading && !error && (
        <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <table className="w-full text-left text-xs text-slate-600 dark:text-slate-300">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 font-semibold border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="py-3 px-4">Nama Niche</th>
                <th className="py-3 px-4">Deskripsi</th>
                <th className="py-3 px-4">Kata Kunci (Keywords)</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {niches.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-400">
                    Belum ada niche terdaftar. Tambahkan niche pertama Anda.
                  </td>
                </tr>
              ) : (
                niches.map((niche) => (
                  <tr key={niche.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="py-3.5 px-4 font-medium text-slate-900 dark:text-slate-100">
                      {niche.name}
                    </td>
                    <td className="py-3.5 px-4 max-w-xs truncate text-slate-500 dark:text-slate-400">
                      {niche.description || "—"}
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex flex-wrap gap-1">
                        {niche.keywords.length > 0 ? (
                          niche.keywords.map((kw, i) => (
                            <span
                              key={i}
                              className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-md text-[10px] bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                            >
                              <Tag className="w-2.5 h-2.5" />
                              {kw}
                            </span>
                          ))
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          niche.status === "active"
                            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                            : niche.status === "paused"
                            ? "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400"
                            : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                        }`}
                      >
                        {niche.status}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right space-x-1">
                      <button
                        onClick={() => handleOpenEdit(niche)}
                        className="p-1 rounded-md text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition-colors"
                        title="Edit Niche"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      {niche.status !== "archived" && (
                        <button
                          onClick={() => handleArchive(niche)}
                          className="p-1 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                          title="Arsipkan Niche"
                        >
                          <Archive className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal Form */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {editingNiche ? "Edit Niche" : "Tambah Niche Baru"}
              </h3>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {formError && (
                <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
                  {formError}
                </div>
              )}
              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Nama Niche <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="Misal: Desk Setup, Coffee Gadgets"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-slate-900 dark:focus:ring-slate-400"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Deskripsi
                </label>
                <textarea
                  rows={2}
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  placeholder="Deskripsi target pembaca dan audiens..."
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-slate-900 dark:focus:ring-slate-400"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Kata Kunci (pisahkan dengan koma)
                </label>
                <input
                  type="text"
                  value={formKeywords}
                  onChange={(e) => setFormKeywords(e.target.value)}
                  placeholder="ergonomic, monitor stand, clean desk"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-slate-900 dark:focus:ring-slate-400"
                />
              </div>

              {editingNiche && (
                <div>
                  <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Status
                  </label>
                  <select
                    value={formStatus}
                    onChange={(e) => setFormStatus(e.target.value as any)}
                    className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                  >
                    <option value="active">Active</option>
                    <option value="paused">Paused</option>
                    <option value="archived">Archived</option>
                  </select>
                </div>
              )}

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="px-3.5 py-2 text-xs font-medium rounded-lg text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                  className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-100 transition-colors disabled:opacity-50"
                >
                  {createMutation.isPending || updateMutation.isPending ? "Menyimpan..." : "Simpan Niche"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
