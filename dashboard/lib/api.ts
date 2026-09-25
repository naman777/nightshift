export const GATEWAY = '/api/gateway'; // same-origin proxy (app/api/gateway) that adds the server-side auth token

export type Incident = { id: string; fingerprint: string; status: string; created_at: number; updated_at: number };
export type Evidence = {
  id: string; agent: string; claim: string; evidence_query: string; evidence_result_ref: string;
  supports_hypothesis: string; confidence: number; created_at: number;
};
export type Step = { seq: number; agent: string; kind: string; name: string; detail: string; duration_ms: number; ts: number };
export type Audit = { seq: number; ts: number; agent: string; tool: string; tier: string; decision: string; reason: string; evidence_ids: string };
export type Action = { type: string; target: string; params: Record<string, unknown>; tier: string };
export type Report = {
  root_cause: string; service: string; category: string; confidence: number; evidence: string[];
  ruled_out: { hypothesis: string; evidence: string[] }[]; ranked: { root_cause: string; service: string; category: string; confidence: number }[];
  proposed_action: Action | null; usage: { cost_usd: number; llm_calls: number; tool_calls: number; input_tokens: number; output_tokens: number };
  rounds: number; degraded: boolean;
};
export type IncidentDetail = {
  incident: { id: string; status: string; report: Report | null; alert: { name?: string; service?: string; labels?: Record<string, string> } };
  evidence: Evidence[]; steps: Step[]; audit: Audit[];
};
export type BenchConfig = {
  runs: number; invalid: number; root_cause_accuracy: number; accuracy_std: number; top3_accuracy: number; judge_accuracy: number;
  remediation_quality: number; unsafe_action_rate: number; evidence_grounding: number; red_herring_accuracy: number; no_herring_accuracy: number;
  dev_accuracy: number | null; heldout_accuracy: number | null;
  cost_usd: { mean: number }; modeled_time_s: { p50: number; p95: number };
};
export type BenchSummary = { prompt_version?: string; split?: string; repeats?: number; scenarios?: number; policy?: string; configs: Record<string, BenchConfig> };

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${GATEWAY}${path}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export async function post(path: string, body: unknown): Promise<void> {
  const r = await fetch(`${GATEWAY}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
}
