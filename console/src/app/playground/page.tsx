"use client";

/*
  Playground: the visitor composes their own payment event and watches
  the real engine score it. Submit once, then reuse the same device in
  a second submission and watch the score jump: the visitor becomes the
  fraud ring, which is the product's entire thesis in two clicks.
*/

import { useState } from "react";
import { ClusterGraph, type ClusterData } from "@/components/ClusterGraph";
import { ReasonChip, ScoreMeter, VerdictBadge } from "@/components/Verdict";
import { fetchCluster, ingestEvent, useApi, type Verdict } from "@/lib/api";
import { factorLabel, rupees } from "@/lib/format";

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

interface Draft {
  device: string;
  phone: string;
  vpa: string;
  merchant: string;
  amountRupees: number;
  outcome: string;
}

const DEFAULT_DRAFT: Draft = {
  device: "dev_visitor_01",
  phone: "+919800000001",
  vpa: "visitor@ybl",
  merchant: "mcht_playground_1",
  amountRupees: 1499,
  outcome: "none",
};

function randomish(): Draft {
  const n = Math.floor(Math.random() * 9000 + 1000);
  return {
    device: `dev_visitor_${n}`,
    phone: `+9198${String(10000000 + n * 733).slice(0, 8)}`,
    vpa: `visitor${n}@ybl`,
    merchant: `mcht_playground_${1 + (n % 6)}`,
    amountRupees: 199 + (n % 2800),
    outcome: "none",
  };
}

