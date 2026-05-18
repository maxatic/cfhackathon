import type {
  AnonymizationResponse,
  AuditEventsResponse,
  BasketPrediction,
  ClientListResponse,
  ForecastPlanResponse,
  PersonalizationResponse,
  ScenarioResponse,
  ScenarioTrajectory,
} from "./types";

export const demoClient = {
  client_id: "nexus_lab_solutions",
  display_name: "NexusLab Solutions",
  domain: "Chemistry research lab",
  status: "demo",
  last_order_week: "2026-05-11",
} as const;

export const intentOptions = [
  "I am visiting this lab next week. What should I prepare?",
  "Plan a conservative reorder basket for the next lab cycle.",
  "Show plausible substitute baskets if solvent demand changes.",
];

export const sensorTokenOptions = [
  "b_dna_kit_3",
  "b_pcr_master_mix",
  "s_filter_membrane",
  "c_solvent_acetonitrile",
  "s_gloves_nitrile_l",
];

export function createLocalClients(): ClientListResponse {
  return {
    clients: [demoClient],
  };
}

export function createLocalBasketPrediction(
  overrides: Partial<Pick<BasketPrediction, "generated_tokens" | "generated_times" | "decoder_config">> = {},
): BasketPrediction {
  const generatedTokens = overrides.generated_tokens ?? [
    "<dt_1w>",
    "c_solvent_acetonitrile",
    "s_gloves_nitrile_l",
    "s_beaker_250ml",
    "<dt_3d>",
    "c_acid_tfa",
    "s_goggles_basic",
    "c_reag_magnesium_turn",
  ];

  return {
    client_id: demoClient.client_id,
    start_sequence: ["<dt_2w>", "c_solvent_ethanol", "s_pipette_tip_200ul"],
    generated_tokens: generatedTokens,
    generated_times: overrides.generated_times ?? [7, 0, 0, 0, 3, 0, 0, 0],
    model_version: "swiftron-onnx-v1",
    decoder_config: {
      strategy: "top_k",
      top_k: 5,
      temperature: 1,
      max_generate: 8,
      ...overrides.decoder_config,
    },
  };
}

export function createLocalScenarios(): ScenarioResponse {
  return {
    client_id: demoClient.client_id,
    model_version: "swiftron-onnx-v1",
    scenarios: [
      {
        rank: 1,
        joint_log_prob: -12.3,
        tokens: ["<dt_1w>", "c_solvent_acetonitrile", "s_gloves_nitrile_l", "s_beaker_250ml"],
        time_deltas: [7, 0, 0, 0],
      },
      {
        rank: 2,
        joint_log_prob: -13.8,
        tokens: ["<dt_1w>", "c_acid_tfa", "s_filter_membrane", "s_vial_amber"],
        time_deltas: [7, 0, 0, 0],
      },
      {
        rank: 3,
        joint_log_prob: -14.1,
        tokens: ["<dt_3d>", "b_pcr_master_mix", "b_dna_kit_3", "s_gloves_nitrile_l"],
        time_deltas: [3, 0, 0, 0],
      },
    ],
  };
}

export function createLocalForecastPlan(intent = intentOptions[0]): ForecastPlanResponse {
  const scenarios = createLocalScenarios().scenarios;
  return {
    client_id: demoClient.client_id,
    intent,
    selected_strategy: "beam_search",
    decoder_config: {
      strategy: "beam_search",
      beam_width: 3,
      horizon: 8,
      temperature: 0.8,
    },
    recommendation_summary:
      "Prepare solvents, nitrile gloves, and bench consumables for the next lab cycle.",
    predicted_basket: createLocalBasketPrediction(),
    scenarios,
  };
}

export function createLocalPersonalization(additionalTokens = sensorTokenOptions.slice(0, 2)): PersonalizationResponse {
  const before = createLocalBasketPrediction();
  const after = createLocalBasketPrediction({
    generated_tokens: ["<dt_1w>", ...additionalTokens, "s_filter_membrane", "s_gloves_nitrile_l"],
    generated_times: [7, ...additionalTokens.map(() => 0), 0, 0],
    decoder_config: {
      strategy: "sensor_profile",
      top_k: 5,
      temperature: 0.9,
      max_generate: 6,
    },
  });

  return {
    client_id: demoClient.client_id,
    session_id: "session_local_nexus_lab",
    added_tokens: additionalTokens,
    before,
    after,
    delta_notes: [
      "Biology supply tokens moved into the first generated basket.",
      "Time delta stayed inside the next lab-cycle window.",
    ],
  };
}

export function createLocalAnonymization(): AnonymizationResponse {
  const rows = [
    { row_id: "row_001", source_label: "Solvent reorder", token: "c_solvent_acetonitrile", time_delta: 7 },
    { row_id: "row_002", source_label: "Bench gloves", token: "s_gloves_nitrile_l", time_delta: 0 },
    { row_id: "row_003", source_label: "Acid restock", token: "c_acid_tfa", time_delta: 3 },
    { row_id: "row_004", source_label: "Amber vials", token: "s_vial_amber", time_delta: 0 },
  ];

  return {
    client_id: demoClient.client_id,
    tokenized: rows.map((row) => row.token),
    time_deltas: rows.map((row) => row.time_delta),
    rows,
    audit_report: {
      row_count: 4,
      fields_hashed: ["customer_name", "contact_email", "po_number"],
      fields_scrubbed: ["ship_to_address", "billing_address"],
      detected_sensitive_fields: ["customer_name", "contact_email", "ship_to_address", "po_number"],
      k_anonymity_proxy: 12,
      privacy_notes: [
        "Direct identifiers are removed before token mapping.",
        "Dates are converted to relative time deltas for the sequence model.",
      ],
    },
  };
}

export function createLocalAuditEvents(): AuditEventsResponse {
  const timestamp = new Date().toISOString();
  return {
    events: [
      {
        event_id: "evt_local_predict",
        tool_name: "predict_next_basket",
        client_id: demoClient.client_id,
        actor: "dashboard",
        status: "success",
        latency_ms: 54,
        timestamp,
      },
      {
        event_id: "evt_local_scenarios",
        tool_name: "predict_scenarios",
        client_id: demoClient.client_id,
        actor: "dashboard",
        status: "success",
        latency_ms: 91,
        timestamp,
      },
      {
        event_id: "evt_local_anonymize",
        tool_name: "anonymize_and_tokenize_orders",
        client_id: demoClient.client_id,
        actor: "dashboard",
        status: "success",
        latency_ms: 38,
        timestamp,
      },
    ],
  };
}
