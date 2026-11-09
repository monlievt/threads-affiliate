"use client";

import React, { useState } from "react";
import { Plus, Edit2, Archive, Sparkles, Check, X, AlertCircle } from "lucide-react";
import { useStyles, useCreateStyle, useUpdateStyle, useArchiveStyle } from "@/hooks/useCatalog";
import { StyleItem } from "@/types";

export default function StyleTab() {
  const { data: styles = [], isLoading, error } = useStyles(true);
  const createMutation = useCreateStyle();
  const updateMutation = useUpdateStyle();
  const archiveMutation = useArchiveStyle();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingStyle, setEditingStyle] = useState<StyleItem | null>(null);
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formToneRules, setFormToneRules] = useState("");
  const [formMaxChars, setFormMaxChars] = useState(400);
  const [formGoodExamples, setFormGoodExamples] = useState("");
  const [formBadExamples, setFormBadExamples] = useState("");
  const [formStatus, setFormStatus] = useState<"active" | "paused" | "archived">("active");
  const [formError, setFormError] = useState<string | null>(null);

  const handleOpenCreate = () => {
    setEditingStyle(null);
    setFormName("");
    setFormDesc("");
    setFormToneRules("");
    setFormMaxChars(400);
    setFormGoodExamples("");
    setFormBadExamples("");
    setFormStatus("active");
    setFormError(null);
    setModalOpen(true);
  };

  const handleOpenEdit = (s: StyleItem) => {
    setEditingStyle(s);
    setFormName(s.name);
    setFormDesc(s.description);
    setFormToneRules(s.tone_rules);
    setFormMaxChars(s.max_chars);
    setFormGoodExamples(s.good_examples.join("\n---\n"));
    setFormBadExamples(s.bad_examples.join("\n---\n"));
    setFormStatus(s.status);
    setFormError(null);
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const goodList = formGoodExamples
      .split("\n---\n")
      .map((ex) => ex.trim())
      .filter(Boolean);

    const badList = formBadExamples
      .split("\n---\n")
      .map((ex) => ex.trim())
      .filter(Boolean);

    try {
      if (editingStyle) {
        await updateMutation.mutateAsync({
          id: editingStyle.id,
          data: {
            name: formName.trim(),
            description: formDesc.trim(),
            tone_rules: formToneRules.trim(),
            max_chars: formMaxChars,
            good_examples: goodList,
            bad_examples: badList,
            status: formStatus,
          },
        });
      } else {
        await createMutation.mutateAsync({
          name: formName.trim(),
          description: formDesc.trim(),
          tone_rules: formToneRules.trim(),
          max_chars: formMaxChars,
          good_examples: goodList,
          bad_examples: badList,
        });
      }
      setModalOpen(false);
    } catch (err: any) {
      setFormError(err.message || "Gagal menyimpan gaya penulisan.");
    }
  };

  const handleArchive = async (s: StyleItem) => {
    if (confirm(`Arsipkan gaya penulisan "${s.name}"? Draf yang ada tidak akan terpengaruh.`)) {
      try {
        await archiveMutation.mutateAsync(s.id);
      } catch (err: any) {
        alert(err.message || "Gagal mengarsipkan gaya.");
      }
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Gaya Penulisan (Content Styles)
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Profil nada suara, batasan karakter, dan instruksi prompting untuk pembuatan draf LLM.
          </p>
        </div>
        <button
          onClick={handleOpenCreate}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium rounded-lg bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100 transition-colors shadow-xs"
        >
          <Plus className="w-4 h-4" />
          <span>Tambah Gaya</span>
        </button>
      </div>

      {isLoading && (
        <div className="p-8 text-center text-sm text-slate-500 animate-pulse">
          Memuat gaya penulisan...
        </div>
      )}

      {error && (
        <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Gagal memuat gaya: {(error as any).message}</span>
        </div>
      )}

      {/* Grid of Styles */}
      {!isLoading && !error && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {styles.map((style) => (
            <div
              key={style.id}
              className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 hover:border-slate-300 dark:hover:border-slate-700 transition-colors shadow-xs"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                      {style.name}
                    </h3>
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                        style.status === "active"
                          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                          : style.status === "paused"
                          ? "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400"
                          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                      }`}
                    >
                      {style.status}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    {style.description}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleOpenEdit(style)}
                    className="p-1 rounded-md text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition-colors"
                    title="Edit Gaya"
                  >
                    <Edit2 className="w-3.5 h-3.5" />
                  </button>
                  {style.status !== "archived" && (
                    <button
                      onClick={() => handleArchive(style)}
                      className="p-1 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                      title="Arsipkan Gaya"
                    >
                      <Archive className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>

              {/* Character Limit Badge */}
              <div className="flex items-center gap-2 text-xs">
                <span className="text-slate-400">Batas Karakter:</span>
                <span className="font-mono font-medium text-slate-800 dark:text-slate-200 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-md text-[11px]">
                  Max {style.max_chars} karakter
                </span>
              </div>

              {/* Tone Rules */}
              <div className="space-y-1">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                  Aturan Nada Suara (Tone Rules):
                </span>
                <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap font-sans">
                  {style.tone_rules}
                </div>
              </div>

              {/* Examples Summary */}
              <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400 pt-1 border-t border-slate-100 dark:border-slate-800">
                <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                  <Check className="w-3 h-3" />
                  <span>{style.good_examples.length} Contoh Bagus</span>
                </span>
                <span className="flex items-center gap-1 text-red-500">
                  <X className="w-3 h-3" />
                  <span>{style.bad_examples.length} Contoh Dihindari</span>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal: Tambah / Edit Gaya */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs overflow-y-auto">
          <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden my-8">
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {editingStyle ? "Edit Gaya Penulisan" : "Tambah Gaya Penulisan Baru"}
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
                  Nama Gaya <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="Misal: personal_story, quick_review, curator_find"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Deskripsi Singkat <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  placeholder="Deskripsi tujuan gaya penulisan ini..."
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Aturan Nada Suara (Tone Rules) <span className="text-red-500">*</span>
                </label>
                <textarea
                  rows={3}
                  required
                  value={formToneRules}
                  onChange={(e) => setFormToneRules(e.target.value)}
                  placeholder="Gunakan sudut pandang orang pertama (saya/I). Nada santai, jujur, fokus ke masalah sehari-hari..."
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Batas Karakter Maksimum (100 - 500)
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={100}
                    max={500}
                    step={10}
                    value={formMaxChars}
                    onChange={(e) => setFormMaxChars(parseInt(e.target.value))}
                    className="flex-1 accent-slate-900 dark:accent-white"
                  />
                  <span className="font-mono font-bold text-xs w-12 text-right text-slate-900 dark:text-slate-100">
                    {formMaxChars}
                  </span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Contoh Bagus (Pisahkan antarkonten dengan &apos;---&apos;)
                </label>
                <textarea
                  rows={2}
                  value={formGoodExamples}
                  onChange={(e) => setFormGoodExamples(e.target.value)}
                  placeholder="Contoh postingan yang ideal..."
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Contoh Dihindari (Pisahkan antarkonten dengan &apos;---&apos;)
                </label>
                <textarea
                  rows={2}
                  value={formBadExamples}
                  onChange={(e) => setFormBadExamples(e.target.value)}
                  placeholder="Contoh postingan yang kaku atau melanggar aturan..."
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              {editingStyle && (
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
                  {createMutation.isPending || updateMutation.isPending ? "Menyimpan..." : "Simpan Gaya"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
