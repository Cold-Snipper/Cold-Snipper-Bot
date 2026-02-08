"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type RunStatus = "idle" | "starting" | "running" | "stopped" | "error";
type LogLine = { type: string; data: string };

const PIPELINE_STEPS = [
  { id: 1, name: "Config", short: "Load config & URLs" },
  { id: 2, name: "Browser", short: "Playwright init" },
  { id: 3, name: "Scroll", short: "Navigate & scroll" },
  { id: 4, name: "Extract", short: "Listings from page" },
  { id: 5, name: "Dedup", short: "Skip seen" },
  { id: 6, name: "Classify", short: "Eligible + private/agent" },
  { id: 7, name: "Contact", short: "Send or log" },
  { id: 8, name: "Cooldown", short: "Then next cycle" },
];

type Stage = { id: number; name: string; inputs: string; outputs: string; status: string };
const STAGES: Stage[] = [
  { id: 1, name: "Setup & source selection", inputs: "config_path, --setup", outputs: "source_type, phase2 URLs in config", status: "Working" },
  { id: 2, name: "Config & phase2 URLs", inputs: "config.yaml (source_type, websites, facebook)", outputs: "start_urls derived, limits defaults", status: "Working" },
  { id: 3, name: "URLs & browser", inputs: "start_urls from config", outputs: "Playwright page, graceful close on SIGINT", status: "Working" },
  { id: 4, name: "Deduplication", inputs: "listing text, db_path, session set", outputs: "skip if seen (DB or session)", status: "Working" },
  { id: 5, name: "Confidence & agent extraction", inputs: "text, config (min_confidence)", outputs: "is_private, agent_details, verify_qualifies", status: "Working" },
  { id: 6, name: "Airbnb gate", inputs: "viability rating, airbnb_min_rating", outputs: "contact only if viable", status: "Working" },
  { id: 7, name: "Contacting (send_all)", inputs: "contacts, message, config (dry_run)", outputs: "email sent / dry-run, log_contact", status: "Working" },
  { id: 8, name: "Logging DB", inputs: "config.database", outputs: "lead_logs, agent_logs in one DB", status: "Working" },
  { id: 9, name: "Cooldown & shutdown", inputs: "cycle_cooldown_seconds, rate limit", outputs: "sleep between cycles, close_browser on exit", status: "Working" },
  { id: 10, name: "Dashboard", inputs: "Config, leads, agents, logs APIs", outputs: "Run, monitor, Test & build", status: "Working" },
];

