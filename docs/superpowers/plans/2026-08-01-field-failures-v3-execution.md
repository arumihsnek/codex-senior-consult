# Codex Senior Consult v3 Field-Failure Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and superpowers:test-driven-development. Execute each task RED → GREEN and stop at every stated gate.

**Goal:** Implement the frozen v3 design without changing the bounded, single-pass, fail-closed consultation model.

**Normative specification:** `references/designs/field-failures-v3-design.md`, introduced by `cd17a6d` and corrected by `f37d752` to clarify deterministic `caller_required` normalization.

**Supporting evidence:** `references/field-reports/2026-08-hermes-kanban.md`.

**Green baseline:** `38a867b`; `python3 -m unittest discover -s tests -v` reported 61/61 passing.

**Architecture:** Keep one executable, `scripts/codex_senior_consult.py`, as the authoritative implementation. Add subcommands that share pure construction, normalization and preflight functions; translate the historical flat CLI into `consult`; keep response contracts versioned and mode-bound; retain existing ledger, cache, replacement, persistence and locking code.

## Global invariants

- No production edit precedes a failing test or fixture that names the broken behavior.
- `caller_required` is construction metadata and never enters the normalized payload or either fingerprint.
- No fingerprint is calculated until normalization succeeds and `caller_required` is empty.
- Preflight consumes zero Codex processes.
- No secret value, raw transport transcript or secret-derived fingerprint is emitted or persisted.
- Malformed output never becomes a verdict and never causes a repair, resume or automatic content retry.
- One explicit replacement remains the maximum; a replacement cannot be replaced.
- Snapshot binding, budgets, process limits, atomic verdict persistence, cache behavior and locking remain strict.
- The wrapper may assert process, JSONL and observed model-turn facts only, never an exact backend HTTP request count.
- Hermes profiles, symlinks, external pytest collection, provider routing/coverage, K8 wiring, active PRs/worktrees and mission continuation are out of scope.

## Task DAG

```text
P1 CLI translation
 └─> P2 construction
      └─> P3 normalization/fingerprints
           ├─> P4 preflight
           └─> P5 privacy
P1 ───────────────> P6 transport
P1 ───────────────> P7 v3 response semantics
P7 ───────────────> P8 historical compatibility
P2,P3,P4,P5,P6,P7,P8 ─> P9 documentation/fixtures
P1..P9 ────────────> P10 offline validation/dogfood/freeze
P10 ───────────────> P11 separate Sol-medium merge gate
```

P1-P9 may be implemented only on `evolve-field-failures-v3`. P10 requires all prior tasks committed. P11 is not part of implementation and must run in a separate Sol-medium consultation against the frozen P10 snapshot.

## P1 — Explicit CLI Subcommands and Legacy Translation

**Exact files:** Modify `scripts/codex_senior_consult.py`; modify `tests/test_codex_senior_consult.py`.

**Contract requirement implemented:** Add `build-bundle`, `preflight`, `consult`, and `status`. Translate the existing flat invocation into internal `consult` arguments before parsing. Every consultation reaches the same shared preflight; no legacy bypass exists.

**Initial failing test or fixture:** Add `test_all_subcommands_have_help`, `test_legacy_cli_translates_to_consult`, and `test_legacy_and_explicit_consult_use_same_preflight`. The last test replaces the process runner with a fail-if-called sentinel and supplies the same invalid bundle through both syntaxes.

**Minimal implementation boundary:** Introduce `build_parser()`, `translate_legacy_argv(argv)`, and `dispatch(args)`. Do not change bundle validation, process spawning or response schemas in this task.

**Expected green tests:** The three new tests plus existing status, one-process, recursion, dangerous-yolo and workspace-read tests.

**Compatibility impact:** Historical flat syntax remains accepted but has no independent execution path. No output semantics change yet.

**Security invariants preserved:** Invalid legacy input consumes zero processes; no new workspace/tool access; recursion guard remains before execution.

**Dependencies:** Green `38a867b` baseline only.

**Completion evidence:** Focused RED output; focused GREEN output; full suite green; commit containing only parser/dispatch and tests.

## P2 — Canonical Construction Bundle and RFC 6901 Metadata

