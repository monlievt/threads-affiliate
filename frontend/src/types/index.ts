/**
 * Application Type Definitions
 */

export interface SystemHealth {
  status: "ok" | "degraded" | "down";
  db: "ok" | "error";
  worker_heartbeat_age_sec: number | null;
  token_valid: boolean | null;
  kill_switch: "on" | "off";
  quota_today: number | null;
}

export interface KillSwitchStatus {
  active: boolean;
  status: "on" | "off";
  reason: string;
  updated_at: string;
}

export interface AccountInfo {
  id: string;
  threads_user_id: string | null;
  username: string | null;
  country_code: string;
  timezone: string;
  active_hours_start: number;
  active_hours_end: number;
  automation_mode: "manual_approve" | "auto_sampled" | "full_auto";
  token_expires_at: string | null;
  connected_at: string | null;
  warmup_started_at: string | null;
}

export interface QuotaSummary {
  posts_today: number;
  max_posts_per_day: number;
  min_interval_minutes: number;
  warmup_week: number;
  llm_calls_today: number;
}
