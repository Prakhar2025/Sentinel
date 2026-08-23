"use client";

import { useEffect, useState } from "react";
import { useApi } from "@/lib/api";
import { rupeesPlain } from "@/lib/format";

interface Metrics {
  model_version: string;
  seed: number;
  thresholds: { review: number; block: number };
  test_events: number;
  test_fraud_events: number;
  event_metrics: { precision: number; recall: number; f1: number };
  precision_ci95: [number, number];
  recall_ci95: [number, number];
  confusion: Record<string, { clean: number; fraud: number }>;
  review_abstentions: { fraud: number; clean: number };
  ring_recall: {
    rings_total: number;
    rings_caught: number;
    per_ring: Record<string, { events: number; flagged: number; event_recall: number; caught: boolean; strategy: string }>;
    missed_rings: string[];
  };
  fp_cost_per_1000: { gross_saved_inr: number; fp_cost_inr: number; review_cost_inr: number; net_saved_inr: number };
  threshold_sensitivity: { threshold: number; tp: number; fp: number; fn: number; precision: number; recall: number; f1: number }[];
  baselines: Record<string, { precision: number; recall: number; f1: number }>;
  evasion_pack: {
    strategies: Record<string, { events: number; missed_entirely: number; missed_entirely_rate: number; not_blocked: number; not_blocked_rate: number }>;
  };
  calibration_deciles: { score_range: string; events: number; fraud: number; fraud_rate: number }[];
  design_point_on_test: boolean;
}

function Big({ value, label, note }: { value: string; label: string; note?: string }) {
  return (
    <div>
      <p className="data text-[38px] font-semibold leading-none">{value}</p>
      <p className="micro mt-2">{label}</p>
      {note && <p className="data mt-1 text-[10px] text-faint">{note}</p>}
    </div>
  );
}

