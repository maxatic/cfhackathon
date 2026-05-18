"use client";

import {
  Activity,
  AlertTriangle,
  Box,
  CheckCircle2,
  Database,
  KeyRound,
  Loader2,
  Network,
  Play,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  createLocalBeams,
  createLocalAuditEvents,
  createLocalForecast,
  createLocalModelVersions,
  createLocalRealSequence,
  createLocalRisk,
  products,
  segments,
  tenant,
} from "@/lib/demo-data";
import type {
  AnonymizationResponse,
  AuditEventsResponse,
  BeamScenario,
  ForecastRun,
  ModelVersionsResponse,
  RealSequenceResponse,
  RetrainingJob,
  RiskResponse,
} from "@/lib/types";

type ActionPanel = "risk" | "models" | "anonymization" | "retraining" | "realModel";
type LoadingAction = ActionPanel | "forecast" | "audit" | null;

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatMoney(value: number): string {
  return `$${formatNumber(Math.round(value))}`;
}

function formatPercent(value: number): string {
  return `${Number(value).toFixed(value % 1 === 0 ? 0 : 1)}%`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function postJson<T>(url: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = (await response.json().catch(() => ({}))) as { error?: string };
  if (!response.ok) {
    throw new Error(payload.error ?? `${url} returned ${response.status}`);
  }
  return payload as T;
}

function ForecastChart({ run }: { run: ForecastRun }) {
  const points = [...run.history_tail.map((item) => item.quantity), ...run.forecast.map((item) => item.predicted_quantity)];
  const min = Math.min(...points) * 0.9;
  const max = Math.max(...points) * 1.08;
  const width = 760;
  const height = 250;
  const xStep = width / Math.max(points.length - 1, 1);
  const y = (value: number) => height - ((value - min) / (max - min || 1)) * height;
  const historyPath = run.history_tail
    .map((item, index) => `${index === 0 ? "M" : "L"} ${index * xStep} ${y(item.quantity)}`)
    .join(" ");
  const forecastOffset = run.history_tail.length - 1;
  const forecastPath = [run.history_tail.at(-1)?.quantity ?? points[0], ...run.forecast.map((item) => item.predicted_quantity)]
    .map((value, index) => `${index === 0 ? "M" : "L"} ${(forecastOffset + index) * xStep} ${y(value)}`)
    .join(" ");

  return (
    <div className="chart" aria-label="Forecast chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        <defs>
          <linearGradient id="forecast-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#b8e23b" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#b8e23b" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map((line) => (
          <line
            key={line}
            x1="0"
            x2={width}
            y1={(height / 4) * line}
            y2={(height / 4) * line}
            stroke="#30352e"
            strokeWidth="1"
          />
        ))}
        <path d={`${forecastPath} L ${width} ${height} L ${forecastOffset * xStep} ${height} Z`} fill="url(#forecast-fill)" />
        <path d={historyPath} fill="none" stroke="#7ca7ff" strokeWidth="3" />
        <path d={forecastPath} fill="none" stroke="#b8e23b" strokeWidth="3" strokeDasharray="7 7" />
        {run.forecast.map((point, index) => (
          <circle
            key={point.week}
            cx={(forecastOffset + index + 1) * xStep}
            cy={y(point.predicted_quantity)}
            r="4"
            fill="#b8e23b"
          />
        ))}
      </svg>
    </div>
  );
}

function LossCurve({ job }: { job: RetrainingJob | null }) {
  if (!job) {
    return <div className="empty-state">Start retraining to see the queued job, loss curve, and model handoff.</div>;
  }
  const maxLoss = Math.max(...job.loss_curve.flatMap((point) => [point.train_loss, point.validation_loss]), 1);

  return (
    <div className="loss-curve" aria-label="Retraining loss curve">
      {job.loss_curve.map((point) => (
        <div className="loss-step" key={point.step}>
          <div className="loss-bars">
            <span
              className="loss-bar train"
              title={`train ${point.train_loss}`}
              style={{ height: `${Math.max(10, (point.train_loss / maxLoss) * 100)}%` }}
            />
            <span
              className="loss-bar validation"
              title={`validation ${point.validation_loss}`}
              style={{ height: `${Math.max(10, (point.validation_loss / maxLoss) * 100)}%` }}
            />
          </div>
          <small>{point.step}</small>
        </div>
      ))}
    </div>
  );
}

