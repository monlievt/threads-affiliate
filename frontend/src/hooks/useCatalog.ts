import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  archiveNiche,
  archivePersona,
  archiveProduct,
  archiveStyle,
  createNiche,
  createPersona,
  createProduct,
  createStyle,
  getNiches,
  getPersonas,
  getProducts,
  getStyles,
  importProductsCSV,
  previewProductsCSV,
  updateNiche,
  updatePersona,
  updateProduct,
  updateStyle,
} from "@/lib/api";
import {
  NicheCreatePayload,
  NicheUpdatePayload,
  PersonaCreatePayload,
  PersonaUpdatePayload,
  ProductCreatePayload,
  ProductUpdatePayload,
  StyleCreatePayload,
  StyleUpdatePayload,
} from "@/types";

export function useNiches(includeArchived = false) {
  return useQuery({
    queryKey: ["niches", { includeArchived }],
    queryFn: () => getNiches(includeArchived),
  });
}

export function useCreateNiche() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: NicheCreatePayload) => createNiche(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["niches"] });
    },
  });
}

export function useUpdateNiche() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: NicheUpdatePayload }) =>
      updateNiche(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["niches"] });
    },
  });
}

export function useArchiveNiche() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => archiveNiche(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["niches"] });
    },
  });
}

export function useProducts(params?: {
  niche_id?: string;
  status?: string;
  include_archived?: boolean;
}) {
  return useQuery({
    queryKey: ["products", params],
    queryFn: () => getProducts(params),
  });
}

export function useCreateProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ProductCreatePayload) => createProduct(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });
}

export function useUpdateProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProductUpdatePayload }) =>
      updateProduct(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });
}

export function useArchiveProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => archiveProduct(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });
}

export function usePreviewProductsCSV() {
  return useMutation({
    mutationFn: (csvContent: string) => previewProductsCSV(csvContent),
  });
}

export function useImportProductsCSV() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (csvContent: string) => importProductsCSV(csvContent),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });
}

export function useStyles(includeArchived = false) {
  return useQuery({
    queryKey: ["styles", { includeArchived }],
    queryFn: () => getStyles(includeArchived),
  });
}

export function useCreateStyle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: StyleCreatePayload) => createStyle(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["styles"] });
    },
  });
}

export function useUpdateStyle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: StyleUpdatePayload }) =>
      updateStyle(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["styles"] });
    },
  });
}

export function useArchiveStyle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => archiveStyle(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["styles"] });
    },
  });
}

export function usePersonas(accountId?: string) {
  return useQuery({
    queryKey: ["personas", { accountId }],
    queryFn: () => getPersonas(accountId),
  });
}

export function useCreatePersona() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PersonaCreatePayload) => createPersona(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["personas"] });
    },
  });
}

export function useUpdatePersona() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PersonaUpdatePayload }) =>
      updatePersona(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["personas"] });
    },
  });
}

export function useArchivePersona() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => archivePersona(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["personas"] });
    },
  });
}
