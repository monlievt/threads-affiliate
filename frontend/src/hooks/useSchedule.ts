import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getScheduleCalendar,
  moveScheduleSlot,
  validateScheduleSlot,
} from "@/lib/api";

export function useScheduleCalendar(startDate?: string, daysCount = 7) {
  return useQuery({
    queryKey: ["schedule", "calendar", { startDate, daysCount }],
    queryFn: () => getScheduleCalendar(startDate, daysCount),
    refetchInterval: 30000, // 30s auto-refresh
  });
}

export function useMoveScheduleSlot() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      draftId,
      newScheduledAt,
    }: {
      draftId: string;
      newScheduledAt: string;
    }) => moveScheduleSlot(draftId, newScheduledAt),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedule"] });
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });
}

export function useValidateScheduleSlot() {
  return useMutation({
    mutationFn: ({
      draftId,
      candidateScheduledAt,
    }: {
      draftId: string | null;
      candidateScheduledAt: string;
    }) => validateScheduleSlot(draftId, candidateScheduledAt),
  });
}
