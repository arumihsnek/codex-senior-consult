# Consolidated Hermes Kanban Field-Failure Report

Date preserved: 2026-08-01

Provenance: normalized transcription of the field-failure report supplied by the mission owner. This document records observed evidence; it is not the approved design or implementation plan.

## Executive result

The skill failed closed. It produced no unsafe verdict, exposed no secrets and caused no incorrect merge. Normal gates were nevertheless impeded by transport failures, malformed senior responses and bundle-construction friction.

Preserved external artifacts reported by the mission:

- `/home/ubuntu/.hermes-worktrees/kanban-k8-config-senior-artifacts/`
- `/home/ubuntu/.hermes-worktrees/.checkpoints/kanban-remediation.md`
- configuration PR #23, draft, head `9acd789`
- product PR #3, draft, head `43978745`

Base invocation:

```bash
python3 /home/ubuntu/.codex/skills/codex-senior-consult/scripts/codex_senior_consult.py \
  --mode merge-gate \
  --mission-id <mission> \
  --bundle <bundle.json> \
  --effort high \
  --ledger <ledger.jsonl> \
  --cache <cache>
```

Explicit replacements used `--replacement-for <execution_id>`.

## Observed skill incidents

### T1: transport before a model turn

- Mode: `merge-gate`.
- Executions: `a98e52f9-d731-416e-a8ca-d0ce5a01b081` and replacement `d1be8efd-5e1c-45da-aa4c-cd29c614a59a`.
- Expected: a valid response or an actionable sanitized transported error.
- Actual: `TRANSPORT_ERROR`, `NO_VERDICT_PROTOCOL_FAILURE`, zero model turns.
- Evidence: `senior-ledger.jsonl`, `observed_model_turns=0`, `protocol_failures=1`.
- Workaround: the single allowed replacement was consumed and the mission continued locally.
- Demonstrated cause: transport failed before the model turn.
- Unconfirmed hypothesis: temporary CLI, environment, service or model incompatibility.
- Reproduced twice; severity P1.

### S2: incomplete v5 bundle

- Mode: `merge-gate`.
- Actual: `BUNDLE_INCOMPLETE` for fields including `objective`, `diff`, `tests`, `runtime_evidence`, `alternatives`, `snapshot` and `requested_output`.
- Workaround: manual completion against `references/contracts.md`.
- Demonstrated cause: incomplete caller bundle.
- Zero senior processes consumed; severity P2.

### S3: ambiguous response-schema guidance

- Expected: the caller intended response v2.
- Actual: rejected because the caller used `"schema_version": "v2"` instead of `"codex-senior-consult-response/v2"`.
- Workaround: correct the exact value.
- Demonstrated cause: incorrect schema value and insufficiently explicit validation guidance.
- Zero senior processes consumed; severity P2.

### S4: benign sensitive-name metadata rejected

- Expected: accept `"secrets_added": false` as safe evidence.
- Actual: `SECRET_DETECTED` based on the field name despite the boolean false value.
- Workaround: remove the field and restate the evidence descriptively.
- Demonstrated cause: a privacy gate too lexical for boolean metadata.
- No privacy bypass and zero senior processes consumed; severity P2.

### S5: second incomplete bundle

- Mode: `merge-gate`, v6.
- Actual: `BUNDLE_INCOMPLETE` because `diff` was absent.
- Workaround: add `diff` manually.
- Demonstrated cause: caller omission.
- Zero senior processes consumed; severity P2.

## Bundle construction and snapshot binding

S2-S5 were construction failures, not senior-model response failures. The mission owner had to read the contract, complete mandatory fields, correct the exact response schema, remove a privacy-gate false positive and manually reconstruct snapshots and fingerprints.

Initial bundles omitted parts of the required identity: `repository_head`, `working_tree_fingerprint`, `plan_fingerprint` and `checkpoint_fingerprint`. The wrapper rejected them. Corrected bundles were bound to commit, diff and checkpoint and valid verdicts remained content-addressed. No verdict with an incorrect snapshot was accepted.

Conclusion: snapshot binding was safe; caller construction was manual and omission-prone. Severity P2 caller/UX.

## Privacy evidence

No secrets were printed, persisted or versioned:

- `secret_values_printed=0`;
- diff-only scans were clean;
- `auth.json` was not copied;
- tokens were not printed;
- ambiguous input was stopped by the gate.

The demonstrated defect is a benign-name false positive, not a P0 vulnerability.

## Transport ledger evidence

No persistence corruption was observed. Valid verdict artifacts included:

- `340657f3-b369-4e97-8b23-fdb1a73abcf1`: `blocked`;
- `a184a205-70e2-45d2-b1ca-aa71ed3bb128`: `changes_required`;
- `49ca1f23-eb12-467a-8a8f-91bd3368ffb1`: `changes_required`;
- `c22464f9-c4ff-42a4-be31-5017957fc16d`: `blocked`.

Malformed failures received neither a verdict nor an actionable response artifact. Ledgers preserved `TRANSPORT_ERROR` but did not retain a sufficiently specific sanitized cause such as timeout, authentication, model availability or network.

