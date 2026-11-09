"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  allocateNextArm,
  createExperiment,
  getExperimentDetails,
  getExperimentEvaluation,
  getExperimentProgress,
  getExperiments,
  updateExperimentStatus,
} from "@/lib/api";

export function useExperimentsList(phase?: string, status?: string) {
  const queryClient = useQueryClient();

  const experimentsQuery = useQuery({
    queryKey: ["experiments", phase, status],
    queryFn: () => getExperiments(phase, status),
  });

  const createMutation = useMutation({
    mutationFn: createExperiment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, newStatus }: { id: string; newStatus: string }) =>
      updateExperimentStatus(id, newStatus),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
      queryClient.invalidateQueries({ queryKey: ["experiment", variables.id] });
      queryClient.invalidateQueries({ queryKey: ["experiment-progress", variables.id] });
      queryClient.invalidateQueries({ queryKey: ["experiment-evaluation", variables.id] });
    },
  });

  return {
    ...experimentsQuery,
    createExperiment: createMutation.mutateAsync,
    isCreating: createMutation.isPending,
    updateStatus: statusMutation.mutateAsync,
    isUpdatingStatus: statusMutation.isPending,
  };
}

export function useExperimentDetails(experimentId: string | null) {
  return useQuery({
    queryKey: ["experiment", experimentId],
    queryFn: () => (experimentId ? getExperimentDetails(experimentId) : Promise.reject("No ID")),
    enabled: !!experimentId,
  });
}

export function useExperimentProgress(experimentId: string | null) {
  return useQuery({
    queryKey: ["experiment-progress", experimentId],
    queryFn: () => (experimentId ? getExperimentProgress(experimentId) : Promise.reject("No ID")),
    enabled: !!experimentId,
    refetchInterval: 15000,
  });
}

export function useExperimentEvaluation(experimentId: string | null) {
  return useQuery({
    queryKey: ["experiment-evaluation", experimentId],
    queryFn: () => (experimentId ? getExperimentEvaluation(experimentId) : Promise.reject("No ID")),
    enabled: !!experimentId,
  });
}

export function useAllocateNextArm(experimentId: string | null) {
  return useMutation({
    mutationFn: (variables?: { lastArmId?: string | null; lastNicheId?: string | null }) => {
      if (!experimentId) throw new Error("No experiment ID provided");
      return allocateNextArm(experimentId, variables?.lastArmId, variables?.lastNicheId);
    },
  });
}
