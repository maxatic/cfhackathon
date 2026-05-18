export type ForecastPoint = {
  week: string;
  predicted_quantity: number;
  lower_bound: number;
  upper_bound: number;
  confidence: number;
  drivers: Record<string, number | string>;
};

export type ForecastRun = {
  forecast_run_id: string;
  tenant_id: string;
  sku: string;
  customer_segment: string;
  horizon_weeks: number;
  model_version: string;
  created_at: string;
  history_tail: Array<{ week: string; quantity: number }>;
  forecast: ForecastPoint[];
  metrics: {
    mae: number;
    smape: number;
    holdout_weeks: number;
  };
};

export type BeamScenario = {
  rank: number;
  probability: number;
  total_units: number;
  quantities: number[];
  weeks: string[];
  label: string;
  explanation: string;
};

export type ProductOption = {
  sku: string;
  name: string;
  category: string;
  unit_price: number;
};

export type RiskCustomer = {
  rank: number;
  customer_ref: string;
  segment: string;
  region: string;
  current_demand: {
    last_4_weeks_units: number;
    weekly_average: number;
    trend_vs_prior_4_weeks_pct: number;
  };
  forecast_demand: {
    horizon_units: number;
    weekly_average: number;
  };
  downside_scenario: {
    label: string;
    probability: number;
    horizon_units: number;
    weekly_average: number;
    decline_vs_current_run_rate_pct: number;
  };
  risk_score: number;
  revenue_at_risk: number;
  recommended_action: string;
};

export type RiskResponse = {
  tenant_id: string;
  sku: string;
  horizon_weeks: number;
  limit: number;
  model_version: string;
  ranked_customers: RiskCustomer[];
};

export type AnonymizedOrderSample = {
  order_date: string;
  sku: string;
  customer_ref: string;
  customer_segment: string;
  region: string;
  quantity: number;
  unit_price_bucket: string;
  promotion: boolean;
  stockout: boolean;
  lead_time_days: number;
};

export type AnonymizationReport = {
  row_count: number;
  source_rows: number;
  sample_size: number;
  fields_scrubbed: string[];
  fields_hashed: string[];
  detected_sensitive_fields: string[];
  removed_fields: string[];
  transformed_fields: string[];
  k_anonymity_proxy: number;
  privacy_notes: string[];
  sample: AnonymizedOrderSample[];
};

export type AnonymizationResponse = {
  tenant_id: string;
  sku: string;
  customer_segment: string;
  anonymization: AnonymizationReport;
};

export type ModelVersion = {
  version_id: string;
  model_name: string;
  tenant_id: string;
  trained_at: string;
  metrics: {
    mae: number;
    smape: number;
    holdout_weeks: number;
  };
  status: "active" | "archived" | "pending" | string;
  base_version_id?: string;
  adapter_multiplier?: number;
  explanation?: string;
};

export type ModelVersionsResponse = {
  tenant_id: string;
  model_versions: ModelVersion[];
};

export type LossPoint = {
  step: number;
  train_loss: number;
  validation_loss: number;
};

export type RetrainingJob = {
  job_id: string;
  tenant_id: string;
  status: "queued" | "running" | "completed" | string;
  reason: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  progress_pct: number;
  loss_curve: LossPoint[];
  before_metrics: {
    mae: number;
    smape: number;
    holdout_weeks: number;
  };
  after_metrics: {
    mae: number;
    smape: number;
    holdout_weeks: number;
  };
  explanation: string;
  base_version_id: string;
  model_version?: ModelVersion;
  forecast_shift?: {
    model_version_id: string;
    adapter_multiplier: number;
    explanation: string;
  };
};

export type AuditEvent = {
  event_id: string;
  tool_name: string;
  tenant_id: string;
  actor: string;
  key_id: string;
  status: "success" | "error" | string;
  latency_ms: number;
  timestamp: string;
  error_summary?: string;
};

export type AuditEventsResponse = {
  tenant_id: string;
  events: AuditEvent[];
};