function ActionNotice({
  error,
  loading,
  message,
}: {
  error: string | null;
  loading: boolean;
  message: string;
}) {
  return (
    <div className={`action-notice ${error ? "is-error" : ""}`}>
      {loading ? (
        <Loader2 className="spin" size={16} aria-hidden="true" />
      ) : error ? (
        <AlertTriangle size={16} aria-hidden="true" />
      ) : (
        <CheckCircle2 size={16} aria-hidden="true" />
      )}
      <span>{error ?? message}</span>
    </div>
  );
}

export function Dashboard() {
  const initialRun = createLocalForecast(products[0].sku, "all", 12);
  const [sku, setSku] = useState(products[0].sku);
  const [segment, setSegment] = useState("all");
  const [horizon, setHorizon] = useState(12);
  const [run, setRun] = useState<ForecastRun>(initialRun);
  const [beams, setBeams] = useState<BeamScenario[]>(() => createLocalBeams(initialRun));
  const [risk, setRisk] = useState<RiskResponse>(() => createLocalRisk(products[0].sku, 12, 5));
  const [models, setModels] = useState<ModelVersionsResponse>(() => createLocalModelVersions());
  const [audit, setAudit] = useState<AuditEventsResponse>(() => createLocalAuditEvents());
  const [realSequence, setRealSequence] = useState<RealSequenceResponse | null>(null);
  const [anonymization, setAnonymization] = useState<AnonymizationResponse | null>(null);
  const [retraining, setRetraining] = useState<RetrainingJob | null>(null);
  const [activePanel, setActivePanel] = useState<ActionPanel>("risk");
  const [loadingAction, setLoadingAction] = useState<LoadingAction>(null);
  const [status, setStatus] = useState("Local forecast ready");
  const [error, setError] = useState<string | null>(null);
  const [panelMessage, setPanelMessage] = useState("At-risk customer workflow ready");
  const [panelError, setPanelError] = useState<string | null>(null);

  const totalUnits = useMemo(
    () => run.forecast.reduce((sum, point) => sum + point.predicted_quantity, 0),
    [run],
  );
  const revenue = useMemo(() => {
    const product = products.find((item) => item.sku === run.sku) ?? products[0];
    return totalUnits * product.unit_price;
  }, [run.sku, totalUnits]);
  const activeModel = models.model_versions.find((model) => model.status === "active") ?? models.model_versions[0];

  async function refreshAuditEvents() {
    try {
      const nextAudit = await postJson<AuditEventsResponse>("/api/audit-events", {
        tenant_id: tenant.id,
        limit: 8,
      });
      setAudit(nextAudit);
    } catch {
      setAudit((current) => current);
    }
  }

  async function runForecast() {
    setError(null);
    setLoadingAction("forecast");
    setStatus("Forecast running");
    try {
      const nextRun = await postJson<ForecastRun>("/api/forecast", {
        tenant_id: tenant.id,
        sku,
        customer_segment: segment,
        horizon_weeks: horizon,
      });
      setRun(nextRun);
      setBeams(createLocalBeams(nextRun));
      setStatus(nextRun.forecast_run_id === "local_demo" ? "Local fallback" : "MCP service");
      void refreshAuditEvents();
    } catch (caught) {
      const fallback = createLocalForecast(sku, segment, horizon);
      setRun(fallback);
      setBeams(createLocalBeams(fallback));
      setStatus("Local fallback");
      setError(caught instanceof Error ? caught.message : "Forecast failed");
    } finally {
      setLoadingAction(null);
    }
  }

  async function loadRisk() {
    setActivePanel("risk");
    setPanelError(null);
    setPanelMessage("Ranking customer downside risk");
    setLoadingAction("risk");
    try {
      const nextRisk = await postJson<RiskResponse>("/api/risk", {
        tenant_id: tenant.id,
        sku,
        horizon_weeks: horizon,
        limit: 5,
      });
      setRisk(nextRisk);
      setPanelMessage(`Ranked ${nextRisk.ranked_customers.length} customers for ${nextRisk.sku}`);
      void refreshAuditEvents();
    } catch (caught) {
      setPanelError(caught instanceof Error ? caught.message : "Risk ranking failed");
    } finally {
      setLoadingAction(null);
    }
  }

  async function loadModelVersions() {
    setActivePanel("models");
    setPanelError(null);
    setPanelMessage("Loading model versions");
    setLoadingAction("models");
    try {
      const nextModels = await postJson<ModelVersionsResponse>("/api/model-versions", {
        tenant_id: tenant.id,
      });
      setModels(nextModels);
      const activeCount = nextModels.model_versions.filter((model) => model.status === "active").length;
      setPanelMessage(`${nextModels.model_versions.length} model versions loaded, ${activeCount} active`);
      void refreshAuditEvents();
    } catch (caught) {
      setPanelError(caught instanceof Error ? caught.message : "Model version request failed");
    } finally {
      setLoadingAction(null);
    }
  }

  async function loadAnonymization() {
    setActivePanel("anonymization");
    setPanelError(null);
    setPanelMessage("Generating anonymization report");
    setLoadingAction("anonymization");
    try {
      const report = await postJson<AnonymizationResponse>("/api/anonymize", {
        tenant_id: tenant.id,
        sku,
        customer_segment: segment,
        sample_size: 8,
      });
      setAnonymization(report);
      setPanelMessage(`Anonymized ${report.anonymization.sample_size} sample rows from ${report.anonymization.source_rows} orders`);
      void refreshAuditEvents();
    } catch (caught) {
      setPanelError(caught instanceof Error ? caught.message : "Anonymization failed");
    } finally {
      setLoadingAction(null);
    }
  }

  async function runRetraining() {
    setActivePanel("retraining");
    setPanelError(null);
    setPanelMessage("Queueing retraining job");
    setLoadingAction("retraining");
    setStatus("Retraining queued");
    try {
      const queued = await postJson<RetrainingJob>("/api/retraining", {
        tenant_id: tenant.id,
        reason: `Dashboard retraining for ${sku}`,
      });
      setRetraining(queued);
      setPanelMessage(`Retraining job ${queued.job_id} is ${queued.status}`);

      let latest = queued;
      for (const pollCount of [1, 2]) {
        await sleep(650);
        latest = await postJson<RetrainingJob>("/api/retraining/status", {
          tenant_id: tenant.id,
          job_id: queued.job_id,
          poll_count: pollCount,
        });
        setRetraining(latest);
        setPanelMessage(`Retraining job ${latest.job_id} is ${latest.status}`);
      }

      if (latest.status === "completed") {
        const nextRun = await postJson<ForecastRun>("/api/forecast", {
          tenant_id: tenant.id,
          sku,
          customer_segment: segment,
          horizon_weeks: horizon,
        });
        setRun(nextRun);
        setBeams(createLocalBeams(nextRun));
        setStatus(`Retraining complete: ${latest.model_version?.version_id ?? nextRun.model_version}`);
        setPanelMessage("Retraining completed, model activated, and forecast refreshed");
        try {
          const nextModels = await postJson<ModelVersionsResponse>("/api/model-versions", {
            tenant_id: tenant.id,
          });
          setModels(nextModels);
          void refreshAuditEvents();
        } catch {
          setModels((current) => current);
        }
      }
    } catch (caught) {
      setPanelError(caught instanceof Error ? caught.message : "Retraining failed");
      setStatus("Retraining failed");
    } finally {
      setLoadingAction(null);
    }
  }

  async function runRealModel() {
    setActivePanel("realModel");
    setPanelError(null);
    setPanelMessage("Calling mounted CTO ONNX sequence model");
    setLoadingAction("realModel");
    try {
      const result = await postJson<RealSequenceResponse>("/api/real-sequence", {
        client_id: "nexus_lab_solutions",
        max_generate: 30,
        temperature: 1,
        top_k: 30,
        seed: 0,
      });
      setRealSequence(result);
      setPanelMessage(`Real model generated ${result.tokens.length} tokens for ${result.client_id}`);
      setStatus("CTO ONNX model");
    } catch (caught) {
      setPanelError(caught instanceof Error ? caught.message : "Real model request failed");
      setRealSequence(null);
      setStatus("Real model unavailable");
    } finally {
      setLoadingAction(null);
    }
  }

  function renderActionPanel() {
    if (activePanel === "realModel") {
      const sequence = realSequence ?? createLocalRealSequence();
      return (
        <div className="action-stack">
          <button className="secondary-button" onClick={runRealModel} disabled={loadingAction === "realModel"}>
            {loadingAction === "realModel" ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <Sparkles size={16} aria-hidden="true" />}
            Run CTO model
          </button>
          <div className="audit-grid real-model-grid">
            <div>
              <span>Client</span>
              <strong>{sequence.client_id}</strong>
            </div>
            <div>
              <span>Temperature</span>
              <strong>{sequence.temperature}</strong>
            </div>
            <div>
              <span>Top K</span>
              <strong>{sequence.top_k}</strong>
            </div>
            <div>
              <span>Generated tokens</span>
              <strong>{sequence.tokens.length}</strong>
            </div>
          </div>
          <div className="sequence-block">
            <h4>Start sequence</h4>
            <p>{sequence.start_sequence}</p>
          </div>
          <div className="sequence-block is-generated">
            <h4>Generated sequence</h4>
            <div className="token-list">
              {sequence.tokens.map((token, index) => (
                <span key={`${token}-${index}`}>{token}</span>
              ))}
            </div>
          </div>
          <p className="panel-copy">
            This panel calls the mounted NDA bundle through the MCP service REST bridge. If it returns a service
            error, restart the Docker container with REAL_MODEL_ARTIFACT_DIR pointing at the CTO folder.
          </p>
        </div>
      );
    }

    if (activePanel === "models") {
      return (
        <div className="version-list">
          {models.model_versions.map((model) => (
            <div className="panel-row" key={model.version_id}>
              <div>
                <div className="row-title">
                  <strong>{model.version_id}</strong>
                  <span className={`status-chip ${model.status}`}>{model.status}</span>
                </div>
                <p>{model.model_name}</p>
                {model.explanation ? <p>{model.explanation}</p> : null}
              </div>
              <div className="compact-metrics">
                <span>MAE {model.metrics.mae}</span>
                <span>SMAPE {model.metrics.smape}%</span>
                {model.adapter_multiplier ? <span>Adapter {model.adapter_multiplier}</span> : null}
              </div>
            </div>
          ))}
        </div>
      );
    }

    if (activePanel === "anonymization") {
      return (
        <div className="action-stack">
          <button className="secondary-button" onClick={loadAnonymization} disabled={loadingAction === "anonymization"}>
            {loadingAction === "anonymization" ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <ShieldCheck size={16} aria-hidden="true" />}
            Generate report
          </button>
          {anonymization ? (
            <>
              <div className="audit-grid">
                <div>
                  <span>Source rows</span>
                  <strong>{formatNumber(anonymization.anonymization.source_rows)}</strong>
                </div>
                <div>
                  <span>Sample rows</span>
                  <strong>{formatNumber(anonymization.anonymization.sample_size)}</strong>
                </div>
                <div>
                  <span>K-anonymity proxy</span>
                  <strong>{anonymization.anonymization.k_anonymity_proxy}</strong>
                </div>
                <div>
                  <span>Sensitive fields</span>
                  <strong>{anonymization.anonymization.detected_sensitive_fields.length}</strong>
                </div>
              </div>
              <div className="audit-columns">
                <div>
                  <h4>Scrubbed</h4>
                  <div className="tag-list">
                    {anonymization.anonymization.fields_scrubbed.map((field) => (
                      <span key={field}>{field}</span>
                    ))}
                  </div>
                </div>
                <div>
                  <h4>Hashed</h4>
                  <div className="tag-list">
                    {anonymization.anonymization.fields_hashed.map((field) => (
                      <span key={field}>{field}</span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="tag-list">
                {anonymization.anonymization.transformed_fields.map((field) => (
                  <span key={field}>{field}</span>
                ))}
              </div>
              <div className="table-wrap">
                <table className="compact-table">
                  <thead>
                    <tr>
                      <th>Week</th>
                      <th>Customer ref</th>
                      <th>Segment</th>
                      <th>Region</th>
                      <th>Qty</th>
                      <th>Price bucket</th>
                    </tr>
                  </thead>
                  <tbody>
                    {anonymization.anonymization.sample.slice(0, 6).map((row) => (
                      <tr key={`${row.order_date}-${row.customer_ref}`}>
                        <td>{row.order_date}</td>
                        <td>{row.customer_ref}</td>
                        <td>{row.customer_segment}</td>
                        <td>{row.region}</td>
                        <td>{formatNumber(row.quantity)}</td>
                        <td>{row.unit_price_bucket}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="empty-state">Generate a report to inspect the anonymized export sample.</div>
          )}
        </div>
      );
    }

    if (activePanel === "retraining") {
      return (
        <div className="action-stack">
          <button className="secondary-button" onClick={runRetraining} disabled={loadingAction === "retraining"}>
            {loadingAction === "retraining" ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <RefreshCcw size={16} aria-hidden="true" />}
            Trigger retraining
          </button>
          {retraining ? (
            <>
              <div className="progress-wrap">
                <div className="progress-meta">
                  <strong>{retraining.status}</strong>
                  <span>{retraining.progress_pct}%</span>
                </div>
                <div className="progress-track">
                  <span style={{ width: `${retraining.progress_pct}%` }} />
                </div>
              </div>
              <LossCurve job={retraining} />
              <div className="audit-grid">
                <div>
                  <span>Before MAE</span>
                  <strong>{retraining.before_metrics.mae}</strong>
                </div>
                <div>
                  <span>After MAE</span>
                  <strong>{retraining.after_metrics.mae}</strong>
                </div>
                <div>
                  <span>Before SMAPE</span>
                  <strong>{retraining.before_metrics.smape}%</strong>
                </div>
                <div>
                  <span>After SMAPE</span>
                  <strong>{retraining.after_metrics.smape}%</strong>
                </div>
              </div>
              <p className="panel-copy">{retraining.explanation}</p>
            </>
          ) : (
            <LossCurve job={null} />
          )}
        </div>
      );
    }

    return (
      <div className="action-stack">
        <button className="secondary-button" onClick={loadRisk} disabled={loadingAction === "risk"}>
          {loadingAction === "risk" ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <AlertTriangle size={16} aria-hidden="true" />}
          Rank risk
        </button>
        <div className="table-wrap">
          <table className="risk-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Customer</th>
                <th>Segment</th>
                <th>Region</th>
                <th>Current demand</th>
                <th>Forecast demand</th>
                <th>Downside scenario</th>
                <th>Risk</th>
                <th>Recommended action</th>
              </tr>
            </thead>
            <tbody>
              {risk.ranked_customers.map((customer) => (
                <tr key={customer.customer_ref}>
                  <td>{customer.rank}</td>
                  <td>{customer.customer_ref}</td>
                  <td>{customer.segment}</td>
                  <td>{customer.region}</td>
                  <td>
                    {formatNumber(customer.current_demand.last_4_weeks_units)} units
                    <span>{formatPercent(customer.current_demand.trend_vs_prior_4_weeks_pct)} trend</span>
                  </td>
                  <td>
                    {formatNumber(customer.forecast_demand.horizon_units)} units
                    <span>{formatNumber(Math.round(customer.forecast_demand.weekly_average))}/wk</span>
                  </td>
                  <td>
                    {customer.downside_scenario.label}
                    <span>{formatNumber(customer.downside_scenario.horizon_units)} units</span>
                  </td>
                  <td>
                    <strong className="risk-score">{Math.round(customer.risk_score)}</strong>
                    <span>{formatMoney(customer.revenue_at_risk)}</span>
                  </td>
                  <td>{customer.recommended_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <main className="app-shell">
      <aside className="side">
        <div className="brand">
          <div className="brand-mark">
            <Network size={21} aria-hidden="true" />
          </div>
          <div>
            <h1>SwiftForecast MCP</h1>
            <p>{tenant.name}</p>
          </div>
        </div>

        <div className="control">
          <label htmlFor="sku">SKU</label>
          <select id="sku" value={sku} onChange={(event) => setSku(event.target.value)}>
            {products.map((product) => (
              <option key={product.sku} value={product.sku}>
                {product.sku} - {product.name}
              </option>
            ))}
          </select>
        </div>

        <div className="control">
          <label htmlFor="segment">Segment</label>
          <select id="segment" value={segment} onChange={(event) => setSegment(event.target.value)}>
            {segments.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>

        <div className="control">
          <label htmlFor="horizon">Weeks</label>
          <input
            id="horizon"
            type="number"
            min="1"
            max="52"
            value={horizon}
            onChange={(event) => setHorizon(Number(event.target.value))}
          />
        </div>

        <button className="run-button" onClick={runForecast} disabled={loadingAction === "forecast"}>
          {loadingAction === "forecast" ? <Loader2 className="spin" size={17} aria-hidden="true" /> : <Play size={17} aria-hidden="true" />}
          Run forecast
        </button>

        <div className="icon-row" aria-label="MCP controls">
          <button className="icon-button" title="Model versions" onClick={loadModelVersions} disabled={loadingAction === "models"}>
            {loadingAction === "models" ? <Loader2 className="spin" size={18} aria-hidden="true" /> : <Box size={18} aria-hidden="true" />}
          </button>
          <button className="icon-button" title="Anonymization" onClick={loadAnonymization} disabled={loadingAction === "anonymization"}>
            {loadingAction === "anonymization" ? (
              <Loader2 className="spin" size={18} aria-hidden="true" />
            ) : (
              <ShieldCheck size={18} aria-hidden="true" />
            )}
          </button>
          <button className="icon-button" title="Retraining" onClick={runRetraining} disabled={loadingAction === "retraining"}>
            {loadingAction === "retraining" ? <Loader2 className="spin" size={18} aria-hidden="true" /> : <RefreshCcw size={18} aria-hidden="true" />}
          </button>
        </div>
      </aside>

      <section className="main">
        <div className="topbar">
          <div>
            <h2>B2B Demand Control Plane</h2>
            <p>
              Forecast run {run.forecast_run_id} is using {run.model_version} for {run.sku} across {run.horizon_weeks} weeks.
            </p>
          </div>
          <div className="status">
            <span className="status-dot" />
            {status}
          </div>
        </div>

        {error ? <div className="card metric error">{error}</div> : null}

        <section className="metrics" aria-label="Forecast metrics">
          <div className="card metric">
            <span>Forecast units</span>
            <strong>{formatNumber(totalUnits)}</strong>
          </div>
          <div className="card metric">
            <span>Projected revenue</span>
            <strong>{formatMoney(revenue)}</strong>
          </div>
          <div className="card metric">
            <span>SMAPE</span>
            <strong>{run.metrics.smape}%</strong>
          </div>
          <div className="card metric">
            <span>Active model</span>
            <strong>{activeModel?.version_id ?? run.model_version}</strong>
          </div>
        </section>

        <section className="grid">
          <div className="card">
            <div className="panel-header">
              <h3>Autoregressive forecast</h3>
              <span className="pill">
                <Sparkles size={14} aria-hidden="true" />
                greedy decode
              </span>
            </div>
            <ForecastChart run={run} />
          </div>

          <div className="card">
            <div className="panel-header">
              <h3>Beam scenarios</h3>
              <span className="pill">
                <Activity size={14} aria-hidden="true" />
                top {beams.length}
              </span>
            </div>
            <div className="beam-list">
              {beams.map((beam) => (
                <div className="beam-item" key={beam.rank}>
                  <div className="rank">{beam.rank}</div>
                  <div>
                    <h4>{beam.label}</h4>
                    <p>{formatNumber(beam.total_units)} units</p>
                  </div>
                  <span className="probability">{Math.round(beam.probability * 100)}%</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid">
          <div className="card">
            <div className="panel-header">
              <h3>Forecast table</h3>
              <span className="pill">
                <Database size={14} aria-hidden="true" />
                tenant RLS
              </span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Week</th>
                    <th>Forecast</th>
                    <th>Lower</th>
                    <th>Upper</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {run.forecast.slice(0, 8).map((point) => (
                    <tr key={point.week}>
                      <td>{point.week}</td>
                      <td>{formatNumber(point.predicted_quantity)}</td>
                      <td>{formatNumber(point.lower_bound)}</td>
                      <td>{formatNumber(point.upper_bound)}</td>
                      <td>{Math.round(point.confidence * 100)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <div className="panel-header">
              <h3>Distribution</h3>
              <span className="pill">
                <KeyRound size={14} aria-hidden="true" />
                API-key scoped
              </span>
            </div>
            <div className="event-list">
              <div className="event-item">
                <h4>MCP endpoint</h4>
                <p>{process.env.NEXT_PUBLIC_MCP_HTTP_URL ?? "http://localhost:8000/mcp"}</p>
              </div>
              <div className="event-item">
                <h4>Tenant API key</h4>
                <p>sk_northstar_forecast_full with forecast, anonymize, retrain, models, audit scopes</p>
              </div>
              <div className="event-item">
                <h4>Next tool call</h4>
                <p>erp_rank_at_risk_customers for {run.sku}</p>
              </div>
              <div className="event-item audit-log">
                <div className="row-title">
                  <h4>Recent tool calls</h4>
                  <button className="text-button" onClick={refreshAuditEvents}>Refresh</button>
                </div>
                <div className="audit-event-list">
                  {audit.events.slice(0, 5).map((event) => (
                    <div className="audit-event" key={event.event_id}>
                      <strong>{event.tool_name.replace("erp_", "")}</strong>
                      <span>{event.status} by {event.actor}</span>
                      <span>{event.latency_ms}ms</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid">
          <div className="card wide-card">
            <div className="panel-header action-header">
              <div>
                <h3>Dashboard actions</h3>
                <p>
                  {activePanel === "risk"
                    ? "At-risk customers"
                    : activePanel === "models"
                      ? "Model versions"
                      : activePanel === "anonymization"
                        ? "Anonymization report"
                        : activePanel === "retraining"
                          ? "Retraining"
                          : "CTO ONNX model"}
                </p>
              </div>
              <div className="panel-actions" aria-label="Dashboard actions">
                <button
                  className={activePanel === "risk" ? "secondary-button is-active" : "secondary-button"}
                  onClick={loadRisk}
                  disabled={loadingAction === "risk"}
                >
                  <AlertTriangle size={16} aria-hidden="true" />
                  Risk
                </button>
                <button
                  className={activePanel === "models" ? "secondary-button is-active" : "secondary-button"}
                  onClick={loadModelVersions}
                  disabled={loadingAction === "models"}
                >
                  <Box size={16} aria-hidden="true" />
                  Models
                </button>
                <button
                  className={activePanel === "anonymization" ? "secondary-button is-active" : "secondary-button"}
                  onClick={loadAnonymization}
                  disabled={loadingAction === "anonymization"}
                >
                  <ShieldCheck size={16} aria-hidden="true" />
                  Privacy
                </button>
                <button
                  className={activePanel === "retraining" ? "secondary-button is-active" : "secondary-button"}
                  onClick={runRetraining}
                  disabled={loadingAction === "retraining"}
                >
                  <RefreshCcw size={16} aria-hidden="true" />
                  Retrain
                </button>
                <button
                  className={activePanel === "realModel" ? "secondary-button is-active" : "secondary-button"}
                  onClick={runRealModel}
                  disabled={loadingAction === "realModel"}
                >
                  <Sparkles size={16} aria-hidden="true" />
                  CTO model
                </button>
              </div>
            </div>
            <div className="action-body">
              <ActionNotice error={panelError} loading={loadingAction === activePanel} message={panelMessage} />
              {renderActionPanel()}
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}
