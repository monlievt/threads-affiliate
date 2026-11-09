"use client";

import React, { useState } from "react";
import { CheckCircle2, MessageSquareShare } from "lucide-react";
import { useGenerateComments, useCommentsQuota } from "@/hooks/useComments";
import CommentsQuotaBar from "@/components/comments/CommentsQuotaBar";
import TargetPostForm from "@/components/comments/TargetPostForm";
import CommentOptionsList from "@/components/comments/CommentOptionsList";
import { CommentGenerateRequest, CommentOption } from "@/types";

export default function CommentsPage() {
  const { data: quota, refetch: refetchQuota } = useCommentsQuota();
  const generateMutation = useGenerateComments();

  const [generatedOptions, setGeneratedOptions] = useState<CommentOption[]>([]);
  const [activeTargetUrl, setActiveTargetUrl] = useState("");
  const [successToast, setSuccessToast] = useState<string | null>(null);

  const handleGenerate = async (payload: CommentGenerateRequest) => {
    setActiveTargetUrl(payload.target_post_url);
    try {
      const res = await generateMutation.mutateAsync(payload);
      setGeneratedOptions(res.options);
      refetchQuota();
    } catch (err: any) {
      alert(err.message || "Gagal membuat opsi komentar.");
    }
  };

  const handleActionSuccess = (msg: string) => {
    setSuccessToast(msg);
    refetchQuota();
    setTimeout(() => setSuccessToast(null), 3500);
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Title */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
          <MessageSquareShare className="w-6 h-6 text-slate-800 dark:text-slate-200" />
          <span>Komentar Bernilai (Feature 10)</span>
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-1">
          Asisten penulisan balasan bernilai tinggi: tempel URL target, hasilkan 2–3 variasi respons berbobot, dan salin ke Threads secara manual.
        </p>
      </div>

      {/* Success Notification Toast */}
      {successToast && (
        <div className="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-xs text-emerald-800 dark:text-emerald-300 flex items-center gap-2 animate-in fade-in duration-150">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{successToast}</span>
        </div>
      )}

      {/* Daily Quota & Avoid List Bar */}
      <CommentsQuotaBar />

      {/* Target Post Form */}
      <TargetPostForm
        onGenerate={handleGenerate}
        isGenerating={generateMutation.isPending}
        quotaFull={quota?.is_quota_full || false}
      />

      {/* Generated Options List */}
      <CommentOptionsList
        options={generatedOptions}
        targetUrl={activeTargetUrl}
        onActionSuccess={handleActionSuccess}
      />
    </div>
  );
}
