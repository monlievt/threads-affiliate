/**
 * API client for interacting with the backend FastAPI service.
 */

import {
  DraftItem,
  KillSwitchStatus,
  RealtimeValidationResponse,
  SystemHealth,
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
