"use client";

import React, { useState } from "react";
import {
  Check,
  Edit3,
  X,
  RotateCw,
  ExternalLink,
  Clock,
  Sparkles,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import { DraftItem } from "@/types";
import { useApproveDraft, useEditDraft, useRejectDraft } from "@/hooks/useDrafts";
import ValidatorBadgeList from "@/components/review/ValidatorBadgeList";
import InlineDraftEditor from "@/components/review/InlineDraftEditor";

export default function DraftCard({
  draft,
  onRegenerate,
}: {
  draft: DraftItem;
  onRegenerate?: (draftId: string) => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const approveMutation = useApproveDraft();
  const rejectMutation = useRejectDraft();
  const editMutation = useEditDraft();

  const isPending = draft.status === "pending_review";
  const isApproved = draft.status === "approved" || draft.status === "scheduled";
  const isPublished = draft.status === "published";
  const isRejected = draft.status === "rejected" || draft.status === "rejected_auto";

  // Slot formatted for EST display
  const slotDisplay = draft.scheduled_at
    ? `${draft.scheduled_at.slice(11, 16)} EST`
    : "Menunggu Jadwal";

  const handleApprove = async () => {
    try {
      await approveMutation.mutateAsync(draft.id);
    } catch (err: any) {
      alert(err?.message || "Gagal menyetujui draf");
    }
  };

  const handleConfirmReject = async () => {
    try {
      await rejectMutation.mutateAsync({
        id: draft.id,
        reason: rejectReason.trim() || undefined,
      });
      setShowRejectModal(false);
    } catch (err: any) {
      alert(err?.message || "Gagal menolak draf");
    }
  };

  const handleSaveEdit = async (newText: string) => {
    await editMutation.mutateAsync({
      id: draft.id,
      text: newText,
    });
    setIsEditing(false);
  };

  return (
    <div
      className={`p-4 sm:p-5 rounded-lg border transition-shadow bg-white dark:bg-slate-900 ${
        isPending
          ? "border-amber-300 dark:border-amber-900 shadow-sm"
          : isApproved
          ? "border-emerald-200 dark:border-emerald-950/60"
          : "border-slate-200 dark:border-slate-800"
      }`}
    >
      {/* 1. Mandatory Explicit Status Badge (docs/08 §4.2) */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-2">
          {isPending ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200 border border-amber-300 dark:border-amber-800">
              <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
              <span>⏳ Menunggu persetujuan Anda</span>
            </span>
          ) : isApproved ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200 border border-emerald-300 dark:border-emerald-800">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span>🕐 Terjadwal terbit: {slotDisplay}</span>
            </span>
          ) : isPublished ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
              <span>🚀 Sudah Terbit di Threads</span>
            </span>
          ) : isRejected ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400">
              <span>❌ Ditolak</span>
            </span>
          ) : (
            <span className="text-xs text-slate-500 capitalize">{draft.status}</span>
          )}
        </div>

        {/* Short ID & Date */}
        <span className="text-[11px] font-mono text-slate-400">
          Draft #{draft.id.slice(0, 8)}
        </span>
      </div>

      {/* 2. Metadata Context Row */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5 text-xs text-slate-500 dark:text-slate-400">
        <div>
          <span>Niche: </span>
          <strong className="text-slate-800 dark:text-slate-200 font-semibold">
            {draft.niche_name || "General"}
          </strong>
        </div>
        <span>·</span>
        <div>
          <span>Gaya: </span>
          <strong className="text-slate-800 dark:text-slate-200 font-semibold">
            {draft.style_name || "Curator"}
          </strong>
        </div>
        {draft.product_title && (
          <>
            <span>·</span>
            <div className="truncate max-w-xs">
              <span>Produk: </span>
              <strong className="text-slate-800 dark:text-slate-200 font-semibold">
                {draft.product_title}
              </strong>
            </div>
          </>
        )}
      </div>

      {/* 3. Post Content (or Inline Editor) */}
      <div className="my-2.5">
        {isEditing ? (
          <InlineDraftEditor
            initialText={draft.text}
            styleId={draft.style_id}
            onSave={handleSaveEdit}
            onCancel={() => setIsEditing(false)}
            isSaving={editMutation.isPending}
          />
        ) : (
          <div className="p-3.5 rounded-md bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs sm:text-sm font-sans leading-relaxed text-slate-800 dark:text-slate-200 whitespace-pre-wrap selection:bg-slate-200">
            {draft.text || "(Konten kosong)"}
          </div>
        )}
      </div>

      {/* 4. Link & Affiliate Target Info */}
      {draft.link_url && (
        <div className="flex items-center gap-2 mb-3 text-xs text-slate-500">
          <span>🔗 Link:</span>
          <a
            href={draft.link_url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-slate-800 dark:text-slate-200 hover:underline flex items-center gap-1 truncate max-w-md"
          >
            <span>{draft.link_url}</span>
            <ExternalLink className="w-3 h-3 shrink-0" />
          </a>
        </div>
      )}

      {/* 5. Validator Badges & Similarity Score Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2.5 border-t border-slate-100 dark:border-slate-800">
        <div className="space-y-1">
          <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">
            Content Safety Checks
          </span>
          <ValidatorBadgeList report={draft.validator_report} />
        </div>

        <div className="text-right">
          <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">
            Dedup Check
          </span>
          <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">
            Mirip terdekat: {draft.similarity_score !== null && draft.similarity_score !== undefined ? `${Math.round(draft.similarity_score)}%` : "< 40%"}
          </span>
        </div>
      </div>

      {/* 6. Action Button Bar (docs/08 §4.2) */}
      <div className="flex flex-wrap items-center justify-end gap-2 pt-4 mt-3 border-t border-slate-100 dark:border-slate-800">
        {/* Approve Button */}
        {isPending && (
          <button
            type="button"
            onClick={handleApprove}
            disabled={approveMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold rounded-md bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs transition"
          >
            {approveMutation.isPending ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Check className="w-3.5 h-3.5 stroke-[3]" />
            )}
            <span>Setujui</span>
          </button>
        )}

        {/* Edit Inline Button */}
        {!isEditing && !isPublished && (
          <button
            type="button"
            onClick={() => setIsEditing(true)}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition"
          >
            <Edit3 className="w-3.5 h-3.5" />
            <span>Edit</span>
          </button>
        )}

        {/* Regenerate Button */}
        {!isPublished && (
          <button
            type="button"
            onClick={() => onRegenerate?.(draft.id)}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition"
          >
            <RotateCw className="w-3.5 h-3.5" />
            <span>Regenerasi</span>
          </button>
        )}

        {/* Reject Button */}
        {isPending && (
          <button
            type="button"
            onClick={() => setShowRejectModal(true)}
            disabled={rejectMutation.isPending}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md hover:bg-rose-50 dark:hover:bg-rose-950/40 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-900 transition"
          >
            <X className="w-3.5 h-3.5" />
            <span>Tolak</span>
          </button>
        )}
      </div>

      {/* Reject Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="w-full max-w-sm p-5 bg-white dark:bg-slate-900 rounded-lg shadow-xl border border-slate-200 dark:border-slate-800">
            <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100 mb-1">
              Tolak Draf #{draft.id.slice(0, 8)}
            </h4>
            <p className="text-xs text-slate-500 mb-3">
              Masukkan alasan penolakan (opsional) untuk pembelajaran model dan catatan audit.
            </p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Misal: Kurang relevan dengan target audiens, nada terlalu formal..."
              rows={3}
              className="w-full p-2 text-xs border rounded-md border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 mb-4 focus:outline-none focus:ring-2 focus:ring-slate-500"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowRejectModal(false)}
                className="px-3 py-1.5 text-xs text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded"
              >
                Batal
              </button>
              <button
                type="button"
                onClick={handleConfirmReject}
                disabled={rejectMutation.isPending}
                className="px-3.5 py-1.5 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded shadow-xs"
              >
                {rejectMutation.isPending ? "Menolak..." : "Konfirmasi Tolak"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
