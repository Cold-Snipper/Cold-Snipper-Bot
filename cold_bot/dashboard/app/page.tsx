"use client";

import { useEffect, useState } from "react";

function RunCommand({
  label,
  command,
}: {
  label: string;
  command: string;
}) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(command).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-stone-300 bg-white px-3 py-2 sm:flex-row sm:items-center">
      <span className="text-xs font-medium text-stone-500">{label}</span>
      <code className="break-all text-sm text-stone-800">{command}</code>
      <button
        type="button"
        onClick={copy}
        className="shrink-0 rounded bg-stone-200 px-2 py-1 text-xs font-medium hover:bg-stone-300"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

type Stage = {
  id: number;
  name: string;
  inputs: string;
  outputs: string;
  status: string;
  docLink?: string;
};

const STAGES: Stage[] = [
  {
    id: 1,
    name: "Setup & source selection",
    inputs: "config_path, --setup",
    outputs: "source_type, phase2 URLs in config",
    status: "Working",
    docLink: "../docs/MISSING_ANALYSIS.md",
  },
  {
    id: 2,
    name: "Config & phase2 URLs",
    inputs: "config.yaml (source_type, websites, facebook)",
    outputs: "start_urls derived, limits defaults",
    status: "Working",
  },
  {
    id: 3,
    name: "URLs & browser",
    inputs: "start_urls from config",
    outputs: "Playwright page, graceful close on SIGINT",
    status: "Working",
  },
  {
    id: 4,
    name: "Deduplication",
    inputs: "listing text, db_path, session set",
    outputs: "skip if seen (DB or session)",
    status: "Working",
  },
  {
    id: 5,
    name: "Confidence & agent extraction",
    inputs: "text, config (min_confidence)",
    outputs: "is_private, agent_details, verify_qualifies",
    status: "Working",
  },
  {
    id: 6,
    name: "Airbnb gate",
    inputs: "viability rating, airbnb_min_rating",
    outputs: "contact only if viable",
    status: "Working",
  },
  {
    id: 7,
    name: "Contacting (send_all)",
    inputs: "contacts, message, config (dry_run)",
    outputs: "email sent / dry-run, log_contact",
    status: "Working",
  },
  {
    id: 8,
    name: "Logging DB",
    inputs: "config.database",
    outputs: "lead_logs, agent_logs in one DB",
    status: "Working",
  },
  {
    id: 9,
    name: "Cooldown & shutdown",
    inputs: "cycle_cooldown_seconds, rate limit",
    outputs: "sleep between cycles, close_browser on exit",
    status: "Working",
  },
  {
    id: 10,
    name: "Dashboard",
    inputs: "Config, leads, agents, logs APIs",
    outputs: "Stages view, previews, auto-refresh",
    status: "Working",
  },
];

