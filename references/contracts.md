# Contracts and Security Reference

## Contents

1. Ownership and single-pass contract
2. Consultation bundle
3. Completeness and escalation gates
4. Modes and response contract
5. Effort policy
6. Transport and observability
7. Cache, ledger, and budgets
8. Security and exceptional access
9. Status codes

## 1. Ownership and single-pass contract

Luna owns repository inspection, documentation lookup, commands, reproduction, tests, plans, checkpoints, evidence, validation, and implementation. Sol is ephemeral, context-only, read-only, tool-free, and advisory. It never becomes coordinator or executor.

Every ordinary consultation approximates:

```text
codex_exec_processes: 1
model_turns_observed: 1
backend_requests_observed: null
tool_calls_observed: 0
follow_up_turns: 0
resume_operations: 0
repair_executions: 0
transport_retries: 0
```

The child prompt always contains the following behavioral contract:

```text
You are a bounded, single-pass senior consultant.

Use only the supplied consultation bundle.

Do not use tools.
Do not inspect the workspace.
Do not read files.
Do not execute commands.
Do not invoke MCP.
Do not invoke subagents or other models.
Do not ask follow-up questions.
Do not request another turn.
Do not produce interim progress messages.
Do not propose continuing later.

Perform all requested analysis from the supplied evidence and return exactly one final response matching the requested contract.
```

The process sets `CODEX_SENIOR_CONSULT_ACTIVE=1`. Nested invocation stops before `codex exec`. The session ends after the first answer, valid or invalid. Never use `codex resume` in the ordinary flow.

## 2. Consultation bundle

Use this base envelope. The implementation also requires `snapshot` and `escalation`, which make caching and the local gate deterministic.

```json
{
  "schema_version": "codex-senior-consult/v1",
  "mission_id": "string",
  "mode": "integrated-review",
  "objective": "string",
  "decision_needed": "string",
  "current_plan": {},
  "progress": {},
  "relevant_contracts": [],
  "observed_facts": [],
  "invalidated_assumptions": [],
  "candidate_decision": {},
  "alternatives": [],
  "code_excerpts": [],
  "diff": {},
  "tests": [],
  "runtime_evidence": [],
  "constraints": [],
  "risks_already_identified": [],
  "questions": [],
  "requested_output": {"schema_version": "codex-senior-consult-response/v1"},
  "snapshot": {
    "repository_head": "string",
    "working_tree_fingerprint": "string",
    "plan_fingerprint": "string",
    "checkpoint_fingerprint": "string"
  },
  "escalation": {
    "justified": true,
    "reasons": ["public_contract"],
    "local_deterministic_checks": ["Read the approved contract", "Ran focused tests"],
    "material_impact": "The answer changes a public contract gate."
  }
}
```

Include only tightly relevant code excerpts, bounded diff summaries, literal test/runtime outcomes, invalidated assumptions, constraints, alternatives, and all related questions. Never include conversation history, chain of thought, full repositories/logs, duplicated evidence, credentials, auth stores, secrets, tokens, or unnecessary personal data.

Supported escalation reasons: `cross_cutting_architecture`, `security`, `credentials`, `process_isolation`, `contradictory_evidence`, `concurrency`, `duplicate_side_effects`, `public_contract`, `destructive_migration`, `alternatives_tie`, `conceptual_plan_failure`, `recovery`, `merge_decision`, `irreversible_action`.

## 3. Completeness and escalation gates

Before transport, require a non-empty objective, concrete decision, constraints, questions, valid requested-output version, identifiable HEAD/worktree/plan/checkpoint snapshot, at least one evidence category, reasonable size, no large duplication, and no detected secret. Missing critical data produces `BUNDLE_INCOMPLETE` with zero sessions/processes.

Resolve locally when reading, documentation, deterministic search, tests, schema inspection, reproduction, diff, logs, approved contracts, or a reversible low-risk choice can answer the question. A false or unsupported escalation gate produces `ESCALATION_NOT_JUSTIFIED` with zero sessions.

Group questions from one snapshot: collect → remove locally answered → normalize/deduplicate → order by impact → request one integrated answer.

## 4. Modes and response contract

- `integrated-review`: review plan, assumptions, risks, questions, alternatives, candidate, minimum delta, next safe step.
- `plan`: exceptional full plan after sufficient local research cannot form a viable plan.
- `plan-review`: verdict, blockers, assumptions, missing gates, minimum changes, next step; avoid rewriting.
- `replan`: current plan, completed phases, last green gate, new evidence, invalidated assumption, closed scope; return a delta unless impossible.
- `blocker-analysis`: reproduction, observed/discarded hypotheses, excerpts, constraints; return ranked causes, cheapest discriminating experiment, stops, next action.
- `risk-audit`: one combined security/privacy/isolation/concurrency/side-effects/rollback/compatibility/data/observability audit.
- `final-review`: classify claims as demonstrated, inferred, deferred, or not demonstrated.
- `merge-gate`: strict verdict plus `safe_to_merge`.

Common response:

```json
{
  "schema_version": "codex-senior-consult-response/v1",
  "mission_id": "string",
  "mode": "string",
  "model": "string",
  "reasoning_effort": "low",
  "verdict": "accept",
  "summary": "string",
  "blocking_findings": [],
  "non_blocking_findings": [],
  "assumptions": [],
  "required_actions": [],
  "plan_delta": [],
  "evidence_missing": [],
  "questions_answered": [],
  "next_safe_step": "string",
  "confidence": "high"
}
```

Each finding contains `id`, `claim`, `severity`, `evidence`, `reasoning_summary`, and nullable `required_change`. Request reasoning summaries, never chain of thought.

For `merge-gate`, require `safe_to_merge`; `accept` requires `true`.

## 5. Effort policy

