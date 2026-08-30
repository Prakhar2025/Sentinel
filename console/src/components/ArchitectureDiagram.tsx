"use client";

/*
  The pipeline, drawn by hand in the watchroom style: event in on the
  left, verdict out on the right, the deterministic spine in the middle,
  the LLM hanging off it asynchronously (it never scores), and the audit
  store underneath. Same visual language as the cluster graph.
*/

import { useEffect, useState } from "react";

const INK = "#15171c";
const TEXT = "#e8e3d5";
const MUTED = "#8b8574";
const FAINT = "#565246";
const AMBER = "#e8a33d";
const ALLOW = "#4cc38a";
const BLOCK = "#e5484d";
const LINE = "#31363f";

const W = 1100;
const H = 320;

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  sub: string;
  color: string;
}

const SPINE_Y = 90;
const SPINE_H = 62;
const BOX_GAP = 55;

const BOXES: Box[] = [
  { x: 30, y: SPINE_Y, w: 150, h: SPINE_H, label: "Event", sub: "payment in", color: "#8fb8d8" },
  { x: 30 + 205, y: SPINE_Y, w: 170, h: SPINE_H, label: "Normalize", sub: "E.164 / VPA", color: "#8fb8d8" },
  { x: 30 + 430, y: SPINE_Y, w: 170, h: SPINE_H, label: "Identity graph", sub: "taint / fanout", color: "#6fbfa8" },
  { x: 30 + 655, y: SPINE_Y, w: 150, h: SPINE_H, label: "Scorer", sub: "7 features", color: AMBER },
  { x: 30 + 860, y: SPINE_Y, w: 180, h: SPINE_H, label: "Verdict engine", sub: "ALLOW / REV / BLK", color: TEXT },
];

const LLM = { x: 460, y: 230, w: 160, h: 56 };
const AUDIT = { x: 890, y: 230, w: 150, h: 56 };

export function ArchitectureDiagram() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 100);
    return () => clearTimeout(timer);
  }, []);

  const enter = (delay: number) => ({
    opacity: mounted ? 1 : 0,
    transform: mounted ? "translateY(0)" : "translateY(8px)",
    transition: `opacity 0.5s ease ${delay}ms, transform 0.5s ease ${delay}ms`,
  });

  const spineY = SPINE_Y + SPINE_H / 2;

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

        {/* arrows between spine boxes */}
        {BOXES.slice(0, -1).map((box, index) => {
          const next = BOXES[index + 1];
          const y = spineY;
          return (
            <g key={`${box.x}-${next.x}`} style={enter(100 + index * 100)}>
              <path d={`M ${box.x + box.w} ${y} L ${next.x - 6} ${y}`} stroke={LINE} strokeWidth="1.6" markerEnd="url(#arrowhead)" />
              <path
                d={`M ${box.x + box.w} ${y} L ${next.x - 6} ${y}`}
                stroke={AMBER}
                strokeWidth="2.4"
                strokeDasharray="12 100"
                className="spine-flow"
                opacity="0.9"
              />
            </g>
          );
        })}

        {/* spine boxes */}
        {BOXES.map((box, index) => (
          <g key={box.label} style={enter(index * 120)}>
            <rect x={box.x} y={box.y} width={box.w} height={box.h} rx="8" fill={INK} stroke={box.color} strokeWidth="1.6" />
            <text x={box.x + box.w / 2} y={box.y + 26} textAnchor="middle" fontSize="14" fontWeight="600" fill={TEXT}>
              {box.label}
            </text>
            <text x={box.x + box.w / 2} y={box.y + 45} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
              {box.sub}
            </text>
          </g>
        ))}

        {/* verdict triad above the verdict engine */}
        {(
          [
            ["ALLOW", ALLOW, 895],
            ["REVIEW", AMBER, 970],
            ["BLOCK", BLOCK, 1040],
          ] as const
        ).map(([label, color, x], index) => (
          <g key={label} style={enter(600 + index * 80)}>
            <rect x={x} y={30} width={label === "REVIEW" ? 60 : 52} height={20} rx="4" fill={INK} stroke={color} strokeWidth="1.2" />
            <text x={x + (label === "REVIEW" ? 30 : 26)} y={44} textAnchor="middle" fontSize="8.5" fontFamily="var(--font-mono, monospace)" fill={color}>
              {label}
            </text>
          </g>
        ))}
        <path d={`M 950 ${52} L 950 ${SPINE_Y - 6}`} stroke={LINE} strokeWidth="1.4" markerEnd="url(#arrowhead)" opacity={mounted ? 0.8 : 0} style={{ transition: "opacity 0.4s ease 800ms" }} />

        {/* LLM branch: dashed amber, hanging off scorer */}
        <g style={enter(700)}>
          <rect x={LLM.x} y={LLM.y} width={LLM.w} height={LLM.h} rx="8" fill={INK} stroke={AMBER} strokeWidth="1.4" strokeDasharray="5 4" />
          <text x={LLM.x + LLM.w / 2} y={LLM.y + 24} textAnchor="middle" fontSize="13" fontWeight="600" fill={TEXT}>
            LLM narrative
          </text>
          <text x={LLM.x + LLM.w / 2} y={LLM.y + 42} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
            Bedrock / async
          </text>
          <path
            d={`M ${LLM.x + LLM.w / 2} ${SPINE_Y + SPINE_H} L ${LLM.x + LLM.w / 2} ${LLM.y - 6}`}
            stroke={AMBER}
            strokeWidth="1.4"
            strokeDasharray="5 4"
            fill="none"
            markerEnd="url(#amberhead)"
            opacity="0.8"
          />
          <text x={LLM.x + LLM.w / 2 + 10} y={LLM.y - 14} fontSize="9" fontFamily="var(--font-mono, monospace)" fill={FAINT} textAnchor="middle">
            never scores
          </text>
        </g>

        {/* audit store beneath verdict engine */}
        <g style={enter(820)}>
          <rect x={AUDIT.x} y={AUDIT.y} width={AUDIT.w} height={AUDIT.h} rx="8" fill={INK} stroke="#7a8391" strokeWidth="1.4" />
          <text x={AUDIT.x + AUDIT.w / 2} y={AUDIT.y + 24} textAnchor="middle" fontSize="13" fontWeight="600" fill={TEXT}>
            Audit store
          </text>
          <text x={AUDIT.x + AUDIT.w / 2} y={AUDIT.y + 42} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
            append-only
          </text>
          <path d={`M 965 ${SPINE_Y + SPINE_H} L 965 ${AUDIT.y - 6}`} stroke={LINE} strokeWidth="1.6" markerEnd="url(#arrowhead)" />
        </g>

        {/* bottom annotations: two clean blocks */}
        <g style={enter(900)}>
          <text x={30} y={270} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
            failure path: store down = spool + 503 REVIEW / LLM down = SKIPPED / never crash
          </text>
          <text x={30} y={290} fontSize="10" fontFamily="var(--font-mono, monospace)" fill={FAINT}>
            security: rate limited per IP / admin routes 404 on public demo / every verdict audited
          </text>
        </g>
      </svg>
      <figcaption className="micro px-2 pb-1 pt-2">
        the deterministic spine in the middle &middot; the LLM hangs off it asynchronously and never scores &middot; every verdict lands in the audit store
      </figcaption>
    </figure>
  );
}