export default function Home() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [leads, setLeads] = useState<unknown[]>([]);
  const [agents, setAgents] = useState<unknown[]>([]);
  const [logs, setLogs] = useState<unknown[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
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
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-white px-6 py-4 shadow-sm">
        <h1 className="text-2xl font-semibold tracking-tight">
          Cold Bot – Real Estate Outreach
        </h1>
        <p className="mt-1 text-sm text-stone-500">
          Dashboard · Stages · Leads & agents · Auto-refresh every 15s
        </p>
      </header>

      <nav className="sticky top-0 z-10 border-b border-stone-200 bg-white/95 px-6 py-2 backdrop-blur">
        <span className="text-sm font-medium text-stone-600">Stages</span>
        <ul className="mt-2 flex flex-wrap gap-2">
          {STAGES.map((s) => (
            <li key={s.id}>
              <a
                href={`#stage-${s.id}`}
                className="inline-block rounded-md bg-stone-100 px-3 py-1.5 text-sm font-medium text-stone-700 hover:bg-stone-200"
              >
                Stage {s.id}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <main className="mx-auto max-w-5xl px-6 py-8">
        {error && (
          <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {error}
          </div>
        )}

        <section className="mb-10">
          <h2 className="mb-4 text-lg font-semibold text-stone-800">
            Operational breakdown
          </h2>
          <div className="space-y-4">
            {STAGES.map((stage) => (
              <div
                key={stage.id}
                id={`stage-${stage.id}`}
                className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-medium text-stone-800">
                    Stage {stage.id}: {stage.name}
                  </h3>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      stage.status === "Working"
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-stone-100 text-stone-600"
                    }`}
                  >
                    {stage.status}
                  </span>
                </div>
                <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-stone-500">Inputs</dt>
                    <dd className="font-mono text-stone-700">{stage.inputs}</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">Outputs</dt>
                    <dd className="font-mono text-stone-700">{stage.outputs}</dd>
                  </div>
                </dl>
                {stage.docLink && (
                  <p className="mt-2 text-xs text-stone-500">
                    See <code className="rounded bg-stone-100 px-1">{stage.docLink}</code>
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className="mb-10">
          <h2 className="mb-4 text-lg font-semibold text-stone-800">Config preview</h2>
          <pre className="max-h-48 overflow-auto rounded-lg border border-stone-200 bg-stone-100 p-4 text-xs text-stone-700">
            {config != null
              ? JSON.stringify(config, null, 2)
              : "(Config not loaded – run bot from cold_bot so config.yaml is available)"}
          </pre>
        </section>

        <section className="mb-10">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-stone-800">Leads</h2>
            <button
              type="button"
              onClick={fetchData}
              className="rounded bg-stone-200 px-3 py-1 text-sm font-medium hover:bg-stone-300"
            >
              Refresh
            </button>
          </div>
          <div className="max-h-64 overflow-auto rounded-lg border border-stone-200 bg-white">
            {Array.isArray(leads) && leads.length > 0 ? (
              <ul className="divide-y divide-stone-100 p-2">
                {(leads as Record<string, unknown>[]).slice(0, 20).map((lead, i) => (
                  <li key={(lead.id as number) ?? i} className="py-2 text-sm">
                    <span className="font-medium">
                      {(lead.contact_email as string) || "(no email)"}
                    </span>
                    {" · "}
                    <span className="text-stone-500">{lead.status as string}</span>
                    {" · "}
                    <span className="text-stone-400">
                      {lead.timestamp
                        ? new Date((lead.timestamp as number) * 1000).toLocaleString()
                        : ""}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="p-4 text-sm text-stone-500">No leads yet.</p>
            )}
          </div>
        </section>

        <section className="mb-10">
          <h2 className="mb-4 text-lg font-semibold text-stone-800">Agent listings</h2>
          <div className="max-h-64 overflow-auto rounded-lg border border-stone-200 bg-white">
            {Array.isArray(agents) && agents.length > 0 ? (
              <ul className="divide-y divide-stone-100 p-2">
                {(agents as Record<string, unknown>[]).slice(0, 20).map((agent, i) => (
                  <li key={(agent.id as number) ?? i} className="py-2 text-sm">
                    <span className="font-medium">{agent.agency_name as string}</span>
                    {" · "}
                    <span className="text-stone-600">{agent.listing_title as string}</span>
                    {" · "}
                    <span className="text-stone-400">
                      {agent.timestamp
                        ? new Date((agent.timestamp as number) * 1000).toLocaleString()
                        : ""}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="p-4 text-sm text-stone-500">No agent listings logged yet.</p>
            )}
          </div>
        </section>

        <section className="mb-10">
          <h2 className="mb-4 text-lg font-semibold text-stone-800">Recent activity (logs)</h2>
          <div className="max-h-48 overflow-auto rounded-lg border border-stone-200 bg-white">
            {Array.isArray(logs) && logs.length > 0 ? (
              <ul className="divide-y divide-stone-100 p-2 text-sm">
                {(logs as Record<string, unknown>[]).slice(0, 15).map((log, i) => (
                  <li key={i} className="py-1.5 font-mono text-stone-600">
                    {(log.time as string) ?? ""} · {log.status as string} ·{" "}
                    {(log.contact_email as string) ?? log.listing_hash}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="p-4 text-sm text-stone-500">No activity yet.</p>
            )}
          </div>
        </section>

        <section className="rounded-xl border border-stone-200 bg-stone-100 p-5">
          <h2 className="mb-3 text-lg font-semibold text-stone-800">Run bot</h2>
          <p className="mb-3 text-sm text-stone-600">
            From <code className="rounded bg-white px-1">cold_bot/</code> in a terminal:
          </p>
          <div className="mb-4 flex flex-wrap gap-3">
            <RunCommand
              label="Dry run (default)"
              command="python main.py --dry-run"
            />
            <RunCommand
              label="Setup then run"
              command="python main.py --setup && python main.py --dry-run"
            />
            <RunCommand
              label="Live (sends emails)"
              command="python main.py --live"
            />
          </div>

          <h2 className="mb-2 text-lg font-semibold text-stone-800">Docs</h2>
          <ul className="list-inside list-disc space-y-1 text-sm text-stone-700">
            <li>
              <strong>MISSING_ANALYSIS.md</strong> – gaps and checklist (
              <code className="rounded bg-white px-1">cold_bot/docs/</code>)
            </li>
            <li>
              <strong>THE DEVELOPMENT PLAN.md</strong> – full build steps (cold_bot root)
            </li>
            <li>
              <strong>BOT_STATUS.md</strong> – status overview (repo root)
            </li>
          </ul>
        </section>
      </main>
    </div>
  );
}