Default to `gpt-5.6-sol` and `low`. Select `medium` locally only when `--critical` names an observable trigger from the supported list: cross-cutting hard-to-reverse architecture, security/credentials, process isolation, materially contradictory evidence, concurrency, duplicate side effects during recovery, public contract, destructive migration, two reasonable alternatives without a deterministic criterion, or conceptual plan failure.

Mission length, file count, uncertainty, spare quota, or model capability never trigger `medium`. `high` and `xhigh` occur only through the explicit `--effort` override.

## 6. Transport and observability

The implementation is verified against `codex-cli 0.146.0`. It builds an argument list and places the global `--ask-for-approval never` before `exec`; it then uses stdin, `--ephemeral`, `-C`, `--sandbox read-only`, `--json`, `--output-schema`, `--output-last-message`, `--ignore-user-config`, `--ignore-rules`, and `shell_environment_policy.inherit=none`. Context-only adds `--skip-git-repo-check` and an empty temporary working directory. CLI user configuration is ignored, so configured MCP servers/plugins are not loaded. Built-in tools cannot be disabled by a verified CLI flag; the prompt forbids them and malformed, unknown, or tool-bearing JSONL fails closed.

Structured JSONL stays on stdout inside the wrapper; diagnostic stderr stays separate. Timeout terminates the process group cleanly. Exit code zero alone never proves a valid answer. A timeout is never a verdict.

Count only observable metrics. `backend_requests_observed` remains `null` because this CLI does not expose backend HTTP request count. Say “single observed inference turn,” never “exactly one backend request.”

Malformed output permits only local removal of an outer fence, extraction of a complete JSON object already present, and newline normalization. Never invent fields or run a repair call. Low confidence, disagreement, blockers, or an unwanted verdict never justify another call.

## 7. Cache, ledger, and budgets

Default soft budget: 2 sessions. Default hard budget: 3, never automatically reset. Normal cadence: initial integrated/plan review, final/merge review; reserve three for a material replan caused by new evidence. Deterministic missions use zero. Exceeding hard budget requires the caller to supply an explicit larger `--hard-budget` after user authorization.

The SHA-256 cache key includes schema, mission, mode, HEAD, sanitized worktree fingerprint, plan fingerprint, checkpoint fingerprint, evidence fingerprint, questions fingerprint, model, effort, and entire normalized bundle. `--no-cache` bypasses reads/writes; `--refresh` bypasses reads but writes the new valid result. Cache files contain response and version, never the prompt, and use restrictive permissions.

The append-only JSONL ledger records UTC time, mission, mode, session number, budgets, cache status, model/effort/triggers, context bytes, questions, workspace access, processes, observed turns, unknown backend requests, tool calls, follow-ups, resume, repair, transport retries, exit status, verdict, and secret exposure. A mission lock serializes budget check and execution; each process is durably reserved before launch, then a result record is appended. `--status` aggregates sessions, remaining budgets, calls, cache hits, models, efforts, modes, and latest verdict.

## 8. Security and exceptional access

The default is no repository exposure, an empty temporary working directory, read-only sandbox, never approval, ignored user config/rules, ephemeral session, minimal environment allowlist, no copied auth store, and no persisted full prompt.

`--workspace-read DIR` is parsed and requires `--workspace-read-justification TEXT`, but on `codex-cli 0.146.0` it returns `WORKSPACE_READ_UNSUPPORTED` before execution. This avoids exposing a repository that the zero-tool child cannot safely consume. Reject traversal, symlinks, FIFOs, sockets, devices, invalid mission IDs, oversize bundles, private absolute paths, and secret-like values. Temporary control/work directories are cleaned.

Normal YOLO means non-interactive, no approvals, no waiting, single-pass, read-only, and no tools. It never means destructive access. `--dangerous-yolo` is off by default and returns `DANGEROUS_YOLO_DISABLED` before execution on this CLI because bypassing the sandbox cannot meet the skill's contract.

Known limitation: the CLI needs its canonical authentication state and offers no verified switch that removes built-in tools entirely. A malicious or prompt-injected child could attempt a read before the wrapper observes and rejects the tool event. Empty working directory, ignored configuration/rules, no workspace path, read-only sandbox, empty tool environment, bounded sanitized input, and strict event detection reduce but cannot eliminate this risk. Do not use the skill for bundles whose disclosure would be catastrophic; never put secrets in a bundle.

## 9. Status codes

| Status | Meaning | New Sol sessions |
|---|---|---:|
| `COMPLETED` | One schema-valid advisory response | 1 normally |
| `CACHE_HIT` | Identical material snapshot reused | 0 |
| `BUNDLE_INCOMPLETE` | Local completeness gate failed | 0 |
| `ESCALATION_NOT_JUSTIFIED` | Deterministic/local work remains | 0 |
| `SECRET_DETECTED` | Secret-like material rejected | 0 |
| `RECURSIVE_ESCALATION_BLOCKED` | Nested escalation rejected | 0 |
| `MALFORMED_SUPERIOR_RESPONSE` | First answer invalid; no repair | 1 |
| `SINGLE_PASS_CONTRACT_VIOLATION` | Tool or extra turn observed; no relaunch | 1 |
| `TRANSPORT_ERROR` | No valid response; retry only if explicitly enabled | 1 or 2 |
| `TIMEOUT` | Process terminated; never a verdict | 1 |
| `MISSION_BUDGET_EXCEEDED` | Hard limit would be crossed | 0 |
| `CACHE_INVALID` | Cached response failed integrity validation | 0 |
| `WORKSPACE_READ_UNSUPPORTED` | Current CLI cannot preserve the zero-tool contract | 0 |
| `DANGEROUS_YOLO_DISABLED` | Unsafe bypass is unavailable | 0 |
