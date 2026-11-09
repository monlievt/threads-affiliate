"use client";

import React, { useState } from "react";
import { Plus, Edit2, Archive, UserCircle2, AlertCircle, ShieldCheck } from "lucide-react";
import { usePersonas, useCreatePersona, useUpdatePersona, useArchivePersona } from "@/hooks/useCatalog";
import { PersonaItem } from "@/types";

export default function PersonaTab() {
  const { data: personas = [], isLoading, error } = usePersonas();
  const createMutation = useCreatePersona();
  const updateMutation = useUpdatePersona();
  const archiveMutation = useArchivePersona();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingPersona, setEditingPersona] = useState<PersonaItem | null>(null);
  const [formName, setFormName] = useState("");
  const [formVoice, setFormVoice] = useState("");
  const [formDisclosure, setFormDisclosure] = useState("");
  const [formPosition, setFormPosition] = useState<"end" | "beginning" | "reply">("end");
  const [formStatus, setFormStatus] = useState<"active" | "paused" | "archived">("active");
  const [formError, setFormError] = useState<string | null>(null);

  const handleOpenCreate = () => {
    setEditingPersona(null);
    setFormName("");
    setFormVoice("");
    setFormDisclosure("Curated finds on Benable (affiliate link)");
    setFormPosition("end");
    setFormStatus("active");
    setFormError(null);
    setModalOpen(true);
  };

  const handleOpenEdit = (p: PersonaItem) => {
    setEditingPersona(p);
    setFormName(p.name);
    setFormVoice(p.voice_description || "");
    setFormDisclosure(p.disclosure_template);
    setFormPosition(p.disclosure_position);
    setFormStatus(p.status);
    setFormError(null);
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!formDisclosure.toLowerCase().includes("affiliate") && !formDisclosure.toLowerCase().includes("benable")) {
      setFormError("Aturan V-DISC: Klausul pengungkapan (disclosure) wajib menyebutkan kata 'affiliate' atau 'benable' demi kepatuhan regulasi FTC.");
      return;
    }

    try {
      if (editingPersona) {
        await updateMutation.mutateAsync({
          id: editingPersona.id,
          data: {
            name: formName.trim(),
            voice_description: formVoice.trim() || undefined,
            disclosure_template: formDisclosure.trim(),
            disclosure_position: formPosition,
            status: formStatus,
          },
        });
      } else {
        await createMutation.mutateAsync({
          account_id: "default_acc", // Default account reference
          name: formName.trim(),
          voice_description: formVoice.trim() || undefined,
          disclosure_template: formDisclosure.trim(),
          disclosure_position: formPosition,
        });
      }
      setModalOpen(false);
    } catch (err: any) {
      setFormError(err.message || "Gagal menyimpan persona.");
    }
  };

  const handleArchive = async (p: PersonaItem) => {
    if (confirm(`Arsipkan persona "${p.name}"?`)) {
      try {
        await archiveMutation.mutateAsync(p.id);
      } catch (err: any) {
        alert(err.message || "Gagal mengarsipkan persona.");
      }
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Persona Akun &amp; Kepatuhan Disclosure
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Pengaturan gaya kepribadian penulisan serta template pengungkapan tautan afiliasi (FTC V-DISC).
          </p>
        </div>
        <button
          onClick={handleOpenCreate}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium rounded-lg bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100 transition-colors shadow-xs"
        >
          <Plus className="w-4 h-4" />
          <span>Tambah Persona</span>
        </button>
      </div>

      {isLoading && (
        <div className="p-8 text-center text-sm text-slate-500 animate-pulse">
          Memuat data persona...
        </div>
      )}

      {error && (
        <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Gagal memuat persona: {(error as any).message}</span>
        </div>
      )}

      {/* Persona Cards Grid */}
      {!isLoading && !error && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {personas.map((persona) => (
            <div
              key={persona.id}
              className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 hover:border-slate-300 dark:hover:border-slate-700 transition-colors shadow-xs"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-700 dark:text-slate-300 font-bold text-sm">
                    {persona.name.slice(0, 1).toUpperCase()}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                        {persona.name}
                      </h3>
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          persona.status === "active"
                            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                            : persona.status === "paused"
                            ? "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400"
                            : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                        }`}
                      >
                        {persona.status}
                      </span>
                    </div>
                    <span className="text-[11px] text-slate-400">
                      Posisi Disclosure: <span className="font-mono text-slate-600 dark:text-slate-300">{persona.disclosure_position}</span>
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleOpenEdit(persona)}
                    className="p-1 rounded-md text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition-colors"
                    title="Edit Persona"
                  >
                    <Edit2 className="w-3.5 h-3.5" />
                  </button>
                  {persona.status !== "archived" && (
                    <button
                      onClick={() => handleArchive(persona)}
                      className="p-1 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                      title="Arsipkan Persona"
                    >
                      <Archive className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>

              {/* Voice Description */}
              <div className="space-y-1">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                  Karakter Suara (Voice Tone):
                </span>
                <p className="text-xs text-slate-700 dark:text-slate-300">
                  {persona.voice_description || "Tone netral, kurator terpercaya."}
                </p>
              </div>

              {/* Disclosure Template Box */}
              <div className="space-y-1">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                  <span>Klausul Afiliasi (V-DISC):</span>
                </span>
                <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 font-mono text-[11px] text-slate-800 dark:text-slate-200">
                  {persona.disclosure_template}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal: Tambah / Edit Persona */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs overflow-y-auto">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden my-8">
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {editingPersona ? "Edit Persona Akun" : "Tambah Persona Akun Baru"}
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
                  Nama Persona <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="Misal: Minimalist Tech Enthusiast"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Deskripsi Karakter Suara
                </label>
                <textarea
                  rows={2}
                  value={formVoice}
                  onChange={(e) => setFormVoice(e.target.value)}
                  placeholder="Gaya santai tapi berbobot, menyukai produk ergonomis dan estetika monokrom..."
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Template Disclosure Afiliasi <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formDisclosure}
                  onChange={(e) => setFormDisclosure(e.target.value)}
                  placeholder="Curated finds on Benable (affiliate link)"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
                <p className="mt-1 text-[10px] text-slate-400">
                  Wajib memuat kata &apos;affiliate&apos; atau &apos;benable&apos; (kepatuhan FTC).
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Posisi Penempatan Disclosure
                </label>
                <select
                  value={formPosition}
                  onChange={(e) => setFormPosition(e.target.value as any)}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                >
                  <option value="end">Di Akhir Teks (end - Direkomendasikan)</option>
                  <option value="beginning">Di Awal Teks (beginning)</option>
                  <option value="reply">Di Komentar Balasan Pertama (reply)</option>
                </select>
              </div>

              {editingPersona && (
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
                  {createMutation.isPending || updateMutation.isPending ? "Menyimpan..." : "Simpan Persona"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
