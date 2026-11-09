/**
 * API client for interacting with the backend FastAPI service.
 */

import { KillSwitchStatus, SystemHealth } from "@/types";

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
      errorDetail = errorJson.detail || errorDetail;
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
