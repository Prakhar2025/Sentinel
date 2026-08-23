/*
  Static demo mode: when NEXT_PUBLIC_DEMO=1 the console serves baked
  fixtures instead of the live API, enabling a zero-backend, zero-key,
  zero-cost deployment (the clickable outreach link). The replay is a
  recorded run, labeled as such on screen. Nothing updates; nothing
  calls anything.
*/
import queueFixture from "@/demo/queue.json";
import evaluationFixture from "@/demo/evaluation.json";
import scenarioFixture from "@/demo/scenario.json";
import clustersFixture from "@/demo/clusters.json";
import type { Scenario, Verdict } from "@/lib/api";

export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO === "1";

export function demoQueue(): Verdict[] {
  return queueFixture as unknown as Verdict[];
}

export function demoEvaluation() {
  return evaluationFixture as unknown as {
    metrics: Record<string, unknown>;
    latency?: { p50_ms: number; p95_ms: number; events: number };
  };
}

export function demoScenario(): Scenario {
  return scenarioFixture as unknown as Scenario;
}

export function demoCluster(customerId: string) {
  const map = clustersFixture as unknown as Record<string, unknown>;
  return (map[customerId] as ReturnType<typeof JSON.parse>) ?? null;
}

export interface DemoFeedRow {
  index: number;
  merchant: string;
  customer: string;
  amount_paise: number;
  score: number;
  verdict: "ALLOW" | "REVIEW" | "BLOCK_REC";
  duplicate: boolean;
}

export function demoFeed(): DemoFeedRow[] {
  const scenario = scenarioFixture as unknown as { recorded_feed?: DemoFeedRow[] };
  return scenario.recorded_feed ?? [];
}
