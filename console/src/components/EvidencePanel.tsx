"use client";

import { useEffect, useState } from "react";
import { ClusterGraph, type ClusterData } from "@/components/ClusterGraph";
import { ReasonChip, ScoreMeter, VerdictBadge } from "@/components/Verdict";
import { explainLive, fetchCluster, ingestEvent, useApi, type Verdict } from "@/lib/api";
import { factorLabel, shortId } from "@/lib/format";

const FEATURE_KEYS = [
  "device_identity_ratio",
  "cross_merchant_fanout",
  "taint_propagation",
  "velocity_72h",
  "burn_rotate",
  "amount_pattern",
  "new_identity_burst",
];

const NORM_KEYS: Record<string, string> = {
  device_identity_ratio: "n_f1",
  cross_merchant_fanout: "n_f2",
  taint_propagation: "n_f3",
  velocity_72h: "n_f4",
  burn_rotate: "n_f5",
  amount_pattern: "n_f6",
  new_identity_burst: "n_f7",
};

function Narrative({
  verdict,
  onGenerate,
  generating,
  cap,
}: {
  verdict: Verdict;
  onGenerate: () => void;
  generating: boolean;
  cap: string | null;
}) {
  if (verdict.explanation_status !== "DONE" || !verdict.explanation) {
    return (
      <div className="rounded-lg border border-hairline bg-panel p-4">
        <span className="micro">analyst narrative</span>
        <p className="mt-2 text-sm text-faint">
          {verdict.explanation_status === "CAP_REACHED"
            ? "Daily live-generation cap reached; stored narrative shown."
            : "No narrative yet. Generate one live with the real model."}
        </p>
        <button
          onClick={onGenerate}
          disabled={generating}
          className="data mt-3 rounded-md border border-amber/50 bg-amber/10 px-3 py-1.5 text-[11px] text-amber transition-colors hover:bg-amber/20 disabled:opacity-50"
        >
          {generating ? "generating with gpt-oss..." : "generate explanation live"}
        </button>
        {cap && <p className="micro mt-2 text-faint">{cap}</p>}
      </div>
    );
  }
  let parsed: { summary?: string; risk_factors?: string[]; recommended_action?: string } = {};
  try {
    parsed = JSON.parse(verdict.explanation);
  } catch {
    parsed = {};
  }
  return (
    <div className="rounded-lg border border-hairline bg-panel p-4">
      <div className="flex items-center justify-between">
        <span className="micro">analyst narrative</span>
        <span className="micro text-faint">generated, evidence-bound</span>
      </div>
      {parsed.summary && <p className="mt-2 font-display text-[17px] leading-snug">{parsed.summary}</p>}
      {parsed.risk_factors && parsed.risk_factors.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {parsed.risk_factors.map((factor, index) => (
            <li
              key={`factor-${index}-${factor}`}
              className="data rounded-sm bg-raised px-1.5 py-0.5 text-[10px] text-muted"
            >
              {factor}
            </li>
          ))}
        </ul>
      )}
      {parsed.recommended_action && (
        <p className="mt-3 border-t border-hairline-soft pt-2 text-[13px] text-muted">
          <span className="micro mr-2">action</span>
          {parsed.recommended_action}
        </p>
      )}
    </div>
  );
}

