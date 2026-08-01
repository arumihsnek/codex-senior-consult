---
name: codex-senior-consult
description: Use when a long-running Codex mission faces a material architecture, security, isolation, concurrency, recovery, public-contract, replanning, final-review, or merge decision that local evidence alone cannot settle confidently.
---

# Codex Senior Consult

## Overview

Keep Luna as mission owner. Consult Sol only with a complete, sanitized snapshot; treat its one structured answer as advisory evidence, validate it locally, and continue the existing mission.

**Core contract:** one `codex exec` process, one stdin payload, one observed inference turn, zero tools, zero follow-ups, zero `resume`, zero repair executions, and zero automatic retries by default. Never claim one backend HTTP request: the CLI does not expose that metric.

## Workflow

1. Investigate locally: inspect, reproduce, read documentation, run tests, maintain the plan/checkpoint, and resolve deterministic questions without Sol.
2. Apply the escalation gate. Escalate only if the answer can materially change architecture, a hard gate, security/isolation/concurrency/recovery, a public contract, merge, or an irreversible action. Otherwise stop with `ESCALATION_NOT_JUSTIFIED`.
3. Group every unresolved question from the same snapshot. Deduplicate and order by impact.
4. Build the v1 bundle. **REQUIRED:** read [references/contracts.md](references/contracts.md) before authoring or reviewing a bundle.
5. Run the bundle-completeness and secret gates locally. Never ask Sol what context it needs.
6. Invoke `scripts/codex_senior_consult.py` once. Use `integrated-review` and `low` unless a documented observable trigger selects `medium`.
7. Validate the response against local evidence. Sol advises; Luna decides and executes.

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/codex-senior-consult/scripts/codex_senior_consult.py" \
  --mode integrated-review \
  --mission-id native-recovery \
  --bundle consultation.json
```

Use `--help` for overrides and `--status --mission-id ID` for budget/ledger totals. Read [references/examples.md](references/examples.md) for plan, integrated-review, replan, merge-gate, and current CLI limitations.

## Quick Reference

| Need | Mode / action |
|---|---|
| Plan + risks + questions + decision | `integrated-review` (recommended) |
| Review an existing plan minimally | `plan-review` |
| New evidence invalidated the plan | `replan` delta |
| Well-investigated blocker | `blocker-analysis` |
| Cross-domain risk review | `risk-audit` |
| Evidence/claim classification | `final-review` |
| Strict merge decision | `merge-gate` |
| Deterministic/local answer | Do not consult; zero sessions |

Normal mission budget: two Sol sessions; hard limit: three. Reserve session three for a material replan. Cache hits consume zero sessions.

## How to run a multi-hour Luna mission with only two single-pass Sol sessions

Luna investigates and plans → Sol `integrated-review` low → Luna executes many phases and validates findings locally → Sol `merge-gate` low. Normal consumption: two sessions, one observed turn each, no tools or follow-ups. If new evidence materially invalidates the plan, use the third and final normal session for `replan`. A deterministic mission uses zero.

## Non-Negotiable Failures

- Incomplete bundle: `BUNDLE_INCOMPLETE`; do not execute Codex.
- Tool event or extra turn: `SINGLE_PASS_CONTRACT_VIOLATION`; never relaunch.
- Malformed answer: `MALFORMED_SUPERIOR_RESPONSE`; only local syntactic extraction, never a repair call.
- Low confidence, disagreement, blockers, or conservative wording: accept the valid advisory result; never follow up.
- Recursion marker present: `RECURSIVE_ESCALATION_BLOCKED` before Codex.
- Transport failure: zero retries unless `--transport-retries 1` was explicitly supplied.

## Common Rationalizations

| Rationalization | Required response |
|---|---|
| “Persistent Sol remembers better.” | Bundle the snapshot; never `resume`. |
| “Repair malformed JSON in one more turn.” | End invalid; repair only syntax locally. |
| “Low confidence needs clarification.” | Record uncertainty; Luna investigates locally. |
| “Frequent checkpoints reassure us.” | Report progress locally; keep the two-session cadence. |
| “Read-only tools are harmless.” | Any tool call violates the contract. |
| “Quota is available.” | Quota never justifies escalation or higher effort. |

## Red Flags — Stop

Separate calls per concern; `resume`; workspace exposure by default; repair prompts; confidence follow-ups; automatic content retry; Sol executing the mission; copied auth stores; full logs/history/repository; secret-bearing bundles. Any of these violates the normal architecture.

On `codex-cli 0.146.0`, `--workspace-read` and `--dangerous-yolo` fail closed before execution because the CLI cannot preserve the zero-tool security boundary in those modes.
