# Codex Senior Consult Field-Failures v3 Design

Status: APPROVED

Approved: 2026-08-01

Normative source evidence: `references/field-reports/2026-08-hermes-kanban.md`

## Document boundaries

This document is the approved design and is normative for the v3 implementation. The field report is observed evidence, not a design specification. A later implementation plan must describe code-edit sequencing and must not change this contract. Hermes profile installation, symlink handling, pytest collection outside this repository, provider routing or coverage, K8 product wiring, active PRs or mission worktrees, and the future mission-continuation skill are out of scope.

The existing single-pass fail-closed model remains unchanged: frozen snapshot binding, strict local semantic validation, secret isolation, bounded replacement, durable response artifacts, zero repair/follow-up/resume behavior, and malformed output never becoming a verdict.

## 1. Caller-neutral construction and commands

Expose four caller-neutral commands:

```text
build-bundle
preflight
consult
status
```

The historical flat invocation remains a strict translation layer:

```text
legacy invocation
-> internal consult arguments
-> shared normalization
-> shared preflight
-> unchanged consultation contract
```

There is no legacy path around preflight.

`build-bundle` supports every consultation mode. It populates only deterministic locally available facts: mission and mode, repository identity, HEAD, dirty state, working-tree or diff fingerprint, input schema version, requested-output schema and snapshot structure. It never invents evidence or inserts placeholder strings.

Every caller-supplied value starts as `null`. A top-level construction-only `caller_required` array lists exact RFC 6901 JSON Pointer paths:

```json
{
  "objective": null,
  "diff": null,
  "tests": null,
  "caller_required": ["/objective", "/diff", "/tests"]
}
```

`caller_required` is never part of the normalized consultation payload, final bundle fingerprint or snapshot fingerprint. Normalization removes a path only after the supplied value has the correct type, satisfies all local constraints, is non-empty where required, contains no disguised sentinel, and passes applicable privacy checks.

Unknown paths, duplicate paths, paths outside the supported schema, and paths pointing to already non-null values fail validation. Missing, null and invalid are distinct states. A still-missing, null or invalid required value keeps preflight fail-closed.

Fingerprints are computed only after normalization succeeds and `caller_required` is empty.

## 2. Shared normalization and actionable preflight

`build-bundle`, `preflight` and `consult` share one normalization and validation implementation. Preflight performs all local input, snapshot, schema, privacy, budget, replacement and concurrency checks without creating a Codex process.

Validation covers:

1. safe regular-file input and size limit;
2. JSON parsing and construction-bundle schema;
3. RFC 6901 `caller_required` integrity;
4. normalization of completed caller values;
5. completeness and field types;
6. mode-specific input contract;
7. repository and snapshot binding;
8. exact requested response schema;
9. secrets and private paths;
10. budget, replacement and concurrency state;
11. final fingerprints only after all content gates pass.

Diagnostics accumulate independent failures but suppress derivative cascades. A missing `/diff` produces the primary missing-field diagnostic, not additional cardinality, sanitization and fingerprint errors.

Every diagnostic contains:

```json
{
  "code": "CALLER_VALUE_NULL",
  "path": "/diff",
  "state": "null",
  "reason": "A merge-gate consultation requires the reviewed diff.",
  "expected": {"type": "array", "constraints": ["non-empty"]},
  "remediation": {
    "guidance": "Supply bounded sanitized diff evidence.",
    "example": [{"path": "src/example.py", "summary": "Changed merge validation."}],
    "suggested_source": "git diff --stat plus selected sanitized hunks"
  },
  "category": "bundle",
  "model_process_consumed": false
}
```

Remediation examples are guidance only and are never copied into a bundle. Exact version failures name the canonical value, never shorthand such as `v2` or `v3`.

At minimum, stable codes distinguish missing, null and invalid caller values; unknown, duplicate and non-null construction paths; input and response schema mismatch; snapshot failure; secret and private-path detection; budget exhaustion; invalid replacement; and concurrent execution.

The command-level response distinguishes checks for `bundle`, `local_state`, `ledger_cache`, `replacement` and `lock`. Its `normalized` member is a stable summary, not a partial payload:

```json
{
  "mode": "merge-gate",
  "mission_id": "example",
  "repository_head": "abc123",
  "dirty": false,
  "bundle_fingerprint": "...",
  "snapshot_fingerprint": "...",
  "caller_required_remaining": 0
}
```

An optional normalized file is written atomically with mode `0600`, never overwrites without an explicit flag, and never includes `caller_required`. The source is not mutated.

```text
preflight valid != consultation executed
preflight invalid -> zero Codex processes
```

## 3. Structural privacy and bounded transport evidence

Privacy classification considers path, key, value type, value shape and context. Benign boolean and descriptive metadata are accepted when their values match the descriptive purpose, including:

```json
{"secrets_added": false}
{"secret_scope_behavior": "fail-closed"}
{"authentication_reviewed": true}
```

Credential values, ambiguous sensitive values, bearer material, private keys and credential-shaped strings remain fail-closed. Entropy is only an auxiliary signal combined with length, alphabet, prefix, key and context; it never rejects a value alone. SHA values, content fingerprints and commit identities remain valid.

Privacy diagnostics report only paths and stable categories such as `credential_shaped_value`, `ambiguous_sensitive_value` and `private_key_material`. They never print, excerpt or persist the value.

Transport analysis parses bounded Codex JSONL and sanitized stderr. It records top-level `error`, `turn.failed`, exit status, timeout, observed turns and terminal-event presence. Malformed, truncated or unknown JSONL lines increment bounded counters and do not stop later parsing or persist raw content.

Supported evidence-based categories are:

