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

// ---------------------------------------------------------------------------
// Schedule & Calendar
// ---------------------------------------------------------------------------
export interface CalendarSlot {
  id: string;
  draft_id: string;
  status: string;
  scheduled_at_utc: string;
  scheduled_at_target: string;
  scheduled_at_operator: string;
  hour_target: number;
  minute_target: number;
  text_snippet: string;
  niche_name: string | null;
  style_name: string | null;
  product_title: string | null;
}

export interface CalendarDay {
  date: string;
  day_name: string;
  is_today: boolean;
  scheduled_count: number;
  published_count: number;
  max_posts: number;
  remaining_quota: number;
  is_quota_full: boolean;
  slots: CalendarSlot[];
}

export interface GovernorRulesSummary {
  target_timezone: string;
  operator_timezone: string;
  active_hours_start: number;
  active_hours_end: number;
  active_hours_label: string;
  operator_active_hours_label: string;
  min_interval_minutes: number;
  warmup_tier_label: string;
  max_posts_per_day: number;
}

export interface CalendarResponse {
  start_date: string;
  end_date: string;
  days: CalendarDay[];
  governor: GovernorRulesSummary;
}

export interface MoveSlotResponse {
  success: boolean;
  draft_id: string;
  new_scheduled_at_utc: string;
  new_scheduled_at_target: string;
  new_scheduled_at_operator: string;
  status: string;
  message: string;
}

export interface ValidateSlotResponse {
  valid: boolean;
  reason: string | null;
  target_time_formatted: string;
  operator_time_formatted: string;
  is_active_hours: boolean;
  violates_interval?: boolean;
  violates_quota?: boolean;
}

// ---------------------------------------------------------------------------
// Settings, Full-Auto & Incidents
// ---------------------------------------------------------------------------
export interface FullAutoCriterion {
  required: string;
  current: string;
  passed: boolean;
  label: string;
}

export interface FullAutoEligibilityResponse {
  eligible: boolean;
  summary_reason: string;
  criteria: Record<string, FullAutoCriterion>;
}

export interface AccountSettingsResponse {
  id: string;
  username: string | null;
  threads_user_id: string | null;
  country_code: string;
  timezone: string;
  active_hours_start: number;
  active_hours_end: number;
  automation_mode: "manual_approve" | "auto_sampled" | "full_auto";
  sample_review_pct: number;
  warmup_started_at: string | null;
  warmup_age_days: number;
  token_valid: boolean;
  token_expires_at: string | null;
  days_until_token_expiry: number | null;
  hard_max_posts_per_day: number;
  hard_max_replies_per_day: number;
}

export interface AccountSettingsUpdatePayload {
  active_hours_start?: number;
  active_hours_end?: number;
  automation_mode?: "manual_approve" | "auto_sampled" | "full_auto";
  sample_review_pct?: number;
  timezone?: string;
}

