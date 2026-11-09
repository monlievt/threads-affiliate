"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveDraft,
  batchApproveDrafts,
  editDraft,
  getDraft,
  getDrafts,
  rejectDraft,
  validateTextRealtime,
} from "@/lib/api";
import { DraftItem } from "@/types";

export function useDrafts(params?: {
  status?: string;
  niche_id?: string;
  style_id?: string;
}) {
  return useQuery<DraftItem[]>({
    queryKey: ["drafts", params],
    queryFn: () => getDrafts(params),
    refetchInterval: 10000, // Poll every 10s for new AI-generated drafts
  });
}

export function useDraftDetail(id: string) {
  return useQuery<DraftItem>({
    queryKey: ["draft", id],
    queryFn: () => getDraft(id),
    enabled: Boolean(id),
  });
}

export function useApproveDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => approveDraft(id),
    onSuccess: (updatedDraft) => {
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      queryClient.setQueryData(["draft", updatedDraft.id], updatedDraft);
    },
  });
}

export function useRejectDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) => rejectDraft(id, reason),
    onSuccess: (updatedDraft) => {
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      queryClient.setQueryData(["draft", updatedDraft.id], updatedDraft);
    },
  });
}

export function useEditDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, text, scheduled_at }: { id: string; text: string; scheduled_at?: string }) =>
      editDraft(id, text, scheduled_at),
    onSuccess: (updatedDraft) => {
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      queryClient.setQueryData(["draft", updatedDraft.id], updatedDraft);
    },
  });
}

export function useBatchApproveDrafts() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => batchApproveDrafts(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });
}