**Exact files:** Modify `scripts/codex_senior_consult.py`; modify `tests/test_codex_senior_consult.py`; create `tests/fixtures/incomplete-bundles/s2-v5.json`, `s3-schema-shorthand.json`, `s4-benign-secret-metadata.json`, and `s5-v6-missing-diff.json`.

**Contract requirement implemented:** `build-bundle` produces a complete skeleton for all eight modes, fills only locally deterministic repository facts, initializes every caller field to `null`, and lists caller fields with exact RFC 6901 pointers. It never invents evidence or uses sentinel strings.

**Initial failing test or fixture:** `test_build_bundle_for_every_mode_is_complete_and_deterministic`, `test_build_bundle_never_invents_evidence`, and table-driven fixture tests for S2-S5.

**Minimal implementation boundary:** Add a closed construction-field registry and `build_bundle_skeleton(mission_id, mode, repository)`. Use argument-vector Git calls for repository root, HEAD, porcelain dirty state and bounded tree/diff identity. Do not normalize filled values in this task.

**Expected green tests:** All construction tests for clean, dirty and non-Git inputs; S2/S3/S5 fail with their primary field; S4 reaches the later privacy gate without a construction error.

**Compatibility impact:** Ordinary generated bundles request `codex-senior-consult-response/v3`; no new v1/v2 generation path.

**Security invariants preserved:** No file contents or secrets are copied automatically; evidence fields remain null; repository commands are read-only and bounded.

**Dependencies:** P1.

**Completion evidence:** Deterministic fixture snapshots, RED/GREEN logs and a construction-only commit.

## P3 — Shared Normalization and Fingerprint Timing

**Exact files:** Modify `scripts/codex_senior_consult.py`; modify `tests/test_codex_senior_consult.py`.

**Contract requirement implemented:** Decode RFC 6901, reject unknown/duplicate/out-of-schema paths, validate newly filled non-null caller values, remove valid paths, retain invalid paths with `CALLER_VALUE_INVALID`, and reserve `CALLER_REQUIRED_NON_NULL` for deterministic non-caller-fillable fields. Strip construction metadata and fingerprint only after successful normalization.

**Initial failing test or fixture:** `test_filled_caller_path_is_removed_after_validation`, `test_invalid_filled_path_remains_pending`, `test_pointer_escape_rules`, `test_duplicate_and_unknown_pointers_fail`, `test_deterministic_field_pointer_is_forbidden`, and `test_no_fingerprint_before_empty_caller_required`.

**Minimal implementation boundary:** Add `decode_json_pointer()`, `resolve_bundle_pointer()`, `normalize_construction_bundle()`, and a result type containing normalized payload, pending pointers and diagnostics. Reuse canonical JSON hashing only after success.

**Expected green tests:** All pointer/state tests plus existing snapshot mismatch, changed-snapshot replacement and cache identity tests.

**Compatibility impact:** Fully complete historical raw bundles without `caller_required` normalize through the same content validator; only explicit historical response-policy flags may request v1/v2 validation.

**Security invariants preserved:** Construction metadata never reaches the prompt or hashes; invalid or sentinel-like values fail closed; snapshot identity remains frozen.

**Dependencies:** P2.

**Completion evidence:** Tests demonstrate no hash call on invalid input and exact normalized fingerprints on valid input; isolated commit.

## P4 — Actionable Zero-Process Preflight

**Exact files:** Modify `scripts/codex_senior_consult.py`; modify `tests/test_codex_senior_consult.py`.

**Contract requirement implemented:** Perform bundle, local-state, ledger/cache, replacement and lock checks without Codex. Return stable code, RFC 6901 path, missing/null/invalid state, reason, exact expected type/value, concrete guidance/source, category and `model_process_consumed: false`. Suppress derivative cascades.

**Initial failing test or fixture:** `test_preflight_consumes_zero_processes`, `test_preflight_distinguishes_missing_null_invalid`, `test_preflight_suppresses_dependent_errors`, `test_preflight_exact_response_schema_guidance`, `test_preflight_reports_check_groups`, and atomic normalized-output overwrite tests.

