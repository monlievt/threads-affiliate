import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getAccountSettings,
  getAuditLogs,
  getFullAutoEligibility,
  getIncidents,
  resolveIncident,
  updateAccountSettings,
} from "@/lib/api";
import { AccountSettingsUpdatePayload } from "@/types";

export function useAccountSettings() {
  return useQuery({
    queryKey: ["settings", "account"],
    queryFn: () => getAccountSettings(),
  });
}

export function useUpdateAccountSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AccountSettingsUpdatePayload) =>
      updateAccountSettings(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "account"] });
      queryClient.invalidateQueries({ queryKey: ["settings", "eligibility"] });
      queryClient.invalidateQueries({ queryKey: ["audit-logs"] });
    },
  });
}

export function useFullAutoEligibility() {
  return useQuery({
    queryKey: ["settings", "eligibility"],
    queryFn: () => getFullAutoEligibility(),
  });
}

export function useIncidents(resolved?: boolean) {
  return useQuery({
    queryKey: ["incidents", { resolved }],
    queryFn: () => getIncidents(resolved),
    refetchInterval: 15000,
  });
}

export function useResolveIncident() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      incidentId,
      notes,
    }: {
      incidentId: string;
      notes: string;
    }) => resolveIncident(incidentId, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["audit-logs"] });
    },
  });
}

export function useAuditLogs(limit = 50, offset = 0, action?: string) {
  return useQuery({
    queryKey: ["audit-logs", { limit, offset, action }],
    queryFn: () => getAuditLogs(limit, offset, action),
    refetchInterval: 30000,
  });
}
