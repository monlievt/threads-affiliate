"use client";

import React, { useState } from "react";
import { X, Sparkles, AlertCircle, Plus, Trash2 } from "lucide-react";
import { useCatalog } from "@/hooks/useCatalog";
import { useExperimentsList } from "@/hooks/useExperiments";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function CreateExperimentModal({ isOpen, onClose, onSuccess }: Props) {
  const { niches, styles } = useCatalog();
  const { createExperiment, isCreating } = useExperimentsList();

  const [phase, setPhase] = useState<"niche_test" | "style_test">("niche_test");
  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState(new Date().toISOString().slice(0, 10));
  const [targetPosts, setTargetPosts] = useState(12);
  const [fixedStyleId, setFixedStyleId] = useState<string>("");
  const [fixedNicheId, setFixedNicheId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  // Arms state
  const [nicheArms, setNicheArms] = useState<string[]>(["", ""]);
  const [styleArms, setStyleArms] = useState<string[]>(["", ""]);

  if (!isOpen) return null;

  // Auto-select defaults
  const activeNiches = niches.filter((n) => n.status !== "archived");
  const activeStyles = styles.filter((s) => s.status !== "archived");
  const curatorStyle = activeStyles.find((s) => s.name.toLowerCase().includes("curator")) || activeStyles[0];

  const handleAddArm = () => {
    if (phase === "niche_test") {
      setNicheArms([...nicheArms, ""]);
    } else {
      setStyleArms([...styleArms, ""]);
    }
  };

  const handleRemoveArm = (index: number) => {
    if (phase === "niche_test") {
      if (nicheArms.length <= 2) return;
      setNicheArms(nicheArms.filter((_, i) => i !== index));
    } else {
      if (styleArms.length <= 2) return;
      setStyleArms(styleArms.filter((_, i) => i !== index));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("Nama eksperimen wajib diisi.");
      return;
    }

    try {
      if (phase === "niche_test") {
        const styleId = fixedStyleId || (curatorStyle ? curatorStyle.id : activeStyles[0]?.id);
        if (!styleId) {
          setError("Gaya konstan wajib dipilih.");
          return;
        }

        const validNiches = nicheArms.filter(Boolean);
        if (validNiches.length < 2) {
          setError("Pilih minimal 2 niche berbeda untuk diuji.");
          return;
        }
        if (new Set(validNiches).size !== validNiches.length) {
          setError("Setiap arm harus menguji niche yang berbeda.");
          return;
        }

        const armsPayload = validNiches.map((nId) => {
          const nObj = activeNiches.find((n) => n.id === nId);
          return {
            label: nObj ? nObj.name : "Niche Arm",
            target_posts: targetPosts,
            niche_id: nId,
            style_id: styleId,
          };
        });

        await createExperiment({
          name: name.trim(),
          phase: "niche_test",
          start_date: startDate,
          arms: armsPayload,
        });
      } else {
        const nicheId = fixedNicheId || activeNiches[0]?.id;
        if (!nicheId) {
          setError("Niche konstan wajib dipilih.");
          return;
        }

        const validStyles = styleArms.filter(Boolean);
        if (validStyles.length < 2) {
          setError("Pilih minimal 2 gaya berbeda untuk diuji.");
          return;
        }
        if (new Set(validStyles).size !== validStyles.length) {
          setError("Setiap arm harus menguji gaya yang berbeda.");
          return;
        }

        const armsPayload = validStyles.map((sId) => {
          const sObj = activeStyles.find((s) => s.id === sId);
          return {
            label: sObj ? sObj.name : "Style Arm",
            target_posts: targetPosts,
            niche_id: nicheId,
            style_id: sId,
          };
        });

        await createExperiment({
          name: name.trim(),
          phase: "style_test",
          start_date: startDate,
          arms: armsPayload,
        });
      }

      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err?.message || "Gagal membuat eksperimen.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-2xl w-full max-w-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
              <Sparkles className="w-4 h-4" />
            </div>
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              Wizard Eksperimen Baru (rule_v1)
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4 max-h-[80vh] overflow-y-auto text-xs">
          {error && (
            <div className="p-3 rounded-md bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Phase selector */}
          <div>
            <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Fase Eksperimen (Prinsip Uji 1 Variabel)
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => {
                  setPhase("niche_test");
                  setTargetPosts(12);
                }}
                className={`p-3 rounded-lg border text-left transition-all ${
                  phase === "niche_test"
                    ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/30 text-indigo-950 dark:text-indigo-200 font-medium"
                    : "border-slate-200 dark:border-slate-800 hover:border-slate-300 text-slate-600 dark:text-slate-400"
                }`}
              >
                <div className="font-bold text-xs">Fase 1: Uji Niche</div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                  Uji 3 niche dengan gaya tetap (curator). Target 12 post/niche.
                </div>
              </button>

              <button
                type="button"
                onClick={() => {
                  setPhase("style_test");
                  setTargetPosts(10);
                }}
                className={`p-3 rounded-lg border text-left transition-all ${
                  phase === "style_test"
                    ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/30 text-indigo-950 dark:text-indigo-200 font-medium"
                    : "border-slate-200 dark:border-slate-800 hover:border-slate-300 text-slate-600 dark:text-slate-400"
                }`}
              >
                <div className="font-bold text-xs">Fase 2: Uji Gaya</div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                  Niche pemenang saja. Uji 3-4 gaya berbeda. Target 10 post/gaya.
                </div>
              </button>
            </div>
          </div>

          {/* Experiment Name */}
          <div>
            <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Nama Eksperimen
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={
                phase === "niche_test"
                  ? "Eksperimen Niche Q4 (Home vs Pet vs Desk)"
                  : "Eksperimen Gaya di Niche Pemenang"
              }
              className="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {/* Date & Target Posts */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Tanggal Mulai
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Target Post per Arm (n)
              </label>
              <input
                type="number"
                min={8}
                max={50}
                value={targetPosts}
                onChange={(e) => setTargetPosts(parseInt(e.target.value) || 8)}
                className="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              />
              <span className="text-[10px] text-slate-400">Minimal 8 post agar lolos aturan rule_v1</span>
            </div>
          </div>

          {/* Constant Variable Selection */}
          {phase === "niche_test" ? (
            <div>
              <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Gaya Konstan (Single Variable Rule)
              </label>
              <select
                value={fixedStyleId || curatorStyle?.id || ""}
                onChange={(e) => setFixedStyleId(e.target.value)}
                className="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              >
                {activeStyles.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} {s.name.toLowerCase() === "curator" ? "(Rekomendasi Standar)" : ""}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Niche Pemenang Konstan (Single Variable Rule)
              </label>
              <select
                value={fixedNicheId || activeNiches[0]?.id || ""}
                onChange={(e) => setFixedNicheId(e.target.value)}
                className="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              >
                {activeNiches.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Arms builder */}
          <div className="pt-2 border-t border-slate-200 dark:border-slate-800">
            <div className="flex items-center justify-between mb-2">
              <label className="font-semibold text-slate-700 dark:text-slate-300">
                Lengan Uji (Arms) — Variabel yang Dibandingkan
              </label>
              <button
                type="button"
                onClick={handleAddArm}
                className="flex items-center gap-1 text-[11px] font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                <Plus className="w-3.5 h-3.5" /> Tambah Arm
              </button>
            </div>

            <div className="space-y-2">
              {phase === "niche_test"
                ? nicheArms.map((val, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="font-mono text-slate-400 w-5 text-right">{idx + 1}.</span>
                      <select
                        value={val}
                        onChange={(e) => {
                          const updated = [...nicheArms];
                          updated[idx] = e.target.value;
                          setNicheArms(updated);
                        }}
                        className="flex-1 px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                      >
                        <option value="">Pilih Niche Kandidat...</option>
                        {activeNiches.map((n) => (
                          <option key={n.id} value={n.id}>
                            {n.name}
                          </option>
                        ))}
                      </select>
                      {nicheArms.length > 2 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveArm(idx)}
                          className="p-1 text-slate-400 hover:text-rose-500"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  ))
                : styleArms.map((val, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="font-mono text-slate-400 w-5 text-right">{idx + 1}.</span>
                      <select
                        value={val}
                        onChange={(e) => {
                          const updated = [...styleArms];
                          updated[idx] = e.target.value;
                          setStyleArms(updated);
                        }}
                        className="flex-1 px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                      >
                        <option value="">Pilih Gaya Kandidat...</option>
                        {activeStyles.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                      {styleArms.length > 2 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveArm(idx)}
                          className="p-1 text-slate-400 hover:text-rose-500"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200 dark:border-slate-800">
            <button
              type="button"
              onClick={onClose}
              disabled={isCreating}
              className="px-4 py-2 rounded-md border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={isCreating}
              className="px-4 py-2 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white font-semibold flex items-center gap-1.5 disabled:opacity-50"
            >
              {isCreating ? "Menyimpan..." : "Buat Eksperimen"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