**Minimal implementation boundary:** Add a diagnostic data shape, prerequisite-aware validation phases, stable normalized summary and atomic `0600` output. Reuse current budget/replacement/lock helpers without reserving an execution or appending ledger entries.

**Expected green tests:** New preflight matrix; all S2-S5 diagnostics; existing budget, replacement and concurrency tests.

**Compatibility impact:** Both legacy and explicit `consult` call this preflight. Status remains read-only. Existing valid bundles remain executable after normalization.

**Security invariants preserved:** Zero process creation; remediation examples never become defaults; no partial normalized payload in stdout; source file never overwritten.

**Dependencies:** P1 and P3.

**Completion evidence:** A process-spawn counter remains zero for valid and invalid preflight; atomic-mode/overwrite assertions pass; isolated commit.

## P5 — Structural Privacy Classification

**Exact files:** Modify `scripts/codex_senior_consult.py`; modify `tests/test_codex_senior_consult.py`; reuse `tests/fixtures/incomplete-bundles/s4-benign-secret-metadata.json`.

**Contract requirement implemented:** Accept benign boolean/descriptive metadata while rejecting actual, ambiguous or credential-shaped values. Entropy is auxiliary only. Diagnostics expose path and category, never values.

**Initial failing test or fixture:** A matrix accepting `secrets_added: false`, `secret_scope_behavior: "fail-closed"`, `authentication_reviewed: true`, SHA-256, commit SHA and content fingerprints; rejecting a token, private key and ambiguous high-entropy sensitive value; and asserting secrets do not appear in output.

**Minimal implementation boundary:** Replace lexical-key rejection with `privacy_findings(value)` using key role, type, credential prefixes/patterns, digest recognition and descriptive context. Keep `secret_locations()` as a compatibility path-only adapter where existing callers require it.

**Expected green tests:** Privacy matrix, S4 end-to-end preflight success, existing FIFO/private-path checks and response-persistence secret regressions.

**Compatibility impact:** Benign metadata previously rejected becomes valid; actual and ambiguous credentials remain rejected. No persisted schema changes.

**Security invariants preserved:** Sanitized paths/categories only; no raw value, excerpt or raw-derived fingerprint; fail closed on ambiguity.

**Dependencies:** P3; P4 for full CLI assertions.

**Completion evidence:** Mutation checks show removing token/private-key detection fails tests and treating entropy alone as decisive fails digest tests; isolated commit.

## P6 — Bounded Transport Diagnostics and Ledger Evidence

**Exact files:** Modify `scripts/codex_senior_consult.py`; modify `tests/test_codex_senior_consult.py`.

**Contract requirement implemented:** Parse bounded top-level `error`, `turn.failed`, malformed/unknown JSONL, exit status, timeout and sanitized stderr. Classify only supported evidence into CLI argument, authentication, model unavailable, quota/rate limit, schema/request rejection, safety/policy rejection, network/service failure, timeout, `PROCESS_EXIT_WITHOUT_STRUCTURED_EVIDENCE`, or `UNKNOWN_TRANSPORT_ERROR` for structured but safely unrecognized evidence.

**Initial failing test or fixture:** Table-driven `test_actionable_transport_categories`; separate malformed-line continuation/truncation tests; `invalid_json_schema`; exact timeout; nonzero exit with no events; unknown structured event; and secret-bearing raw messages that must not survive.

**Minimal implementation boundary:** Add sanitize-first `parse_transport_evidence()` with event/evidence/length bounds, deterministic primary category, deduplicated secondary evidence and counters. Persist only normalized sanitized evidence.

**Expected green tests:** New classification matrix plus existing transport retry, malformed JSONL, no-repair and ledger status tests.

**Compatibility impact:** Status gains bounded diagnostic fields; failure status remains `NO_VERDICT_PROTOCOL_FAILURE`. No previously failed transport becomes a verdict.

**Security invariants preserved:** Sanitize before truncation/fingerprint/persistence; no stdout/stderr transcript; unknown evidence is not over-classified.

**Dependencies:** P1. May proceed independently of P2-P5.

**Completion evidence:** Every category has a direct fixture, no diagnostic contains seeded secrets, process-without-evidence and structured-unknown are distinct, isolated commit.