export default function PlaygroundPage() {
  const { base, key } = useApi();
  const [draft, setDraft] = useState<Draft>(DEFAULT_DRAFT);
  const [history, setHistory] = useState<{ draft: Draft; verdict: Verdict | null; note?: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (reuseDevice: boolean) => {
    setBusy(true);
    setError(null);
    const eventDraft = reuseDevice && history.length
      ? { ...draft, device: history[0].draft.device, phone: history[0].draft.phone, vpa: history[0].draft.vpa }
      : draft;
    const index = history.length + 1;
    const payload = {
      event_id: `pg-${Date.now().toString(36)}-${index}`,
      merchant_id: eventDraft.merchant,
      customer_id: `cust_visitor_${Math.floor(Math.random() * 900000 + 100000)}`,
      amount_paise: Math.round(eventDraft.amountRupees * 100),
      currency: "INR",
      upi_vpa: eventDraft.vpa.toLowerCase(),
      phone: eventDraft.phone,
      device_id: eventDraft.device,
      email: null,
      ip: "103.21.58.7",
      ts: new Date().toISOString(),
      payment_method: "upi",
      prior_outcome:
        eventDraft.outcome === "none"
          ? null
          : eventDraft.outcome === "chargeback"
            ? "chargeback"
            : "refund_abuse",
    };
    try {
      const result = await ingestEvent(base, key, payload);
      const verdictBody = result.status === 409 ? result.body.verdict : result.body;
      setHistory((prev) => [{ draft: eventDraft, verdict: verdictBody ?? null }, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "request failed");
    } finally {
      setBusy(false);
    }
  };

  const latest = history[0];
  const first = history[history.length - 1];
  const jump =
    history.length >= 2 && latest?.verdict && first?.verdict
      ? latest.verdict.score - first.verdict.score
      : null;
  const [clusterCustomer, setClusterCustomer] = useState<string | null>(null);
  const [cluster, setCluster] = useState<ClusterData | null>(null);

  const openCluster = async (customerId: string | null | undefined) => {
    if (!customerId) return;
    setClusterCustomer(customerId);
    try {
      setCluster(await fetchCluster(base, key, customerId));
    } catch {
      setCluster(null);
    }
  };

  return (
    <div className="grid gap-5 pt-5 lg:grid-cols-[400px_1fr]">
      <section className="flex flex-col gap-4">
        <div>
          <h1 className="font-display text-[26px] leading-none">Try your own event</h1>
          <p className="micro mt-2 leading-relaxed">
            compose a payment and submit it to the real engine. then submit again reusing the
            same device: watch your score jump as the ring builds
          </p>
        </div>

        <div className="flex flex-col gap-3 rounded-lg border border-hairline bg-panel p-4">
          {(
            [
              ["device", "device id"],
              ["phone", "phone"],
              ["vpa", "upi vpa"],
              ["merchant", "merchant id"],
            ] as const
          ).map(([field, label]) => (
            <label key={field} className="flex flex-col gap-1">
              <span className="micro">{label}</span>
              <input
                value={draft[field]}
                onChange={(e) => setDraft({ ...draft, [field]: e.target.value })}
                className="data rounded-md border border-hairline bg-raised px-2.5 py-1.5 text-[12px] outline-none focus:border-amber/60"
              />
            </label>
          ))}
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="micro">amount (inr)</span>
              <input
                type="number"
                value={draft.amountRupees}
                onChange={(e) => setDraft({ ...draft, amountRupees: Number(e.target.value) })}
                className="data rounded-md border border-hairline bg-raised px-2.5 py-1.5 text-[12px] outline-none focus:border-amber/60"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="micro">prior outcome</span>
              <select
                value={draft.outcome}
                onChange={(e) => setDraft({ ...draft, outcome: e.target.value })}
                className="data rounded-md border border-hairline bg-raised px-2.5 py-1.5 text-[12px] outline-none focus:border-amber/60"
              >
                <option value="none">none</option>
                <option value="chargeback">chargeback</option>
                <option value="refund_abuse">refund abuse</option>
              </select>
            </label>
          </div>
          <div className="flex gap-2 pt-1">
            <button
              onClick={() => submit(false)}
              disabled={busy}
              className="data flex-1 rounded-md border border-amber/50 bg-amber/10 px-3 py-2 text-[12px] text-amber transition-colors hover:bg-amber/20 disabled:opacity-50"
            >
              {busy ? "scoring..." : "score this event"}
            </button>
            <button
              onClick={() => setDraft(randomish())}
              className="micro rounded-md border border-hairline px-3 py-2 text-muted transition-colors hover:text-text"
            >
              random identity
            </button>
          </div>
          {history.length >= 1 && (
            <button
              onClick={() => submit(true)}
              disabled={busy}
              className="data rounded-md border border-block/50 bg-block/10 px-3 py-2 text-[12px] text-block transition-colors hover:bg-block/20 disabled:opacity-50"
            >
              attack again, reusing the first event's device
            </button>
          )}
          {error && <p className="data text-[11px] text-block">{error}</p>}
        </div>

        {jump !== null && (
          <div className="rounded-lg border border-amber/40 bg-amber/5 p-4">
            <p className="micro text-amber">the ring effect, live</p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-text">
              your first event scored{" "}
              <span className="data font-semibold">{first?.verdict?.score}</span>. this one:{" "}
              <span className="data font-semibold">{latest?.verdict?.score}</span>{" "}
              <span className="data text-amber">
                ({jump >= 0 ? "+" : ""}
                {jump})
              </span>{" "}
              because the graph now knows your device.
            </p>
          </div>
        )}

        {history.length > 0 && (
          <ul className="flex flex-col divide-y divide-hairline-soft overflow-hidden rounded-lg border border-hairline bg-panel">
            {[...history].reverse().map((entry, reverseIndex) => {
              const index = history.length - 1 - reverseIndex;
              return (
                <li key={index} className="grid grid-cols-[46px_1fr_70px] items-center gap-3 px-3 py-2">
                  <span className="micro">#{index + 1}</span>
                  <span className="data truncate text-[11px] text-muted">
                    {entry.draft.device} · {entry.draft.merchant} · {rupees(entry.draft.amountRupees * 100)}
                  </span>
                  {entry.verdict ? (
                    <button
                      onClick={() =>
                        openCluster(
                          (entry.verdict?.evidence as { customer_id?: string } | undefined)
                            ?.customer_id ?? null
                        )
                      }
                      className="micro text-right text-amber hover:underline"
                    >
                      {entry.verdict.score} · graph
                    </button>
                  ) : (
                    <span className="micro text-right">failed</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-4">
        {latest && latest.verdict ? (() => {
          const v = latest.verdict;
          return (
          <>
            <header className="rounded-lg border border-hairline bg-panel p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-2">
                  <VerdictBadge verdict={latest.verdict.verdict} />
                  <span className="data text-[12px] text-muted">
                    your event, scored live
                  </span>
                </div>
                <div className="w-56">
                  <ScoreMeter
                    score={latest.verdict.score}
                    reviewAt={35}
                    blockAt={49}
                  />
                </div>
              </div>
              {latest.verdict.reason_codes.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5 border-t border-hairline-soft pt-3">
                  {latest.verdict.reason_codes.map((code) => (
                    <ReasonChip key={code} code={code} />
                  ))}
                </div>
              )}
            </header>

            <div className="rounded-lg border border-hairline bg-panel p-4">
              <span className="micro">signal decomposition</span>
              <ul className="mt-3 flex flex-col gap-2.5">
                {FEATURE_KEYS.map((feature) => {
                  const normalized = v.features[NORM_KEYS[feature]] ?? 0;
                  return (
                    <li key={feature} className="grid grid-cols-[130px_1fr_46px] items-center gap-3">
                      <span className="text-[12px] text-muted">{factorLabel(feature)}</span>
                      <span className="h-[3px] rounded-full bg-raised">
                        <span
                          className="block h-[3px] rounded-full bg-amber/80"
                          style={{ width: `${Math.round(normalized * 100)}%` }}
                        />
                      </span>
                      <span className="data text-right text-[11px] text-muted">
                        {v.features[feature]}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>

            {cluster ? (
              <ClusterGraph cluster={cluster} subject={String(cluster.customer_id)} />
            ) : (
              clusterCustomer && (
                <button
                  onClick={() => openCluster(clusterCustomer)}
                  className="micro rounded-lg border border-hairline bg-panel p-6 text-center hover:text-text"
                >
                  load identity cluster
                </button>
              )
            )}
          </>
          );
        })() : (
          <section className="flex h-96 flex-col items-center justify-center gap-3 rounded-lg border border-hairline bg-panel">
            <p className="font-display text-[22px]">Become the fraud ring.</p>
            <p className="micro max-w-sm text-center leading-relaxed">
              score an event, then reuse its identity and watch the graph remember. every
              submission runs the real deterministic engine: no simulation
            </p>
          </section>
        )}
      </section>
    </div>
  );
}