export default function Home() {
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [liveLog, setLiveLog] = useState<LogLine[]>([]);
  const [dryRun, setDryRun] = useState(true);
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [leads, setLeads] = useState<unknown[]>([]);
  const [agents, setAgents] = useState<unknown[]>([]);
  const [logs, setLogs] = useState<unknown[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [fbSource, setFbSource] = useState<"marketplace" | "groups">("marketplace");
  const [fbCity, setFbCity] = useState("");
  const [fbRadius, setFbRadius] = useState("");
  const [fbGroupUrls, setFbGroupUrls] = useState("");
  const [fbKeywords, setFbKeywords] = useState("");
  const [fbConfigSaved, setFbConfigSaved] = useState(false);
  const [targetsData, setTargetsData] = useState<{
    countries: string[];
    sitesByCountry: Record<string, { id: string; label: string; baseUrl: string; listingTypes?: { value: string; label: string; path: string }[] }[]>;
    defaultListingTypes?: { value: string; label: string; path: string }[];
  } | null>(null);
  const [webCountry, setWebCountry] = useState("");
  const [webSiteId, setWebSiteId] = useState("");
  const [webListingPath, setWebListingPath] = useState("");
  const [webConfigSaved, setWebConfigSaved] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    fetch("/api/targets")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setTargetsData(data ?? null))
      .catch(() => setTargetsData(null));
  }, []);

  const fetchData = useCallback(async () => {
    setError(null);
    try {
      const [configRes, leadsRes, agentsRes, logsRes] = await Promise.all([
        fetch("/api/config"),
        fetch("/api/leads"),
        fetch("/api/agents"),
        fetch("/api/logs"),
      ]);
      if (configRes.ok) setConfig(await configRes.json());
      else setConfig(null);
      if (leadsRes.ok) setLeads(await leadsRes.json());
      else setLeads([]);
      if (agentsRes.ok) setAgents(await agentsRes.json());
      else setAgents([]);
      if (logsRes.ok) setLogs(await logsRes.json());
      else setLogs([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [liveLog]);

  const startBot = async () => {
    if (runStatus === "running" || runStatus === "starting") return;
    setRunStatus("starting");
    setLiveLog([]);
    abortRef.current = new AbortController();
    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dryRun }),
        signal: abortRef.current.signal,
      });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        setLiveLog((prev) => [...prev, { type: "stderr", data: err.error || "Failed to start" }]);
        setRunStatus("error");
        return;
      }
      setRunStatus("running");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let exited = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const obj = JSON.parse(line) as LogLine;
            setLiveLog((prev) => [...prev, obj]);
            if (obj.type === "exit") {
              exited = true;
              setRunStatus("stopped");
            }
          } catch {
            setLiveLog((prev) => [...prev, { type: "stdout", data: line }]);
          }
        }
      }
      if (!exited) setRunStatus("stopped");
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setLiveLog((prev) => [...prev, { type: "stderr", data: String(e) }]);
      setRunStatus("error");
    } finally {
      abortRef.current = null;
    }
  };

  const stopBot = async () => {
    try {
      await fetch("/api/run", { method: "DELETE" });
      setRunStatus("stopped");
    } catch {
      setRunStatus("stopped");
    }
  };

  const runStreamingJob = async (
    url: string,
    jobLabel: string
  ) => {
    setRunStatus("starting");
    setLiveLog([{ type: "status", data: `${jobLabel}…` }]);
    const abort = new AbortController();
    try {
      const res = await fetch(url, { method: "POST", signal: abort.signal });
      if (!res.ok || !res.body) {
        setLiveLog((prev) => [...prev, { type: "stderr", data: "Request failed" }]);
        setRunStatus("error");
        return;
      }
      setRunStatus("running");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let exited = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const obj = JSON.parse(line) as LogLine;
            setLiveLog((prev) => [...prev, obj]);
            if (obj.type === "exit") {
              exited = true;
              setRunStatus("stopped");
            }
          } catch {
            setLiveLog((prev) => [...prev, { type: "stdout", data: line }]);
          }
        }
      }
      if (!exited) setRunStatus("stopped");
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setLiveLog((prev) => [...prev, { type: "stderr", data: String(e) }]);
      setRunStatus("error");
    }
  };

  const runTests = () => runStreamingJob("/api/test", "Running tests");
  const runBuild = () => runStreamingJob("/api/build", "Building dashboard");

  function buildFbStartUrls(): string[] {
    if (fbSource === "marketplace") {
      const city = (fbCity || "miami").trim().toLowerCase().replace(/\s+/g, "");
      let url = `https://www.facebook.com/marketplace/${city}/propertyforsale`;
      const params = new URLSearchParams();
      if (fbKeywords.trim()) params.set("query", fbKeywords.trim());
      if (fbRadius.trim()) params.set("radius", String(Number(fbRadius) || 25));
      const qs = params.toString();
      if (qs) url += "?" + qs;
      return [url];
    }
    return fbGroupUrls
      .split("\n")
      .map((u) => u.trim())
      .filter(Boolean);
  }

  async function updateConfigAndStartScan() {
    const urls = buildFbStartUrls();
    if (urls.length === 0) {
      setLiveLog((prev) => [...prev, { type: "stderr", data: "Enter city (Marketplace) or group URLs (Groups)." }]);
      return;
    }
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_type: "facebook",
          start_urls: urls,
          facebook:
            fbSource === "marketplace"
              ? { marketplace_enabled: true, marketplace_url_template: urls[0] }
              : { groups: { group_urls: urls } },
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setLiveLog((prev) => [...prev, { type: "stderr", data: (err as { error?: string }).error || "Failed to update config" }]);
        return;
      }
      setFbConfigSaved(true);
      setLiveLog((prev) => [...prev, { type: "stdout", data: "Config updated with: " + urls.join(", ") }]);
      await startBot();
    } catch (e) {
      setLiveLog((prev) => [...prev, { type: "stderr", data: String(e) }]);
    }
  }

  const webSites = (webCountry && targetsData?.sitesByCountry?.[webCountry]) || [];
  const webSite = webSites.find((s) => s.id === webSiteId);
  const webListingTypes = webSite?.listingTypes ?? targetsData?.defaultListingTypes ?? [];
  const webStartUrl = webSite
    ? webSite.baseUrl.replace(/\/$/, "") + (webListingPath || "")
    : "";

  async function updateConfigAndStartWebsiteScan() {
    if (!webStartUrl) {
      setLiveLog((prev) => [...prev, { type: "stderr", data: "Select country, site and listing type." }]);
      return;
    }
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_type: "website",
          start_urls: [webStartUrl],
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setLiveLog((prev) => [...prev, { type: "stderr", data: (err as { error?: string }).error || "Failed to update config" }]);
        return;
      }
      setWebConfigSaved(true);
      setLiveLog((prev) => [...prev, { type: "stdout", data: "Config updated with: " + webStartUrl }]);
      await startBot();
    } catch (e) {
      setLiveLog((prev) => [...prev, { type: "stderr", data: String(e) }]);
    }
  }

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-white px-4 py-3 shadow-sm">
        <h1 className="text-xl font-semibold tracking-tight">Cold Bot</h1>
        <p className="text-xs text-stone-500">Run · Monitor · Leads & agents</p>
        <nav className="mt-2 flex gap-2">
          <a href="#run" className="text-xs font-medium text-stone-600 hover:text-stone-900">Run</a>
          <a href="#website" className="text-xs font-medium text-stone-600 hover:text-stone-900">Website scan</a>
          <a href="#facebook" className="text-xs font-medium text-stone-600 hover:text-stone-900">Facebook scan</a>
          <a href="#stages" className="text-xs font-medium text-stone-600 hover:text-stone-900">Stages</a>
          <a href="#test" className="text-xs font-medium text-stone-600 hover:text-stone-900">Test & build</a>
        </nav>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-6">
        {error && (
          <div className="mb-4 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {error}
          </div>
        )}

        {/* Run controls + live monitor */}
        <section id="run" className="mb-6 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking text-stone-500">
            Run & live monitor
          </h2>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                disabled={runStatus === "running" || runStatus === "starting"}
                className="rounded border-stone-300"
              />
              Dry run (no emails)
            </label>
            <button
              type="button"
              onClick={startBot}
              disabled={runStatus === "running" || runStatus === "starting"}
              className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {runStatus === "running" || runStatus === "starting" ? "Running…" : "Start bot"}
            </button>
            <button
              type="button"
              onClick={stopBot}
              disabled={runStatus !== "running"}
              className="rounded border border-stone-300 bg-white px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50 disabled:opacity-50"
            >
              Stop
            </button>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                runStatus === "running"
                  ? "bg-emerald-100 text-emerald-800"
                  : runStatus === "starting"
                    ? "bg-amber-100 text-amber-800"
                    : runStatus === "error"
                      ? "bg-red-100 text-red-800"
                      : "bg-stone-100 text-stone-600"
              }`}
            >
              {runStatus}
            </span>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-900 p-3 font-mono text-xs text-stone-100">
            <div className="mb-1 text-stone-400">Process output (live)</div>
            <div className="max-h-64 overflow-auto whitespace-pre-wrap break-words">
              {liveLog.length === 0 && runStatus === "idle" && (
                <span className="text-stone-500">Start the bot to see output here.</span>
              )}
              {liveLog.map((line, i) => (
                <div
                  key={i}
                  className={
                    line.type === "stderr"
                      ? "text-red-300"
                      : line.type === "exit"
                        ? "text-amber-300"
                        : ""
                  }
                >
                  {line.data}
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        </section>

        {/* Website scan */}
        <section id="website" className="mb-6 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking text-stone-500">
            Website scan
          </h2>
          <p className="mb-3 text-xs text-stone-600">
            Choose country, site and listing type. Start URL is built automatically, then update config and start the bot.
          </p>
          <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-stone-600">Country (EU)</label>
              <select
                value={webCountry}
                onChange={(e) => {
                  setWebCountry(e.target.value);
                  setWebSiteId("");
                  setWebListingPath("");
                }}
                className="w-full rounded border border-stone-300 bg-white px-3 py-2 text-sm"
              >
                <option value="">Select country</option>
                {(targetsData?.countries ?? []).map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-stone-600">Target site</label>
              <select
                value={webSiteId}
                onChange={(e) => {
                  setWebSiteId(e.target.value);
                  const site = webSites.find((s) => s.id === e.target.value);
                  const types = site?.listingTypes ?? targetsData?.defaultListingTypes ?? [];
                  setWebListingPath(types[0]?.path ?? "");
                }}
                className="w-full rounded border border-stone-300 bg-white px-3 py-2 text-sm"
              >
                <option value="">Select site</option>
                {webSites.map((s) => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-stone-600">Listing type</label>
              <select
                value={webListingPath}
                onChange={(e) => setWebListingPath(e.target.value)}
                className="w-full rounded border border-stone-300 bg-white px-3 py-2 text-sm"
              >
                {webListingTypes.length === 0 && (
                  <option value="">—</option>
                )}
                {webListingTypes.map((t) => (
                  <option key={t.path || "all"} value={t.path}>{t.label}</option>
                ))}
              </select>
            </div>
          </div>
          {webStartUrl && (
            <p className="mb-3 font-mono text-xs text-stone-600 break-all">
              Start URL: {webStartUrl}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={updateConfigAndStartWebsiteScan}
              disabled={runStatus === "running" || runStatus === "starting" || !webStartUrl}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Update config & start scan
            </button>
            {webConfigSaved && (
              <span className="text-xs text-stone-500">Config saved. Bot will use the URL above.</span>
            )}
          </div>
        </section>

        {/* Facebook scan */}
        <section id="facebook" className="mb-6 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking text-stone-500">
            Facebook scan
          </h2>
          <p className="mb-3 text-xs text-stone-600">
            Choose Marketplace or Groups, set location (city + radius) or group URLs, then update config and start the bot.
          </p>
          <div className="mb-3">
            <label className="mb-1 block text-xs font-medium text-stone-600">Source</label>
            <select
              value={fbSource}
              onChange={(e) => setFbSource(e.target.value as "marketplace" | "groups")}
              className="w-full max-w-xs rounded border border-stone-300 bg-white px-3 py-2 text-sm"
            >
              <option value="marketplace">Marketplace</option>
              <option value="groups">Groups</option>
            </select>
          </div>

          {fbSource === "marketplace" && (
            <div className="space-y-3 rounded-lg border border-stone-100 bg-stone-50/50 p-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-stone-600">City</label>
                  <input
                    type="text"
                    value={fbCity}
                    onChange={(e) => setFbCity(e.target.value)}
                    placeholder="e.g. miami"
                    className="w-full rounded border border-stone-300 bg-white px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-stone-600">Radius (km)</label>
                  <input
                    type="text"
                    value={fbRadius}
                    onChange={(e) => setFbRadius(e.target.value)}
                    placeholder="e.g. 25"
                    className="w-full rounded border border-stone-300 bg-white px-3 py-2 text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-stone-600">Keywords (optional)</label>
                <input
                  type="text"
                  value={fbKeywords}
                  onChange={(e) => setFbKeywords(e.target.value)}
                  placeholder="e.g. FSBO, owner"
                  className="w-full rounded border border-stone-300 bg-white px-3 py-2 text-sm"
                />
              </div>
            </div>
          )}

          {fbSource === "groups" && (
            <div className="rounded-lg border border-stone-100 bg-stone-50/50 p-3">
              <label className="mb-1 block text-xs font-medium text-stone-600">Group URLs (one per line)</label>
              <textarea
                value={fbGroupUrls}
                onChange={(e) => setFbGroupUrls(e.target.value)}
                placeholder="https://www.facebook.com/groups/..."
                rows={4}
                className="w-full rounded border border-stone-300 bg-white px-3 py-2 text-sm font-mono"
              />
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={updateConfigAndStartScan}
              disabled={runStatus === "running" || runStatus === "starting"}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Update config & start scan
            </button>
            {fbConfigSaved && (
              <span className="text-xs text-stone-500">Config saved. Bot will use the URLs above.</span>
            )}
          </div>
        </section>

        {/* Pipeline */}
        <section className="mb-6 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking text-stone-500">
            Pipeline
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            {PIPELINE_STEPS.map((step, i) => (
              <span key={step.id} className="flex items-center gap-1.5">
                <span className="rounded bg-stone-100 px-2 py-1 font-mono text-xs font-medium text-stone-700">
                  {step.name}
                </span>
                {i < PIPELINE_STEPS.length - 1 && (
                  <span className="text-stone-300" aria-hidden>→</span>
                )}
              </span>
            ))}
          </div>
          <p className="mt-2 text-xs text-stone-500">
            Config → Browser → Scroll → Extract → Dedup → Classify → Contact → Cooldown
          </p>
        </section>

        {/* Stages tab */}
        <section id="stages" className="mb-6 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking text-stone-500">
            Stages
          </h2>
          <div className="space-y-3">
            {STAGES.map((stage) => (
              <div
                key={stage.id}
                className="rounded-lg border border-stone-100 p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-medium text-stone-800">
                    Stage {stage.id}: {stage.name}
                  </h3>
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">
                    {stage.status}
                  </span>
                </div>
                <dl className="mt-2 grid gap-1 text-xs sm:grid-cols-2">
                  <div>
                    <dt className="text-stone-500">Inputs</dt>
                    <dd className="font-mono text-stone-700">{stage.inputs}</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">Outputs</dt>
                    <dd className="font-mono text-stone-700">{stage.outputs}</dd>
                  </div>
                </dl>
              </div>
            ))}
          </div>
        </section>

        {/* Test & build */}
        <section id="test" className="mb-6 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking text-stone-500">
            Test & build
          </h2>
          <p className="mb-3 text-xs text-stone-600">
            Run Python tests and build the dashboard. Output appears in the live monitor above.
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={runTests}
              disabled={runStatus === "running" || runStatus === "starting"}
              className="rounded border border-stone-300 bg-white px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50 disabled:opacity-50"
            >
              Run tests
            </button>
            <button
              type="button"
              onClick={runBuild}
              disabled={runStatus === "running" || runStatus === "starting"}
              className="rounded border border-stone-300 bg-white px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50 disabled:opacity-50"
            >
              Build dashboard
            </button>
          </div>
          <p className="mt-2 text-xs text-stone-500">
            Plan: <code className="rounded bg-stone-100 px-1">cold_bot/docs/TEST_AND_BUILD_PLAN.md</code>
          </p>
        </section>

        {/* Config */}
        <details className="mb-4 rounded-xl border border-stone-200 bg-white shadow-sm">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-stone-700">
            Config
          </summary>
          <pre className="max-h-40 overflow-auto border-t border-stone-100 p-4 text-xs text-stone-600">
            {config != null
              ? JSON.stringify(config, null, 2)
              : "Config not loaded"}
          </pre>
        </details>

        {/* Leads */}
        <details className="mb-4 rounded-xl border border-stone-200 bg-white shadow-sm">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-stone-700">
            Leads ({Array.isArray(leads) ? leads.length : 0})
          </summary>
          <div className="max-h-48 overflow-auto border-t border-stone-100 p-3 text-sm">
            {Array.isArray(leads) && leads.length > 0 ? (
              <ul className="divide-y divide-stone-100">
                {(leads as Record<string, unknown>[]).slice(0, 15).map((lead, i) => (
                  <li key={i} className="py-1.5">
                    {(lead.contact_email as string) || "(no email)"} · {lead.status as string}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-stone-500">No leads yet.</p>
            )}
          </div>
        </details>

        {/* Agents */}
        <details className="mb-4 rounded-xl border border-stone-200 bg-white shadow-sm">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-stone-700">
            Agent listings ({Array.isArray(agents) ? agents.length : 0})
          </summary>
          <div className="max-h-48 overflow-auto border-t border-stone-100 p-3 text-sm">
            {Array.isArray(agents) && agents.length > 0 ? (
              <ul className="divide-y divide-stone-100">
                {(agents as Record<string, unknown>[]).slice(0, 15).map((agent, i) => (
                  <li key={i} className="py-1.5">
                    {agent.agency_name as string} · {agent.listing_title as string}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-stone-500">No agent listings yet.</p>
            )}
          </div>
        </details>

        {/* Activity logs */}
        <details className="mb-4 rounded-xl border border-stone-200 bg-white shadow-sm">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-stone-700">
            Recent activity
          </summary>
          <div className="max-h-40 overflow-auto border-t border-stone-100 p-3 font-mono text-xs text-stone-600">
            {Array.isArray(logs) && logs.length > 0 ? (
              <ul className="divide-y divide-stone-100">
                {(logs as Record<string, unknown>[]).slice(0, 10).map((log, i) => (
                  <li key={i} className="py-1">
                    {(log.time as string) ?? ""} · {log.status as string}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-stone-500">No activity yet.</p>
            )}
          </div>
        </details>

        {/* Docs */}
        <section className="rounded-xl border border-stone-200 bg-stone-100 p-4 text-sm text-stone-700">
          <strong>Docs:</strong> MISSING_ANALYSIS.md · SILO_ANALYSIS.md · THE DEVELOPMENT PLAN.md · BOT_STATUS.md
        </section>
      </main>
    </div>
  );
}