## P7 — Mode-Bound Response v3 and Merge-Gate Semantics

**Exact files:** Modify `scripts/codex_senior_consult.py`; modify `tests/test_codex_senior_consult.py`; create six files under `tests/fixtures/malformed-responses/` for the v2/v4/v6 field incidents.

**Contract requirement implemented:** Default to exact `codex-senior-consult-response/v3`, bind shape to requested mode, require `non_blocking_observations` with `[]` valid, preserve the strict accept invariant, separate residual risks, and report every independent contradiction with exact path.

**Initial failing test or fixture:** An explicit eight-way accept truth table; mode-crossing rejection; accept with observations/risks; changes-required without blockers/actions; blocked without evidence; structured blocker in observations; structured pre-merge action in residual risks; six reconstructed incident fixtures.

**Minimal implementation boundary:** Add closed v3 observation/risk schemas, versioned mode contracts and path-structured semantic diagnostics. Update the positive senior prompt recipe. Do not use free-text NLP to infer blockers.

**Expected green tests:** All v3 shape/semantic tests, backend-schema allowlist tests, no-repair tests and valid-artifact persistence tests.

**Compatibility impact:** New ordinary responses are v3. V2 artifacts are not mutated or reinterpreted. V3 for the wrong mode fails.

**Security invariants preserved:** Local validation remains stricter than transport schema; contradictory/malformed output has no verdict or artifact; no second process is launched.

**Dependencies:** P1. P8 depends on this task.

**Completion evidence:** Exactly one truth-table combination passes; every invalid combination exposes its contradictory paths; reconstructed fixtures declare provenance; isolated commit.

## P8 — V1/V2 Historical Read-Only Compatibility

**Exact files:** Modify `scripts/codex_senior_consult.py`; modify `tests/test_codex_senior_consult.py`.

**Contract requirement implemented:** Permit v1/v2 only through explicit test/compatibility validation. Do not generate new ordinary v1/v2 bundles or silently migrate historical artifacts. Preserve recovery and unusable-evidence semantics.

**Initial failing test or fixture:** `test_builder_only_generates_v3`, `test_normal_consult_rejects_v1_v2_request`, `test_explicit_compatibility_validates_historical_v1_v2`, `test_historical_artifact_is_not_rewritten`, and existing corrupt/missing historical evidence cases.

**Minimal implementation boundary:** Separate ordinary accepted schema from `HISTORICAL_RESPONSE_SCHEMAS`; gate historical validation behind an explicit compatibility/testing option not used by `build-bundle`.

**Expected green tests:** New compatibility matrix plus all existing v1/v2 artifact, replacement and cache tests.

**Compatibility impact:** Historical reading remains available; creation defaults exclusively to v3; shorthand version strings fail with exact canonical guidance.

**Security invariants preserved:** No reinterpretation, auto-migration, replacement after a historically valid verdict, or bypass of evidence recoverability.

**Dependencies:** P7 and P3.

**Completion evidence:** Byte-identical historical artifact before/after validation, exact guidance assertions and isolated commit.

## P9 — Documentation, Reconstructed Fixtures and Pressure Contract

**Exact files:** Modify `SKILL.md`, `agents/openai.yaml`, `references/contracts.md`, `references/examples.md`, `references/consultation-bundle.example.json`, `tests/pressure-baseline.md`, and `tests/test_codex_senior_consult.py`; create fixture files listed in P2 and P7.

**Contract requirement implemented:** Document the four commands, construction/normalization lifecycle, exact v3 schema, historical-only v1/v2, diagnostic shapes, privacy behavior, transport evidence and positive merge-gate recipe. Preserve fixture provenance and all pressure rejections.

**Initial failing test or fixture:** Executable pressure-contract test checking no repair, resume, post-execution clarification, low-confidence/inconvenient-verdict retry, tools/workspace, mission-failure inference, unrestricted second process, replacement-of-replacement or backend-request claim. Add documentation smoke assertions for exact command/version strings.

**Minimal implementation boundary:** Update only documentation/prompts/examples needed to expose implemented behavior. Reconstructed response fixtures contain only demonstrated contradictions and the exact provenance notice; they are not presented as lossless originals.

