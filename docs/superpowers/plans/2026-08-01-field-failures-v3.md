# Codex Senior Consult Field-Failures v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved caller-neutral v3 bundle construction, zero-process preflight, structural privacy, actionable transport evidence, and mode-bound response semantics without weakening the single-pass fail-closed consultation contract.

**Architecture:** Keep `scripts/codex_senior_consult.py` as the single executable and authoritative contract implementation. Add explicit subcommands over shared pure normalization/preflight functions, retain the historical CLI only as a translation into `consult`, and derive transport/local response validation from mode-specific versioned contracts. Preserve all ledger, cache, replacement, persistence, concurrency, zero-tool, and zero-follow-up paths.

**Tech Stack:** Python 3.12 standard library, `jsonschema`, `unittest`, Git CLI, Codex CLI JSONL.

## Global Constraints

- Normative design: `references/designs/field-failures-v3-design.md` at design commit `cd17a6d` plus correction commit `f37d752`.
- Observed evidence: `references/field-reports/2026-08-hermes-kanban.md`; evidence is not specification.
- Baseline harness restoration: commit `38a867b`; baseline is 61 tests passing.
- Preserve the core single-pass, fail-closed model, snapshot binding, strict local semantic validation, secret isolation, bounded replacements, durable response artifacts, and malformed-output no-verdict rule.
- New ordinary construction and consultations use only `codex-senior-consult-response/v3`; v1/v2 are explicit read-only compatibility/test surfaces.
- `caller_required` is construction metadata and is absent from normalized payloads and fingerprints.
- Preflight never creates a Codex process.
- Do not modify Hermes profile installation, symlink handling, external pytest collection, provider routing, K8 product wiring, current PRs or mission worktrees, or the future mission-continuation skill.
- Keep `tests/pressure-baseline.md` normative: no repair, resume, clarification follow-up, low-confidence/inconvenient-verdict retry, tools/workspace, mission-failure inference, second replacement, or exact-backend-request claim.
- Reserve a separate Sol-medium merge gate for the final committed, clean, fully validated snapshot; implementation remains Sol-low.

---

## File Map

- Modify `scripts/codex_senior_consult.py`: version constants, subcommand parsing, repository discovery, canonical construction skeletons, RFC 6901 normalization, preflight diagnostics, structural privacy classification, bounded JSONL transport evidence, v3 schemas, semantic contradictions, prompt recipe, legacy translation and command dispatch.
- Modify `tests/test_codex_senior_consult.py`: unit and CLI coverage for every new contract plus existing invariant regressions.
- Create `tests/fixtures/incomplete-bundles/*.json`: S2-S5 reconstructed incomplete construction inputs with provenance.
- Create `tests/fixtures/malformed-responses/*.json`: six reconstructed accept contradictions with explicit provenance.
- Modify `references/contracts.md`: v3 default contract, v1/v2 historical-only rules, subcommands and normalized preflight output.
- Modify `references/examples.md`: caller-neutral build → fill → preflight → consult example and field-path remediation.
- Modify `references/consultation-bundle.example.json`: canonical v3 construction bundle with `null` caller fields and RFC 6901 `caller_required`.
- Modify `SKILL.md`: concise workflow pointing callers to `build-bundle`, `preflight`, exact v3 contract and fail-closed behavior.
- Modify `agents/openai.yaml`: update the default prompt only if it names the old invocation or response version.

### Task 1: Versioned Contracts and Mode-Bound v3 Semantics

**Files:**
- Modify: `scripts/codex_senior_consult.py:21-286`
- Modify: `tests/test_codex_senior_consult.py:192-403`
- Create: `tests/fixtures/malformed-responses/v2-accept-contradiction-1.json`
- Create: `tests/fixtures/malformed-responses/v2-accept-contradiction-2.json`
- Create: `tests/fixtures/malformed-responses/v4-accept-contradiction-1.json`
- Create: `tests/fixtures/malformed-responses/v4-accept-contradiction-2.json`
- Create: `tests/fixtures/malformed-responses/v6-accept-contradiction-1.json`
- Create: `tests/fixtures/malformed-responses/v6-accept-contradiction-2.json`