## Malformed response evidence

Statuses remained correctly differentiated:

- `BUNDLE_INCOMPLETE`
- `SECRET_DETECTED`
- `TRANSPORT_ERROR`
- `MALFORMED_SUPERIOR_RESPONSE`
- `VALID_ADVISORY_VERDICT`
- `NO_VERDICT_PROTOCOL_FAILURE`

Malformed-response execution prefixes:

- v2: `bd8805ba...`, `cd9d40e...`
- v4: `a0967a4c...`, `2e5d0159...`
- v6: `5d6bee53...`, `a11746a2...`

The common preserved diagnostic was:

```text
merge-gate accept is inconsistent
```

The skill correctly refused reinterpretation. The demonstrated P2 defect is insufficient structural detail about which accept fields contradicted one another. The report does not preserve lossless copies of all six response payloads.

## Budget and replacement behavior

The following behavior worked as designed:

- one process per consultation;
- one model turn when transport reached a model;
- zero follow-ups, resume or repair calls;
- maximum one replacement per snapshot;
- no replacement after a valid verdict;
- no improper automatic retry.

Observed replacements existed for the original transport failure and config v2, v4 and v6. There is no demonstrated budget or replacement defect.

## External Hermes and product incidents: out of skill scope

### H1: profile installation rejected symlinks

Hermes v0.19 rejected distribution symlinks such as `skills/hermes-dojo` and `scripts/kanban-human-gate-notifier.py`. Isolated `cp -aL` staging allowed three profiles to install with zero symlinks and cron disabled. The canonical checkout and credentials remained untouched. This is an operational Hermes issue, not a senior-consult skill defect.

### H2: historical executable contaminated pytest collection

`python3 -m pytest -q` ended in `INTERNALERROR` because a historical attachment executed `SystemExit(0)` during collection. A scoped configuration/profile matrix passed 54 tests. This is an external harness issue.

### H3: K8 product initially exposed only a pure adapter

A valid cross-repository verdict found that K8 was not connected to dispatcher/spawn boundaries. Product wiring was corrected locally at `43978745`. This is product integration, not this skill.

### H4: configured providers lacked live proof

Only the Codex route had live evidence; other candidates were unauthenticated or unproven. Routes were marked `inactive-unproven`, `routable=false` and product returned `POLICY_BLOCK`. This is provider coverage/policy, not this skill.

## Demonstrated skill defects

1. Transport failures lacked sufficiently actionable sanitized ledger diagnostics.
2. The structural privacy gate falsely rejected benign boolean metadata based on sensitive key names.
3. Strict bundle validation was too difficult and omission-prone for long-running callers.
4. Merge-gate contradiction diagnostics identified inconsistency without enumerating the contradictory fields.

## Behavior not demonstrated defective

- verdict integrity;
- snapshot correctness enforcement;
- replacement budget;
- persistence correctness;
- secret isolation;
- zero-tool and zero-workspace-read senior execution.

## Unconfirmed hypotheses

- exact cause of the two transport errors;
- whether malformed responses originated in prompt, model, CLI or validator interaction;
- backend incompatibility specific to `gpt-5.6-sol`.

These hypotheses must not be reported as causes without new evidence.

## Incident counts and severity

Sixteen tracked events:

- two transport failures;
- six malformed responses;
- four local bundle rejections;
- four integration, harness or provider findings.

Severity summary:

- P0: zero;
- P1: transport failures, malformed senior responses, profile-install blockage and merge gates lacking valid verdicts;
- P2: bundle rejections, incomplete transport diagnosis, collection contamination and initially routable unproven providers;
- P3: documentation and bundle UX.

Deduplicated causes:

1. insufficient transport diagnosis;
2. merge-gate responses inconsistent with the contract;
3. strict but manually difficult bundle schema;
4. privacy detector too lexical;
5. Hermes symlink incompatibility;
6. incomplete live provider evidence;
7. executable historical pytest fixture.

## Temporary safe operating rules reported by the mission

- Do not interpret malformed output as a verdict.
- Do not merge PR #23 or PR #3 on this evidence.
- Keep unproven provider routes inactive and non-routable.
- Use complete v1 input bundles and the exact requested response schema.
- Keep worktrees and runtimes isolated.
- Never copy `auth.json`, tokens or secrets.
- Treat synthetic evidence as offline, never live PASS.

## Minimum skill remediation requested by the report

1. Local actionable bundle preflight before `codex exec`.
2. A complete reusable canonical bundle builder.
3. Sanitized categorized transport evidence persisted in the ledger.
4. Structural privacy handling for benign sensitive-name metadata.
5. Fixtures and field-path diagnostics for contradictory accept responses.
6. A fresh caller-neutral skill validation before any real merge gate.

## Evidence boundary

This report proves safe fail-closed behavior and the listed ergonomic and diagnostic defects. It does not prove the exact transport root cause, any provider claim beyond the reported mission evidence, or any defect in Hermes installation, symlink handling, pytest collection, provider routing or K8 wiring that should be fixed inside `codex-senior-consult`.