**Expected green tests:** Pressure contract, help/documentation smokes, prompt recipe and fixture provenance tests; full suite.

**Compatibility impact:** Callers receive v3 examples and migration guidance; historical users retain explicit read-only instructions.

**Security invariants preserved:** Examples contain no credentials/private paths; remediation examples are guidance only; pressure rules remain mandatory.

**Dependencies:** P2-P8.

**Completion evidence:** Documentation diff review, secret scan, fixture provenance check, full suite green and documentation-only commit.

## P10 — Offline Validation, Caller-Neutral Dogfood and Frozen Snapshot

**Exact files:** No planned repository edits. Runtime artifacts go in a fresh `mktemp -d` directory outside Git. If verification exposes an in-scope defect, return to the owning task with a new failing test and isolated fix commit.

**Contract requirement implemented:** Complete all requested offline gates, perform one non-Hermes real consultation, separate protocol from functional success, and freeze a committed clean snapshot.

**Initial failing test or fixture:** Not a new behavior task. Entry requires P1-P9 focused GREEN evidence and commits. Any new failure becomes a RED test in its owning task before a fix.

**Minimal implementation boundary:** Run, do not redesign: full suite; `py_compile`; `git diff --check`; four subcommand help smokes; status/build/preflight smokes; secret regressions; clean/dirty construction; atomic artifact recovery.

**Expected green tests:** Full suite with zero failures/skips/expected failures; compile and whitespace exit 0; preflight reports zero processes; secret matrix passes.

**Compatibility impact:** Validate legacy translation and historical artifacts alongside v3. No migration is executed.

**Security invariants preserved:** Dogfood uses a fresh caller-neutral non-Hermes repository; one ordinary process; no production PR; no replacement for preference; sanitized ledger/artifact only.

**Dependencies:** P1-P9 committed.

**Completion evidence:** Exact commands/results; `protocol_execution_success` and `valid_advisory_verdict` reported separately; valid response artifact persisted and recovered if produced; final `git status --short` empty; recorded HEAD unchanged after final validation.

## P11 — Separate Sol-Medium Merge Gate

**Exact files:** No implementation files. Create only an external/fresh consultation bundle and runtime ledger/artifact for the frozen P10 HEAD.

**Contract requirement implemented:** Reserve the final senior merge decision for a separate Sol-medium consultation after the implementation is committed, clean and fully validated.

**Initial failing test or fixture:** Gate entry itself fails closed if any entry criterion is absent; no model process may start on an incomplete gate bundle.

**Minimal implementation boundary:** Build a fresh merge-gate bundle from the P10 HEAD, pass preflight and invoke once. Do not use Hermes production PRs as the first test and do not alter the frozen snapshot.

**Expected green tests:** Preflight valid with zero processes before consult; process completes; response is mode-bound v3; payload persists atomically and is recoverable.

**Compatibility impact:** None. This is an advisory gate over the completed v3 implementation.

**Security invariants preserved:** Same snapshot, model, effort and normalized bundle binding; no tools/workspace/follow-up/resume/repair; replacement rules unchanged.

**Dependencies:** P10 evidence complete and frozen.

**Completion evidence:** Sol-medium ledger/artifact, exact verdict usability, frozen HEAD identity and a resume/hold recommendation for Hermes senior gates.

## Exact test strategy

1. Run each new test alone and record the expected failure caused by the absent behavior.
2. Implement only the smallest boundary named in that task.
3. Re-run the focused test and its nearest existing regressions.
4. Run the complete suite before each task commit.
5. Never commit a skipped/expected-failure test as a substitute for GREEN.
6. Keep fake Codex assertions at wrapper-controlled boundaries; Python locale coercion is already isolated by `38a867b`.
7. Mutation-check critical branches: omit preflight, fingerprint early, leak construction metadata, accept a token, misclassify exit-without-evidence, accept wrong-mode v3, or allow a second replacement; each mutation must fail a named test.

## Migration and compatibility checkpoints