**Interfaces:**
- Consumes: existing `MODE_CONTRACTS`, `local_semantic_contract()`, `backend_transport_schema()`, `validate_response()`.
- Produces: `RESPONSE_SCHEMA = "codex-senior-consult-response/v3"`, `HISTORICAL_RESPONSE_SCHEMAS`, mode-bound v3 schemas, `semantic_diagnostics(response, mode) -> list[dict[str, Any]]`.

- [ ] **Step 1: Add failing v3 shape and compatibility tests**

Add tests asserting v3 is the ordinary default, `non_blocking_observations` is required and accepts `[]`, each mode rejects another mode's v3 shape, and v1/v2 require an explicit compatibility flag. Add a table-driven eight-combination merge-gate test:

```python
for safe, findings, actions in itertools.product((False, True), ([], [blocking_finding()]), ([], ["fix first"])):
    payload = merge_gate_v3(safe_to_merge=safe, blocking_findings=findings, required_actions=actions)
    errors = self.mod.validate_response(payload, "m", "merge-gate", "model", "low", [], "a" * 40)
    self.assertEqual(not errors, safe and not findings and not actions)
```

Add independent tests for `changes_required` without findings/actions, `blocked` without evidence, accept with observations, accept with residual risks, a structured blocker in observations, and a required action in residual risks.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_v3_merge_gate_accept_truth_table tests.test_codex_senior_consult.ConsultProductTests.test_v3_is_bound_to_requested_mode`

Expected: FAIL because v3 and structured contradiction diagnostics do not exist.

- [ ] **Step 3: Implement the minimal versioned contracts**

Add closed v3 observation/risk shapes and keep historical validators separate:

```python
RESPONSE_SCHEMA = "codex-senior-consult-response/v3"
HISTORICAL_RESPONSE_SCHEMAS = {
    "codex-senior-consult-response/v1",
    "codex-senior-consult-response/v2",
}

NON_BLOCKING_OBSERVATION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "claim", "evidence", "reasoning_summary"],
    "properties": {"id": STRING, "claim": STRING, "evidence": STRING_LIST, "reasoning_summary": STRING},
}
```

Return one diagnostic per independent contradictory field using RFC 6901 paths. Do not duplicate array and per-item errors unless an item has an independent structural defect. Preserve the exact accept invariant.

- [ ] **Step 4: Add the six reconstructed field fixtures**

Each fixture includes only the demonstrated contradiction and a sibling provenance record or top-level test metadata read outside the response payload:

```text
fixture provenance: reconstructed from preserved diagnostic,
not a lossless copy of the original response
```

Verify every fixture is rejected without a verdict, repair call or relaunch.

- [ ] **Step 5: Run focused and full schema tests**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_v3_merge_gate_accept_truth_table tests.test_codex_senior_consult.ConsultProductTests.test_reconstructed_field_response_fixtures tests.test_codex_senior_consult.ConsultProductTests.test_every_v3_mode_has_schema_and_local_validator_parity`

Expected: PASS.

- [ ] **Step 6: Commit the versioned contract slice**

```bash
git add scripts/codex_senior_consult.py tests/test_codex_senior_consult.py tests/fixtures/malformed-responses
git commit -m "feat: add mode-bound v3 response contracts"
```

### Task 2: Canonical Bundle Construction and RFC 6901 Normalization

**Files:**
- Modify: `scripts/codex_senior_consult.py:41-173`
- Modify: `tests/test_codex_senior_consult.py:28-191,493-535`
- Create: `tests/fixtures/incomplete-bundles/s2-v5-missing-required-fields.json`
- Create: `tests/fixtures/incomplete-bundles/s3-response-schema-shorthand.json`
- Create: `tests/fixtures/incomplete-bundles/s4-benign-secrets-added.json`
- Create: `tests/fixtures/incomplete-bundles/s5-v6-missing-diff.json`