export function EvidencePanel({ verdict, reviewAt, blockAt }: { verdict: Verdict; reviewAt: number; blockAt: number }) {
  const { base, key } = useApi();
  const [cluster, setCluster] = useState<ClusterData | null>(null);
  const [generating, setGenerating] = useState(false);
  const [cap, setCap] = useState<string | null>(null);
  const [live, setLive] = useState<Verdict | null>(null);
  const shown = live ?? verdict;

  const generate = async () => {
    setGenerating(true);
    try {
      const result = await explainLive(base, key, shown.event_id);
      setLive({
        ...shown,
        explanation: result.explanation,
        explanation_status: result.explanation_status as Verdict["explanation_status"],
      });
      setCap(
        `live generation ${result.cap.used}/${result.cap.cap} today (UTC)`
      );
    } catch (err) {
      setCap(err instanceof Error ? err.message : "generation failed");
    } finally {
      setGenerating(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    fetchCluster(base, key, customerIdOf(verdict))
      .then((data) => {
        if (!cancelled) setCluster(data);
      })
      .catch(() => {
        if (!cancelled) setCluster(null);
      });
    return () => {
      cancelled = true;
    };
  }, [base, key, verdict.event_id]);

  return (
    <section className="flex flex-col gap-4">
      <header className="rounded-lg border border-hairline bg-panel p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <VerdictBadge verdict={verdict.verdict} />
              <span className="data text-[12px] text-muted">{shortId(verdict.event_id, 18)}</span>
            </div>
            <h2 className="data mt-2 text-[13px] text-muted">
              customer <span className="text-text">{customerIdOf(verdict)}</span>
            </h2>
          </div>
          <div className="w-56">
            <ScoreMeter score={verdict.score} reviewAt={reviewAt} blockAt={blockAt} />
          </div>
        </div>
        {verdict.reason_codes.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-hairline-soft pt-3">
            {verdict.reason_codes.map((code) => (
              <ReasonChip key={code} code={code} />
            ))}
          </div>
        )}
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <div className="rounded-lg border border-hairline bg-panel p-4">
            <span className="micro">signal decomposition</span>
            <ul className="mt-3 flex flex-col gap-2.5">
              {FEATURE_KEYS.map((feature) => {
                const normalized = verdict.features[NORM_KEYS[feature]] ?? 0;
                const raw = verdict.features[feature];
                return (
                  <li key={feature} className="grid grid-cols-[130px_1fr_46px] items-center gap-3">
                    <span className="text-[12px] text-muted">{factorLabel(feature)}</span>
                    <span className="h-[3px] rounded-full bg-raised">
                      <span
                        className="block h-[3px] rounded-full bg-amber/80"
                        style={{ width: `${Math.round(normalized * 100)}%` }}
                      />
                    </span>
                    <span className="data text-right text-[11px] text-muted">{raw}</span>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="rounded-lg border border-hairline bg-panel p-4">
            <span className="micro">cross-merchant evidence</span>
            <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2">
              <div>
                <p className="data text-[20px] font-semibold">{verdict.evidence.linked_merchants?.length ?? 0}</p>
                <p className="micro">merchants linked</p>
              </div>
              <div>
                <p className="data text-[20px] font-semibold">{verdict.evidence.shared_devices?.[0]?.linked_identities ?? "-"}</p>
                <p className="micro">identities on top device</p>
              </div>
            </div>
            {verdict.evidence.linked_merchants && verdict.evidence.linked_merchants.length > 0 && (
              <p className="data mt-3 text-[11px] leading-relaxed text-faint">
                {verdict.evidence.linked_merchants.join("  \u00b7  ")}
              </p>
            )}
            {verdict.evidence.taint_path && verdict.evidence.taint_path.length > 1 && (
              <p className="data mt-3 border-t border-hairline-soft pt-2 text-[11px] text-block">
                taint path &nbsp;{verdict.evidence.taint_path.join(" \u2192 ")}
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-4">
          {cluster ? (
            <ClusterGraph cluster={cluster} subject={customerIdOf(verdict)} />
          ) : (
            <div className="flex h-64 items-center justify-center rounded-lg border border-hairline bg-panel">
              <span className="micro">cluster unavailable</span>
            </div>
          )}
          <Narrative verdict={shown} onGenerate={generate} generating={generating} cap={cap} />
        </div>
      </div>
    </section>
  );
}

function customerIdOf(verdict: Verdict): string {
  const stored = (verdict.evidence as { customer_id?: string }).customer_id;
  if (stored) return stored;
  return verdict.event_id; // placeholder until event detail is fetched
}

export { ingestEvent };
