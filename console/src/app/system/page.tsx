"use client";

/*
  The System view: the repo's depth, rendered for people who don't
  read files. Everything here is served from the real documents
  (what-broke log, ADRs, threat model) and the real evaluation
  artifacts, via GET /v1/system. No authored marketing text.
*/

import { useEffect, useState } from "react";
import { ArchitectureDiagram } from "@/components/ArchitectureDiagram";
import { EvalProtocolDiagram } from "@/components/EvalProtocolDiagram";
import { useApi } from "@/lib/api";

interface SystemData {
  what_broke: { date: string; phase: string; broke: string; cause: string; fix: string }[];
  decisions: { id: string; title: string; decision: string }[];
  threats: { number: string; class: string; threat: string; control: string; residual: string }[];
  disclosures: { title: string; detail: string }[];
  headline: { precision?: number; recall?: number; f1?: number; rings_caught?: number; rings_total?: number };
  components: { name: string; detail: string }[];
}

const TABS = ["System", "Honesty", "Decisions", "Security", "Build log"] as const;
type Tab = (typeof TABS)[number];

function Panel({
  children,
  title,
  aside,
}: {
  children: React.ReactNode;
  title: string;
  aside?: string;
}) {
  return (
    <section className="rounded-lg border border-hairline bg-panel p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="micro">{title}</h2>
        {aside && <span className="micro text-faint">{aside}</span>}
      </div>
      {children}
    </section>
  );
}