| Checkpoint | Required evidence |
|---|---|
| After P1 | Legacy and explicit consult share identical preflight path. |
| After P3 | Complete old input bundles normalize without construction metadata; fingerprints remain stable. |
| After P7 | Ordinary output request is exact v3 and mode-bound. |
| After P8 | V1/v2 validate only under explicit historical mode and artifacts remain byte-identical. |
| After P9 | Docs/examples never instruct ordinary v1/v2 creation. |
| P10 | Legacy, historical and v3 matrices pass together. |

## Security review points

| Review point | Evidence |
|---|---|
| Preflight boundary | Spawn counter is zero for valid and invalid preflight. |
| Normalization boundary | `caller_required` absent from prompt and fingerprints; no hash on pending input. |
| Privacy boundary | Output includes paths/categories only; seeded secrets absent from all outputs/artifacts. |
| Transport boundary | Sanitization precedes truncation and fingerprinting; no raw transcript persists. |
| Response boundary | Transport schema, mode contract and local semantic validation all pass before persistence. |
| Persistence boundary | Atomic artifact is re-read and verified before usable ledger entry. |
| Replacement boundary | One eligible replacement maximum; no replacement of replacement or valid verdict. |

## Dogfood entry criteria

- P1-P9 committed.
- Full offline suite green.
- `py_compile` and `git diff --check` exit 0.
- CLI help/status/build/preflight smokes pass.
- Secret regressions pass with no original values in diagnostics.
- Fresh non-Hermes repository and mission.
- Built bundle completed with bounded synthetic evidence.
- Preflight valid and `model_processes_consumed=0`.

Dogfood must report `protocol_execution_success` independently from `valid_advisory_verdict`. A well-rejected malformed response may satisfy protocol handling but is not functional consultation success. A diagnosed transport failure demonstrates fail-closed handling only.

## Final merge-gate entry criteria

- Implementation committed on the isolated branch.
- Worktree clean, with exact HEAD recorded.
- Full validation rerun after dogfood.
- Real dogfood process completed.
- Mode-bound v3 response valid.
- Canonical payload atomically persisted and recovered.
- No unresolved in-scope test or security finding.
- Fresh bundle bound to the exact frozen HEAD.
- Separate Sol-medium session; no model switch inside implementation work.

Hermes senior gates remain paused unless every criterion above succeeds.

## Explicit stop conditions

- Any requirement conflicts with the frozen design.
- Any proposed change touches an out-of-scope Hermes/product surface.
- Baseline or unrelated tests fail without a demonstrated cause.
- A test cannot be made RED for the intended production behavior.
- Preflight or an invalid bundle starts a Codex process.
- Any secret value/raw transcript appears in stdout, ledger, cache or artifact.
- Snapshot or fingerprint identity changes unexpectedly.
- A malformed response becomes usable or triggers repair/resume/follow-up.
- Budget, concurrency or replacement guarantees regress.
- Three fix attempts fail for the same issue; stop and reassess architecture.
- Dogfood entry criteria are incomplete.
- Worktree is dirty or HEAD changes before the Sol-medium gate.

## Design coverage matrix

| Approved design section | Plan tasks | Verification |
|---|---|---|
| 1. Caller-neutral construction and commands | P1, P2, P3 | CLI translation tests; all-mode skeletons; RFC 6901 normalization; fingerprint timing. |
| 2. Shared normalization and actionable preflight | P3, P4 | missing/null/invalid diagnostics; cascade suppression; zero process; atomic output. |
| 3. Structural privacy and bounded transport evidence | P5, P6 | privacy matrix; sanitized diagnostic assertions; transport classification/counters. |
| 4. Response v3 and merge-gate semantics | P7, P8 | mode binding; accept truth table; hidden blocker/action cases; historical read-only matrix. |
| 5. Testing, dogfood and reactivation | P9, P10, P11 | pressure suite; full offline gates; neutral dogfood; frozen Sol-medium gate. |
| Deliberately unchanged behavior | P1-P11 | existing budget, replacement, persistence, cache, concurrency, zero-tool and no-repair regressions. |
| Out-of-scope Hermes defects | Global constraint and stop conditions | Path/scope diff review before every commit. |

## Plan self-review result

- Uncovered approved requirements: none.
- Internal contradictions found: none.
- Compatibility policy changes: none.
- Safety invariants weakened: none.
- Out-of-scope work introduced: none.
- Production files modified while planning: none.
