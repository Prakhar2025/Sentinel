"use client";

import { useMemo, useState } from "react";
import { EvidencePanel } from "@/components/EvidencePanel";
import { ScoreNumber, VerdictBadge } from "@/components/Verdict";
import { useApi, useVerdictQueue, type Verdict } from "@/lib/api";
import { shortId, timeAgo } from "@/lib/format";

const FILTERS = [
  { id: null, label: "all" },
  { id: "BLOCK_REC", label: "block rec" },
  { id: "REVIEW", label: "review" },
  { id: "ALLOW", label: "allow" },
];

export default function QueuePage() {
  const [filter, setFilter] = useState<string | null>(null);
  const { rows, error, loaded } = useVerdictQueue(filter);
  const [selected, setSelected] = useState<Verdict | null>(null);
  const { base, key } = useApi();

  const current = useMemo(() => {
    if (selected) {
      const refreshed = rows.find((row) => row.event_id === selected.event_id);
      if (refreshed) return refreshed;
    }
    return rows[0] ?? null;
  }, [rows, selected]);

  return (
    <div className="grid gap-5 pt-5 lg:grid-cols-[380px_1fr]">
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h1 className="font-display text-[26px] leading-none">Ranked queue</h1>
          <span className="micro">{rows.length} shown &middot; refresh 5s</span>
        </div>

        <div className="flex gap-1">
          {FILTERS.map((item) => (
            <button
              key={item.label}
              onClick={() => setFilter(item.id)}
              className={`micro rounded-md border px-2.5 py-1 transition-colors ${
                filter === item.id
                  ? "border-hairline bg-raised text-text"
                  : "border-transparent text-muted hover:text-text"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {error && (
          <div className="rounded-lg border border-block/40 bg-block/5 p-4">
            <p className="micro text-block">api unreachable</p>
            <p className="data mt-1 text-[11px] text-muted">{error}</p>
            <p className="mt-2 text-[12px] text-muted">
              Start the service with <code className="data text-amber">make serve</code>, then load
              data with <code className="data text-amber">make backfill</code>.
            </p>
          </div>
        )}

        {loaded && !error && rows.length === 0 && (
          <div className="rounded-lg border border-hairline bg-panel p-4 text-[13px] text-muted">
            No verdicts yet. Ingest events or run the replay view.
          </div>
        )}

        <ul className="flex flex-col divide-y divide-hairline-soft overflow-hidden rounded-lg border border-hairline bg-panel">
          {rows.map((row) => (
            <li key={row.event_id}>
              <button
                onClick={() => setSelected(row)}
                className={`grid w-full grid-cols-[38px_86px_1fr_62px] items-center gap-3 px-3 py-2.5 text-left transition-colors ${
                  current?.event_id === row.event_id ? "bg-raised" : "hover:bg-raised/60"
                }`}
              >
                <ScoreNumber score={row.score} />
                <VerdictBadge verdict={row.verdict} />
                <span className="data truncate text-[11px] text-muted">
                  {shortId(row.event_id, 16)}
                  {row.reason_codes[0] ? ` \u00b7 ${row.reason_codes[0].replace("RNG_", "").toLowerCase()}` : ""}
                </span>
                <span className="micro text-right">{timeAgo(row.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>

        <p className="micro leading-relaxed">
          verdicts are recommendations &middot; block rec requires a human decision &middot; api{" "}
          {base.replace(/^https?:\/\//, "")} with key {key.slice(0, 4)}&hellip;
        </p>
      </section>

      {current ? (
        <EvidencePanel verdict={current} reviewAt={35} blockAt={49} />
      ) : (
        <section className="flex h-96 items-center justify-center rounded-lg border border-hairline bg-panel">
          <span className="micro">select a verdict</span>
        </section>
      )}
    </div>
  );
}
