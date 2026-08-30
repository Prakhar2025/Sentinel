"use client";

/*
  The pipeline, drawn by hand in the watchroom style: event in on the
  left, verdict out on the right, the deterministic spine in the middle,
  the LLM hanging off it asynchronously (it never scores), and the audit
  store underneath. Same visual language as the cluster graph.
*/

const INK = "#15171c";
const TEXT = "#e8e3d5";
const MUTED = "#8b8574";
const FAINT = "#565246";
const AMBER = "#e8a33d";
const ALLOW = "#4cc38a";
const BLOCK = "#e5484d";
const LINE = "#31363f";

const W = 920;
const H = 300;

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  sub: string;
  color: string;
}

const BOXES: Box[] = [
  { x: 20, y: 92, w: 120, h: 56, label: "Event", sub: "payment in", color: "#8fb8d8" },
  { x: 180, y: 92, w: 130, h: 56, label: "Normalize", sub: "E.164 · VPA · device", color: "#8fb8d8" },
  { x: 350, y: 92, w: 130, h: 56, label: "Identity graph", sub: "taint · fan-out", color: "#6fbfa8" },
  { x: 520, y: 92, w: 130, h: 56, label: "Scorer", sub: "7 features · 2-4 ms", color: "#e8a33d" },
  { x: 710, y: 92, w: 150, h: 56, label: "Verdict engine", sub: "ALLOW / REVIEW / BLOCK", color: TEXT },
];

const LLM = { x: 520, y: 210, w: 130, h: 52 };
const AUDIT = { x: 710, y: 210, w: 150, h: 52 };

function arrow(x1: number, x2: number, y: number) {
  return (
    <path
      key={`${x1}-${x2}`}
      d={`M ${x1} ${y} L ${x2 - 6} ${y}`}
      stroke={LINE}
      strokeWidth="1.6"
      markerEnd="url(#arrowhead)"
    />
  );
}

export function ArchitectureDiagram() {
  const spineY = 92 + 28;
  return (
    <figure className="rounded-lg border border-hairline bg-panel p-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="system architecture">
        <defs>
          <pattern id="archgrid" width="26" height="26" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.8" fill="#1c2027" />
          </pattern>
          <marker id="arrowhead" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
            <path d="M0,0 L7,3 L0,6 Z" fill={LINE} />
          </marker>
          <marker id="amberhead" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
            <path d="M0,0 L7,3 L0,6 Z" fill={AMBER} />
          </marker>
        </defs>
        <rect width={W} height={H} fill="url(#archgrid)" rx="6" />

        {/* deterministic spine */}
        {BOXES.slice(0, -1).map((box, index) => {
          const next = BOXES[index + 1];
          return arrow(box.x + box.w, next.x, spineY);
        })}
        {BOXES.map((box) => (
          <g key={box.label}>
            <rect
              x={box.x}
              y={box.y}
              width={box.w}
              height={box.h}
              rx="8"
              fill={INK}
              stroke={box.color}
              strokeWidth="1.6"
            />
            <text x={box.x + box.w / 2} y={box.y + 24} textAnchor="middle" fontSize="13" fontWeight="600" fill={TEXT}>
              {box.label}
            </text>
            <text x={box.x + box.w / 2} y={box.y + 41} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
              {box.sub}
            </text>
          </g>
        ))}

        {/* verdict triad */}
        {(
          [
            ["ALLOW", ALLOW, 668],
            ["REVIEW", AMBER, 756],
            ["BLOCK", BLOCK, 844],
          ] as const
        ).map(([label, color, x]) => (
          <g key={label}>
            <rect x={x} y={30} width={64} height={22} rx="4" fill={INK} stroke={color} strokeWidth="1.2" />
            <text x={x + 32} y={45} textAnchor="middle" fontSize="9.5" fontFamily="var(--font-mono, monospace)" fill={color}>
              {label}
            </text>
            <line x1={x + 32} y1={54} x2={x + 32} y2={72} stroke={color} strokeWidth="1" opacity="0.5" />
          </g>
        ))}
        <path d={`M 785 88 L 785 74`} stroke={LINE} strokeWidth="1.6" markerEnd="url(#arrowhead)" />

        {/* async LLM branch */}
        <rect
          x={LLM.x}
          y={LLM.y}
          width={LLM.w}
          height={LLM.h}
          rx="8"
          fill={INK}
          stroke={AMBER}
          strokeWidth="1.4"
          strokeDasharray="5 4"
        />
        <text x={LLM.x + LLM.w / 2} y={LLM.y + 22} textAnchor="middle" fontSize="12.5" fontWeight="600" fill={TEXT}>
          LLM narrative
        </text>
        <text x={LLM.x + LLM.w / 2} y={LLM.y + 39} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
          Bedrock · async · capped
        </text>
        <path
          d={`M 585 ${92 + 56} C 585 ${LLM.y - 40}, 585 ${LLM.y - 24}, 585 ${LLM.y - 6}`}
          stroke={AMBER}
          strokeWidth="1.4"
          strokeDasharray="5 4"
          fill="none"
          markerEnd="url(#amberhead)"
          opacity="0.8"
        />
        <text x={LLM.x + LLM.w / 2} y={LLM.y - 14} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          evidence only, never scores
        </text>

        {/* audit store */}
        <rect
          x={AUDIT.x}
          y={AUDIT.y}
          width={AUDIT.w}
          height={AUDIT.h}
          rx="8"
          fill={INK}
          stroke="#7a8391"
          strokeWidth="1.4"
        />
        <text x={AUDIT.x + AUDIT.w / 2} y={AUDIT.y + 22} textAnchor="middle" fontSize="12.5" fontWeight="600" fill={TEXT}>
          Audit store
        </text>
        <text x={AUDIT.x + AUDIT.w / 2} y={AUDIT.y + 39} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
          append-only · every verdict
        </text>
        <path d={`M 785 ${92 + 56} L 785 ${AUDIT.y - 6}`} stroke={LINE} strokeWidth="1.6" markerEnd="url(#arrowhead)" />

        {/* degradation annotation */}
        <text x={20} y={214} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          failure path:
        </text>
        <text x={20} y={230} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          store down = spool +
        </text>
        <text x={20} y={246} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          REVIEW · llm down =
        </text>
        <text x={20} y={262} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          SKIPPED · never crash
        </text>
        <line x1={140} y1={214} x2={140} y2={262} stroke={LINE} strokeWidth="1" />
        <text x={152} y={214} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          threats + controls:
        </text>
        <text x={152} y={230} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          rate limit per IP,
        </text>
        <text x={152} y={246} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          admin routes 404 on
        </text>
        <text x={152} y={262} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
          public demo · audit all
        </text>
      </svg>
      <figcaption className="micro px-2 pb-1 pt-2">
        the deterministic spine in the middle &middot; the LLM hangs off it asynchronously and never scores &middot; every verdict lands in the audit store
      </figcaption>
    </figure>
  );
}
