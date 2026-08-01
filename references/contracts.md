# Contracts and Security Reference

## Ownership and execution boundary

The caller is the calling agent or mission owner. The senior consultant is advisory. A consultation execution may terminate fail-closed while the mission owner continues locally or starts one explicitly authorized replacement execution; ending the execution does not end the surrounding mission.

Every ordinary execution has one `codex exec` process, one stdin payload, one observed inference turn, zero tools, zero workspace reads, zero follow-ups, zero resume operations, zero repair executions, zero automatic content retries, an ephemeral session, and a bounded sanitized bundle. The wrapper observes process and turn facts only. It does not claim an exact backend HTTP request count.

## Input bundle

Input remains `codex-senior-consult/v1` for practical compatibility. It must contain the existing complete evidence, constraints, escalation, and snapshot fields. Questions may be strings for v1 callers; the wrapper deterministically normalizes them to `{ "id": "Q1", "text": "..." }`. New callers should provide stable IDs themselves. The normalized bundle fingerprint includes the IDs and all supplied material.

The bundle must contain no credentials, private paths, full history, or unnecessary logs. Secret detection reports JSON locations only. Descriptive fields such as `secret_scope`, `authentication_contract`, and redaction policies are allowed when they contain discussion rather than values; exact credential keys with non-empty values remain ambiguous and fail closed.

## Response v2

The target model returns only the mode payload and `schema_version: codex-senior-consult-response/v2`. The wrapper owns and records mission ID, mode, model, effort, snapshot fingerprint, normalized bundle fingerprint, execution ID, and replacement linkage. These are not copied metadata requirements for the target response.

All mode schemas are strict and reject additional properties. Focused contracts are:

```json
{
  "merge-gate": ["verdict", "safe_to_merge", "blocking_findings", "required_actions", "residual_risks", "summary"],
  "blocker-analysis": ["verdict", "ranked_causes", "continuation_paths", "recommended_path", "cheapest_discriminating_experiment", "stop_conditions", "next_safe_step"],
  "replan": ["verdict", "invalidated_assumptions", "plan_delta", "closed_phases_preserved", "new_stop_conditions", "next_safe_step"]
}
```

Other supported modes use similarly minimal focused fields defined by `response_schema()` in the script. For `merge-gate`, `accept` requires `safe_to_merge: true`, `blocking_findings: []`, and `required_actions: []`; every non-accept verdict requires `safe_to_merge: false`. Contradictions are invalid, not advisory verdicts.

## v1 transition

Legacy v1 responses that repeat wrapper metadata and question text are accepted only when the input explicitly requests `codex-senior-consult-response/v1` or the caller passes `--legacy-response-v1`. This is a deterministic transition path, not a silent compatibility claim. New integrations should request v2 and consume wrapper metadata from the ledger/CLI result. v1 support may be removed in a future major version after consumers migrate.

## Failure and replacement

`NO_VERDICT_PROTOCOL_FAILURE` is the semantic status for a failed execution. Its `detailed_status` preserves the cause: `MALFORMED_SUPERIOR_RESPONSE`, `SINGLE_PASS_CONTRACT_VIOLATION`, `TRANSPORT_ERROR`, or `TIMEOUT`. No failure is interpreted as `accept`, `changes_required`, or `blocked`.

`--replacement-for EXECUTION_ID` is caller initiated and never automatic. Before transport, the wrapper verifies that the referenced entry exists, has no valid verdict, is not itself a replacement, has no prior replacement, and matches mission, mode, model, effort, snapshot, and normalized bundle fingerprint. The replacement uses a fresh process and the same prompt material. A second replacement, replacement after a valid verdict, changed material, or cache hit is rejected. Transport retries are a separate explicit legacy allowance and are counted; they are not content retries.

## Budgets and ledger

Normal semantic limits are two valid verdicts by default and three hard maximum. `replacement_attempts` has an independent default maximum of one. `process_attempts` has a separate hard cap (four by default, or the explicit `--process-hard-budget`); legacy `--hard-budget` remains the semantic cap and constrains total processes when set below the default. Mission locking covers budget checks, replacement authorization, cache decisions, and append-only ledger writes.

Ledger entries identify execution ID, replacement linkage, snapshot identity, normalized bundle fingerprint, process attempts, valid verdicts, protocol failures, cache hits, transport retries, and observed model turns. Cache records contain only validated response and identity, have restrictive permissions, and never count as replacement executions.

## Security model

The child receives a minimal environment, an empty temporary working directory, read-only sandbox configuration, ignored user config/rules, no workspace path, and no copied auth store. Tool-bearing or malformed JSONL fails closed. Timeout kills the process group. The model is instructed not to use tools; the wrapper treats any observed tool event as a contract violation. This reduces but cannot eliminate risks intrinsic to the CLI; do not submit catastrophic-disclosure material.
