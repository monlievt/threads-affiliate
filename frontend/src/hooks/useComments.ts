import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  generateComments,
  getCommentsQuota,
  publishOrCopyComment,
} from "@/lib/api";
import { CommentGenerateRequest, CommentPublishRequest } from "@/types";

export function useCommentsQuota() {
  return useQuery({
    queryKey: ["comments", "quota"],
    queryFn: () => getCommentsQuota(),
    refetchInterval: 15000,
  });
}

export function useGenerateComments() {
  return useMutation({
    mutationFn: (payload: CommentGenerateRequest) => generateComments(payload),
  });
}

export function usePublishOrCopyComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CommentPublishRequest) =>
      publishOrCopyComment(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["comments", "quota"] });
      queryClient.invalidateQueries({ queryKey: ["audit-logs"] });
    },
  });
}
