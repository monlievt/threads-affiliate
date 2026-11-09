"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createLinkClickManual,
  deleteLinkClick,
  getAccountGrowth,
  getAnalyticsOverview,
  getLinkClicks,
  getWeeklyReport,
  importClicksCsv,
  previewClicksCsv,
  triggerCollectMetrics,
} from "@/lib/api";

export function useAnalyticsOverview(limitRecent: number = 50) {
  const queryClient = useQueryClient();

  const overviewQuery = useQuery({
    queryKey: ["analytics-overview", limitRecent],
    queryFn: () => getAnalyticsOverview(limitRecent),
    refetchInterval: 30000,
  });

  const collectMutation = useMutation({
    mutationFn: triggerCollectMetrics,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analytics-overview"] });
      queryClient.invalidateQueries({ queryKey: ["account-growth"] });
    },
  });

  return {
    ...overviewQuery,
    triggerCollect: collectMutation.mutateAsync,
    isCollecting: collectMutation.isPending,
  };
}

export function useAccountGrowth(limit: number = 30) {
  return useQuery({
    queryKey: ["account-growth", limit],
    queryFn: () => getAccountGrowth(limit),
  });
}

export function useLinkClicks(
  productId?: string,
  postId?: string,
  startDate?: string,
  endDate?: string
) {
  const queryClient = useQueryClient();

  const clicksQuery = useQuery({
    queryKey: ["link-clicks", productId, postId, startDate, endDate],
    queryFn: () => getLinkClicks(productId, postId, startDate, endDate),
  });

  const createMutation = useMutation({
    mutationFn: createLinkClickManual,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["link-clicks"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteLinkClick,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["link-clicks"] });
    },
  });

  const previewMutation = useMutation({
    mutationFn: previewClicksCsv,
  });

  const importMutation = useMutation({
    mutationFn: importClicksCsv,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["link-clicks"] });
    },
  });

  return {
    ...clicksQuery,
    createClick: createMutation.mutateAsync,
    isCreating: createMutation.isPending,
    deleteClick: deleteMutation.mutateAsync,
    isDeleting: deleteMutation.isPending,
    previewCsv: previewMutation.mutateAsync,
    isPreviewing: previewMutation.isPending,
    importCsv: importMutation.mutateAsync,
    isImporting: importMutation.isPending,
  };
}

export function useWeeklyReport(days: number = 7) {
  return useQuery({
    queryKey: ["weekly-report", days],
    queryFn: () => getWeeklyReport(days),
  });
}
