import { Step, IncidentDetail } from './api';

export const SPECIALISTS = ['metrics', 'logs', 'changes', 'code'] as const;

export const AGENT: Record<string, { label: string; role: string }> = {
  commander: { label: 'Commander', role: 'Plans the investigation and decides the root cause' },
  metrics: { label: 'Metrics', role: 'Finds what deviates from baseline, and when' },
  logs: { label: 'Logs', role: 'Clusters errors and finds new failure signatures' },
  changes: { label: 'Changes', role: 'Checks deploys and config changes before onset' },
  code: { label: 'Code', role: 'Reads the code and runs the tests (sandboxed)' },
  remediation: { label: 'Remediation', role: 'Proposes a fix; the trust tier decides who may run it' },
  single: { label: 'Single agent', role: 'One agent does everything' },
};

const TOOL_VERB: Record<string, string> = {
  top_anomalies: 'scanning every metric for anomalies', query_range: 'reading a metric time series', compare_windows: 'comparing before vs. after',
  search: 'searching the logs', cluster_errors: 'clustering error messages', tail: 'tailing recent logs',
  recent_deploys: 'listing recent deploys', config_diff: 'diffing config changes', commit_diff: 'reading a commit diff',
  read_file: 'reading source code', grep: 'searching the code', run_tests: 'running the test suite',
};

export function toolVerb(name: string): string {
  const short = name.split('__').pop() ?? name;
  return TOOL_VERB[short] ?? `calling ${short}`;
}

export type Plan = {
  hypotheses: { id: string; text: string; service: string; category: string }[];
  assignments: { agent: string; question: string }[];
};

export function parsePlan(steps: Step[]): Plan | null {
  const s = [...steps].reverse().find((x) => x.kind === 'plan');
  if (!s) return null;
  try { return JSON.parse(s.detail) as Plan; } catch { return null; }
}

export type AgentState = { id: string; state: 'idle' | 'working' | 'done'; activity: string; tools: number; llm: number; steps: Step[]; summary: string; status: string };

export function agentStates(steps: Step[], assigned: string[]): AgentState[] {
  const ids = new Set<string>(['commander', ...assigned]);
  steps.forEach((s) => ids.add(s.agent));
  const order = ['commander', ...SPECIALISTS, 'remediation', 'single'];
  return order.filter((a) => ids.has(a)).map((id) => {
    const rows = steps.filter((s) => s.agent === id && s.kind !== 'plan' && s.kind !== 'decision');
    const fin = rows.filter((s) => s.kind === 'finding');
    const last = rows[rows.length - 1];
    const done = fin.length > 0 && (id !== 'commander' || steps.some((s) => s.kind === 'decision' && s.name === 'report'));
    let activity = 'waiting for its assignment';
    if (last) activity = last.kind === 'tool' ? toolVerb(last.name) : last.kind === 'llm' ? 'reasoning about what to check next' : 'wrapping up';
    if (done) activity = id === 'remediation' ? 'proposed a fix' : 'finished';
    else if (rows.length === 0 && assigned.includes(id)) activity = 'assigned, starting soon';
    return { id, state: done ? 'done' : rows.length ? 'working' : 'idle', activity, steps: rows, tools: rows.filter((s) => s.kind === 'tool').length,
             llm: rows.filter((s) => s.kind === 'llm').length, summary: id === 'remediation' ? '' : fin[fin.length - 1]?.detail ?? '', status: fin[fin.length - 1]?.name ?? '' };
  });
}

export const STAGES_MULTI = ['Alert', 'Plan', 'Investigate', 'Diagnose', 'Approval', 'Resolved'];
export const STAGES_SINGLE = ['Alert', 'Investigate', 'Diagnose', 'Approval', 'Resolved'];

export type Progress = {
  stages: string[]; current: number; tone: 'active' | 'done' | 'stopped';
  now: string; next: string; plan: Plan | null; agents: AgentState[]; followUps: number;
};

const TERMINAL = ['resolved', 'rejected', 'blocked', 'escalated'];