**Interfaces:**
- Consumes: `BUNDLE_SCHEMA`, `BASE_REQUIRED`, mode set, repository path supplied to the command.
- Produces: `build_bundle_skeleton(mission_id, mode, repository) -> dict`, `resolve_json_pointer()`, `normalize_construction_bundle() -> NormalizationResult`, `Diagnostic` dictionaries.

- [ ] **Step 1: Write failing skeleton and pointer tests**

Cover every supported mode; deterministic repository HEAD/dirty/fingerprint fields; all caller fields as `null`; exact RFC 6901 paths; no sentinel strings; unknown/duplicate/out-of-schema pointers; caller-filled valid values being removed; invalid values remaining with `CALLER_VALUE_INVALID`; and `CALLER_REQUIRED_NON_NULL` only for deterministic non-caller fields.

- [ ] **Step 2: Run construction tests and verify RED**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_build_bundle_for_every_mode tests.test_codex_senior_consult.ConsultProductTests.test_caller_required_normalizes_filled_values`

Expected: FAIL because builder/normalizer APIs do not exist.

- [ ] **Step 3: Implement canonical construction skeletons**

Use `git rev-parse HEAD`, `git status --porcelain=v1 -z` and a canonical bounded working-tree/diff digest through argument-vector subprocess calls. Do not synthesize caller evidence. Build `requested_output.schema_version` as exact v3 and construct the full snapshot shape.

- [ ] **Step 4: Implement strict RFC 6901 normalization**

Decode `~0` and `~1`, reject invalid escapes, arrays and unknown schema paths, track primary `missing`/`null`/`invalid` state, and remove valid newly filled paths. Strip `caller_required` before returning the normalized payload. Reject disguised sentinels before fingerprinting.

- [ ] **Step 5: Add the four field bundle fixtures and exact schema guidance**

Fixture tests must reproduce S2-S5, assert complete JSON Pointer diagnostics, and assert that shorthand `v3`/`v2` guidance names `codex-senior-consult-response/v3` exactly. In this task, the S4 fixture asserts only construction completeness and pointer normalization. Task 4 adds and satisfies the separate end-to-end privacy acceptance assertion for the same fixture.

- [ ] **Step 6: Verify construction normalization**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_build_bundle_for_every_mode tests.test_codex_senior_consult.ConsultProductTests.test_caller_required_pointer_failures tests.test_codex_senior_consult.ConsultProductTests.test_observed_incomplete_bundle_fixtures`

Expected: PASS for the construction and normalization assertions selected in this task.

- [ ] **Step 7: Commit the construction slice**

```bash
git add scripts/codex_senior_consult.py tests/test_codex_senior_consult.py tests/fixtures/incomplete-bundles
git commit -m "feat: build canonical consultation bundles"
```

### Task 3: Zero-Process Preflight and Explicit Subcommands

**Files:**
- Modify: `scripts/codex_senior_consult.py:524-760`
- Modify: `tests/test_codex_senior_consult.py:404-779`

**Interfaces:**
- Consumes: Task 2 normalization, existing ledger/cache/lock/replacement helpers.
- Produces: `preflight(args, *, acquire_execution_lock: bool) -> dict`, explicit `build-bundle`, `preflight`, `consult`, `status` argparse subcommands, `translate_legacy_argv(argv) -> list[str]`.

- [ ] **Step 1: Write failing CLI/preflight tests**

Assert help for every subcommand; legacy translation reaches the same internal `consult`; incomplete and valid preflight both spawn zero model processes; cascade suppression; stable normalized summary; check groups for bundle/local state/ledger-cache/replacement/lock; and atomic `0600` normalized output with explicit overwrite only.

