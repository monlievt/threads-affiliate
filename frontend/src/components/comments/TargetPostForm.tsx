"use client";

import React, { useState } from "react";
import { Sparkles, AlertTriangle, Link as LinkIcon, ExternalLink, MessageSquareQuote } from "lucide-react";
import { useNiches, usePersonas, useProducts } from "@/hooks/useCatalog";
import { CommentGenerateRequest, CommentGenerateResponse } from "@/types";

interface TargetPostFormProps {
  onGenerate: (payload: CommentGenerateRequest) => void;
  isGenerating: boolean;
  quotaFull: boolean;
}

export default function TargetPostForm({
  onGenerate,
  isGenerating,
  quotaFull,
}: TargetPostFormProps) {
  const { data: niches = [] } = useNiches(false);
  const { data: personas = [] } = usePersonas();
  const { data: products = [] } = useProducts({ status: "active" });

  const [targetUrl, setTargetUrl] = useState("");
  const [targetText, setTargetText] = useState("");
  const [selectedNiche, setSelectedNiche] = useState("");
  const [selectedPersona, setSelectedPersona] = useState("");
  const [selectedStrategy, setSelectedStrategy] = useState<"all" | "insight" | "relate" | "question">("all");
  const [includeLink, setIncludeLink] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setUrlError(null);

    if (!targetUrl.toLowerCase().includes("threads.net")) {
      setUrlError("URL target harus merupakan tautan postingan Threads resmi (contoh: https://www.threads.net/@user/post/...)");
      return;
    }

    onGenerate({
      target_post_url: targetUrl.trim(),
      target_post_text: targetText.trim(),
      strategy: selectedStrategy,
      niche_id: selectedNiche || null,
      persona_id: selectedPersona || null,
      include_link: includeLink,
      product_id: includeLink ? selectedProduct || null : null,
    });
  };

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 shadow-xs">
      <div className="flex items-center gap-2">
        <MessageSquareQuote className="w-5 h-5 text-slate-700 dark:text-slate-300" />
        <div>
          <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
            Form Analisis Postingan Target
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Tempel URL dan cuplikan teks postingan Threads yang ingin Anda komentari.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4 pt-1">
        {/* Target Post URL */}
        <div>
          <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
            URL Postingan Threads Target <span className="text-red-500">*</span>
          </label>
          <input
            type="url"
            required
            placeholder="https://www.threads.net/@creator/post/C4xyz..."
            value={targetUrl}
            onChange={(e) => {
              setTargetUrl(e.target.value);
              setUrlError(null);
            }}
            className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
          />
          {urlError && <p className="mt-1 text-[11px] text-red-500">{urlError}</p>}
        </div>

        {/* Target Post Text */}
        <div>
          <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
            Cuplikan Teks Postingan Target <span className="text-red-500">*</span>
          </label>
          <textarea
            rows={3}
            required
            placeholder="Salin teks postingan target di sini agar AI dapat memahami konteks pembicaraan secara akurat..."
            value={targetText}
            onChange={(e) => setTargetText(e.target.value)}
            className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
          />
        </div>

        {/* Context Controls */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
              Konteks Niche (Opsional)
            </label>
            <select
              value={selectedNiche}
              onChange={(e) => setSelectedNiche(e.target.value)}
              className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            >
              <option value="">Semua Niche</option>
              {niches.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
              Persona Penulis (Opsional)
            </label>
            <select
              value={selectedPersona}
              onChange={(e) => setSelectedPersona(e.target.value)}
              className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            >
              <option value="">Default Persona</option>
              {personas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
              Fokus Strategi
            </label>
            <select
              value={selectedStrategy}
              onChange={(e) => setSelectedStrategy(e.target.value as any)}
              className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            >
              <option value="all">Semua Strategi (3 Opsi Berbeda)</option>
              <option value="insight">Insight Praktis</option>
              <option value="relate">Empati &amp; Relate</option>
              <option value="question">Pemantik Diskusi</option>
            </select>
          </div>
        </div>

        {/* Link Policy & Warning */}
        <div className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/40 space-y-2">
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={includeLink}
              onChange={(e) => setIncludeLink(e.target.checked)}
              className="rounded-sm accent-slate-900 dark:accent-white w-4 h-4"
            />
            <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
              Sertakan Tautan Link Rekomendasi (Tidak Disarankan untuk Komentar Biasa)
            </span>
          </label>

          {includeLink ? (
            <div className="space-y-2 pt-1 animate-in fade-in duration-150">
              <div className="p-2.5 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-[11px] text-amber-800 dark:text-amber-300 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
                <span>
                  <strong>PERINGATAN ALGORITMA THREADS:</strong> Menaruh link dalam komentar berisiko menurunkan impresi atau dianggap spam. Hanya gunakan link jika audiens secara eksplisit bertanya &quot;beli di mana?&quot; atau &quot;rekomendasinya apa?&quot;.
                </span>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Pilih Produk Benable Terkait
                </label>
                <select
                  value={selectedProduct}
                  onChange={(e) => setSelectedProduct(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                >
                  <option value="">Pilih Produk...</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title} ({p.niche_name || "Niche"})
                    </option>
                  ))}
                </select>
              </div>
            </div>
          ) : (
            <p className="text-[11px] text-emerald-600 dark:text-emerald-400">
              ✅ <strong>Value-First Direkomendasikan:</strong> Komentar tanpa tautan link mendapatkan distribusi jangkauan 4x lebih tinggi pada feed Threads.
            </p>
          )}
        </div>

        {/* Submit Button */}
        <div className="pt-2 flex justify-end">
          <button
            type="submit"
            disabled={isGenerating || quotaFull || !targetText.trim() || !targetUrl.trim()}
            className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100 transition-colors disabled:opacity-50 flex items-center gap-1.5 shadow-xs"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>{isGenerating ? "Membuat 2-3 Opsi Komentar..." : "Buat Opsi Komentar (Gemini Pro)"}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
