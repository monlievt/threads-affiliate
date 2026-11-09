/**
 * API client for interacting with the backend FastAPI service.
 */

import {
  AccountSettingsResponse,
  AccountSettingsUpdatePayload,
  AuditLogItem,
  CalendarResponse,
  CommentGenerateRequest,
  CommentGenerateResponse,
  CommentPublishRequest,
  CommentPublishResponse,
  CommentsQuotaResponse,
  CSVImportRowError,
  DraftItem,
  FullAutoEligibilityResponse,
  IncidentItem,
  KillSwitchStatus,
  MoveSlotResponse,
  NicheCreatePayload,
  NicheItem,
  NicheUpdatePayload,
  PersonaCreatePayload,
  PersonaItem,
  PersonaUpdatePayload,
  ProductCreatePayload,
  ProductImportResponse,
  ProductItem,
  ProductUpdatePayload,
  RealtimeValidationResponse,
  StyleCreatePayload,
  StyleItem,
  StyleUpdatePayload,
  SystemHealth,
  ValidateSlotResponse,
  ValidateUrlResponse,
} from "@/types";

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
  return match ? decodeURIComponent(match[2]) : null;
}

export async function fetchApi<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  
  // Attach CSRF token on mutating requests
  const csrfToken = getCookie("threads_affiliate_csrf") || getCookie("csrf_token");
  if (csrfToken && !["GET", "HEAD"].includes(options.method || "GET")) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(endpoint, {
    ...options,
    headers,
    credentials: "include", // send session cookies
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errorJson = await response.json();
      errorDetail = errorJson.detail?.message || errorJson.detail || errorDetail;
    } catch {
      // Body not JSON
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

/**
 * Health & Kill Switch API
 */
export async function getSystemHealth(): Promise<SystemHealth> {
  return fetchApi<SystemHealth>("/health");
}

export async function getKillSwitch(): Promise<KillSwitchStatus> {
  return fetchApi<KillSwitchStatus>("/api/system/kill-switch");
}

export async function toggleKillSwitch(active: boolean, reason: string): Promise<KillSwitchStatus> {
  return fetchApi<KillSwitchStatus>("/api/system/kill-switch", {
    method: "POST",
    body: JSON.stringify({ active, reason }),
  });
}

/**
 * Drafts API
 */
export async function getDrafts(params?: {
  status?: string;
  niche_id?: string;
  style_id?: string;
  limit?: number;
  offset?: number;
}): Promise<DraftItem[]> {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.niche_id) q.set("niche_id", params.niche_id);
  if (params?.style_id) q.set("style_id", params.style_id);
  if (params?.limit) q.set("limit", params.limit.toString());
  if (params?.offset) q.set("offset", params.offset.toString());

  const queryStr = q.toString() ? `?${q.toString()}` : "";
  return fetchApi<DraftItem[]>(`/api/drafts${queryStr}`);
}

export async function getDraft(id: string): Promise<DraftItem> {
  return fetchApi<DraftItem>(`/api/drafts/${id}`);
}

export async function approveDraft(id: string): Promise<DraftItem> {
  return fetchApi<DraftItem>(`/api/drafts/${id}/approve`, {
    method: "POST",
  });
}

export async function rejectDraft(id: string, reason?: string): Promise<DraftItem> {
  return fetchApi<DraftItem>(`/api/drafts/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function editDraft(id: string, text: string, scheduled_at?: string): Promise<DraftItem> {
  return fetchApi<DraftItem>(`/api/drafts/${id}`, {
    method: "PUT",
    body: JSON.stringify({ text, scheduled_at }),
  });
}

export async function batchApproveDrafts(): Promise<{
  total_eligible: number;
  approved_count: number;
  approved_ids: string[];
}> {
  return fetchApi(`/api/drafts/batch-approve`, {
    method: "POST",
  });
}

export async function validateTextRealtime(payload: {
  text: string;
  style_id?: string;
  is_affiliate?: boolean;
  disclosure_text?: string;
}): Promise<RealtimeValidationResponse> {
  return fetchApi<RealtimeValidationResponse>(`/api/drafts/validate-text`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Catalog: Niches API
 */
export async function getNiches(includeArchived: boolean = false): Promise<NicheItem[]> {
  const q = includeArchived ? "?include_archived=true" : "";
  return fetchApi<NicheItem[]>(`/api/niches${q}`);
}

export async function createNiche(payload: NicheCreatePayload): Promise<NicheItem> {
  return fetchApi<NicheItem>("/api/niches", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateNiche(id: string, payload: NicheUpdatePayload): Promise<NicheItem> {
  return fetchApi<NicheItem>(`/api/niches/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function archiveNiche(id: string): Promise<NicheItem> {
  return fetchApi<NicheItem>(`/api/niches/${id}`, {
    method: "DELETE",
  });
}

/**
 * Catalog: Products API
 */
export async function getProducts(params?: {
  niche_id?: string;
  status?: string;
  include_archived?: boolean;
  limit?: number;
  offset?: number;
}): Promise<ProductItem[]> {
  const q = new URLSearchParams();
  if (params?.niche_id) q.set("niche_id", params.niche_id);
  if (params?.status) q.set("status", params.status);
  if (params?.include_archived) q.set("include_archived", "true");
  if (params?.limit) q.set("limit", params.limit.toString());
  if (params?.offset) q.set("offset", params.offset.toString());

  const queryStr = q.toString() ? `?${q.toString()}` : "";
  return fetchApi<ProductItem[]>(`/api/products${queryStr}`);
}

export async function createProduct(payload: ProductCreatePayload): Promise<ProductItem> {
  return fetchApi<ProductItem>("/api/products", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateProduct(id: string, payload: ProductUpdatePayload): Promise<ProductItem> {
  return fetchApi<ProductItem>(`/api/products/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function archiveProduct(id: string): Promise<ProductItem> {
  return fetchApi<ProductItem>(`/api/products/${id}`, {
    method: "DELETE",
  });
}

export async function previewProductsCSV(csvContent: string): Promise<ProductImportResponse> {
  return fetchApi<ProductImportResponse>("/api/products/preview-csv", {
    method: "POST",
    body: JSON.stringify({ csv_content: csvContent }),
  });
}

export async function importProductsCSV(csvContent: string): Promise<ProductImportResponse> {
  return fetchApi<ProductImportResponse>("/api/products/import-csv", {
    method: "POST",
    body: JSON.stringify({ csv_content: csvContent }),
  });
}

export async function validateProductUrl(url: string): Promise<ValidateUrlResponse> {
  return fetchApi<ValidateUrlResponse>("/api/products/validate-url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

/**
 * Catalog: Styles API
 */
export async function getStyles(includeArchived: boolean = false): Promise<StyleItem[]> {
  const q = includeArchived ? "?include_archived=true" : "";
  return fetchApi<StyleItem[]>(`/api/styles${q}`);
}

export async function createStyle(payload: StyleCreatePayload): Promise<StyleItem> {
  return fetchApi<StyleItem>("/api/styles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateStyle(id: string, payload: StyleUpdatePayload): Promise<StyleItem> {
  return fetchApi<StyleItem>(`/api/styles/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function archiveStyle(id: string): Promise<StyleItem> {
  return fetchApi<StyleItem>(`/api/styles/${id}`, {
    method: "DELETE",
  });
}

/**
 * Catalog: Personas API
 */
export async function getPersonas(accountId?: string): Promise<PersonaItem[]> {
  const q = accountId ? `?account_id=${accountId}` : "";
  return fetchApi<PersonaItem[]>(`/api/personas${q}`);
}

export async function createPersona(payload: PersonaCreatePayload): Promise<PersonaItem> {
  return fetchApi<PersonaItem>("/api/personas", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updatePersona(id: string, payload: PersonaUpdatePayload): Promise<PersonaItem> {
  return fetchApi<PersonaItem>(`/api/personas/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function archivePersona(id: string): Promise<PersonaItem> {
  return fetchApi<PersonaItem>(`/api/personas/${id}`, {
    method: "DELETE",
  });
}

/**
 * Schedule & Calendar API
 */
export async function getScheduleCalendar(
  startDate?: string,
  daysCount: number = 7
): Promise<CalendarResponse> {
  const q = new URLSearchParams();
  if (startDate) q.set("start_date", startDate);
  if (daysCount) q.set("days_count", daysCount.toString());
  const queryStr = q.toString() ? `?${q.toString()}` : "";
  return fetchApi<CalendarResponse>(`/api/schedule/calendar${queryStr}`);
}

export async function moveScheduleSlot(
  draftId: string,
  newScheduledAt: string
): Promise<MoveSlotResponse> {
  return fetchApi<MoveSlotResponse>("/api/schedule/move-slot", {
    method: "POST",
    body: JSON.stringify({ draft_id: draftId, new_scheduled_at: newScheduledAt }),
  });
}

export async function validateScheduleSlot(
  draftId: string | null,
  candidateScheduledAt: string
): Promise<ValidateSlotResponse> {
  return fetchApi<ValidateSlotResponse>("/api/schedule/validate-slot", {
    method: "POST",
    body: JSON.stringify({
      draft_id: draftId,
      candidate_scheduled_at: candidateScheduledAt,
    }),
  });
}

/**
 * Settings, Automation & Hard Limits API
 */
export async function getAccountSettings(): Promise<AccountSettingsResponse> {
  return fetchApi<AccountSettingsResponse>("/api/system/account");
}

export async function updateAccountSettings(
  payload: AccountSettingsUpdatePayload
): Promise<AccountSettingsResponse> {
  return fetchApi<AccountSettingsResponse>("/api/system/account", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getFullAutoEligibility(): Promise<FullAutoEligibilityResponse> {
  return fetchApi<FullAutoEligibilityResponse>("/api/system/full-auto-eligibility");
}

/**
 * Incidents API
 */
export async function getIncidents(resolved?: boolean): Promise<IncidentItem[]> {
  const q = resolved !== undefined ? `?resolved=${resolved}` : "";
  return fetchApi<IncidentItem[]>(`/api/system/incidents${q}`);
}

export async function resolveIncident(
  incidentId: string,
  resolutionNotes: string
): Promise<IncidentItem> {
  return fetchApi<IncidentItem>(`/api/system/incidents/${incidentId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ resolution_notes: resolutionNotes }),
  });
}

/**
 * Audit Trail API
 */
export async function getAuditLogs(
  limit: number = 50,
  offset: number = 0,
  action?: string
): Promise<AuditLogItem[]> {
  const q = new URLSearchParams({ limit: limit.toString(), offset: offset.toString() });
  if (action) q.set("action", action);
  return fetchApi<AuditLogItem[]>(`/api/system/audit-logs?${q.toString()}`);
}

/**
 * Value-First Comments (Feature 10) API
 */
export async function getCommentsQuota(): Promise<CommentsQuotaResponse> {
  return fetchApi<CommentsQuotaResponse>("/api/comments/quota");
}

export async function generateComments(
  payload: CommentGenerateRequest
): Promise<CommentGenerateResponse> {
  return fetchApi<CommentGenerateResponse>("/api/comments/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function publishOrCopyComment(
  payload: CommentPublishRequest
): Promise<CommentPublishResponse> {
  return fetchApi<CommentPublishResponse>("/api/comments/publish", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
