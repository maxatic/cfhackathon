import {
  createLocalAnonymization,
  createLocalAuditEvents,
  createLocalForecast,
  createLocalModelVersions,
  createLocalRealSequence,
  createLocalRetrainingJob,
  createLocalRisk,
} from "./demo-data";
import type {
  AnonymizationResponse,
  AuditEventsResponse,
  ForecastRun,
  ModelVersionsResponse,
  RealSequenceResponse,
  RetrainingJob,
  RiskResponse,
} from "./types";

export type ForecastRequest = {
  tenant_id: string;
  sku: string;
  customer_segment: string;
  horizon_weeks: number;
};

export type RiskRequest = {
  tenant_id: string;
  sku: string;
  horizon_weeks: number;
  limit: number;
};

export type AnonymizationRequest = {
  tenant_id: string;
  sku: string;
  customer_segment: string;
  sample_size: number;
  raw_order_rows?: Array<Record<string, unknown>>;
};

export type ModelVersionsRequest = {
  tenant_id: string;
};

export type RetrainingRequest = {
  tenant_id: string;
  reason: string;
};

export type RetrainingStatusRequest = {
  tenant_id: string;
  job_id: string;
  poll_count?: number;
};

export type AuditEventsRequest = {
  tenant_id: string;
  limit: number;
};

export type RealSequenceRequest = {
  client_id: string;
  start_sequence?: string;
  max_generate: number;
  temperature: number;
  top_k: number;
  seed: number;
};

async function postMcpService<T>(path: string, input: Record<string, unknown>, fallback: () => T): Promise<T> {
  const endpoint = process.env.MCP_REST_URL;
  if (!endpoint) {
    return fallback();
  }

  const response = await fetch(`${endpoint}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      ...input,
      api_token: process.env.MCP_DEMO_TOKEN ?? "sk_northstar_forecast_full",
    }),
    cache: "no-store",
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { error?: string };
    const detail = payload.error ? `: ${payload.error}` : "";
    throw new Error(`MCP service returned ${response.status}${detail}`);
  }

  return (await response.json()) as T;
}

export async function requestForecast(input: ForecastRequest): Promise<ForecastRun> {
  return postMcpService("/api/forecast", input, () =>
    createLocalForecast(input.sku, input.customer_segment, input.horizon_weeks),
  );
}

export async function requestRisk(input: RiskRequest): Promise<RiskResponse> {
  return postMcpService("/api/risk", input, () => createLocalRisk(input.sku, input.horizon_weeks, input.limit));
}

export async function requestAnonymization(input: AnonymizationRequest): Promise<AnonymizationResponse> {
  return postMcpService("/api/anonymize", input, () =>
    createLocalAnonymization(input.sku, input.customer_segment, input.sample_size),
  );
}

export async function requestModelVersions(input: ModelVersionsRequest): Promise<ModelVersionsResponse> {
  return postMcpService("/api/model-versions", input, () => createLocalModelVersions());
}

export async function triggerRetraining(input: RetrainingRequest): Promise<RetrainingJob> {
  return postMcpService("/api/retraining", input, () => createLocalRetrainingJob("queued"));
}

export async function requestRetrainingStatus(input: RetrainingStatusRequest): Promise<RetrainingJob> {
  return postMcpService("/api/retraining/status", input, () =>
    createLocalRetrainingJob(input.poll_count && input.poll_count > 1 ? "completed" : "running", input.job_id),
  );
}

export async function requestAuditEvents(input: AuditEventsRequest): Promise<AuditEventsResponse> {
  return postMcpService("/api/audit-events", input, () => createLocalAuditEvents());
}

export async function requestRealSequence(input: RealSequenceRequest): Promise<RealSequenceResponse> {
  return postMcpService("/api/real-sequence", input, () => createLocalRealSequence());
}