- [ ] **Step 2: Run preflight tests and verify RED**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_preflight_consumes_zero_model_processes tests.test_codex_senior_consult.ConsultProductTests.test_legacy_cli_translates_to_consult`

Expected: FAIL because the subcommands and preflight result do not exist.

- [ ] **Step 3: Implement subcommands and legacy translation**

Parse explicit commands first. When argv matches the historical flat form, prepend/translate to `consult` before parsing; do not keep a second execution path.

- [ ] **Step 4: Implement actionable preflight**

Accumulate independent `Diagnostic` objects while suppressing downstream errors whose prerequisite field is missing/null/type-invalid. Always return `model_processes_consumed: 0`. Run budget and replacement checks separately from bundle content; probe lock without consuming a Codex process.

- [ ] **Step 5: Implement safe normalized-file output**

Reuse `secure_write()`/atomic rename semantics, enforce `0600`, and reject an existing output unless `--overwrite` is explicit. Never copy remediation examples into output.

- [ ] **Step 6: Verify CLI and preserved guarantees**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_preflight_consumes_zero_model_processes tests.test_codex_senior_consult.ConsultProductTests.test_preflight_suppresses_cascades tests.test_codex_senior_consult.ConsultProductTests.test_legacy_cli_translates_to_consult tests.test_codex_senior_consult.ConsultProductTests.test_concurrent_invocations_cannot_exceed_hard_budget`

Expected: PASS.

- [ ] **Step 7: Commit the command/preflight slice**

```bash
git add scripts/codex_senior_consult.py tests/test_codex_senior_consult.py
git commit -m "feat: add zero-process consultation preflight"
```

### Task 4: Structural Privacy Classification

**Files:**
- Modify: `scripts/codex_senior_consult.py:31-132`
- Modify: `tests/test_codex_senior_consult.py:192-224,729-743,816-823,972-985`

**Interfaces:**
- Consumes: normalized construction payload from Task 2.
- Produces: `privacy_findings(value) -> list[dict[str, str]]`; compatibility wrapper `secret_locations()` returning paths only.

- [ ] **Step 1: Write failing privacy matrix tests**

Accept `secrets_added: false`, `secret_scope_behavior: "fail-closed"`, `authentication_reviewed: true`, SHA-256, commit SHA and content fingerprints. Reject an actual token, private key and high-entropy ambiguous value under a sensitive key. Assert diagnostics contain only path/category and never the original value.

- [ ] **Step 2: Run privacy tests and verify RED**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_structural_privacy_matrix`

Expected: FAIL on the benign boolean field and missing category output.

- [ ] **Step 3: Implement structural classification**

Classify using key role, value type, explicit credential prefixes/patterns and descriptive metadata context. Use entropy only as an auxiliary signal and explicitly recognize validated digest/commit fields. Sanitize paths/categories before any output.

- [ ] **Step 4: Verify privacy and persistence regressions**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_structural_privacy_matrix tests.test_codex_senior_consult.ConsultProductTests.test_secret_and_fifo_are_rejected_before_exec tests.test_codex_senior_consult.ConsultProductTests.test_duplicate_execution_id_is_rejected_and_sensitive_response_is_not_persisted`

Expected: PASS.

- [ ] **Step 5: Commit the privacy slice**

```bash
git add scripts/codex_senior_consult.py tests/test_codex_senior_consult.py
git commit -m "fix: classify privacy metadata structurally"
```

### Task 5: Bounded Actionable Transport Evidence

**Files:**
- Modify: `scripts/codex_senior_consult.py:288-360,524-760`
- Modify: `tests/test_codex_senior_consult.py:331-341,449-461,536-568`

**Interfaces:**
- Consumes: Codex stdout JSONL, stderr, exit code and timeout bit.
- Produces: `parse_transport_evidence(stdout, stderr, exit_code, timed_out) -> TransportEvidence`, bounded ledger fields and deterministic primary category.

- [ ] **Step 1: Write failing transport classification tests**

Cover CLI argument failure, authentication, model unavailable, quota/rate limit, schema/request rejection, safety/policy rejection, network/service failure, exact timeout, non-zero exit without events, structured unknown evidence, malformed lines, unknown event types, truncation, top-level `error` and `turn.failed`. Include secrets in raw test messages and assert no returned or persisted diagnostic contains them.