function Panel({ title, children, aside }: { title: string; children: React.ReactNode; aside?: string }) {
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

export default function MetricsPage() {
  const { base, key } = useApi();
  const [data, setData] = useState<Metrics | null>(null);
  const [latency, setLatency] = useState<{ p50_ms: number; p95_ms: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${base}/v1/evaluation`, { headers: { "X-API-Key": key } });
        if (!response.ok) throw new Error(`${response.status}: run make evaluate`);
        const payload = await response.json();
        if (!cancelled) {
          setData(payload.metrics as Metrics);
          setLatency(payload.latency ?? null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [base, key]);

  if (error) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-lg border border-amber/40 bg-amber/5 p-6">
        <p className="micro text-amber">evaluation artifacts missing</p>
        <p className="mt-2 font-display text-[18px]">No metrics yet.</p>
        <p className="mt-2 text-[13px] text-muted">
          Run <code className="data text-amber">make calibrate</code> then{" "}
          <code className="data text-amber">make evaluate</code> to generate the held-out report
          this page renders.
        </p>
      </div>
    );
  }

  if (!data) {
    return <div className="mt-16 text-center micro">loading evaluation&hellip;</div>;
  }

  const em = data.event_metrics;

  return (
    <div className="flex flex-col gap-5 pt-5">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-hairline pb-5">
        <div>
          <h1 className="font-display text-[34px] leading-none">Evaluation dossier</h1>
          <p className="micro mt-2">
            held-out test &middot; seed {data.seed} &middot; model {data.model_version} &middot;
            thresholds {data.thresholds.review}/{data.thresholds.block}
          </p>
        </div>
        <span
          className={`data rounded-sm border px-2 py-1 text-[11px] ${
            data.design_point_on_test
              ? "border-allow/40 bg-allow/10 text-allow"
              : "border-block/40 bg-block/10 text-block"
          }`}
        >
          design point {data.design_point_on_test ? "hit" : "missed"} (P&ge;0.80 at R&ge;0.70)
        </span>
      </header>

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <Panel title="event-level metrics" aside={`${data.test_events} events, ${data.test_fraud_events} fraud`}>
          <div className="grid grid-cols-3 gap-6">
            <Big value={em.precision.toFixed(3)} label="precision" note={`95% CI ${data.precision_ci95[0].toFixed(2)}\u2013${data.precision_ci95[1].toFixed(2)}`} />
            <Big value={em.recall.toFixed(3)} label="recall" note={`95% CI ${data.recall_ci95[0].toFixed(2)}\u2013${data.recall_ci95[1].toFixed(2)}`} />
            <Big value={em.f1.toFixed(3)} label="f1" note={latency ? `p95 ${latency.p95_ms} ms` : undefined} />
          </div>
        </Panel>

        <Panel title="rupee ledger per 1,000 events" aside="fp ₹321 · fn ₹1,100 · review ₹120">
          <dl className="data flex flex-col gap-1.5 text-[13px]">
            <div className="flex justify-between">
              <dt className="text-muted">gross fraud saved</dt>
              <dd className="text-allow">+₹{rupeesPlain(data.fp_cost_per_1000.gross_saved_inr)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">false-positive cost</dt>
              <dd className="text-block">&minus;₹{rupeesPlain(data.fp_cost_per_1000.fp_cost_inr)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">review labor</dt>
              <dd className="text-amber">&minus;₹{rupeesPlain(data.fp_cost_per_1000.review_cost_inr)}</dd>
            </div>
            <div className="mt-1 flex justify-between border-t border-hairline-soft pt-2 text-[15px] font-semibold">
              <dt>net</dt>
              <dd className={data.fp_cost_per_1000.net_saved_inr >= 0 ? "text-allow" : "text-block"}>
                ₹{rupeesPlain(data.fp_cost_per_1000.net_saved_inr)}
              </dd>
            </div>
          </dl>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-[380px_1fr]">
        <Panel title="confusion" aside="positive = block rec">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="micro">
                <th className="py-1 text-left font-normal">band</th>
                <th className="py-1 text-right font-normal">clean</th>
                <th className="py-1 text-right font-normal">fraud</th>
              </tr>
            </thead>
            <tbody className="data divide-y divide-hairline-soft">
              {Object.entries(data.confusion).map(([band, cells]) => (
                <tr key={band}>
                  <td className="py-1.5 text-muted">{band}</td>
                  <td className="py-1.5 text-right">{cells.clean}</td>
                  <td className={`py-1.5 text-right ${band === "BLOCK_REC" ? "text-block" : band === "ALLOW" ? "text-allow" : "text-amber"}`}>
                    {cells.fraud}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="micro mt-3 leading-relaxed">
            review is abstention: {data.review_abstentions.fraud} fraud queued, not silently passed
          </p>
        </Panel>

        <Panel title="rings caught" aside={`${data.ring_recall.rings_caught} of ${data.ring_recall.rings_total}`}>
          <ul className="flex flex-col divide-y divide-hairline-soft">
            {Object.entries(data.ring_recall.per_ring).map(([ring, r]) => (
              <li key={ring} className="grid grid-cols-[90px_70px_1fr_60px] items-center gap-3 py-2">
                <span className="data text-[11px] text-muted">{ring}</span>
                <span className={`micro ${r.strategy === "sophisticated" ? "text-amber" : ""}`}>
                  {r.strategy === "sophisticated" ? "slow" : "burst"}
                </span>
                <span className="h-[3px] rounded-full bg-raised">
                  <span
                    className={`block h-[3px] rounded-full ${r.caught ? "bg-allow/80" : "bg-block/80"}`}
                    style={{ width: `${Math.round(r.event_recall * 100)}%` }}
                  />
                </span>
                <span className={`data text-right text-[11px] ${r.caught ? "text-allow" : "text-block"}`}>
                  {r.flagged}/{r.events}
                </span>
              </li>
            ))}
          </ul>
          {data.ring_recall.missed_rings.length > 0 && (
            <p className="micro mt-3 text-block">
              missed, named: {data.ring_recall.missed_rings.join(", ")}
            </p>
          )}
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="baselines, same features same splits" aside="disclosed even when they win">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="micro">
                <th className="py-1 text-left font-normal">model</th>
                <th className="py-1 text-right font-normal">precision</th>
                <th className="py-1 text-right font-normal">recall</th>
                <th className="py-1 text-right font-normal">f1</th>
              </tr>
            </thead>
            <tbody className="data divide-y divide-hairline-soft">
              <tr>
                <td className="py-1.5 text-text">rule ensemble (ours)</td>
                <td className="py-1.5 text-right">{em.precision.toFixed(3)}</td>
                <td className="py-1.5 text-right">{em.recall.toFixed(3)}</td>
                <td className="py-1.5 text-right font-semibold">{em.f1.toFixed(3)}</td>
              </tr>
              {Object.entries(data.baselines).map(([name, r]) => (
                <tr key={name}>
                  <td className="py-1.5 text-muted">{name.replace(/_/g, " ")}</td>
                  <td className="py-1.5 text-right">{r.precision.toFixed(3)}</td>
                  <td className="py-1.5 text-right">{r.recall.toFixed(3)}</td>
                  <td className={`py-1.5 text-right ${r.f1 > em.f1 ? "font-semibold text-amber" : ""}`}>
                    {r.f1.toFixed(3)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="adversarial evasion pack" aside="we attacked ourselves">
          <ul className="flex flex-col divide-y divide-hairline-soft">
            {Object.entries(data.evasion_pack.strategies).map(([strategy, r]) => (
              <li key={strategy} className="flex items-center justify-between py-2">
                <span className="text-[12px] text-muted">{strategy.replace(/_/g, " ")}</span>
                <span className="flex items-baseline gap-3">
                  <span className="data text-[11px] text-faint">{r.events} events</span>
                  <span className={`data text-[13px] ${r.missed_entirely_rate > 0.5 ? "text-block" : "text-amber"}`}>
                    {(r.missed_entirely_rate * 100).toFixed(0)}% missed
                  </span>
                </span>
              </li>
            ))}
          </ul>
          <p className="micro mt-3 leading-relaxed">
            slow-rate evasion is the known blind spot; the v2 fix is time-windowed fan-out
          </p>
        </Panel>
      </div>

      <Panel title="threshold sensitivity" aside="the tradeoff, not one number">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="micro">
              <th className="py-1 text-left font-normal">threshold</th>
              <th className="py-1 text-right font-normal">tp</th>
              <th className="py-1 text-right font-normal">fp</th>
              <th className="py-1 text-right font-normal">fn</th>
              <th className="py-1 text-right font-normal">precision</th>
              <th className="py-1 text-right font-normal">recall</th>
            </tr>
          </thead>
          <tbody className="data divide-y divide-hairline-soft">
            {data.threshold_sensitivity.map((row) => (
              <tr key={row.threshold} className={row.threshold === data.thresholds.block ? "text-text" : "text-muted"}>
                <td className="py-1.5">
                  {row.threshold}
                  {row.threshold === data.thresholds.block && <span className="micro ml-2 text-amber">locked</span>}
                </td>
                <td className="py-1.5 text-right">{row.tp}</td>
                <td className="py-1.5 text-right">{row.fp}</td>
                <td className="py-1.5 text-right">{row.fn}</td>
                <td className="py-1.5 text-right">{row.precision.toFixed(3)}</td>
                <td className="py-1.5 text-right">{row.recall.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel title="score calibration" aside="fraud rate by score bucket">
        <ul className="grid gap-2 md:grid-cols-2">
          {data.calibration_deciles.map((row, index) => (
            <li
              key={`cal-${row.score_range}-${index}`}
              className="grid grid-cols-[80px_1fr_60px] items-center gap-3"
            >
              <span className="data text-[11px] text-faint">{row.score_range}</span>
              <span className="h-[3px] rounded-full bg-raised">
                <span
                  className="block h-[3px] rounded-full bg-amber/70"
                  style={{ width: `${Math.round(row.fraud_rate * 100)}%` }}
                />
              </span>
              <span className="data text-right text-[11px] text-muted">
                {(row.fraud_rate * 100).toFixed(0)}%
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