export default function SystemPage() {
  const { base, key } = useApi();
  const [data, setData] = useState<SystemData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("System");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${base}/v1/system`, { headers: { "X-API-Key": key } });
        if (!response.ok) throw new Error(`${response.status}`);
        setData((await response.json()) as SystemData);
      } catch (err) {
        setError(err instanceof Error ? err.message : "failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [base, key]);

  if (error) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-lg border border-amber/40 bg-amber/5 p-6">
        <p className="micro text-amber">system data unavailable</p>
        <p className="mt-2 text-[13px] text-muted">
          The About data comes from the repository documents. Run the API from the repo root
          (where /docs lives) with <code className="data text-amber">make serve</code>.
        </p>
      </div>
    );
  }

  if (!data) {
    return <div className="mt-16 text-center micro">loading system&hellip;</div>;
  }

  return (
    <div className="pt-5">
      <header className="border-b border-hairline pb-5">
        <h1 className="font-display text-[34px] leading-none">The system, honestly</h1>
        <p className="micro mt-2">
          everything on this page is rendered from the repository&rsquo;s real documents and
          evaluation artifacts &middot; nothing authored for show
        </p>
      </header>

      <nav className="mt-4 flex flex-wrap gap-1">
        {TABS.map((item) => (
          <button
            key={item}
            onClick={() => setTab(item)}
            className={`micro rounded-md border px-3 py-1.5 transition-colors ${
              tab === item
                ? "border-hairline bg-raised text-text"
                : "border-transparent text-muted hover:text-text"
            }`}
          >
            {item}
          </button>
        ))}
      </nav>

      <div className="mt-5 flex flex-col gap-5">
        {tab === "System" && (
          <>
            <div className="grid gap-5 lg:grid-cols-4">
              {(
                [
                  ["precision", data.headline.precision?.toFixed(3)],
                  ["recall", data.headline.recall?.toFixed(3)],
                  ["f1", data.headline.f1?.toFixed(3)],
                  [
                    "rings caught",
                    `${data.headline.rings_caught ?? 0}/${data.headline.rings_total ?? 0}`,
                  ],
                ] as const
              ).map(([label, value]) => (
                <Panel key={label} title={label}>
                  <p className="data text-[30px] font-semibold leading-none">{value}</p>
                </Panel>
              ))}
            </div>
            <ArchitectureDiagram />
            <EvalProtocolDiagram />
            <Panel title="the seven components, end to end" aside="every layer tested and documented">
              <ol className="flex flex-col divide-y divide-hairline-soft">
                {data.components.map((component, index) => (
                  <li key={component.name} className="grid grid-cols-[30px_220px_1fr] items-baseline gap-4 py-3">
                    <span className="data text-[11px] text-faint">{String(index + 1).padStart(2, "0")}</span>
                    <span className="text-[13px] font-medium">{component.name}</span>
                    <span className="text-[12px] leading-relaxed text-muted">{component.detail}</span>
                  </li>
                ))}
              </ol>
            </Panel>
            <Panel title="try it yourself" aside="real engine, no simulation">
              <p className="text-[13px] leading-relaxed text-muted">
                Open the <b className="text-text">Playground</b> tab: compose a payment event,
                score it, then reuse the same device and watch your score climb as the graph
                remembers you. The replay tab runs a recorded fraud ring across six merchants.
              </p>
            </Panel>
          </>
        )}

        {tab === "Honesty" && (
          <>
            <Panel title="the two disclosures, in the open" aside="shown, not buried">
              <div className="flex flex-col gap-5">
                {data.disclosures.map((disclosure) => (
                  <div key={disclosure.title} className="border-l-2 border-amber/50 pl-4">
                    <p className="text-[14px] font-medium">{disclosure.title}</p>
                    <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{disclosure.detail}</p>
                  </div>
                ))}
              </div>
            </Panel>
            <Panel title="what broke" aside={`${data.what_broke.length} genuine entries, logged in real time`}>
              <ul className="flex flex-col divide-y divide-hairline-soft">
                {data.what_broke.map((entry, index) => (
                  <li key={index} className="py-3">
                    <div className="flex items-baseline gap-3">
                      <span className="micro">{entry.date}</span>
                      <span className="micro text-faint">phase {entry.phase}</span>
                    </div>
                    <p className="mt-1 text-[13px] leading-relaxed">{entry.broke}</p>
                    <p className="mt-1 text-[12px] leading-relaxed text-muted">
                      <span className="micro mr-2 text-block">cause</span>
                      {entry.cause}
                    </p>
                    <p className="mt-1 text-[12px] leading-relaxed text-muted">
                      <span className="micro mr-2 text-allow">fix</span>
                      {entry.fix}
                    </p>
                  </li>
                ))}
              </ul>
            </Panel>
          </>
        )}

        {tab === "Decisions" && (
          <Panel title="architecture decision records" aside="the calls that define the system">
            <ul className="flex flex-col gap-5">
              {data.decisions.map((adr) => (
                <li key={adr.id} className="border-l-2 border-hairline pl-4">
                  <p className="micro text-amber">{adr.id}</p>
                  <p className="mt-1 font-display text-[17px]">{adr.title}</p>
                  <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{adr.decision}</p>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        {tab === "Security" && (
          <Panel title="threat model" aside="ten threats, mapped to built controls">
            <ul className="flex flex-col divide-y divide-hairline-soft">
              {data.threats.map((threat) => (
                <li key={threat.number} className="py-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[13px] font-medium">
                      {threat.class}: {threat.threat}
                    </span>
                    <span className="micro text-faint">#{threat.number}</span>
                  </div>
                  <p className="mt-1 text-[12px] leading-relaxed text-muted">
                    <span className="micro mr-2 text-allow">control</span>
                    {threat.control}
                  </p>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        {tab === "Build log" && (
          <Panel title="repository map" aside="everything a reviewer needs">
            <ul className="data flex flex-col gap-2 text-[12px]">
              {[
                ["docs/01-04", "problem, PRD, architecture, data design"],
                ["docs/05", "evaluation protocol: features, metrics, rupee FP-cost model"],
                ["docs/06-07", "API specification; security, DPDP/PCI, defense-only analysis"],
                ["docs/08-13", "tech decisions, testing, risks, roadmap, pitch, glossary"],
                ["docs/14", "champion/challenger shadow model and promotion criteria"],
                ["docs/15", "productionization RFC from measured load tests"],
                ["docs/16-18", "threat model, operations runbook, six ADRs"],
                ["docs/19", "all-AWS deployment kit"],
                ["docs/what-broke.md", "every genuine failure, logged in real time"],
                ["evaluation/report.md", "the full held-out evaluation report"],
              ].map(([path, description]) => (
                <li key={path} className="flex flex-wrap items-baseline gap-3">
                  <span className="text-amber">{path}</span>
                  <span className="text-muted">{description}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </div>
  );
}