- [ ] **Step 2: Run transport tests and verify RED**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_actionable_transport_classification_matrix tests.test_codex_senior_consult.ConsultProductTests.test_malformed_jsonl_is_bounded_and_processing_continues`

Expected: FAIL because categories/counters/evidence records are incomplete.

- [ ] **Step 3: Implement sanitize-first parsing**

Parse line-by-line under event, evidence-count and message-length bounds. Sanitize before truncation, normalization, coalescing, fingerprinting or persistence. Continue after malformed lines. Record counters without raw content.

- [ ] **Step 4: Implement deterministic evidence-based classification**

Use exact structured codes before sanitized message markers. Preserve a primary category plus deduplicated secondary evidence. Define timeout independently. Use `PROCESS_EXIT_WITHOUT_STRUCTURED_EVIDENCE` only with no classifiable structured event, and `UNKNOWN_TRANSPORT_ERROR` only when structured evidence exists but is safely unrecognized.

- [ ] **Step 5: Verify ledger and no-verdict behavior**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_actionable_transport_classification_matrix tests.test_codex_senior_consult.ConsultProductTests.test_transport_failure_retains_sanitized_actionable_diagnostics tests.test_codex_senior_consult.ConsultProductTests.test_malformed_response_has_no_repair_call`

Expected: PASS and every transport result remains `NO_VERDICT_PROTOCOL_FAILURE`.

- [ ] **Step 6: Commit the transport slice**

```bash
git add scripts/codex_senior_consult.py tests/test_codex_senior_consult.py
git commit -m "fix: retain bounded transport evidence"
```

### Task 6: Prompt, Documentation, Compatibility and Pressure Regression

**Files:**
- Modify: `scripts/codex_senior_consult.py:341-347`
- Modify: `SKILL.md`
- Modify: `agents/openai.yaml`
- Modify: `references/contracts.md`
- Modify: `references/examples.md`
- Modify: `references/consultation-bundle.example.json`
- Modify: `tests/pressure-baseline.md`
- Modify: `tests/test_codex_senior_consult.py`

**Interfaces:**
- Consumes: Tasks 1-5 commands and contracts.
- Produces: positive senior response recipe, current caller workflow, historical compatibility documentation and executable pressure regressions.

- [ ] **Step 1: Write failing prompt/documentation contract tests**

Assert the prompt distinguishes blockers, required actions, non-blocking observations and residual risks; help/docs use v3 by default; v1/v2 are historical-only; all four commands are documented; and every normative pressure rejection maps to an executable assertion.

- [ ] **Step 2: Run documentation/prompt tests and verify RED**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_v3_prompt_uses_positive_merge_gate_recipe tests.test_codex_senior_consult.ConsultProductTests.test_pressure_baseline_contract`

Expected: FAIL because current docs/prompt describe v2 and do not expose subcommands.

- [ ] **Step 3: Update the positive senior prompt recipe**

Tell the senior exactly where blocking findings, required pre-merge actions, non-blocking observations and accepted residual risks belong. State that any true blocker/action makes `accept` invalid. Preserve zero tools/workspace/follow-up/resume/repair instructions.

- [ ] **Step 4: Update caller documentation and examples**

Show `build-bundle` → caller fill → `preflight` → `consult`; exact v3 schema; atomic normalized output; legacy translation; and historical artifact validation. Keep examples sanitized and never use remediation examples as defaults.

- [ ] **Step 5: Run compatibility and pressure regression matrix**

Run: `python3 -m unittest -v tests.test_codex_senior_consult.ConsultProductTests.test_pressure_baseline_contract tests.test_codex_senior_consult.ConsultProductTests.test_historical_v1_v2_artifacts_are_read_only tests.test_codex_senior_consult.ConsultProductTests.test_complete_bundle_uses_one_process_one_stdin_one_turn_and_no_tools tests.test_codex_senior_consult.ConsultProductTests.test_one_explicit_replacement_is_fresh_and_linked tests.test_codex_senior_consult.ConsultProductTests.test_second_replacement_and_replacement_after_valid_verdict_are_rejected`

Expected: PASS.

- [ ] **Step 6: Commit the documentation and compatibility slice**

```bash
git add SKILL.md agents/openai.yaml references scripts/codex_senior_consult.py tests
git commit -m "docs: document v3 consultation workflow"
```

### Task 7: Full Offline Verification and Caller-Neutral Dogfood

**Files:**
- Modify only if a failing verification reveals an in-scope defect, using a new RED→GREEN cycle.
- Create runtime artifacts outside Git under a fresh `mktemp -d` directory.

**Interfaces:**
- Consumes: committed Tasks 1-6.
- Produces: clean committed offline-validated snapshot, one caller-neutral dogfood ledger/artifact, separate protocol/functional result, and evidence for the later Sol-medium gate.

- [ ] **Step 1: Run the complete deterministic suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: all tests PASS, zero skips and zero expected failures.

- [ ] **Step 2: Run compile and whitespace gates**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scripts/codex_senior_consult.py`

