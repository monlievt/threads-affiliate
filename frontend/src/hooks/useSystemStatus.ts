"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getKillSwitch, getSystemHealth, toggleKillSwitch } from "@/lib/api";
import { KillSwitchStatus, SystemHealth } from "@/types";

export function useSystemHealth() {
  return useQuery<SystemHealth>({
    queryKey: ["systemHealth"],
    queryFn: getSystemHealth,
    // Poll every 4 seconds to guarantee state sync <= 5 seconds
    refetchInterval: 4000,
  });
}

export function useKillSwitch() {
  const queryClient = useQueryClient();

  const query = useQuery<KillSwitchStatus>({
    queryKey: ["killSwitch"],
    queryFn: getKillSwitch,
    // Poll every 3 seconds so external /pause via Telegram or auto-trigger is visible <= 5s
    refetchInterval: 3000,
  });

  const mutation = useMutation({
    mutationFn: ({ active, reason }: { active: boolean; reason: string }) =>
      toggleKillSwitch(active, reason),
    onMutate: async ({ active, reason }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ["killSwitch"] });
      await queryClient.cancelQueries({ queryKey: ["systemHealth"] });

      // Snapshot previous value
      const previous = queryClient.getQueryData<KillSwitchStatus>(["killSwitch"]);

      // Optimistically update
      queryClient.setQueryData<KillSwitchStatus>(["killSwitch"], {
        active,
        status: active ? "on" : "off",
        reason,
        updated_at: new Date().toISOString(),
      });

      return { previous };
    },
    onError: (err, variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["killSwitch"], context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["killSwitch"] });
      queryClient.invalidateQueries({ queryKey: ["systemHealth"] });
    },
  });

  return {
    ...query,
    toggle: mutation.mutateAsync,
    isToggling: mutation.isPending,
  };
}
