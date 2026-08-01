# Contracts and Security Reference

## Ownership and execution boundary

The caller is the calling agent or mission owner. The senior consultant is advisory. A consultation execution may terminate fail-closed while the mission owner continues locally or starts one explicitly authorized replacement execution; ending the execution does not end the surrounding mission.

Every ordinary execution has one `codex exec` process, one stdin payload, one observed inference turn, zero tools, zero workspace reads, zero follow-ups, zero resume operations, zero repair executions, zero automatic content retries, an ephemeral session, and a bounded sanitized bundle. The wrapper observes process and turn facts only. It does not claim an exact backend HTTP request count.

## Input bundle

Input remains `codex-senior-consult/v1` for practical compatibility. It must contain the existing complete evidence, constraints, escalation, and snapshot fields. Questions may be strings for v1 callers; the wrapper deterministically normalizes them to `{ "id": "Q1", "text": "..." }`. New callers should provide stable IDs themselves. The normalized bundle fingerprint includes the IDs and all supplied material.

The bundle must contain no credentials, private paths, full history, or unnecessary logs. Secret detection reports JSON locations only. Descriptive fields such as `secret_scope`, `authentication_contract`, and redaction policies are allowed when they contain discussion rather than values; exact credential keys with non-empty values remain ambiguous and fail closed.

## Response v2

The target model returns only the mode payload and `schema_version: codex-senior-consult-response/v2`. The wrapper owns and records mission ID, mode, model, effort, snapshot fingerprint, normalized bundle fingerprint, execution ID, and replacement linkage. These are not copied metadata requirements for the target response.

The authoritative mode contract generates two artifacts. The transport schema is intentionally conservative and uses only `type`, `properties`, `required`, `additionalProperties`, `items`, and mode verdict `enum`. It is the schema sent to Codex. The local semantic contract retains non-empty fields, exact question coverage, cross-field invariants, snapshot checks, and every other strict v2 rule. A backend-valid response is only structurally valid; it becomes an advisory verdict only after local semantic validation succeeds.

All mode transport schemas are strict about object shape and reject additional properties. In the backend strict-output dialect, every declared property is also transport-required; local semantic validation retains the distinction between required and optional meaning. Focused contracts are:

```json
{
  "merge-gate": ["verdict", "safe_to_merge", "blocking_findings", "required_actions", "residual_risks", "summary"],
  "blocker-analysis": ["verdict", "ranked_causes", "continuation_paths", "recommended_path", "cheapest_discriminating_experiment", "stop_conditions", "next_safe_step"],
  "replan": ["verdict", "invalidated_assumptions", "plan_delta", "closed_phases_preserved", "new_stop_conditions", "next_safe_step"]
}
```

Every v2 mode also requires `question_answers`, an array of `{ "id": "Q1", "answer": "..." }`. Each normalized bundle question ID must appear exactly once; unknown or duplicate IDs and empty answers are invalid. Question text is not repeated.

The bounded verdict vocabularies are: `merge-gate`, `integrated-review`, `plan-review`, and `final-review`: `accept | changes_required | blocked`; `blocker-analysis`: `continue | human_required | blocked`; `replan`, `plan`, and `risk-audit`: `continue | changes_required | blocked`. For `merge-gate`, `accept` requires `safe_to_merge: true`, `blocking_findings: []`, and `required_actions: []`; every non-accept verdict requires `safe_to_merge: false`. Contradictions are invalid, not advisory verdicts.

All arrays are audited: action and stop-condition arrays contain non-empty strings; findings, causes, paths, risks, and claim classifications have strict small object shapes. Conditional singular fields such as `required_change` and `control` are not transported; plural arrays use deterministic empty values when nothing applies. `decision` and `plan` are objects in both JSON Schema and local validation; they are never accepted as arbitrary lists. The transport schema deliberately excludes `uniqueItems`, `minItems`, `maxItems`, `minLength`, `maxLength`, `pattern`, `format`, `contains`, `dependentRequired`, `oneOf`, `allOf`, `not`, `if`/`then`/`else`, `unevaluatedProperties`, and `propertyNames`. Exact question-ID uniqueness and coverage, non-empty values, array cardinality where required, verdict vocabulary, merge consistency, replacement linkage, and snapshot identity are enforced locally.

## v1 transition