- `CLI_ARGUMENT_FAILURE`
- `AUTHENTICATION_FAILURE`
- `MODEL_UNAVAILABLE`
- `QUOTA_OR_RATE_LIMIT`
- `SCHEMA_OR_REQUEST_REJECTION`
- `SAFETY_OR_POLICY_REJECTION`
- `NETWORK_OR_SERVICE_FAILURE`
- `PROCESS_TIMEOUT`
- `PROCESS_EXIT_WITHOUT_STRUCTURED_EVIDENCE`
- `UNKNOWN_TRANSPORT_ERROR`

`PROCESS_EXIT_WITHOUT_STRUCTURED_EVIDENCE` means no classifiable structured evidence exists. `UNKNOWN_TRANSPORT_ERROR` means structured evidence exists but cannot safely be mapped to a known category.

Sanitization occurs before persistence, truncation or diagnostic fingerprinting. Any fingerprint derives only from sanitized normalized data. A deterministic primary category does not discard secondary sanitized evidence. Duplicate indicators are coalesced.

The ledger may retain a primary category, bounded sanitized evidence records, exit code, structured-evidence flag, malformed and unknown event counts, and truncation flag. It never retains raw stdout, stderr, transcript, prompt, credentials or secret-derived fingerprints.

Improved diagnosis does not relax fail-closed behavior. Every transport failure remains a no-verdict protocol failure.

## 4. Response v3 and merge-gate semantics

The default creation and consultation contract is `codex-senior-consult-response/v3`. New ordinary bundles cannot request v1 or v2. Explicit testing or compatibility operations may validate historical v1/v2 artifacts, but do not reinterpret or silently migrate them.

The v3 response contract is bound to the requested mode. A structurally valid v3 response for another mode cannot pass validation.

For merge-gate, the invariant remains strict:

```text
accept:
safe_to_merge = true
blocking_findings = []
required_actions = []
```

V3 adds required `non_blocking_observations`, with `[]` valid. The field contains only observations compatible with acceptance. Its closed object schema rejects structural blocker or required-action properties such as `severity=blocking`, `must_fix_before_merge=true`, `required_action` or `safe_to_merge=false`. No fragile free-text NLP rule attempts to infer every blocking phrase.

`residual_risks` means risk remaining after implemented controls, explicitly accepted, requiring no pre-merge action, and compatible with `safe_to_merge=true`. A pre-merge requirement belongs in `required_actions`, making `accept` invalid.

The senior prompt uses a positive recipe:

- `blocking_findings`: facts preventing acceptance;
- `required_actions`: work required before acceptance;
- `non_blocking_observations`: optional improvements or follow-up compatible with acceptance;
- `residual_risks`: explicitly accepted risk compatible with acceptance.

Local semantic validation accumulates every independent contradiction with stable code, exact JSON Pointer path, reason and expected state. For an accept response it reports contradictions at `/safe_to_merge`, `/blocking_findings` and `/required_actions`. It does not emit one redundant error per item merely because a required-empty array is non-empty; item paths are used only for independent item defects.

All eight boolean/empty/non-empty accept combinations are fixtures; exactly one is valid. Additional fixtures cover changes-required without findings/actions, blocked without blocking evidence, accept with non-blocking observations, accept with residual risks, structural blockers hidden in observations, and required actions hidden in residual risks.

The six field incidents are reconstructed only from the preserved common diagnostic unless lossless original payloads are found. Each such fixture states:

```text
fixture provenance: reconstructed from preserved diagnostic,
not a lossless copy of the original response
```

Malformed output remains non-actionable, receives no verdict artifact, and triggers no repair or automatic relaunch.

## 5. Testing, dogfood and reactivation

Deterministic tests cover every incomplete bundle incident, missing/null/invalid construction states, exact schema guidance, RFC 6901 errors, construction-to-preflight success, zero-process preflight, privacy regressions, all transport categories and malformed JSONL behavior, all merge-gate contradictions, complete field-path diagnostics, mode binding, legacy translation, and existing budget, replacement, persistence, cache and concurrency guarantees.

Offline validation includes the full skill suite, `py_compile`, `git diff --check`, help for each subcommand, status/build/preflight smoke tests and secret regressions.

After offline validation, one caller-neutral real consultation uses a fresh non-Hermes scenario. Reporting separates:

```text
protocol_execution_success
valid_advisory_verdict
```

A malformed response correctly rejected may demonstrate protocol execution but is not a valid advisory verdict. A diagnosed transport failure demonstrates fail-closed handling but not functional end-to-end consultation.

Hermes senior gates may resume only after:

```text
valid preflight
+ completed process
+ valid mode-bound v3 response
+ atomically persisted and recoverable payload
```

A separate Sol-medium merge gate is reserved for the final committed, clean and fully validated snapshot. Implementation and offline validation remain in the current Sol-low session.

## Deliberately unchanged behavior

- one bounded process per ordinary consultation;
- one stdin bundle and one observed inference turn when transport reaches the model;
- zero tools, workspace reads, follow-ups, resume and repair calls;
- no automatic content retry;
- frozen snapshot and normalized bundle binding;
- explicit single replacement limit and existing budgets;
- atomic durable evidence before a verdict becomes usable;
- malformed output never becomes a verdict;
- mission-owner responsibility for technical validation and execution.

## Out-of-scope observed Hermes defects

The field report also records Hermes profile symlink rejection, unrelated pytest collection contamination, K8 product wiring and provider coverage. They are evidence about the mission environment, not defects to absorb into this skill. This work must not modify Hermes profiles, symlinks, pytest collection outside this repository, provider routing, K8 wiring, current PRs or mission worktrees.

## Implementation-plan boundary

The implementation plan is a separate future artifact derived from this approved design. It will name exact code and test edits, preserve TDD red-green evidence, and may not broaden scope or weaken any invariant here.
