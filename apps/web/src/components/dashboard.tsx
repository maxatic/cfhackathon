"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  Fingerprint,
  GitCompare,
  Loader2,
  Network,
  Play,
  ScanSearch,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  createLocalAnonymization,
  createLocalAuditEvents,
  createLocalBasketPrediction,
  createLocalClients,
  createLocalForecastPlan,
  createLocalPersonalization,
  createLocalScenarios,
  demoClient,
  intentOptions,
  sensorTokenOptions,
} from "@/lib/demo-data";
import type {
  AnonymizationResponse,
  AuditEventsResponse,
  BasketPrediction,
  ClientListResponse,
  ForecastPlanResponse,
  PersonalizationResponse,
  ResponseSource,
  ScenarioResponse,
  ScenarioTrajectory,
} from "@/lib/types";

type ActionPanel = "plan" | "personalize" | "anonymize" | "audit";
type LoadingAction = ActionPanel | "predict" | "scenarios" | null;
type StatusTone = "live" | "fallback" | "working" | "error";
type RuntimeStatus = {
  label: string;
  tone: StatusTone;
};

function formatDelta(days: number): string {
  if (days === 0) {
    return "same basket";
  }
  return `${days}d later`;
}

function formatLogProb(value: number): string {
  return value.toFixed(1);
}

