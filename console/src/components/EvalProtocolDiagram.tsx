"use client";

/*
  The evaluation protocol, drawn clean: one dataset fans out into three
  ring-stratified splits, weights freeze under train and thresholds
  lock under calibration, and the test box arrows once into the
  held-out verdicts. Entrance staggers left to right.
*/

import { useEffect, useState } from "react";

const TEXT = "#e8e3d5";
const MUTED = "#8b8574";
const AMBER = "#e8a33d";
const LINE = "#31363f";
const TRAIN = "#6fbfa8";
const CAL = "#d8b36a";
const TEST = "#e5484d";

const W = 920;
const H = 210;

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

  const splitY = 70;
  const splitH = 58;

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

        <g style={enter(0)}>
          <rect x={24} y={splitY} width={130} height={splitH} rx="8" fill="#15171c" stroke={TEXT} strokeWidth="1.6" />
          <text x={89} y={splitY + 24} textAnchor="middle" fontSize="12.5" fontWeight="600" fill={TEXT}>
            1,000 events
          </text>
          <text x={89} y={splitY + 42} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
            seed 42 · 100 fraud
          </text>
        </g>

        {(
          [
            [248],
            [418],
            [588],
          ] as const
        ).map(([x], index) => (
          <path
            key={x}
            d={`M 154 ${splitY + splitH / 2} C 190 ${splitY + splitH / 2}, 200 ${splitY + splitH / 2}, ${x - 6} ${splitY + splitH / 2}`}
            stroke={LINE}
            strokeWidth="1.4"
            fill="none"
            markerEnd="url(#evalhead)"
            opacity={mounted ? 0.85 : 0}
            style={{ transition: `opacity 0.4s ease ${200 + index * 120}ms` }}
          />
        ))}

        {(
          [
            ["TRAIN 60%", TRAIN, "weights fit here", 250],
            ["CALIB 20%", CAL, "thresholds locked", 420],
            ["TEST 20%", TEST, "touched once", 590],
          ] as const
        ).map(([label, color, sub, x], index) => (
          <g key={label} style={enter(250 + index * 140)}>
            <rect x={x} y={splitY} width={140} height={splitH} rx="8" fill="#15171c" stroke={color} strokeWidth="1.6" />
            <text x={x + 70} y={splitY + 24} textAnchor="middle" fontSize="12" fontWeight="600" fill={color}>
              {label}
            </text>
            <text x={x + 70} y={splitY + 42} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
              {sub}
            </text>
          </g>
        ))}

        {(
          [
            ["weights frozen · published", 250, TRAIN],
            ["thresholds locked · 42 / 49", 420, CAL],
          ] as const
        ).map(([label, x, color], index) => (
          <g key={label} style={enter(650 + index * 120)}>
            <line
              x1={x + 70}
              y1={splitY + splitH}
              x2={x + 70}
              y2={162}
              stroke={color}
              strokeWidth="1.2"
              strokeDasharray="3 3"
              opacity="0.7"
              markerEnd="url(#evalhead)"
            />
            <rect x={x} y={164} width={140} height={34} rx="6" fill="#15171c" stroke={color} strokeWidth="1.1" strokeDasharray="4 3" />
            <text x={x + 70} y={185} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono, monospace)" fill={TEXT}>
              {label}
            </text>
          </g>
        ))}

        <g style={enter(1000)}>
          <path
            d={`M 730 ${splitY + splitH / 2} L ${758 - 6} ${splitY + splitH / 2}`}
            stroke={TEST}
            strokeWidth="1.6"
            fill="none"
            markerEnd="url(#testhead)"
          />
          <rect x={760} y={splitY} width={136} height={splitH} rx="8" fill="#15171c" stroke={TEST} strokeWidth="1.8" />
          <text x={828} y={splitY + 24} textAnchor="middle" fontSize="12" fontWeight="600" fill={TEST}>
            held-out verdicts
          </text>
          <text x={828} y={splitY + 42} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono, monospace)" fill={MUTED}>
            P 0.833 · R 0.882 · 2/2 rings
          </text>
        </g>
      </svg>
      <figcaption className="micro px-2 pb-1 pt-2">
        order of operations: weights on train, thresholds on calibration, one single pass on test · peeking forfeits the protocol that makes any number meaningful
      </figcaption>
    </figure>
  );
}
