export type ClientSummary = {
  client_id: string;
  display_name: string;
  domain: string;
  status: "demo" | "available" | string;
  last_order_week: string;
};

export type ClientListResponse = {
  clients: ClientSummary[];
};

export type DecoderConfig = {
  strategy: string;
  top_k?: number;
  temperature?: number;
  max_generate?: number;
  seed?: number;
  beam_width?: number;
  horizon?: number;
};

export type BasketPrediction = {
  client_id: string;
  start_sequence: string[];
  generated_tokens: string[];
  generated_times: number[];
  model_version: string;
  decoder_config: DecoderConfig;
};

export type ScenarioTrajectory = {
  rank: number;
  joint_log_prob: number;
  tokens: string[];
  time_deltas: number[];
};

export type ScenarioResponse = {
  client_id: string;
  model_version: string;
  decoder_config?: DecoderConfig;
  scenarios: ScenarioTrajectory[];
};

export type ForecastPlanResponse = {
  client_id: string;
  intent: string;
  selected_strategy: string;
  decoder_config: DecoderConfig;
  recommendation_summary: string;
  predicted_basket: BasketPrediction;
  scenarios: ScenarioTrajectory[];
};

export type PersonalizationResponse = {
  client_id: string;
  session_id: string;
  added_tokens: string[];
  before: BasketPrediction;
  after: BasketPrediction;
  delta_notes: string[];
};

export type AnonymizationAuditReport = {
  row_count: number;
  fields_hashed: string[];
  fields_scrubbed: string[];
  detected_sensitive_fields: string[];
  k_anonymity_proxy: number;
  privacy_notes: string[];
};

export type TokenizedOrderRow = {
  row_id: string;
  source_label: string;
  token: string;
  time_delta: number;
};

export type AnonymizationResponse = {
  client_id: string;
  tokenized: string[];
  time_deltas: number[];
  audit_report: AnonymizationAuditReport;
  rows: TokenizedOrderRow[];
};

export type AuditEvent = {
  event_id: string;
  tool_name: string;
  tenant_id?: string;
  client_id?: string;
  actor: string;
  key_id?: string;
  status: "success" | "error" | string;
  latency_ms: number;
  timestamp: string;
  error_summary?: string;
};

export type AuditEventsResponse = {
  events: AuditEvent[];
  count?: number;
};

export type PredictNextBasketResponse = BasketPrediction;
export type PredictScenariosResponse = ScenarioResponse;
export type PersonalizeClientResponse = {
  session_id: string;
  client_id: string;
  additional_tokens: string[];
  prediction: BasketPrediction;
};
export type AnonymizeAuditReport = AnonymizationAuditReport;
export type TokenizedRow = TokenizedOrderRow;
export type AnonymizeAndTokenizeResponse = AnonymizationResponse;
export type ListClientsResponse = {
  clients: string[];
  count: number;
  model_version: string;
};
export type ListAuditEventsResponse = {
  tenant_id: string;
  events: AuditEvent[];
  count: number;
};
