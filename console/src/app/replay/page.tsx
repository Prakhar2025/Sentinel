"use client";

import { useEffect, useRef, useState } from "react";
import { ScoreNumber, VerdictBadge } from "@/components/Verdict";
import { fetchScenario, ingestEvent, useApi, type Scenario } from "@/lib/api";
import { rupees, shortId } from "@/lib/format";

interface FeedRow {
  index: number;
  merchant: string;
  customer: string;
  amount: number;
  score: number | null;
  verdict: "ALLOW" | "REVIEW" | "BLOCK_REC" | "DUP";
  duplicate: boolean;
}

const STEP_MS = 750;

export default function ReplayPage() {
  const { base, key } = useApi();
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [feed, setFeed] = useState<FeedRow[]>([]);
  const runToken = useRef(0);

  useEffect(() => {
    let cancelled = false;
    fetchScenario(base, key)
      .then((data) => !cancelled && setScenario(data))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "failed"));
    return () => {
      cancelled = true;
    };
  }, [base, key]);

  const run = async () => {
    if (!scenario || running) return;
    setRunning(true);
    setFeed([]);
    const token = ++runToken.current;
    for (let index = 0; index < scenario.events.length; index++) {
      if (runToken.current !== token) break;
      const event = scenario.events[index];
      let row: FeedRow = {
        index,
        merchant: event.merchant_id,
        customer: event.customer_id,
        amount: event.amount_paise,
        score: null,
        verdict: "DUP",
        duplicate: false,
      };
      setFeed((prev) => [...prev, row]);
      try {
        const result = await ingestEvent(base, key, event);
        const verdictBody = result.status === 409 ? result.body.verdict : result.body;
        row = {
          ...row,
          score: verdictBody?.score ?? null,
          verdict: result.status === 409 ? "DUP" : verdictBody?.verdict ?? "REVIEW",
          duplicate: result.status === 409,
        };
      } catch (err) {
        row = { ...row, verdict: "REVIEW" };
        setError(err instanceof Error ? err.message : "ingest failed");
      }
      setFeed((prev) => prev.map((r) => (r.index === index ? row : r)));
      await new Promise((resolve) => setTimeout(resolve, STEP_MS));
    }
    if (runToken.current === token) setRunning(false);
  };

  const blocked = feed.filter((row) => row.verdict === "BLOCK_REC").length;
  const reviewed = feed.filter((row) => row.verdict === "REVIEW").length;
  const avg =
    feed.filter((row) => row.score !== null).reduce((sum, row) => sum + (row.score ?? 0), 0) /
    Math.max(feed.filter((row) => row.score !== null).length, 1);

  return (
    <div className="mx-auto max-w-4xl pt-5">
      <header className="border-b border-hairline pb-5">
        <h1 className="font-display text-[34px] leading-none">Ring replay</h1>
        <p className="micro mt-2">
          {scenario
            ? `${scenario.ring_id} &middot; ${scenario.events.length} events &middot; ${scenario.merchants.length} merchants &middot; live ingestion, real scoring`
            : "loading scenario&hellip;"}
        </p>
      </header>

      {error && (
        <div className="mt-4 rounded-lg border border-block/40 bg-block/5 p-4 text-[13px] text-muted">
          <span className="micro text-block">error</span>
          <p className="data mt-1 text-[11px]">{error}</p>
        </div>
      )}

      {scenario && (
        <>
          <div className="mt-5 flex items-center gap-4">
            <button
              onClick={run}
              disabled={running}
              className={`data rounded-md border px-4 py-2 text-[12px] tracking-wide transition-colors ${
                running
                  ? "border-hairline text-faint"
                  : "border-amber/50 bg-amber/10 text-amber hover:bg-amber/20"
              }`}
            >
              {running ? `replaying ${feed.length}/${scenario.events.length}` : "run replay"}
            </button>
            <p className="micro max-w-md leading-relaxed">
              the same device, vpas and phones hit {scenario.merchants.length} merchants in
              sequence; each event is scored against everything that came before it
            </p>
          </div>

          <div className="mt-5 grid grid-cols-3 gap-4 rounded-lg border border-hairline bg-panel p-4">
            <div>
              <p className="data text-[26px] font-semibold leading-none">{blocked}</p>
              <p className="micro mt-1.5">blocked (rec)</p>
            </div>
            <div>
              <p className="data text-[26px] font-semibold leading-none text-amber">{reviewed}</p>
              <p className="micro mt-1.5">sent to review</p>
            </div>
            <div>
              <p className="data text-[26px] font-semibold leading-none">{Number.isFinite(avg) ? avg.toFixed(0) : "\u2014"}</p>
              <p className="micro mt-1.5">avg risk score</p>
            </div>
          </div>

          <ul className="mt-5 flex flex-col divide-y divide-hairline-soft overflow-hidden rounded-lg border border-hairline bg-panel">
            {feed.map((row) => (
              <li
                key={row.index}
                className="row-arrival grid grid-cols-[30px_110px_120px_1fr_86px_40px] items-center gap-3 px-3 py-2"
              >
                <span className="micro">{String(row.index + 1).padStart(2, "0")}</span>
                <span className="data text-[11px] text-muted">{shortId(row.customer, 12)}</span>
                <span className="data text-[11px] text-muted">{row.merchant}</span>
                <span className="data text-[11px] text-faint">{rupees(row.amount)}</span>
                {row.duplicate ? (
                  <span className="micro">duplicate, prior verdict</span>
                ) : (
                  <VerdictBadge verdict={row.verdict as "ALLOW" | "REVIEW" | "BLOCK_REC"} />
                )}
                {row.score !== null && <ScoreNumber score={row.score} />}
              </li>
            ))}
          </ul>

          <p className="micro mt-4 leading-relaxed">
            watch the score climb as the ring&rsquo;s shared entities accumulate fan-out and taint
            &middot; duplicates return the original verdict (idempotent replay)
          </p>
        </>
      )}
    </div>
  );
}
