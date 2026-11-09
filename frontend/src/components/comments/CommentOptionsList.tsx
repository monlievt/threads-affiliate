"use client";

import React, { useState } from "react";
import {
  Copy,
  Check,
  Send,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ExternalLink,
  ShieldAlert,
} from "lucide-react";
import { usePublishOrCopyComment } from "@/hooks/useComments";
import { CommentOption } from "@/types";

interface CommentOptionsListProps {
  options: CommentOption[];
  targetUrl: string;
  onActionSuccess: (msg: string) => void;
}

export default function CommentOptionsList({
  options,
  targetUrl,
  onActionSuccess,
}: CommentOptionsListProps) {
  const publishMutation = usePublishOrCopyComment();
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [publishedId, setPublishedId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleCopy = async (opt: CommentOption) => {
    setActionError(null);
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        await navigator.clipboard.writeText(opt.text);
      }

      await publishMutation.mutateAsync({
        target_post_url: targetUrl,
        selected_text: opt.text,
        link_url: opt.link_url || undefined,
        action_type: "copied_clipboard",
      });

      setCopiedId(opt.option_id);
      onActionSuccess("Teks komentar disalin ke clipboard dan kuota berhasil diperbarui!");
      setTimeout(() => setCopiedId(null), 2500);
    } catch (err: any) {
      setActionError(err.message || "Gagal menyalin komentar.");
    }
  };

  const handlePublishApi = async (opt: CommentOption) => {
    setActionError(null);
    try {
      await publishMutation.mutateAsync({
        target_post_url: targetUrl,
        selected_text: opt.text,
        link_url: opt.link_url || undefined,
        action_type: "publish_api",
      });

      setPublishedId(opt.option_id);
      onActionSuccess("Komentar diterbitkan ke Threads via API!");
      setTimeout(() => setPublishedId(null), 2500);
    } catch (err: any) {
      setActionError(err.message || "Gagal menerbitkan komentar via API.");
    }
  };

  if (options.length === 0) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
            Hasil Opsi Komentar Bernilai
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Pilih opsi terbaik untuk disalin ke clipboard atau dikirimkan langsung.
          </p>
        </div>
      </div>

      {actionError && (
        <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
          {actionError}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {options.map((opt) => (
          <div
            key={opt.option_id}
            className={`rounded-xl border p-4 flex flex-col justify-between space-y-3 transition-all shadow-xs ${
              opt.has_link
                ? "border-amber-300 dark:border-amber-800 bg-amber-50/10 dark:bg-amber-950/10"
                : "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900"
            }`}
          >
            <div className="space-y-2.5">
              {/* Strategy Header */}
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-900 dark:text-slate-100">
                  {opt.strategy_label}
                </span>
                <span className="text-[10px] font-mono text-slate-400">
                  {opt.char_count} / 250 krt
                </span>
              </div>

              {/* Link Warning Banner */}
              {opt.has_link ? (
                <div className="p-2 rounded-lg bg-amber-100/70 dark:bg-amber-950/40 border border-amber-300/80 text-[10px] text-amber-800 dark:text-amber-300 flex items-start gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-amber-600" />
                  <span>
                    <strong>Peringatan Link:</strong> Komentar ini memuat tautan luar ({opt.link_url}). Jangkauan impresi organik mungkin dibatasi.
                  </span>
                </div>
              ) : (
                <div className="text-[10px] text-emerald-600 dark:text-emerald-400 flex items-center gap-1 font-medium">
                  <CheckCircle2 className="w-3 h-3" />
                  <span>Murni Bernilai (Tanpa Link — Jangkauan Maksimal)</span>
                </div>
              )}

              {/* Safety issues if any */}
              {!opt.safety_valid && (
                <div className="p-2 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 text-[10px] text-red-700 dark:text-red-300 space-y-0.5">
                  {opt.safety_issues.map((iss, i) => (
                    <div key={i} className="flex items-center gap-1">
                      <XCircle className="w-3 h-3 shrink-0" />
                      <span>{iss}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Comment Text Content */}
              <p className="text-xs text-slate-800 dark:text-slate-200 leading-relaxed font-sans select-all p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800">
                {opt.text}
              </p>
            </div>

            {/* Actions Bar */}
            <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-2">
              <button
                onClick={() => handleCopy(opt)}
                disabled={publishMutation.isPending}
                className="flex-1 inline-flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100 text-xs font-medium transition-colors shadow-2xs"
                title="Salin ke clipboard (Rekomendasi Utama)"
              >
                {copiedId === opt.option_id ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400 dark:text-emerald-600" />
                    <span>Disalin!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Salin Teks</span>
                  </>
                )}
              </button>

              <button
                onClick={() => handlePublishApi(opt)}
                disabled={publishMutation.isPending || !opt.safety_valid}
                className="inline-flex items-center justify-center gap-1 py-1.5 px-2.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 text-xs font-medium transition-colors disabled:opacity-40"
                title="Kirim otomatis ke Threads via API"
              >
                {publishedId === opt.option_id ? (
                  <Check className="w-3.5 h-3.5 text-emerald-600" />
                ) : (
                  <Send className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
