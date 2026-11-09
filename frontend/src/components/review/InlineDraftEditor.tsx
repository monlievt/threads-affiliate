"use client";

import React, { useState, useEffect } from "react";
import { Check, AlertCircle, Loader2, Save, X } from "lucide-react";
import { validateTextRealtime } from "@/lib/api";
import { RealtimeValidationResponse } from "@/types";

export default function InlineDraftEditor({
  initialText,
  styleId,
  maxChars = 500,
  onSave,
  onCancel,
  isSaving = false,
}: {
  initialText: string;
  styleId?: string | null;
  maxChars?: number;
  onSave: (newText: string) => Promise<void>;
  onCancel: () => void;
  isSaving?: boolean;
}) {
  const [text, setText] = useState(initialText);
  const [validation, setValidation] = useState<RealtimeValidationResponse | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Debounced real-time validation on keystrokes
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (!text.trim()) {
        setValidation(null);
        return;
      }

      setIsValidating(true);
      try {
        const res = await validateTextRealtime({
          text,
          style_id: styleId || undefined,
        });
        setValidation(res);
      } catch {
        // Fallback local char count check
      } finally {
        setIsValidating(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [text, styleId]);

  const charCount = text.length;
  const isOverLength = charCount > maxChars;
  const hasSafetyViolation = validation ? !validation.valid : false;
  const canSave = !isOverLength && !hasSafetyViolation && !isSaving && text.trim().length > 0;

  const handleSaveClick = async () => {
    if (!canSave) return;
    setSaveError(null);
    try {
      await onSave(text.trim());
    } catch (err: any) {
      setSaveError(err?.message || "Gagal menyimpan draf");
    }
  };

  return (
    <div className="p-3 bg-slate-50 dark:bg-slate-950/60 rounded-lg border border-slate-300 dark:border-slate-700 space-y-3">
      <div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          disabled={isSaving}
          className="w-full p-2.5 text-xs font-sans border rounded-md border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-500"
          placeholder="Tulis atau edit teks postingan Threads..."
        />
      </div>

      {/* Live Counter & Validation State Bar */}
      <div className="flex flex-wrap items-center justify-between text-xs gap-2">
        <div className="flex items-center gap-2">
          {/* Character count */}
          <span
            className={`font-mono font-bold ${
              isOverLength
                ? "text-rose-600 dark:text-rose-400"
                : "text-slate-600 dark:text-slate-400"
            }`}
          >
            {charCount} / {maxChars} karakter
          </span>

          {/* Validation feedback indicator */}
          {isValidating ? (
            <span className="flex items-center gap-1 text-slate-400 text-[11px]">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>Memvalidasi aturan...</span>
            </span>
          ) : hasSafetyViolation ? (
            <span className="flex items-center gap-1 text-rose-600 dark:text-rose-400 text-[11px] font-semibold">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>Pelanggaran: {validation?.failed_codes.join(", ")}</span>
            </span>
          ) : validation?.valid ? (
            <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 text-[11px] font-semibold">
              <Check className="w-3.5 h-3.5" />
              <span>Lolos semua aturan (V-LEN s/d V-MISC)</span>
            </span>
          ) : null}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSaving}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-800 rounded transition"
          >
            <X className="w-3.5 h-3.5" />
            <span>Batal</span>
          </button>
          <button
            type="button"
            onClick={handleSaveClick}
            disabled={!canSave}
            className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded text-white shadow-xs transition ${
              canSave
                ? "bg-slate-900 hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
                : "bg-slate-300 dark:bg-slate-800 text-slate-500 cursor-not-allowed"
            }`}
          >
            {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            <span>Simpan Perubahan</span>
          </button>
        </div>
      </div>

      {saveError && (
        <div className="p-2 text-xs text-rose-700 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded">
          {saveError}
        </div>
      )}
    </div>
  );
}
