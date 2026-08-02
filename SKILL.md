---
name: codex-senior-consult
description: Use when a long-running agent or orchestration mission faces a material architecture, security, isolation, concurrency, recovery, public-contract, replanning, final-review, or merge decision that local evidence alone cannot settle confidently and the caller can provide a complete sanitized bundle.
---

# Codex Senior Consult

This is a caller-neutral, bounded senior-consultation primitive. The calling agent or mission owner supplies a complete frozen bundle; the senior consultant returns advisory evidence; the mission owner validates findings and performs all implementation and operational work. For example, Luna may be the mission owner and `gpt-5.6-sol` the default target model.

The core execution contract is strict: one `codex exec` process per ordinary consultation execution, one stdin payload, one observed inference turn, zero tools, zero workspace reads, zero follow-ups, zero resume operations, zero repair executions, zero automatic content retries, an ephemeral session, a sanitized bounded bundle, and strict local validation. The CLI does not expose backend HTTP request counts, so this skill never claims exactly one backend request.

The consultation execution ending does not end the surrounding mission. A malformed response, tool violation, timeout, or transport failure has no valid verdict. Its detailed status remains visible (`MALFORMED_SUPERIOR_RESPONSE`, `SINGLE_PASS_CONTRACT_VIOLATION`, `TIMEOUT`, or `TRANSPORT_ERROR`) and is wrapped as `NO_VERDICT_PROTOCOL_FAILURE`. A schema- and locally-valid response is actionable only after its canonical response artifact has been atomically persisted and verified. If that commit fails, the result is `NO_USABLE_VERDICT / VERDICT_PERSISTENCE_FAILURE`, never an actionable verdict; no automatic retry or replacement follows.

After a no-verdict protocol failure, the caller may initiate at most one fresh replacement with `--replacement-for <execution-id>`. It must use the same mission, mode, target model, effort, frozen snapshot, and normalized bundle. A replacement is never allowed after a schema-valid model verdict (including a historically valid but evidence-unavailable one), never replaces a replacement, and never exists merely because the caller dislikes a verdict or its confidence. Cache hits are not replacements.

## Workflow

Use `build-bundle -> preflight -> consult -> status`. `build-bundle` emits only deterministic local identity and represents caller evidence as `null` plus RFC 6901 `caller_required` paths. Preflight uses the same normalization and consumes zero Codex processes. The historical flat invocation is translated into `consult` and cannot bypass preflight.

New consultations request `codex-senior-consult-response/v3`. V1/v2 response handling is historical read-only compatibility and is never the ordinary generated flow.

1. Investigate locally and resolve deterministic questions without consultation.
2. Apply the escalation gate; group unresolved questions in one bundle.
3. Read [references/contracts.md](references/contracts.md), build the v1 input bundle, and pass local completeness, path, and secret gates.
4. Invoke the script once with `--mode`, `--mission-id`, and `--bundle`; use `gpt-5.6-sol` and `low` unless a documented trigger selects `medium`.
5. Validate the advisory result locally. The mission owner decides and executes.
6. If and only if the execution has a no-verdict protocol failure, a caller may make one explicit fresh replacement using its returned execution ID.

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/codex-senior-consult/scripts/codex_senior_consult.py" \
  --mode merge-gate --mission-id example-mission --bundle consultation.json
```

Normal semantic policy is two valid senior verdicts; three is the maximum for a material replan. Process attempts, valid verdicts, protocol failures, replacement attempts, cache hits, transport retries, and observed model turns are counted separately. `--status` exposes both semantic usage and actual process cost. The total process budget is hard-bounded; replacement allowance is one by default.

The response contract is version `codex-senior-consult-response/v2`. It is mode-specific, minimal, strict (`additionalProperties: false`), and does not require the target model to copy wrapper metadata. v1 responses remain available only through the explicit transition represented by a v1 bundle request or `--legacy-response-v1`; see the migration notes in [references/contracts.md](references/contracts.md).

Do not grant workspace access or tools for convenience, do not use `resume`, and do not turn low confidence or an inconvenient valid verdict into a retry. See [tests/pressure-baseline.md](tests/pressure-baseline.md) for pressure cases.
