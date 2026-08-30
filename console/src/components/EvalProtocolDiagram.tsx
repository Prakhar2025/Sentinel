"use client";

/*
  The evaluation protocol, drawn clean: one dataset fans out into three
  ring-stratified splits, weights freeze under train and thresholds
  lock under calibration, and the test box arrows once into the
  held-out verdicts. Every string is measured to fit its box.
*/

import { useEffect, useState } from "react";

const TEXT = "#e8e3d5";
const MUTED = "#8b8574";
const LINE = "#31363f";
const TRAIN = "#6fbfa8";
const CAL = "#d8b36a";
const TEST = "#e5484d";

const W = 1000;
const H = 230;
const SPLIT_Y = 76;
const SPLIT_H = 64;
const SPLIT_W = 150;

export function EvalProtocolDiagram() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 150);
    return () => clearTimeout(timer);
  }, []);

  const enter = (delay: number) => ({
    opacity: mounted ? 1 : 0,
    transform: mounted ? "translateY(0)" : "translateY(8px)",
    transition: `opacity 0.5s ease ${delay}ms, transform 0.5s ease ${delay}ms`,
  });

  const midY = SPLIT_Y + SPLIT_H / 2;
  const splits = [
    { label: "TRAIN 60%", color: TRAIN, sub: "weights fit here", x: 240 },
    { label: "CALIB 20%", color: CAL, sub: "thresholds locked", x: 424 },
    { label: "TEST 20%", color: TEST, sub: "touched once", x: 608 },
  ];
  const freezes = [
    { line1: "weights frozen", line2: "published in code", x: 240, color: TRAIN },
    { line1: "thresholds locked", line2: "42 / 49", x: 424, color: CAL },
  ];

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
          <marker id="testhead" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
            <path d="M0,0 L7,3 L0,6 Z" fill={TEST} />
          </marker>
        </defs>
        <rect width={W} height={H} fill="url(#evalgrid)" rx="6" />

        {/* dataset */}
        <g style={enter(0)}>
          <rect x={30} y={SPLIT_Y} width={140} height={SPLIT_H} rx="8" fill="#15171c" stroke={TEXT} strokeWidth="1.6" />
          <text x={100} y={SPLIT_Y + 26} textAnchor="middle" fontSize="13" fontWeight="600" fill={TEXT}>
            1,000 events
          </text>
          <text x={100} y={SPLIT_Y + 46} textAnchor="middle" fontSize="9.5" fontFamily="var(--font-mono, monospace)" fill="#8b8574">
            seed 42 · 100 fraud
          </text>
        </g>

        {/* fan-out curves */}
        {splits.map((split, index) => (
          <path
            key={split.x}
            d={`M 170 ${midY} C 200 ${midY}, 205 ${midY}, ${split.x - 6} ${midY}`}
            stroke={LINE}
            strokeWidth="1.4"
            fill="none"
            markerEnd="url(#evalhead)"
            opacity={mounted ? 0.85 : 0}
            style={{ transition: `opacity 0.4s ease ${200 + index * 120}ms` }}
          />
        ))}

        {/* three splits, one row */}
        {splits.map((split, index) => (
          <g key={split.label} style={enter(250 + index * 140)}>
            <rect x={split.x} y={SPLIT_Y} width={SPLIT_W} height={SPLIT_H} rx="8" fill="#15171c" stroke={split.color} strokeWidth="1.6" />
            <text x={split.x + SPLIT_W / 2} y={SPLIT_Y + 25} textAnchor="middle" fontSize="12.5" fontWeight="600" fill={split.color}>
              {split.label}
            </text>
            <text x={split.x + SPLIT_W / 2} y={SPLIT_Y + 45} textAnchor="middle" fontSize="9.5" fontFamily="var(--font-mono, monospace)" fill="#8b8574">
              {split.sub}
            </text>
          </g>
        ))}

        {/* freeze boxes directly beneath their splits */}
        {freezes.map((freeze, index) => (
          <g key={freeze.line1} style={enter(650 + index * 120)}>
            <line
              x1={freeze.x + SPLIT_W / 2}
              y1={SPLIT_Y + SPLIT_H}
              x2={freeze.x + SPLIT_W / 2}
              y2={168}
              stroke={freeze.color}
              strokeWidth="1.2"
              strokeDasharray="3 3"
              opacity="0.7"
              markerEnd="url(#evalhead)"
            />
            <rect x={freeze.x} y={170} width={SPLIT_W} height={44} rx="6" fill="#15171c" stroke={freeze.color} strokeWidth="1.1" strokeDasharray="4 3" />
            <text x={freeze.x + SPLIT_W / 2} y={188} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono, monospace)" fill={TEXT}>
              {freeze.line1}
            </text>
            <text x={freeze.x + SPLIT_W / 2} y={203} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
              {freeze.line2}
            </text>
          </g>
        ))}

        {/* test flows once into held-out verdicts */}
        <g style={enter(1000)}>
          <path
            d={`M ${608 + SPLIT_W} ${midY} L ${774 - 6} ${midY}`}
            stroke={TEST}
            strokeWidth="1.6"
            fill="none"
            markerEnd="url(#testhead)"
          />
          <rect x={776} y={SPLIT_Y} width={190} height={SPLIT_H} rx="8" fill="#15171c" stroke={TEST} strokeWidth="1.8" />
          <text x={776 + 95} y={SPLIT_Y + 26} textAnchor="middle" fontSize="12.5" fontWeight="600" fill={TEST}>
            held-out verdicts
          </text>
          <text x={776 + 95} y={SPLIT_Y + 46} textAnchor="middle" fontSize="9.5" fontFamily="var(--font-mono, monospace)" fill="#8b8574">
            P 0.833 / R 0.882 / 2 of 2
          </text>
        </g>
      </svg>
      <figcaption className="micro px-2 pb-1 pt-2">
        order of operations: weights on train, thresholds on calibration, one single pass on test · ring-stratified so no identity spans splits · peeking forfeits the protocol
      </figcaption>
    </figure>
  );
}