export interface IncidentItem {
  id: string;
  severity: "info" | "warning" | "critical";
  code: string;
  detail: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface AuditLogItem {
  id: string;
  at: string;
  actor: string;
  action: string;
  entity: string | null;
  entity_id: string | null;
  detail: string | null;
}

// ---------------------------------------------------------------------------
// Value-First Comments (Feature 10)
// ---------------------------------------------------------------------------
export interface CommentOption {
  option_id: string;
  strategy: "insight" | "relate" | "question" | "curator_tip";
  strategy_label: string;
  text: string;
  char_count: number;
  has_link: boolean;
  link_url: string | null;
  safety_valid: boolean;
  safety_issues: string[];
}

export interface CommentGenerateRequest {
  target_post_url: string;
  target_post_text: string;
  strategy?: "all" | "insight" | "relate" | "question";
  niche_id?: string | null;
  persona_id?: string | null;
  include_link?: boolean;
  product_id?: string | null;
}

export interface CommentGenerateResponse {
  target_post_url: string;
  target_post_id: string | null;
  options: CommentOption[];
  daily_replies_used: number;
  daily_replies_limit: number;
  hard_max_replies: number;
  remaining_replies_today: number;
  avoid_list: string[];
}

export interface CommentPublishRequest {
  target_post_url: string;
  selected_text: string;
  link_url?: string | null;
  action_type: "publish_api" | "copied_clipboard";
}

export interface CommentPublishResponse {
  success: boolean;
  message: string;
  action_type: string;
  threads_reply_id: string | null;
  daily_replies_used: number;
  remaining_replies_today: number;
}

export interface CommentsQuotaResponse {
  replies_today: number;
  max_replies_today: number;
  hard_max_replies: number;
  remaining_today: number;
  is_quota_full: boolean;
  avoid_list: string[];
}

// ---------------------------------------------------------------------------
// Analytics & Metrics (T-040)
// ---------------------------------------------------------------------------

export interface PostMetricItem {
  id: string;
  age_bucket: string;
  captured_at: string;
  views: number;
  likes: number;
  replies: number;
  reposts: number;
  quotes: number;
}

export interface PublishedPostAnalytics {
  post_id: string;
  draft_id: string;
  threads_media_id: string | null;
  permalink: string | null;
  published_at: string;
  text_snippet: string;
  niche_name: string | null;
  style_name: string | null;
  product_title: string | null;
  latest_views: number;
  latest_likes: number;
  latest_replies: number;
  latest_reposts: number;
  metrics: PostMetricItem[];
}

export interface AnalyticsOverviewResponse {
  total_posts_published: number;
  total_views: number;
  total_likes: number;
  total_replies: number;
  total_reposts: number;
  total_quotes: number;
  bucket_totals: Record<string, Record<string, number>>;
  recent_posts: PublishedPostAnalytics[];
}

export interface AccountSnapshotItem {
  id: string;
  captured_at: string;
  followers: number | null;
  profile_views: number | null;
}

export interface CollectMetricsResponse {
  success: boolean;
  posts_evaluated: number;
  metrics_saved: number;
  posts_failed: number;
  buckets_processed: Record<string, number>;
  snapshot_id: string | null;
}

// ---------------------------------------------------------------------------
// Link Clicks & Benable Import (T-041)
// ---------------------------------------------------------------------------

export interface LinkClickItem {
  id: string;
  product_id: string | null;
  product_title: string | null;
  post_id: string | null;
  period_start: string;
  period_end: string;
  clicks: number;
  source: string;
  note: string | null;
  created_at: string;
}

export interface LinkClickListResponse {
  total_clicks: number;
  items_count: number;
  attribution_caveat: string;
  items: LinkClickItem[];
}

export interface ClickImportRowError {
  row: number;
  product: string | null;
  reason: string;
}

export interface ClickImportResponse {
  total_rows: number;
  imported_count: number;
  failed_count: number;
  is_preview: boolean;
  attribution_caveat: string;
  errors: ClickImportRowError[];
  imported_items: LinkClickItem[];
}

// ---------------------------------------------------------------------------
// Experiments & Allocation (T-042)
// ---------------------------------------------------------------------------

export interface ExperimentArmItem {
  id: string;
  experiment_id: string;
  label: string;
  target_posts: number;
  niche_id: string | null;
  niche_name: string | null;
  style_id: string | null;
  style_name: string | null;
}

export interface ExperimentItem {
  id: string;
  name: string;
  phase: "niche_test" | "style_test" | "scale";
  status: "planned" | "running" | "completed" | "aborted";
  start_date: string;
  end_date: string | null;
  config: Record<string, any>;
  created_at: string;
  updated_at: string;
  arms: ExperimentArmItem[];
}

export interface ArmProgressItem {
  arm_id: string;
  label: string;
  niche_id: string | null;
  niche_name: string | null;
  style_id: string | null;
  style_name: string | null;
  target_posts: number;
  total_drafts: number;
  published_posts: number;
  metrics_completed_72h: number;
  progress_pct: number;
}

export interface ExperimentProgressResponse {
  experiment_id: string;
  name: string;
  phase: string;
  status: string;
  total_target_posts: number;
  total_published_posts: number;
  overall_progress_pct: number;
  arms: ArmProgressItem[];
}

export interface AllocateNextArmResponse {
  experiment_id: string;
  has_eligible_arm: boolean;
  recommended_arm: ExperimentArmItem | null;
  reason: string;
}

// ---------------------------------------------------------------------------
// rule_v1 Evaluation & Weekly Report (T-043)
// ---------------------------------------------------------------------------

export interface ArmRuleEvaluationItem {
  arm_id: string;
  label: string;
  niche_id: string | null;
  niche_name: string | null;
  style_id: string | null;
  style_name: string | null;
  n: number;
  insufficient_data: boolean;
  median_views_72: number;
  median_er_72: number;
  click_rate: number | null;
  raw_clicks: number;
  score: number;
  rank: number | null;
  outliers_views: Array<Record<string, any>>;
  outliers_er: Array<Record<string, any>>;
}

export interface ExperimentEvaluationResponse {
  experiment_id: string;
  phase: string;
  status: string;
  evaluated_at: string;
  total_arms: number;
  eligible_arms_count: number;
  recommendation: "winner_found" | "no_clear_winner" | "insufficient_data";
  winner_arm_id: string | null;
  winner_arm_label: string | null;
  runner_up_arm_id: string | null;
  score_ratio: number | null;
  recommended_extension_posts: number;
  explanation: string;
  arms: ArmRuleEvaluationItem[];
}

export interface WeeklyReportResponse {
  period_start: string;
  period_end: string;
  generated_at: string;
  total_posts_published: number;
  total_views: number;
  total_engagements: number;
  average_er_pct: number;
  operator_workload: {
    drafts_created_this_period: number;
    approved: number;
    rejected: number;
    current_pending_queue: number;
  };
  incidents: {
    total_incidents: number;
    unresolved_count: number;
    critical_count: number;
    recent_incidents: Array<Record<string, any>>;
  };
  experiments: Array<Record<string, any>>;
  suggested_actions: string[];
}