export function progress(d: IncidentDetail): Progress {
  const inc = d.incident, steps = d.steps, single = inc.alert?.labels?.mode === 'single';
  const stages = single ? STAGES_SINGLE : STAGES_MULTI;
  const plan = parsePlan(steps);
  const assigned = plan?.assignments.map((a) => a.agent) ?? [];
  const agents = agentStates(steps, assigned);
  const followUps = steps.filter((s) => s.kind === 'decision' && s.name === 'followup').length;
  const at = (name: string) => stages.indexOf(name);
  const status = inc.status;
  const specialists = agents.filter((a) => (SPECIALISTS as readonly string[]).includes(a.id));
  const allDone = assigned.length > 0 && specialists.filter((a) => assigned.includes(a.id)).every((a) => a.state === 'done');
  const working = agents.filter((a) => a.state === 'working');

  let current = at('Plan') >= 0 ? at('Plan') : at('Investigate');
  if (single ? steps.length > 0 : plan) current = at('Investigate');
  if (!single && allDone) current = at('Diagnose');
  if (single && agents.some((a) => a.id === 'single' && a.state === 'done')) current = at('Diagnose');
  if (inc.report) current = at('Approval');
  if (status === 'resolved') current = stages.length - 1;
  const stopped = ['rejected', 'blocked', 'escalated'].includes(status);
  const tone: Progress['tone'] = status === 'resolved' ? 'done' : stopped ? 'stopped' : 'active';

  const a = inc.report?.proposed_action;
  let now = 'Alert received. Starting the investigation.', next = 'The commander drafts hypotheses and gives each specialist one question.';
  const latest = [...working].sort((x, y) => (y.steps[y.steps.length - 1]?.seq ?? 0) - (x.steps[x.steps.length - 1]?.seq ?? 0))[0];
  if (!single && plan && !inc.report) {
    now = latest ? `${AGENT[latest.id]?.label ?? latest.id} agent is ${latest.activity}.` : 'Specialists are finishing up.';
    const pending = specialists.filter((s) => assigned.includes(s.id) && s.state !== 'done').map((s) => AGENT[s.id].label);
    next = allDone ? 'The commander weighs all the evidence, checks every claim cites a real tool call, and picks a root cause.'
      : `When ${pending.length ? pending.join(', ').replace(/, ([^,]*)$/, ' and $1') : 'the specialists'} report${pending.length === 1 ? 's' : ''} back, the commander weighs the evidence and picks a root cause.`;
    if (allDone) now = 'All specialists have reported. The commander is deciding.';
  } else if (single && !inc.report) {
    now = latest ? `The single agent is ${latest.activity}.` : 'The single agent is starting.';
    next = 'It submits a cited root cause; the remediation agent then proposes a fix.';
  }
  if (inc.report && !TERMINAL.includes(status)) {
    if (status === 'awaiting_approval' && a) {
      now = 'Diagnosis complete. Waiting for a human decision.';
      next = `Nothing runs until you approve ${a.type} ${a.target}. Approve to execute it (simulated), or reject.`;
    } else {
      now = 'Diagnosis complete. The remediation agent is choosing a fix.';
      next = 'The proposed action goes to the trust gate; anything that changes state needs human approval.';
    }
  }
  if (status === 'resolved') { now = 'Fix executed and verified in the audit log.'; next = 'Nothing left. Compare the diagnosis with the answer key below, or run another scenario.'; }
  if (status === 'rejected') { now = 'Fix rejected by a human. Nothing was changed.'; next = 'The diagnosis stays on record. Run another scenario to compare.'; }
  if (status === 'blocked') { now = 'The trust gate blocked the action.'; next = 'See the safety audit tab for the reason.'; }
  if (status === 'escalated') { now = 'No safe automatic fix: escalated to a human.'; next = 'The agents will not guess when they are not confident.'; }
  return { stages, current, tone, now, next, plan, agents, followUps };
}

export const fmtTime = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
export const pct = (x: number) => `${Math.round(x * 100)}%`;
export const cleanClaim = (c: string) => c.replace(/\[[^\]]*\]/g, '').replace(/\s+/g, ' ').trim();
export const prettyId = (id: string) => id.replace(/^inc-(demo-)?/, '').replace(/-[0-9a-f]{6}$/, '');