function statusFromSource(source: ResponseSource | undefined, liveLabel: string): RuntimeStatus {
  if (source === "live_mcp") {
    return { label: liveLabel, tone: "live" };
  }

  return { label: "Local fallback active", tone: "fallback" };
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

function groupTokens(tokens: string[], deltas: number[]) {
  return tokens.reduce<Array<{ label: string; tokens: string[] }>>((groups, token, index) => {
    const delta = deltas[index] ?? 0;
    if (index === 0 || delta > 0 || groups.length === 0) {
      groups.push({ label: formatDelta(delta), tokens: [token] });
      return groups;
    }
    groups[groups.length - 1]?.tokens.push(token);
    return groups;
  }, []);
}

function TokenGroups({ tokens, deltas }: { tokens: string[]; deltas: number[] }) {
  const groups = groupTokens(tokens, deltas);

  return (
    <div className="timeline">
      {groups.map((group, index) => (
        <div className="timeline-group" key={`${group.label}-${index}`}>
          <span>{group.label}</span>
          <div className="token-list">
            {group.tokens.map((token, tokenIndex) => (
              <code key={`${token}-${tokenIndex}`}>{token}</code>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ScenarioCard({ scenario }: { scenario: ScenarioTrajectory }) {
  return (
    <article className="scenario-card">
      <div className="scenario-rank">#{scenario.rank}</div>
      <div>
        <span>joint log-prob</span>
        <strong>{formatLogProb(scenario.joint_log_prob)}</strong>
      </div>
      <TokenGroups tokens={scenario.tokens} deltas={scenario.time_deltas} />
    </article>
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
  const [clientId] = useState(demoClient.client_id);
  const [intent, setIntent] = useState(intentOptions[0]);
  const [maxGenerate, setMaxGenerate] = useState(8);
  const [topK, setTopK] = useState(5);
  const [temperature, setTemperature] = useState(1);
  const [beamWidth, setBeamWidth] = useState(3);
  const [horizon, setHorizon] = useState(8);
  const [selectedSensorTokens, setSelectedSensorTokens] = useState<string[]>(sensorTokenOptions.slice(0, 2));
  const [prediction, setPrediction] = useState<BasketPrediction>(() => createLocalBasketPrediction());
  const [scenarios, setScenarios] = useState<ScenarioResponse>(() => createLocalScenarios());
  const [plan, setPlan] = useState<ForecastPlanResponse>(() => createLocalForecastPlan(intentOptions[0]));
  const [personalization, setPersonalization] = useState<PersonalizationResponse>(() => createLocalPersonalization());
  const [anonymization, setAnonymization] = useState<AnonymizationResponse>(() => createLocalAnonymization());
  const [audit, setAudit] = useState<AuditEventsResponse>(() => createLocalAuditEvents());
  const [clients, setClients] = useState<ClientListResponse>(() => createLocalClients());
  const [activePanel, setActivePanel] = useState<ActionPanel>("plan");
  const [loadingAction, setLoadingAction] = useState<LoadingAction>(null);
  const [status, setStatus] = useState<RuntimeStatus>({
    label: "Local fallback active",
    tone: "fallback",
  });
  const [error, setError] = useState<string | null>(null);
  const [panelMessage, setPanelMessage] = useState("Forecast plan ready");
  const [panelError, setPanelError] = useState<string | null>(null);

  const generatedProductCount = useMemo(
    () => prediction.generated_tokens.filter((token) => !token.startsWith("<dt_")).length,
    [prediction.generated_tokens],
  );
  const bestScenario = scenarios.scenarios[0];
  const activeClient = clients.clients.find((client) => client.client_id === clientId) ?? demoClient;

  useEffect(() => {
    let ignore = false;

    async function loadClients() {
      try {
        const response = await fetch("/api/clients", { method: "GET" });
        const payload = (await response.json().catch(() => ({}))) as ClientListResponse & { error?: string };
        if (!response.ok) {
          throw new Error(payload.error ?? `Client list returned ${response.status}`);
        }
        if (!ignore) {
          setClients(payload);
          setStatus(statusFromSource(payload.response_source, "Live MCP connected"));
        }
      } catch {
        if (!ignore) {
          setClients(createLocalClients());
          setStatus({ label: "Local fallback active", tone: "fallback" });
        }
      }
    }

    void loadClients();
    return () => {
      ignore = true;
    };
  }, []);

  async function refreshAuditEvents() {
    setLoadingAction("audit");
    try {
      const nextAudit = await postJson<AuditEventsResponse>("/api/audit", {
        client_id: clientId,
        limit: 8,
      });
      setAudit(nextAudit);
      setStatus(statusFromSource(nextAudit.response_source, "Live MCP audit loaded"));
    } catch {
      setAudit((current) => current);
    } finally {
      setLoadingAction(null);
    }
  }

  async function runPrediction() {
    setError(null);
    setLoadingAction("predict");
    setStatus({ label: "Calling predict_next_basket", tone: "working" });
    try {
      const result = await postJson<BasketPrediction>("/api/predict", {
        client_id: clientId,
        max_generate: maxGenerate,
        top_k: topK,
        temperature,
        seed: 42,
      });
      setPrediction(result);
      setStatus(statusFromSource(result.response_source, "Live MCP prediction ready"));
      void refreshAuditEvents();
    } catch (caught) {
      setPrediction(createLocalBasketPrediction());
      setStatus({ label: "Local fallback active", tone: "fallback" });
      setError(caught instanceof Error ? caught.message : "Prediction failed");
    } finally {
      setLoadingAction(null);
    }
  }

  async function runScenarios() {
    setError(null);
    setLoadingAction("scenarios");
    setStatus({ label: "Calling predict_scenarios", tone: "working" });
    try {
      const result = await postJson<ScenarioResponse>("/api/scenarios", {
        client_id: clientId,
        beam_width: beamWidth,
        horizon,
        temperature,
      });
      setScenarios(result);
      setStatus(statusFromSource(result.response_source, `Live MCP: ${result.scenarios.length} scenarios ready`));
      void refreshAuditEvents();
    } catch (caught) {
      setScenarios(createLocalScenarios());
      setStatus({ label: "Local fallback active", tone: "fallback" });
      setError(caught instanceof Error ? caught.message : "Scenario request failed");
    } finally {
      setLoadingAction(null);
    }
  }

  async function runForecastPlan() {
    setActivePanel("plan");
    setPanelError(null);
    setPanelMessage("Calling forecast_plan");
    setLoadingAction("plan");
    try {
      const result = await postJson<ForecastPlanResponse>("/api/forecast-plan", {
        client_id: clientId,
        intent,
      });
      setPlan(result);
      setPrediction(result.predicted_basket);
      setScenarios({
        client_id: result.client_id,
        model_version: result.predicted_basket.model_version,
        scenarios: result.scenarios,
        response_source: result.response_source,
      });
      setPanelMessage(`Strategy selected: ${result.selected_strategy}`);
      setStatus(statusFromSource(result.response_source, "Live MCP plan ready"));
      void refreshAuditEvents();
    } catch (caught) {
      setPanelError(caught instanceof Error ? caught.message : "Forecast plan failed");
      setStatus({ label: "MCP request failed", tone: "error" });
    } finally {
      setLoadingAction(null);
    }
  }

  async function runPersonalization() {
    setActivePanel("personalize");
    setPanelError(null);
    setPanelMessage("Calling personalize_client");
    setLoadingAction("personalize");
    try {
      const result = await postJson<PersonalizationResponse>("/api/personalize", {
        client_id: clientId,
        additional_tokens: selectedSensorTokens,
      });
      setPersonalization(result);
      setPrediction(result.after);
      setPanelMessage(`Session ${result.session_id} updated`);
      setStatus(statusFromSource(result.response_source, "Live MCP sensor profile applied"));
      void refreshAuditEvents();
    } catch (caught) {
      setPanelError(caught instanceof Error ? caught.message : "Personalization failed");
      setStatus({ label: "MCP request failed", tone: "error" });
    } finally {
      setLoadingAction(null);
    }
  }

  async function runAnonymization() {
    setActivePanel("anonymize");
    setPanelError(null);
    setPanelMessage("Calling anonymize_and_tokenize_orders");
    setLoadingAction("anonymize");
    try {
      const result = await postJson<AnonymizationResponse>("/api/anonymize", {
        client_id: clientId,
        raw_rows: [],
      });
      setAnonymization(result);
      setPanelMessage(`${result.audit_report.row_count} rows tokenized`);
      setStatus(statusFromSource(result.response_source, "Live MCP token audit ready"));
      void refreshAuditEvents();
    } catch (caught) {
      setPanelError(caught instanceof Error ? caught.message : "Anonymization failed");
      setStatus({ label: "MCP request failed", tone: "error" });
    } finally {
      setLoadingAction(null);
    }
  }

  function toggleSensorToken(token: string) {
    setSelectedSensorTokens((current) =>
      current.includes(token) ? current.filter((item) => item !== token) : [...current, token],
    );
  }

  function renderActionPanel() {
    if (activePanel === "personalize") {
      return (
        <div className="action-stack">
          <div className="tag-list">
            {sensorTokenOptions.map((token) => (
              <button
                className={selectedSensorTokens.includes(token) ? "tag-button is-active" : "tag-button"}
                key={token}
                onClick={() => toggleSensorToken(token)}
                type="button"
              >
                {token}
              </button>
            ))}
          </div>
          <button className="secondary-button" onClick={runPersonalization} disabled={loadingAction === "personalize"}>
            {loadingAction === "personalize" ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <GitCompare size={16} aria-hidden="true" />}
            Apply sensor profile
          </button>
          <div className="compare-grid">
            <div>
              <h4>Before</h4>
              <TokenGroups tokens={personalization.before.generated_tokens} deltas={personalization.before.generated_times} />
            </div>
            <div>
              <h4>After</h4>
              <TokenGroups tokens={personalization.after.generated_tokens} deltas={personalization.after.generated_times} />
            </div>
          </div>
          <div className="event-list compact">
            {personalization.delta_notes.map((note) => (
              <div className="event-item" key={note}>
                <p>{note}</p>
              </div>
            ))}
          </div>
        </div>
      );
    }

    if (activePanel === "anonymize") {
      return (
        <div className="action-stack">
          <button className="secondary-button" onClick={runAnonymization} disabled={loadingAction === "anonymize"}>
            {loadingAction === "anonymize" ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <ShieldCheck size={16} aria-hidden="true" />}
            Run privacy audit
          </button>
          <div className="audit-grid">
            <div>
              <span>Rows</span>
              <strong>{anonymization.audit_report.row_count}</strong>
            </div>
            <div>
              <span>K-anonymity proxy</span>
              <strong>{anonymization.audit_report.k_anonymity_proxy}</strong>
            </div>
            <div>
              <span>Hashed fields</span>
              <strong>{anonymization.audit_report.fields_hashed.length}</strong>
            </div>
            <div>
              <span>Scrubbed fields</span>
              <strong>{anonymization.audit_report.fields_scrubbed.length}</strong>
            </div>
          </div>
          <div className="audit-columns">
            <div>
              <h4>Scrubbed</h4>
              <div className="tag-list">
                {anonymization.audit_report.fields_scrubbed.map((field) => (
                  <span key={field}>{field}</span>
                ))}
              </div>
            </div>
            <div>
              <h4>Hashed</h4>
              <div className="tag-list">
                {anonymization.audit_report.fields_hashed.map((field) => (
                  <span key={field}>{field}</span>
                ))}
              </div>
            </div>
          </div>
          <div className="table-wrap">
            <table className="compact-table">
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Source label</th>
                  <th>Token</th>
                  <th>Time delta</th>
                </tr>
              </thead>
              <tbody>
                {anonymization.rows.map((row) => (
                  <tr key={row.row_id}>
                    <td>{row.row_id}</td>
                    <td>{row.source_label}</td>
                    <td>{row.token}</td>
                    <td>{formatDelta(row.time_delta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      );
    }

    if (activePanel === "audit") {
      return (
        <div className="action-stack">
          <button className="secondary-button" onClick={refreshAuditEvents} disabled={loadingAction === "audit"}>
            <Activity size={16} aria-hidden="true" />
            Refresh audit
          </button>
          <div className="audit-event-list">
            {audit.events.map((event) => (
              <div className="audit-event" key={event.event_id}>
                <strong>{event.tool_name}</strong>
                <span>{event.status} by {event.actor}</span>
                <span>{event.latency_ms}ms</span>
              </div>
            ))}
          </div>
        </div>
      );
    }

    return (
      <div className="action-stack">
        <div className="control inline-control">
          <label htmlFor="intent">Intent</label>
          <select id="intent" value={intent} onChange={(event) => setIntent(event.target.value)}>
            {intentOptions.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
        <button className="secondary-button" onClick={runForecastPlan} disabled={loadingAction === "plan"}>
          {loadingAction === "plan" ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <SlidersHorizontal size={16} aria-hidden="true" />}
          Ask forecast planner
        </button>
        <div className="plan-summary">
          <span>{plan.selected_strategy}</span>
          <p>{plan.recommendation_summary}</p>
        </div>
        <div className="scenario-grid">
          {plan.scenarios.slice(0, 3).map((scenario) => (
            <ScenarioCard key={scenario.rank} scenario={scenario} />
          ))}
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
            <h1>Swiftron MCP</h1>
            <p>{demoClient.display_name}</p>
          </div>
        </div>

        <div className="control">
          <label htmlFor="client">Client</label>
          <select id="client" value={clientId} disabled>
            {clients.clients.map((client) => (
              <option key={client.client_id} value={client.client_id}>
                {client.client_id}
              </option>
            ))}
          </select>
        </div>

        <div className="control-grid">
          <div className="control">
            <label htmlFor="max-generate">Tokens</label>
            <input
              id="max-generate"
              type="number"
              min="1"
              max="80"
              value={maxGenerate}
              onChange={(event) => setMaxGenerate(Number(event.target.value))}
            />
          </div>
          <div className="control">
            <label htmlFor="top-k">Top K</label>
            <input
              id="top-k"
              type="number"
              min="1"
              max="100"
              value={topK}
              onChange={(event) => setTopK(Number(event.target.value))}
            />
          </div>
        </div>

        <div className="control">
          <label htmlFor="temperature">Temperature: {temperature.toFixed(1)}</label>
          <input
            id="temperature"
            type="range"
            min="0.1"
            max="2"
            step="0.1"
            value={temperature}
            onChange={(event) => setTemperature(Number(event.target.value))}
          />
        </div>

        <div className="control-grid">
          <div className="control">
            <label htmlFor="beam-width">Beams</label>
            <input
              id="beam-width"
              type="number"
              min="1"
              max="8"
              value={beamWidth}
              onChange={(event) => setBeamWidth(Number(event.target.value))}
            />
          </div>
          <div className="control">
            <label htmlFor="horizon">Horizon</label>
            <input
              id="horizon"
              type="number"
              min="1"
              max="32"
              value={horizon}
              onChange={(event) => setHorizon(Number(event.target.value))}
            />
          </div>
        </div>

        <button className="run-button" onClick={runPrediction} disabled={loadingAction === "predict"}>
          {loadingAction === "predict" ? <Loader2 className="spin" size={17} aria-hidden="true" /> : <Play size={17} aria-hidden="true" />}
          Predict basket
        </button>

        <div className="icon-row" aria-label="MCP controls">
          <button className="icon-button" title="Scenarios" onClick={runScenarios} disabled={loadingAction === "scenarios"}>
            {loadingAction === "scenarios" ? <Loader2 className="spin" size={18} aria-hidden="true" /> : <ScanSearch size={18} aria-hidden="true" />}
          </button>
          <button className="icon-button" title="Personalize" onClick={runPersonalization} disabled={loadingAction === "personalize"}>
            {loadingAction === "personalize" ? <Loader2 className="spin" size={18} aria-hidden="true" /> : <Fingerprint size={18} aria-hidden="true" />}
          </button>
          <button className="icon-button" title="Privacy audit" onClick={runAnonymization} disabled={loadingAction === "anonymize"}>
            {loadingAction === "anonymize" ? <Loader2 className="spin" size={18} aria-hidden="true" /> : <ShieldCheck size={18} aria-hidden="true" />}
          </button>
        </div>
      </aside>

      <section className="main">
        <div className="topbar">
          <div>
            <h2>Vendor-side B2B order forecast</h2>
            <p>
              Plan the next NexusLab Solutions order basket, compare ranked futures, and verify privacy handling before order rows become model tokens.
            </p>
          </div>
          <div className={`status ${status.tone}`}>
            <span className="status-dot" />
            {status.label}
          </div>
        </div>

        {error ? <div className="card metric error">{error}</div> : null}

        <section className="metrics" aria-label="Prediction summary">
          <div className="card metric">
            <span>Client</span>
            <strong>{activeClient.display_name}</strong>
          </div>
          <div className="card metric">
            <span>Generated products</span>
            <strong>{generatedProductCount}</strong>
          </div>
          <div className="card metric">
            <span>Best scenario</span>
            <strong>{bestScenario ? `#${bestScenario.rank}` : "none"}</strong>
          </div>
          <div className="card metric">
            <span>Model</span>
            <strong>{prediction.model_version}</strong>
          </div>
        </section>

        <section className="grid">
          <div className="card">
            <div className="panel-header">
              <h3>Client directory</h3>
              <span className="pill">
                <Database size={14} aria-hidden="true" />
                list_clients
              </span>
            </div>
            <div className="event-list">
              {clients.clients.map((client) => (
                <div className="event-item" key={client.client_id}>
                  <div className="row-title">
                    <h4>{client.display_name}</h4>
                    <span className={`status-chip ${client.status}`}>{client.status}</span>
                  </div>
                  <p>{client.client_id}</p>
                  <p>{client.domain}, last order week {client.last_order_week}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="panel-header">
              <h3>Tool coverage</h3>
              <span className="pill">
                <CheckCircle2 size={14} aria-hidden="true" />
                locked surface
              </span>
            </div>
            <div className="tool-grid">
              {[
                "predict_next_basket",
                "predict_scenarios",
                "forecast_plan",
                "personalize_client",
                "anonymize_and_tokenize_orders",
                "list_clients",
                "list_audit_events",
              ].map((tool) => (
                <div className="tool-chip" key={tool}>
                  <CheckCircle2 size={14} aria-hidden="true" />
                  <span>{tool}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid">
          <div className="card">
            <div className="panel-header">
              <h3>Basket sequence</h3>
              <span className="pill">
                <Database size={14} aria-hidden="true" />
                predict_next_basket
              </span>
            </div>
            <div className="sequence-panel">
              <h4>Start sequence</h4>
              <TokenGroups tokens={prediction.start_sequence} deltas={prediction.start_sequence.map(() => 0)} />
              <h4>Generated basket</h4>
              <TokenGroups tokens={prediction.generated_tokens} deltas={prediction.generated_times} />
            </div>
          </div>

          <div className="card">
            <div className="panel-header">
              <h3>Decoder settings</h3>
              <span className="pill">
                <SlidersHorizontal size={14} aria-hidden="true" />
                {prediction.decoder_config.strategy}
              </span>
            </div>
            <div className="event-list">
              {Object.entries(prediction.decoder_config).map(([key, value]) => (
                <div className="event-item" key={key}>
                  <h4>{key}</h4>
                  <p>{String(value)}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid">
          <div className="card wide-card">
            <div className="panel-header">
              <h3>Scenario comparison</h3>
              <span className="pill">
                <Activity size={14} aria-hidden="true" />
                {beamWidth} beams
              </span>
            </div>
            <div className="scenario-grid">
              {scenarios.scenarios.slice(0, 3).map((scenario) => (
                <ScenarioCard key={scenario.rank} scenario={scenario} />
              ))}
            </div>
            <div className="table-wrap scenario-table">
              <table>
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Joint log-prob</th>
                    <th>First token</th>
                    <th>Time delta</th>
                    <th>Token count</th>
                  </tr>
                </thead>
                <tbody>
                  {scenarios.scenarios.map((scenario) => (
                    <tr key={scenario.rank}>
                      <td>{scenario.rank}</td>
                      <td>{formatLogProb(scenario.joint_log_prob)}</td>
                      <td>{scenario.tokens[0] ?? "none"}</td>
                      <td>{formatDelta(scenario.time_deltas[0] ?? 0)}</td>
                      <td>{scenario.tokens.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section className="grid">
          <div className="card wide-card">
            <div className="panel-header action-header">
              <div>
                <h3>Dashboard actions</h3>
                <p>
                  {activePanel === "plan"
                    ? "Forecast planner"
                    : activePanel === "personalize"
                      ? "Sensor profile"
                      : activePanel === "anonymize"
                        ? "Privacy and token mapping"
                        : "Tool audit"}
                </p>
              </div>
              <div className="panel-actions" aria-label="Dashboard actions">
                <button
                  className={activePanel === "plan" ? "secondary-button is-active" : "secondary-button"}
                  onClick={runForecastPlan}
                  disabled={loadingAction === "plan"}
                >
                  <SlidersHorizontal size={16} aria-hidden="true" />
                  Plan
                </button>
                <button
                  className={activePanel === "personalize" ? "secondary-button is-active" : "secondary-button"}
                  onClick={runPersonalization}
                  disabled={loadingAction === "personalize"}
                >
                  <Fingerprint size={16} aria-hidden="true" />
                  Personalize
                </button>
                <button
                  className={activePanel === "anonymize" ? "secondary-button is-active" : "secondary-button"}
                  onClick={runAnonymization}
                  disabled={loadingAction === "anonymize"}
                >
                  <ShieldCheck size={16} aria-hidden="true" />
                  Privacy
                </button>
                <button
                  className={activePanel === "audit" ? "secondary-button is-active" : "secondary-button"}
                  onClick={() => {
                    setActivePanel("audit");
                    void refreshAuditEvents();
                  }}
                >
                  <Activity size={16} aria-hidden="true" />
                  Audit
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
