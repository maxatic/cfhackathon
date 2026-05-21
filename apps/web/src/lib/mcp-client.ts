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
  ListAuditEventsResponse,
  ListClientsResponse,
  PersonalizeClientResponse,
  PersonalizationResponse,
  ResponseSource,
  ScenarioResponse,
  SourceTagged,
} from "./types";

const SERVICE_TIMEOUT_MS = 1800;

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

type ServerForecastPlanResponse = {
  client_id: string;
  chosen_strategy: string;
  rationale: string;
  payload: BasketPrediction | ScenarioResponse;
  model_version: string;
} & SourceTagged;

function tagSource<T extends object>(payload: T, source: ResponseSource): T & SourceTagged {
  return {
    ...payload,
    response_source: source,
  };
}

async function postMcpService<T extends object>(path: string, input: Record<string, unknown>, fallback: () => T): Promise<T & SourceTagged> {
  const endpoint = process.env.MCP_REST_URL;
  if (!endpoint) {
    return tagSource(fallback(), "local_fallback");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), SERVICE_TIMEOUT_MS);
  let response: Response;

  try {
    response = await fetch(`${endpoint}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        ...input,
        api_token: process.env.MCP_DEMO_TOKEN,
      }),
      cache: "no-store",
      signal: controller.signal,
    });
  } catch {
    return tagSource(fallback(), "local_fallback");
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    if (process.env.MCP_REST_STRICT !== "1") {
      return tagSource(fallback(), "local_fallback");
    }
    const payload = (await response.json().catch(() => ({}))) as { error?: string };
    const detail = payload.error ? `: ${payload.error}` : "";
    throw new Error(`MCP service returned ${response.status}${detail}`);
  }

  try {
    return tagSource((await response.json()) as T, "live_mcp");
  } catch {
    if (process.env.MCP_REST_STRICT === "1") {
      throw new Error("MCP service returned invalid JSON");
    }
    return tagSource(fallback(), "local_fallback");
  }
}

export async function requestClients(): Promise<ClientListResponse> {
  const endpoint = process.env.MCP_REST_URL;
  if (!endpoint) {
    return tagSource(createLocalClients(), "local_fallback");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), SERVICE_TIMEOUT_MS);
  let response: Response;

  try {
    response = await fetch(`${endpoint}/api/clients`, {
      method: "GET",
      headers: { "content-type": "application/json" },
      cache: "no-store",
      signal: controller.signal,
    });
  } catch {
    return tagSource(createLocalClients(), "local_fallback");
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    if (process.env.MCP_REST_STRICT !== "1") {
      return tagSource(createLocalClients(), "local_fallback");
    }
    const payload = (await response.json().catch(() => ({}))) as { error?: string };
    throw new Error(payload.error ?? `MCP service returned ${response.status}`);
  }

  try {
    return normalizeClients(tagSource((await response.json()) as ListClientsResponse | ClientListResponse, "live_mcp"));
  } catch {
    if (process.env.MCP_REST_STRICT === "1") {
      throw new Error("MCP service returned invalid JSON");
    }
    return tagSource(createLocalClients(), "local_fallback");
  }
}

function normalizeClients(response: ListClientsResponse | ClientListResponse): ClientListResponse {
  if (response.clients.length === 0 || typeof response.clients[0] !== "string") {
    return response as ClientListResponse;
  }

  return {
    clients: (response as ListClientsResponse).clients.map((clientId) => ({
      client_id: clientId,
      display_name: clientId === "nexus_lab_solutions" ? "NexusLab Solutions" : clientId,
      domain: clientId === "nexus_lab_solutions" ? "Chemistry research lab" : "Swiftron client",
      status: clientId === "nexus_lab_solutions" ? "demo" : "available",
      last_order_week: "from model bundle",
    })),
    response_source: response.response_source,
  };
}

function isScenarioResponse(payload: BasketPrediction | ScenarioResponse): payload is ScenarioResponse {
  return "scenarios" in payload;
}

function normalizeForecastPlan(response: ServerForecastPlanResponse, intent: string): ForecastPlanResponse {
  const payload = response.payload;
  const scenarios = isScenarioResponse(payload) ? payload.scenarios : [];
  const predictedBasket = isScenarioResponse(payload) ? createLocalBasketPrediction() : payload;

  return {
    client_id: response.client_id,
    intent,
    selected_strategy: response.chosen_strategy,
    decoder_config: isScenarioResponse(payload)
      ? (payload.decoder_config ?? { strategy: response.chosen_strategy })
      : payload.decoder_config,
    recommendation_summary: response.rationale,
    predicted_basket: predictedBasket,
    scenarios,
    response_source: response.response_source,
  };
}

function normalizePersonalization(
  response: PersonalizeClientResponse,
  additionalTokens: string[],
): PersonalizationResponse {
  return {
    client_id: response.client_id,
    session_id: response.session_id,
    added_tokens: response.additional_tokens,
    before: createLocalBasketPrediction(),
    after: response.prediction,
    delta_notes: [
      `${additionalTokens.length} sensor tokens applied to this session.`,
      `Decoder strategy returned: ${response.prediction.decoder_config.strategy}.`,
    ],
    response_source: response.response_source,
  };
}

export async function requestPrediction(input: PredictRequest): Promise<BasketPrediction> {
  return postMcpService("/api/predict", input, () => createLocalBasketPrediction());
}

export async function requestScenarios(input: ScenariosRequest): Promise<ScenarioResponse> {
  return postMcpService("/api/scenarios", input, () => createLocalScenarios());
}

export async function requestForecastPlan(input: ForecastPlanRequest): Promise<ForecastPlanResponse> {
  const response = await postMcpService<ServerForecastPlanResponse>(
    "/api/forecast-plan",
    {
      client_id: input.client_id,
      objective_text: input.intent,
      horizon_hint: 8,
    },
    () => ({
      client_id: input.client_id,
      chosen_strategy: "beam_search",
      rationale: createLocalForecastPlan(input.intent).recommendation_summary,
      payload: createLocalScenarios(),
      model_version: "swiftron-onnx-v1",
    }),
  );
  return normalizeForecastPlan(response, input.intent);
}

export async function requestPersonalization(input: PersonalizeRequest): Promise<PersonalizationResponse> {
  const response = await postMcpService<PersonalizeClientResponse>(
    "/api/personalize",
    input,
    () => {
      const fallback = createLocalPersonalization(input.additional_tokens);
      return {
        session_id: fallback.session_id,
        client_id: fallback.client_id,
        additional_tokens: fallback.added_tokens,
        prediction: fallback.after,
      };
    },
  );
  return normalizePersonalization(response, input.additional_tokens);
}

export async function requestAnonymization(input: AnonymizeRequest): Promise<AnonymizationResponse> {
  return postMcpService("/api/anonymize", input, () => createLocalAnonymization());
}

export async function requestAuditEvents(input: AuditRequest): Promise<AuditEventsResponse> {
  const response = await postMcpService<ListAuditEventsResponse | AuditEventsResponse>(
    "/api/audit",
    input,
    () => createLocalAuditEvents(),
  );
  return {
    events: response.events,
    count: "count" in response ? response.count : response.events.length,
    response_source: response.response_source,
  };
}
