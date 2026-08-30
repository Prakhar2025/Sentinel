"use client";

/*
  The evaluation protocol, drawn: one dataset, ring-stratified splits,
  weights fit on train, thresholds locked on calibration, a single pass
  on the held-out test set. The lock marks what can never be retouched.
*/

const TEXT = "#e8e3d5";
const MUTED = "#8b8574";
const FAINT = "#565246";
const AMBER = "#e8a33d";
const ALLOW = "#4cc38a";
const BLOCK = "#e5484d";
const LINE = "#31363f";
const TRAIN = "#6fbfa8";
const CAL = "#d8b36a";
const TEST = "#e5484d";

const W = 920;
const H = 250;

export function EvalProtocolDiagram() {
  return (
    <figure className="rounded-lg border border-hairline bg-panel p-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="evaluation protocol">
        <defs>
          <pattern id="evalgrid" width="26" height="26" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.8" fill="#1c2027" />
          </pattern>
          <marker id="evalhead" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
            <path d="M0,0 L7,3 L0,6 Z" fill={LINE} />
          </marker>
        </defs>
        <rect width={W} height={H} fill="url(#evalgrid)" rx="6" />

        {/* dataset */}
        <rect x={24} y={92} width={120} height={56} rx="8" fill="#15171c" stroke={TEXT} strokeWidth="1.6" />
        <text x={84} y={114} textAnchor="middle" fontSize="12.5" fontWeight="600" fill={TEXT}>
          1,000 events
        </text>
        <text x={84} y={132} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
          seed 42 · 100 fraud
        </text>

        {/* splits */}
        {(
          [
            ["TRAIN 60%", TRAIN, "weights fit here"],
            ["CALIB 20%", CAL, "thresholds locked"],
            ["TEST 20%", TEST, "touched ONCE"],
          ] as const
        ).map(([label, color, sub], index) => (
          <g key={label}>
            <rect
              x={230 + index * 150}
              y={index === 2 ? 60 : 92}
              width={130}
              height={56}
              rx="8"
              fill="#15171c"
              stroke={color}
              strokeWidth="1.6"
            />
            <text x={295 + index * 150} y={index === 2 ? 84 : 116} textAnchor="middle" fontSize="12" fontWeight="600" fill={color}>
              {label}
            </text>
            <text
              x={295 + index * 150}
              y={index === 2 ? 100 : 132}
              textAnchor="middle"
              fontSize="9"
              fontFamily="var(--font-mono, monospace)"
              fill={MUTED}
            >
              {sub}
            </text>
            <path
              d={`M 144 ${index === 2 ? 100 : 118} L ${224 - 6} ${index === 2 ? 88 : 120}`}
              stroke={LINE}
              strokeWidth="1.4"
              markerEnd="url(#evalhead)"
              opacity="0.8"
            />
          </g>
        ))}

        {/* protocol rail */}
        <text x={230} y={30} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          ring-stratified: no identity spans two splits (union-find enforced, tested)
        </text>
        <line x1={230} y1={40} x2={660} y2={40} stroke={LINE} strokeWidth="1" />

        {/* locks */}
        {(
          [
            ["weights frozen", "published in code", 230, TRAIN],
            ["thresholds locked", "review 42 · block 49", 380, CAL],
          ] as const
        ).map(([label, sub, x, color]) => (
          <g key={label}>
            <rect x={x} y={170} width={130} height={44} rx="8" fill="#15171c" stroke={color} strokeWidth="1.2" strokeDasharray="4 3" />
            <text x={x + 65} y={188} textAnchor="middle" fontSize="10.5" fontFamily="var(--font-mono, monospace)" fill={TEXT}>
              {label}
            </text>
            <text x={x + 65} y={204} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
              {sub}
            </text>
          </g>
        ))}

        {/* single test pass */}
        <path d={`M 725 88 C 790 70, 820 90, 838 108`} stroke={TEST} strokeWidth="1.6" fill="none" markerEnd="url(#evalhead)" />
        <rect x={764} y={112} width={132} height={56} rx="8" fill="#15171c" stroke={TEST} strokeWidth="1.8" />
        <text x={830} y={134} textAnchor="middle" fontSize="12" fontWeight="600" fill={TEST}>
          held-out verdicts
        </text>
        <text x={830} y={152} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
          P 0.833 · R 0.882 · 2/2 rings
        </text>

        {/* honesty note */}
        <text x={24} y={216} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          order of operations, non-negotiable:
        </text>
        <text x={24} y={232} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          weights (train) → thresholds (calibration) → one pass (test).
        </text>
        <text x={24} y={248} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          peeking at test data forfeits the protocol that makes any number meaningful.
        </text>
      </svg>
      <figcaption className="micro px-2 pb-1 pt-2">
        the honesty protocol &middot; every published number regenerates from make evaluate, byte-identical
      </figcaption>
    </figure>
  );
}