Legacy v1 responses that repeat wrapper metadata and question text are accepted only when the input explicitly requests `codex-senior-consult-response/v1` or the caller passes `--legacy-response-v1`. This is a deterministic transition path, not a silent compatibility claim. New integrations should request v2 and consume wrapper metadata from the ledger/CLI result. v1 support may be removed in a future major version after consumers migrate.

## Failure and replacement

`NO_VERDICT_PROTOCOL_FAILURE` is the semantic status for a failed execution. Its `detailed_status` preserves the cause: `MALFORMED_SUPERIOR_RESPONSE`, `SINGLE_PASS_CONTRACT_VIOLATION`, `TRANSPORT_ERROR`, or `TIMEOUT`. A `TRANSPORT_ERROR` retains the process exit code, bounded redacted stderr and top-level JSONL error summaries, fingerprints, and an evidence-based category: `SCHEMA_OR_REQUEST_REJECTION`, `CLI_ARGUMENT_ERROR`, `AUTHENTICATION_ERROR`, `MODEL_UNAVAILABLE`, `RATE_LIMIT_OR_QUOTA`, `NETWORK_OR_SERVICE_ERROR`, or `UNKNOWN_TRANSPORT_ERROR`. No failure is interpreted as `accept`, `changes_required`, or `blocked`.

`VALID_ADVISORY_VERDICT` is emitted only after the canonical structured response is stored and re-read successfully. If parsing or semantic validation fails, the result is `NO_VERDICT_PROTOCOL_FAILURE`. If validation succeeds but canonical evidence cannot be durably committed, the result is `NO_USABLE_VERDICT` with `VERDICT_PERSISTENCE_FAILURE`: `verdict` and `response` are withheld, `validated_model_verdict` is informational only, and neither merge nor automatic replacement is authorized.

`--replacement-for EXECUTION_ID` is caller initiated and never automatic. Before transport, the wrapper verifies that the referenced entry exists, has no valid verdict, is not itself a replacement, has no prior replacement, and matches mission, mode, model, effort, snapshot, and normalized bundle fingerprint. The replacement uses a fresh process and the same prompt material. A second replacement, replacement after a valid verdict, changed material, or cache hit is rejected. Transport retries are a separate explicit legacy allowance and are counted; they are not content retries.

## Budgets and ledger

Normal semantic limits are two valid verdicts by default and three hard maximum. `replacement_attempts` has an independent default maximum of one. `process_attempts` has a separate hard cap (four by default, or the explicit `--process-hard-budget`); legacy `--hard-budget` remains the semantic cap and constrains total processes when set below the default. Mission locking covers budget checks, replacement authorization, cache decisions, and append-only ledger writes.

Ledger entries identify execution ID, replacement linkage, snapshot identity, normalized bundle fingerprint, process attempts, valid verdicts, protocol failures, cache hits, transport retries, and observed model turns. A usable entry additionally references a private content-addressed response artifact (`responses/<response-fingerprint>.json`, mode `0600`). The artifact contains only the validated canonical response, its fingerprint, response-schema version, identity, and question-answer coverage—never raw JSONL or unrelated model text. The wrapper atomically writes, fsyncs, re-reads, and verifies that artifact before it appends and fsyncs the ledger entry.

`--status` separately reports `valid_verdicts`, `usable_valid_verdicts`, and `unusable_valid_verdicts`. An older entry with a verdict but no response artifact is reported as `HISTORICAL_VALID_VERDICT_UNUSABLE`; a missing or corrupt referenced artifact is `VERDICT_EVIDENCE_UNUSABLE`. These are valid historical model outcomes but cannot authorize a merge, do not gain fabricated findings, and remain ineligible for replacement merely because their evidence is lost.

## Security model

The child environment allowlist is exactly `PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `TMPDIR`, and `CODEX_HOME` when present, plus the wrapper recursion marker `CODEX_SENIOR_CONSULT_ACTIVE=1`. `CODEX_HOME` is preserved because Codex authentication may live there even when `--ignore-user-config` remains enabled. API keys, provider credentials, authorization headers, and every other parent variable are excluded. The child receives an empty temporary working directory, read-only sandbox configuration, ignored user config/rules, and no workspace path. Tool-bearing or malformed JSONL fails closed. Timeout kills the process group. The model is instructed not to use tools; the wrapper treats any observed tool event as a contract violation. This reduces but cannot eliminate risks intrinsic to the CLI; do not submit catastrophic-disclosure material.
