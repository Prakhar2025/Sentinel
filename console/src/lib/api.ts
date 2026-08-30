"use client";

import { useEffect, useState } from "react";

/*
  Demo-scope client (docs/07): the console runs locally against the API
  and uses only the standard API key, which is intentionally visible
  here. A production deployment replaces this with a server-side
  proxy and per-merchant OAuth (documented in the security doc).
*/

import { DEMO_MODE, demoCluster, demoEvaluation, demoQueue, demoScenario } from "@/lib/demo";

const FALLBACK_BASE = "http://localhost:8000";
const FALLBACK_KEY = "dev-sentinel-key";

export function useApi() {
  const base = process.env.NEXT_PUBLIC_API_URL || FALLBACK_BASE;
  const key = process.env.NEXT_PUBLIC_API_KEY || FALLBACK_KEY;
  return { base, key };
}

export interface Verdict {
  verdict_id: string;
  event_id: string;
  score: number;
  verdict: "ALLOW" | "REVIEW" | "BLOCK_REC";
  reason_codes: string[];
  evidence: Record<string, unknown> & {
    linked_merchants?: string[];
    shared_devices?: { device_id: string; linked_identities: number; merchant_count: number }[];
    taint?: number;
    taint_path?: string[];
    cluster?: { customers?: number; truncated?: boolean };
  };
  features: Record<string, number>;
  contributions: Record<string, number>;
  explanation: string | null;
  explanation_status: "PENDING" | "DONE" | "SKIPPED" | "FAILED" | "CAP_REACHED";
  created_at: string;
}

export interface ScenarioEvent {
  event_id: string;
  merchant_id: string;
  customer_id: string;
  amount_paise: number;
  upi_vpa: string | null;
  phone: string | null;
  device_id: string | null;
  email: string | null;
  ip: string | null;
  ts: string;
  payment_method: string;
  prior_outcome: string | null;
}

export interface Scenario {
  ring_id: string;
  strategy: string;
  merchants: string[];
  events: ScenarioEvent[];
}

async function request<T>(base: string, key: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { "X-API-Key": key, "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${detail.slice(0, 200)}`);
  }
  return response.json() as Promise<T>;
}

export function useVerdictQueue(filter: string | null) {
  const { base, key } = useApi();
  const [rows, setRows] = useState<Verdict[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (DEMO_MODE) {
        setRows(demoQueue());
        setLoaded(true);
        return;
      }
      try {
        const params = new URLSearchParams({ limit: "50" });
        if (filter) params.set("verdict", filter);
        const data = await request<Verdict[]>(base, key, `/v1/verdicts?${params.toString()}`);
        if (!cancelled) {
          setRows(Array.isArray(data) ? data : []);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "request failed");
      } finally {
        if (!cancelled) setLoaded(true);
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [base, key, filter]);

  return { rows, error, loaded };
}

export async function fetchVerdict(base: string, key: string, eventId: string): Promise<Verdict> {
  return request<Verdict>(base, key, `/v1/verdicts/${eventId}`);
}

export async function fetchCluster(base: string, key: string, customerId: string) {
  if (DEMO_MODE) return demoCluster(customerId);
  return request<{
    customer_id: string;
    nodes: { type: string; id: string; taint: number }[];
    edges: { source: string; target: string }[];
    truncated: boolean;
  }>(base, key, `/v1/graph/cluster/${customerId}`);
}

export async function fetchEvaluation(base: string, key: string) {
  if (DEMO_MODE) return demoEvaluation();
  return request<{
    metrics: Record<string, unknown>;
    latency?: { p50_ms: number; p95_ms: number; events: number };
  }>(base, key, "/v1/evaluation");
}

export async function fetchScenario(base: string, key: string): Promise<Scenario> {
  if (DEMO_MODE) return demoScenario();
  return request<Scenario>(base, key, "/v1/demo/scenario");
}

export async function explainLive(
  base: string,
  key: string,
  eventId: string
): Promise<{ explanation: string | null; explanation_status: string; cap: Record<string, string | number> }> {
  const response = await fetch(`${base}/v1/explain/${eventId}`, {
    method: "POST",
    headers: { "X-API-Key": key, "Content-Type": "application/json" },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(`${response.status} ${JSON.stringify(body).slice(0, 160)}`);
  return body;
}

export async function ingestEvent(base: string, key: string, event: ScenarioEvent) {
  const response = await fetch(`${base}/v1/events`, {
    method: "POST",
    headers: { "X-API-Key": key, "Content-Type": "application/json" },
    body: JSON.stringify(event),
  });
  const body = await response.json();
  if (!response.ok && response.status !== 409) {
    throw new Error(`${response.status} ${JSON.stringify(body).slice(0, 160)}`);
  }
  return { status: response.status, body } as { status: number; body: Verdict & { verdict?: Verdict } };
}
