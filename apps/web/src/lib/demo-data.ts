import type {
  AnonymizationResponse,
  AuditEventsResponse,
  BeamScenario,
  ForecastRun,
  ModelVersionsResponse,
  ProductOption,
  RetrainingJob,
  RiskResponse,
} from "./types";

export const tenant = {
  id: "tenant_northstar",
  name: "Northstar Industrial",
};

export const products: ProductOption[] = [
  { sku: "NSI-VAL-100", name: "Valves Kit 1", category: "valves", unit_price: 184 },
  { sku: "NSI-PUM-101", name: "Pumps Kit 2", category: "pumps", unit_price: 292 },
  { sku: "NSI-FIL-102", name: "Filters Kit 3", category: "filters", unit_price: 88 },
  { sku: "NSI-SEN-103", name: "Sensors Kit 4", category: "sensors", unit_price: 132 },
];

export const segments = ["all", "enterprise", "wholesale", "regional"];

const baseHistory = [612, 628, 641, 635, 660, 684, 702, 718, 694, 732, 748, 781];

function nextWeek(start: string, offset: number): string {
  const date = new Date(`${start}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + offset * 7);
  return date.toISOString().slice(0, 10);
}

function skuFactor(sku: string): number {
  const index = products.findIndex((product) => product.sku === sku);
  return [1, 1.18, 0.74, 0.92][Math.max(index, 0)] ?? 1;
}

function segmentFactor(segment: string): number {
  return {
    all: 1,
    enterprise: 1.32,
    wholesale: 0.86,
    regional: 0.58,
  }[segment] ?? 1;
}

export function createLocalForecast(sku: string, customerSegment: string, horizonWeeks: number): ForecastRun {
  const factor = skuFactor(sku) * segmentFactor(customerSegment);
  const historyTail = baseHistory.map((quantity, index) => ({
    week: nextWeek("2026-02-23", index),
    quantity: Math.round(quantity * factor),
  }));
  const last = historyTail.at(-1)?.quantity ?? 720;
  const forecast = Array.from({ length: horizonWeeks }, (_, index) => {
    const seasonal = 1 + Math.sin((index + 2) / 3) * 0.06;
    const trend = 1 + index * 0.011;
    const promotion = index % 6 === 4 ? 1.11 : 1;
    const predicted = Math.round(last * seasonal * trend * promotion);
    const spread = Math.round(predicted * (0.13 + index * 0.01));
    return {
      week: nextWeek("2026-05-18", index),
      predicted_quantity: predicted,
      lower_bound: Math.max(0, predicted - spread),
      upper_bound: predicted + spread,
      confidence: Number(Math.max(0.62, 0.91 - index * 0.018).toFixed(3)),
      drivers: {
        recent_average: Math.round(last * 0.96),
        attention_context: Math.round(last * 1.02),
        seasonal_prior: Math.round(last * seasonal),
        trend_pct: Number(((trend - 1) * 100).toFixed(2)),
        decoder: "dashboard fallback",
      },
    };
  });

  return {
    forecast_run_id: "local_demo",
    tenant_id: tenant.id,
    sku,
    customer_segment: customerSegment,
    horizon_weeks: horizonWeeks,
    model_version: "mini-transformer-v1",
    created_at: new Date().toISOString(),
    history_tail: historyTail.slice(-8),
    forecast,
    metrics: {
      mae: 18.4,
      smape: 8.7,
      holdout_weeks: 8,
    },
  };
}

export function createLocalBeams(run: ForecastRun): BeamScenario[] {
  const multipliers = [
    { label: "Base Demand", probability: 0.42, factor: 1 },
    { label: "Promotion Lift", probability: 0.27, factor: 1.18 },
    { label: "Supplier Delay", probability: 0.18, factor: 0.86 },
    { label: "Stockout Drag", probability: 0.13, factor: 0.64 },
  ];
  return multipliers.map((item, index) => {
    const quantities = run.forecast.map((point) => Math.round(point.predicted_quantity * item.factor));
    return {
      rank: index + 1,
      probability: item.probability,
      total_units: quantities.reduce((sum, quantity) => sum + quantity, 0),
      quantities,
      weeks: run.forecast.map((point) => point.week),
      label: item.label,
      explanation: `${item.label}; decoded with causal demand attention over recent weekly order tokens.`,
    };
  });
}

export function createLocalRisk(sku: string, horizonWeeks: number, limit = 5): RiskResponse {
  const product = products.find((item) => item.sku === sku) ?? products[0];
  const rows = [
    {
      customer_ref: "cust_71f25a90bc",
      segment: "enterprise",
      region: "Midwest",
      currentWeekly: 142,
      forecastFactor: 0.92,
      downsideFactor: 0.61,
      trend: -11.8,
      label: "Stockout Drag",
      probability: 0.18,
      action: "Call this customer this week, review open quotes, and protect inventory for downside demand.",
    },
    {
      customer_ref: "cust_4c0dcdb819",
      segment: "wholesale",
      region: "Southeast",
      currentWeekly: 118,
      forecastFactor: 1.01,
      downsideFactor: 0.69,
      trend: -6.5,
      label: "Supplier Delay",
      probability: 0.22,
      action: "Ask the account owner to confirm near-term orders and prepare a conservative procurement plan.",
    },
    {
      customer_ref: "cust_f69eb7c24d",
      segment: "regional",
      region: "West",
      currentWeekly: 87,
      forecastFactor: 0.96,
      downsideFactor: 0.65,
      trend: -9.2,
      label: "Lower Confidence Band",
      probability: 0.24,
      action: "Monitor declining recent demand and check whether the customer is shifting orders to a substitute SKU.",
    },
    {
      customer_ref: "cust_a2d3f15957",
      segment: "enterprise",
      region: "Northeast",
      currentWeekly: 132,
      forecastFactor: 1.08,
      downsideFactor: 0.77,
      trend: 2.4,
      label: "Supplier Delay",
      probability: 0.19,
      action: "Ask the account owner to confirm near-term orders and prepare a conservative procurement plan.",
    },
    {
      customer_ref: "cust_9187f501aa",
      segment: "regional",
      region: "Southwest",
      currentWeekly: 74,
      forecastFactor: 0.99,
      downsideFactor: 0.73,
      trend: -3.1,
      label: "Stockout Drag",
      probability: 0.13,
      action: "Monitor in the weekly demand review; no urgent intervention required.",
    },
  ];

  const ranked = rows
    .map((row) => {
      const currentHorizon = row.currentWeekly * horizonWeeks;
      const forecastUnits = Math.round(currentHorizon * row.forecastFactor);
      const downsideUnits = Math.round(currentHorizon * row.downsideFactor);
      const decline = Math.max(0, (1 - row.downsideFactor) * 100);
      const revenueAtRisk = Math.max(0, (currentHorizon - downsideUnits) * product.unit_price);
      const riskScore = Math.min(
        100,
        decline * 1.24 + Math.max(0, -row.trend) * 1.4 + Math.min(14, revenueAtRisk / 9000),
      );
      return {
        customer_ref: row.customer_ref,
        segment: row.segment,
        region: row.region,
        current_demand: {
          last_4_weeks_units: Math.round(row.currentWeekly * 4),
          weekly_average: row.currentWeekly,
          trend_vs_prior_4_weeks_pct: row.trend,
        },
        forecast_demand: {
          horizon_units: forecastUnits,
          weekly_average: Number((forecastUnits / horizonWeeks).toFixed(2)),
        },
        downside_scenario: {
          label: row.label,
          probability: row.probability,
          horizon_units: downsideUnits,
          weekly_average: Number((downsideUnits / horizonWeeks).toFixed(2)),
          decline_vs_current_run_rate_pct: Number(decline.toFixed(2)),
        },
        risk_score: Number(riskScore.toFixed(2)),
        revenue_at_risk: Math.round(revenueAtRisk),
        recommended_action: row.action,
      };
    })
    .sort((left, right) => right.risk_score - left.risk_score)
    .slice(0, limit)
    .map((row, index) => ({ rank: index + 1, ...row }));

  return {
    tenant_id: tenant.id,
    sku,
    horizon_weeks: horizonWeeks,
    limit,
    model_version: "mini-transformer-v1",
    ranked_customers: ranked,
  };
}

export function createLocalAnonymization(
  sku: string,
  customerSegment: string,
  sampleSize = 8,
): AnonymizationResponse {
  const regions = ["Midwest", "Southeast", "West", "Northeast", "Southwest"];
  const sample = Array.from({ length: sampleSize }, (_, index) => ({
    order_date: nextWeek("2026-03-30", index % 8),
    sku,
    customer_ref: `anon_${(index + 1).toString().padStart(3, "0")}`,
    customer_segment: customerSegment === "all" ? ["enterprise", "wholesale", "regional"][index % 3] : customerSegment,
    region: regions[index % regions.length],
    quantity: Math.round((76 + index * 9) * skuFactor(sku)),
    unit_price_bucket: ["$50-100", "$100-250", "$250-500"][index % 3],
    promotion: index % 5 === 0,
    stockout: index % 7 === 0,
    lead_time_days: 6 + (index % 4) * 2,
  }));

  return {
    tenant_id: tenant.id,
    sku,
    customer_segment: customerSegment,
    anonymization: {
      row_count: 384,
      source_rows: 384,
      sample_size: sample.length,
      fields_scrubbed: ["ship_to_address", "billing_address", "po_number"],
      fields_hashed: ["customer_id", "customer_name", "contact_email"],
      detected_sensitive_fields: ["customer_id", "customer_name", "contact_email", "ship_to_address", "po_number"],
      removed_fields: ["customer_id", "customer_name", "ship_to_address", "po_number"],
      transformed_fields: ["customer_ref", "unit_price_bucket", "order_week"],
      k_anonymity_proxy: 12,
      privacy_notes: [
        "Direct customer identifiers removed before export.",
        "Prices are bucketed and dates are weekly to reduce reidentification risk.",
      ],
      sample,
    },
  };
}

export function createLocalModelVersions(): ModelVersionsResponse {
  return {
    tenant_id: tenant.id,
    model_versions: [
      {
        version_id: "model_demo_seed",
        model_name: "mini-transformer-v1",
        tenant_id: tenant.id,
        trained_at: "2026-05-17T00:00:00+00:00",
        metrics: { mae: 18.4, smape: 8.7, holdout_weeks: 8 },
        status: "active",
        explanation: "Seed checkpoint trained on synthetic Northstar ERP demand.",
      },
      {
        version_id: "model_demo_baseline",
        model_name: "seasonal-naive-baseline",
        tenant_id: tenant.id,
        trained_at: "2026-05-10T00:00:00+00:00",
        metrics: { mae: 26.1, smape: 12.4, holdout_weeks: 8 },
        status: "archived",
        explanation: "Baseline retained for before and after judging comparison.",
      },
    ],
  };
}

export function createLocalRetrainingJob(
  status: RetrainingJob["status"] = "queued",
  jobId = "rt_local_demo",
): RetrainingJob {
  const lossCurve = [
    { step: 0, train_loss: 0.473, validation_loss: 0.524 },
    { step: 1, train_loss: 0.337, validation_loss: 0.376 },
    { step: 2, train_loss: 0.245, validation_loss: 0.277 },
    { step: 3, train_loss: 0.182, validation_loss: 0.209 },
    { step: 4, train_loss: 0.139, validation_loss: 0.164 },
    { step: 5, train_loss: 0.11, validation_loss: 0.133 },
  ];
  const curveSize = status === "queued" ? 1 : status === "running" ? 3 : lossCurve.length;
  const createdAt = new Date().toISOString();
  const completed = status === "completed";
  return {
    job_id: jobId,
    tenant_id: tenant.id,
    status,
    reason: "dashboard retraining trigger",
    created_at: createdAt,
    started_at: status === "queued" ? null : createdAt,
    completed_at: completed ? createdAt : null,
    progress_pct: status === "queued" ? 0 : status === "running" ? 45 : 100,
    loss_curve: lossCurve.slice(0, curveSize),
    before_metrics: { mae: 18.4, smape: 8.7, holdout_weeks: 8 },
    after_metrics: { mae: 14.35, smape: 7.13, holdout_weeks: 8 },
    explanation:
      "Tenant adapter fit on anonymized recent orders lowered the demand baseline by 10% and tightened validation error for the demo slice.",
    base_version_id: "model_demo_seed",
    model_version: completed
      ? {
          version_id: "model_local_adapter",
          model_name: "mini-transformer-v1+tenant-adapter",
          tenant_id: tenant.id,
          trained_at: createdAt,
          metrics: { mae: 14.35, smape: 7.13, holdout_weeks: 8 },
          status: "active",
          base_version_id: "model_demo_seed",
          adapter_multiplier: 0.9,
          explanation:
            "Tenant adapter fit on anonymized recent orders lowered the demand baseline by 10% and tightened validation error for the demo slice.",
        }
      : undefined,
    forecast_shift: completed
      ? {
          model_version_id: "model_local_adapter",
          adapter_multiplier: 0.9,
          explanation:
            "Tenant adapter fit on anonymized recent orders lowered the demand baseline by 10% and tightened validation error for the demo slice.",
        }
      : undefined,
  };
}

export function createLocalAuditEvents(): AuditEventsResponse {
  const timestamp = new Date().toISOString();
  return {
    tenant_id: tenant.id,
    events: [
      {
        event_id: "evt_local_risk",
        tool_name: "erp_rank_at_risk_customers",
        tenant_id: tenant.id,
        actor: "agent-northstar-demand-planner",
        key_id: "key_northstar_full",
        status: "success",
        latency_ms: 84,
        timestamp,
      },
      {
        event_id: "evt_local_forecast",
        tool_name: "erp_forecast_orders",
        tenant_id: tenant.id,
        actor: "agent-northstar-demand-planner",
        key_id: "key_northstar_full",
        status: "success",
        latency_ms: 42,
        timestamp,
      },
    ],
  };
}
