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

export interface ValidationRuleResult {
  code: string;
  valid: boolean;
  reason: string | null;
}

export interface ValidatorReportData {
  valid: boolean;
  results: Record<string, ValidationRuleResult>;
  failed_codes: string[];
}

export interface DraftItem {
  id: string;
  account_id: string;
  kind: "post" | "thread" | "comment";
  niche_id: string | null;
  niche_name: string | null;
  style_id: string | null;
  style_name: string | null;
  product_id: string | null;
  product_title: string | null;
  prompt_version: string;
  llm_model: string;
  parts: Array<{ part_index?: number; text: string; char_count?: number }>;
  text: string;
  link_url: string | null;
  link_placement: string | null;
  status:
    | "generated"
    | "rejected_auto"
    | "pending_review"
    | "approved"
    | "rejected"
    | "scheduled"
    | "publishing"
    | "published"
    | "failed"
    | "failed_permanent"
    | "expired"
    | "cancelled";
  reject_reason: string | null;
  validator_report: ValidatorReportData | null;
  similarity_score: number | null;
  text_hash: string;
  scheduled_at: string | null;
  reviewed_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RealtimeValidationResponse {
  valid: boolean;
  char_count: number;
  max_chars: number;
  failed_codes: string[];
  results: Record<string, ValidationRuleResult>;
}

// ---------------------------------------------------------------------------
// Catalog: Niches
// ---------------------------------------------------------------------------
export interface NicheItem {
  id: string;
  name: string;
  description: string | null;
  keywords: string[];
  status: "active" | "paused" | "archived";
  created_at: string;
  updated_at: string;
}

export interface NicheCreatePayload {
  name: string;
  description?: string;
  keywords?: string[];
}

export interface NicheUpdatePayload {
  name?: string;
  description?: string;
  keywords?: string[];
  status?: "active" | "paused" | "archived";
}

// ---------------------------------------------------------------------------
// Catalog: Products
// ---------------------------------------------------------------------------
export interface ProductItem {
  id: string;
  niche_id: string;
  niche_name?: string | null;
  title: string;
  benable_url: string;
  amazon_ref_url?: string | null;
  benefits: string[];
  tags: string[];
  status: "active" | "paused" | "archived";
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductCreatePayload {
  niche_id: string;
  title: string;
  benable_url: string;
  amazon_ref_url?: string;
  benefits?: string[];
  tags?: string[];
}

export interface ProductUpdatePayload {
  niche_id?: string;
  title?: string;
  benable_url?: string;
  amazon_ref_url?: string;
  benefits?: string[];
  tags?: string[];
  status?: "active" | "paused" | "archived";
}

export interface CSVImportRowError {
  row: number;
  title?: string | null;
  reason: string;
}

export interface ProductImportResponse {
  total_rows: number;
  imported_count: number;
  failed_count: number;
  is_preview?: boolean;
  errors: CSVImportRowError[];
  imported_products: ProductItem[];
}

export interface ValidateUrlResponse {
  url: string;
  valid: boolean;
  error?: string | null;
  normalized_url?: string | null;
}

// ---------------------------------------------------------------------------
// Catalog: Styles
// ---------------------------------------------------------------------------
export interface StyleItem {
  id: string;
  name: string;
  description: string;
  tone_rules: string;
  max_chars: number;
  good_examples: string[];
  bad_examples: string[];
  status: "active" | "paused" | "archived";
  created_at: string;
  updated_at: string;
}

export interface StyleCreatePayload {
  name: string;
  description: string;
  tone_rules: string;
  max_chars?: number;
  good_examples?: string[];
  bad_examples?: string[];
}

export interface StyleUpdatePayload {
  name?: string;
  description?: string;
  tone_rules?: string;
  max_chars?: number;
  good_examples?: string[];
  bad_examples?: string[];
  status?: "active" | "paused" | "archived";
}

// ---------------------------------------------------------------------------
// Catalog: Personas
// ---------------------------------------------------------------------------
export interface PersonaItem {
  id: string;
  account_id: string;
  name: string;
  voice_description: string | null;
  disclosure_template: string;
  disclosure_position: "end" | "beginning" | "reply";
  status: "active" | "paused" | "archived";
  created_at: string;
  updated_at: string;
}

export interface PersonaCreatePayload {
  account_id: string;
  name: string;
  voice_description?: string;
  disclosure_template: string;
  disclosure_position?: "end" | "beginning" | "reply";
}

export interface PersonaUpdatePayload {
  name?: string;
  voice_description?: string;
  disclosure_template?: string;
  disclosure_position?: "end" | "beginning" | "reply";
  status?: "active" | "paused" | "archived";
}
