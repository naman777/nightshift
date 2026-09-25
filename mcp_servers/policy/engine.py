"""The policy layer: the ONE place where permissions, timeouts, the kill switch and audit logging live.

Agents never call a tool directly; every call goes through PolicyEngine.execute:

  read_only    -> runs automatically
  reversible   -> needs `ctx.approved_by` (a human clicked approve in Slack)
  destructive  -> needs `ctx.approved_by` AND a typed confirmation `CONFIRM <tool>` plus a reason; blocked in benchmark mode
  kill switch  -> NIGHTSHIFT_DRY_RUN=1 turns every write tool into a dry run (recorded, never executed)
  benchmark    -> write tools are recorded as proposals and never executed
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from agents.core.db import Database
from agents.core.mcp_client import CallContext, ToolResult
from agents.core.models import Tier

from ..base import Server, Tool, positional_ok

DEFAULT_TIMEOUTS = {Tier.READ_ONLY: 15.0, Tier.REVERSIBLE: 60.0, Tier.DESTRUCTIVE: 120.0}


def kill_switch_on() -> bool:
    return os.environ.get("NIGHTSHIFT_DRY_RUN", "0").lower() in ("1", "true", "yes")


@dataclass
class PolicyEngine:
    db: Database
    benchmark_mode: bool = False
    dry_run: bool | None = None  # None -> read the env flag on every call
    timeouts: dict[Tier, float] = field(default_factory=lambda: dict(DEFAULT_TIMEOUTS))
    proposals: list[dict[str, Any]] = field(default_factory=list)

    # -- audit ---------------------------------------------------------------------
    def audit(self, ctx: CallContext, tool: Tool, args: dict, decision: str, reason: str, dry_run: bool) -> None:
        self.db.insert("audit_log", dict(
            ts=time.time(), incident_id=ctx.incident_id, agent=ctx.agent, tool=tool.name, tier=tool.tier.value,
            arguments=json.dumps(args, sort_keys=True, default=str), decision=decision, reason=reason,
            evidence_ids=json.dumps(ctx.evidence_ids), dry_run=int(dry_run)))

    def audit_rows(self, incident_id: str | None = None) -> list[dict]:
        if incident_id:
            return self.db.execute("SELECT * FROM audit_log WHERE incident_id = ? ORDER BY seq", [incident_id])
        return self.db.execute("SELECT * FROM audit_log ORDER BY seq")

    # -- decision ------------------------------------------------------------------
    def decide(self, tool: Tool, ctx: CallContext) -> tuple[str, str]:
        """Returns (decision, reason); decision in allow | deny | propose."""
        if tool.tier is Tier.READ_ONLY:
            return "allow", "read-only"
        if self.benchmark_mode:
            return "propose", "benchmark mode: write tools are recorded, not executed"
        if tool.tier is Tier.DESTRUCTIVE:
            if not ctx.approved_by:
                return "deny", "destructive tools require human approval"
            if ctx.confirmation != f"CONFIRM {tool.name}" or not ctx.reason.strip():
                return "deny", f"destructive tools require typed confirmation 'CONFIRM {tool.name}' and a reason"
            return "allow", f"approved by {ctx.approved_by} with typed confirmation"
        if not ctx.approved_by:
            return "deny", "reversible tools require one-click approval"
        return "allow", f"approved by {ctx.approved_by}"

    # -- execution -----------------------------------------------------------------
    async def execute(self, server: Server, tool: Tool, args: dict[str, Any], ctx: CallContext) -> ToolResult:
        decision, reason = self.decide(tool, ctx)
        dry = kill_switch_on() if self.dry_run is None else self.dry_run
        if decision == "deny":
            self.audit(ctx, tool, args, "blocked", reason, dry)
            return ToolResult(f"BLOCKED by policy: {reason}", blocked=True)
        if decision == "propose":
            self.proposals.append({"tool": tool.name, "args": args, "tier": tool.tier.value, "agent": ctx.agent})
            self.audit(ctx, tool, args, "proposed", reason, True)
            return ToolResult(f"PROPOSED (not executed): {tool.name} {json.dumps(args, sort_keys=True)}", dry_run=True)
        if tool.tier is not Tier.READ_ONLY and dry:
            self.audit(ctx, tool, args, "dry_run", "kill switch (NIGHTSHIFT_DRY_RUN) is on", True)
            return ToolResult(f"DRY RUN (kill switch): {tool.name} {json.dumps(args, sort_keys=True)}", dry_run=True)
        try:
            out = await asyncio.wait_for(server.call(tool, positional_ok(tool.handler, args)), self.timeouts[tool.tier])
        except asyncio.TimeoutError:
            self.audit(ctx, tool, args, "timeout", f"exceeded {self.timeouts[tool.tier]}s", dry)
            return ToolResult(f"tool timed out after {self.timeouts[tool.tier]}s", is_error=True)
        except Exception as e:
            self.audit(ctx, tool, args, "error", f"{type(e).__name__}: {e}", dry)
            return ToolResult(f"tool error: {type(e).__name__}: {e}", is_error=True)
        self.audit(ctx, tool, args, "allowed", reason, dry)
        return ToolResult(out if isinstance(out, str) else json.dumps(out, default=str, sort_keys=True))
