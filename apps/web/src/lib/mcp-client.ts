import {
  createLocalAnonymization,
  createLocalAuditEvents,
  createLocalBasketPrediction,
  createLocalClients,
  createLocalForecastPlan,
  createLocalPersonalization,
  createLocalScenarios,
} from "./demo-data";
import type {
  AnonymizationResponse,
  AuditEventsResponse,
  BasketPrediction,
  ClientListResponse,
  ForecastPlanResponse,
  PersonalizationResponse,
  ScenarioResponse,
} from "./types";

export type PredictRequest = {
  client_id: string;
  start_sequence?: string[];
  max_generate: number;
  top_k: number;
  temperature: number;
  seed?: number;
};

export type ScenariosRequest = {
  client_id: string;
  start_sequence?: string[];
  beam_width: number;
  horizon: number;
  temperature: number;
};

export type ForecastPlanRequest = {
  client_id: string;
  intent: string;
};

export type PersonalizeRequest = {
  client_id: string;
  additional_tokens: string[];
};

export type AnonymizeRequest = {
  client_id: string;
  raw_rows?: Array<Record<string, unknown>>;
};

export type AuditRequest = {
  client_id?: string;
  limit: number;
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
      api_token: process.env.MCP_DEMO_TOKEN ?? "sk_nexus_lab_demo",
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

export async function requestClients(): Promise<ClientListResponse> {
  const endpoint = process.env.MCP_REST_URL;
  if (!endpoint) {
    return createLocalClients();
  }

  const response = await fetch(`${endpoint}/api/clients`, {
    method: "GET",
    headers: { "content-type": "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { error?: string };
    throw new Error(payload.error ?? `MCP service returned ${response.status}`);
  }

  return (await response.json()) as ClientListResponse;
}

export async function requestPrediction(input: PredictRequest): Promise<BasketPrediction> {
  return postMcpService("/api/predict", input, () => createLocalBasketPrediction());
}

export async function requestScenarios(input: ScenariosRequest): Promise<ScenarioResponse> {
  return postMcpService("/api/scenarios", input, () => createLocalScenarios());
}

export async function requestForecastPlan(input: ForecastPlanRequest): Promise<ForecastPlanResponse> {
  return postMcpService("/api/forecast-plan", input, () => createLocalForecastPlan(input.intent));
}

export async function requestPersonalization(input: PersonalizeRequest): Promise<PersonalizationResponse> {
  return postMcpService("/api/personalize", input, () => createLocalPersonalization(input.additional_tokens));
}

export async function requestAnonymization(input: AnonymizeRequest): Promise<AnonymizationResponse> {
  return postMcpService("/api/anonymize", input, () => createLocalAnonymization());
}

export async function requestAuditEvents(input: AuditRequest): Promise<AuditEventsResponse> {
  return postMcpService("/api/audit", input, () => createLocalAuditEvents());
}
