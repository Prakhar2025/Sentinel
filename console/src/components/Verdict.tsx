export function VerdictBadge({ verdict }: { verdict: "ALLOW" | "REVIEW" | "BLOCK_REC" }) {
  const style =
    verdict === "BLOCK_REC"
      ? "border-block/40 bg-block/10 text-block"
      : verdict === "REVIEW"
        ? "border-amber/40 bg-amber/10 text-amber"
        : "border-allow/30 bg-allow/10 text-allow";
  const label = verdict === "BLOCK_REC" ? "BLOCK REC" : verdict;
  return (
    <span
      className={`data inline-flex items-center rounded-sm border px-1.5 py-0.5 text-[10px] font-medium tracking-[0.08em] ${style}`}
    >
      {label}
    </span>
  );
}

export function ScoreNumber({ score }: { score: number }) {
  const color = score >= 70 ? "text-block" : score >= 35 ? "text-amber" : "text-allow";
  return <span className={`data text-[15px] font-semibold ${color}`}>{score}</span>;
}

export function ScoreMeter({ score, reviewAt, blockAt }: { score: number; reviewAt: number; blockAt: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="micro">risk score</span>
        <span className="data text-[28px] font-semibold leading-none">{score}</span>
      </div>
      <div className="relative mt-3 h-1.5 rounded-full bg-raised">
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${
            score >= blockAt ? "bg-block" : score >= reviewAt ? "bg-amber" : "bg-allow"
          }`}
          style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
        />
        <div className="absolute inset-y-[-3px] w-px bg-hairline" style={{ left: `${reviewAt}%` }} />
        <div className="absolute inset-y-[-3px] w-px bg-hairline" style={{ left: `${blockAt}%` }} />
      </div>
      <div className="micro mt-1.5 flex justify-between">
        <span>0</span>
        <span>review {reviewAt}</span>
        <span>block {blockAt}</span>
        <span>100</span>
      </div>
    </div>
  );
}

export function ReasonChip({ code }: { code: string }) {
  const system = code === "SYS_DEGRADED";
  return (
    <span
      className={`data rounded-sm border px-1.5 py-0.5 text-[10px] tracking-[0.06em] ${
        system ? "border-block/50 text-block" : "border-hairline bg-raised text-muted"
      }`}
    >
      {code}
    </span>
  );
}