Run: `git diff --check`

Expected: both exit 0. Do not stage generated bytecode.

- [ ] **Step 3: Run CLI smoke tests**

Run each of:

```bash
python3 scripts/codex_senior_consult.py --help
python3 scripts/codex_senior_consult.py build-bundle --help
python3 scripts/codex_senior_consult.py preflight --help
python3 scripts/codex_senior_consult.py consult --help
python3 scripts/codex_senior_consult.py status --help
```

Then create a fresh non-Hermes local Git fixture, run `build-bundle`, fill every caller path with bounded synthetic evidence, run `preflight`, and verify `model_processes_consumed=0`.

- [ ] **Step 4: Run secret regressions explicitly**

Run the focused structural privacy, transport-redaction and persistence-sensitive tests. Expected: benign metadata and fingerprints pass; actual credentials and private keys fail; no diagnostic contains originals.

- [ ] **Step 5: Commit any final in-scope verification correction**

Only if a verification failure required a tested fix, commit that isolated fix. Otherwise make no empty commit.

- [ ] **Step 6: Verify the candidate snapshot is committed and clean**

Run: `git status --short`

Run: `git rev-parse HEAD`

Expected: no tracked or untracked changes. Generated tracked bytecode from baseline commands must be restored to committed content without staging; do not clean unrelated user files.

- [ ] **Step 7: Perform one real caller-neutral dogfood consultation**

Use a fresh temporary repository and mission unrelated to Hermes. Use the new `build-bundle`, fill only caller-required evidence, pass `preflight`, then invoke `consult` once with the normal Sol-low target/configuration. Do not use replacement merely to obtain a favorable result.

Record separately:

```text
protocol_execution_success = <true|false>
valid_advisory_verdict = <true|false>
```

Require the ledger/artifact to contain no raw transcript or credentials. A transport or malformed failure remains no-verdict and is not functional end-to-end success.

- [ ] **Step 8: Re-run the full offline suite after dogfood**

Run the complete suite, `py_compile`, `git diff --check`, CLI smoke matrix and secret regressions again. Verify the repository remains clean and the committed HEAD is unchanged.

- [ ] **Step 9: Prepare, but do not consume, the final Sol-medium merge gate**

Capture the committed HEAD, clean status, exact test results, dogfood protocol/functional fields, response artifact recoverability and remaining risks. The later separate Sol-medium gate may run only against this frozen snapshot. Hermes senior gates may resume only if preflight passed, the process completed, a valid mode-bound v3 response was returned, and its payload was atomically persisted and recovered.

---

## Plan Self-Review Checklist

- Every approved design section maps to at least one task: commands/construction (Tasks 2-3), preflight (Task 3), privacy (Task 4), transport (Task 5), v3 semantics (Task 1), compatibility/prompt/docs (Task 6), verification/dogfood/reactivation (Task 7).
- Each production behavior begins with a focused failing test and observed RED result.
- Compatibility explicitly covers legacy CLI translation and historical-only v1/v2 artifacts.
- Existing budget, replacement, persistence, cache, concurrency, zero-tool and pressure guarantees remain in the verification matrix.
- Hermes profile, symlink, pytest-collection, provider and K8 defects remain excluded.
- The final Sol-medium gate is reserved for a committed, clean and fully validated snapshot.
