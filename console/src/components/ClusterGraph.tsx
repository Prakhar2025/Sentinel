"use client";

/*
  The identity cluster, drawn by hand as a radial observatory plot:
  the subject customer sits at the aperture; identity entities occupy
  the inner ring; merchants the outer perimeter. Tainted nodes breathe.
  No graph library: this is ours, glyph by glyph.
*/

const ENTITY_COLOR: Record<string, string> = {
  customer: "#e8e3d5",
  device: "#8fb8d8",
  upi: "#6fbfa8",
  phone: "#d8b36a",
  email: "#b8a88f",
  merchant: "#7a8391",
};

const GLYPH: Record<string, string> = {
  customer: "C",
  device: "D",
  upi: "V",
  phone: "P",
  email: "E",
  merchant: "M",
};

export interface ClusterNode {
  type: string;
  id: string;
  taint: number;
}

export interface ClusterData {
  customer_id: string;
  nodes: ClusterNode[];
  edges: { source: string; target: string }[];
  truncated: boolean;
}

interface Placed extends ClusterNode {
  x: number;
  y: number;
  r: number;
  color: string;
}

const WIDTH = 420;
const HEIGHT = 320;
const CENTER = { x: WIDTH / 2, y: HEIGHT / 2 };

function place(cluster: ClusterData, subject: string): Placed[] {
  const entities = cluster.nodes.filter(
    (n) => n.type !== "merchant" && n.id !== subject
  );
  const merchants = cluster.nodes.filter((n) => n.type === "merchant");
  const placed: Placed[] = [];

  const subjectNode = cluster.nodes.find((n) => n.id === subject);
  if (subjectNode) {
    placed.push({
      ...subjectNode,
      x: CENTER.x,
      y: CENTER.y,
      r: 16,
      color: ENTITY_COLOR.customer,
    });
  }

  entities.slice(0, 12).forEach((node, index) => {
    const angle = (index / Math.max(entities.length, 1)) * Math.PI * 2 - Math.PI / 2;
    const wobble = index % 2 === 0 ? 0 : 0.35;
    const radius = 78 + wobble * 26;
    placed.push({
      ...node,
      x: CENTER.x + Math.cos(angle) * radius,
      y: CENTER.y + Math.sin(angle) * radius * 0.78,
      r: 11,
      color: ENTITY_COLOR[node.type] || "#8b8574",
    });
  });

  merchants.slice(0, 10).forEach((node, index) => {
    const angle = (index / Math.max(merchants.length, 1)) * Math.PI * 2 - Math.PI / 2;
    placed.push({
      ...node,
      x: CENTER.x + Math.cos(angle) * 168,
      y: CENTER.y + Math.sin(angle) * 118,
      r: 9,
      color: ENTITY_COLOR.merchant,
    });
  });

  return placed;
}

export function ClusterGraph({ cluster, subject }: { cluster: ClusterData; subject: string }) {
  const placed = place(cluster, subject);
  const byId = new Map<string, Placed>(placed.map((p) => [`${p.type}:${p.id}`, p]));

  const edges = cluster.edges
    .map((edge) => ({ from: byId.get(edge.source), to: byId.get(edge.target) }))
    .filter(
      (edge): edge is { from: Placed; to: Placed } =>
        Boolean(edge.from) && Boolean(edge.to)
    );

  return (
    <figure className="rounded-lg border border-hairline bg-panel p-2">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="img" aria-label="identity cluster">
        <defs>
          <pattern id="grid" width="26" height="26" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.8" fill="#22262e" />
          </pattern>
        </defs>
        <rect width={WIDTH} height={HEIGHT} fill="url(#grid)" rx="6" />

        {/* faint radar rings behind the plot */}
        <circle cx={CENTER.x} cy={CENTER.y} r="62" fill="none" stroke="#1f232a" />
        <circle cx={CENTER.x} cy={CENTER.y} r="118" fill="none" stroke="#1f232a" strokeDasharray="2 6" />

        {edges.map((edge, index) => {
          const tainted = (edge.from.taint ?? 0) >= 0.3 || (edge.to.taint ?? 0) >= 0.3;
          return (
            <line
              key={index}
              x1={edge.from.x}
              y1={edge.from.y}
              x2={edge.to.x}
              y2={edge.to.y}
              stroke={tainted ? "#e5484d" : "#31363f"}
              strokeWidth={tainted ? 1.4 : 1}
              strokeDasharray={tainted ? "4 4" : undefined}
              opacity={tainted ? 0.9 : 0.7}
              className={tainted ? "taint-pulse" : undefined}
            />
          );
        })}

        {placed.map((node) => {
          const tainted = (node.taint ?? 0) >= 0.3;
          return (
            <g key={`${node.type}:${node.id}`}>
              {tainted && (
                <circle cx={node.x} cy={node.y} r={node.r + 5} fill="none" stroke="#e5484d" strokeOpacity="0.5" className="taint-pulse" />
              )}
              <circle
                cx={node.x}
                cy={node.y}
                r={node.r}
                fill="#15171c"
                stroke={node.color}
                strokeWidth={node.id === subject ? 2.4 : 1.4}
              />
              <text
                x={node.x}
                y={node.y + 3.5}
                textAnchor="middle"
                fontSize={node.r > 12 ? 11 : 9}
                fontFamily="var(--font-mono, monospace)"
                fill={node.color}
              >
                {GLYPH[node.type] ?? "?"}
              </text>
              {node.type !== "customer" && (
                <text
                  x={node.x}
                  y={node.y - node.r - 5}
                  textAnchor="middle"
                  fontSize="7.5"
                  fontFamily="var(--font-mono, monospace)"
                  fill="#565246"
                >
                  {node.id.length > 14 ? `${node.id.slice(0, 13)}\u2026` : node.id}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <figcaption className="micro flex items-center justify-between px-2 pb-1 pt-2">
        <span>identity cluster &middot; C customer &middot; D device &middot; V vpa &middot; P phone &middot; M merchant</span>
        {cluster.truncated && <span className="text-amber">truncated view</span>}
      </figcaption>
    </figure>
  );
}
