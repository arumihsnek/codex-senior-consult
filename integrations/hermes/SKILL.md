---
name: codex-senior-consult
description: Use when a Hermes mission needs one bounded senior Codex consultation for a material architecture, security, recovery, replanning, final-review, or merge decision and can supply a complete sanitized evidence bundle.
version: 3.0.0
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [codex, senior-consult, review, merge-gate, orchestration]
    related_skills: []
---

# Codex Senior Consult for Hermes

Use this skill from Hermes to call Codex CLI as a bounded external senior consultant. Hermes remains the mission owner: it investigates, edits, runs tests, constructs the frozen bundle, validates the advisory result, and performs every operational action. The consultant receives only the supplied sanitized bundle and must not inspect the workspace or use tools.

The installed command is caller-neutral:

```bash
codex-senior-consult build-bundle ...
codex-senior-consult preflight ...
codex-senior-consult consult ...
codex-senior-consult status ...
```

Do not depend on the skill installation path. The installer places `codex-senior-consult` in the selected bin directory and preserves the existing Codex skill distribution separately.

## Required workflow

1. **Investigate locally.** Resolve deterministic questions with repository inspection, tests, logs, and existing contracts before escalating.
2. **Build one bounded bundle.** Group the unresolved material questions and include only sanitized, mission-owned evidence.
3. **Run preflight first.** Preflight must report `valid: true` and consume zero model processes before any consultation is allowed.
4. **Run one consultation.** Use the local terminal backend and give the outer Hermes terminal timeout more margin than the wrapper timeout. For the default wrapper timeout of 180 seconds, use at least 240 seconds outside it.
5. **Parse stdout as JSON even on a non-zero exit code.** Diagnostic failures intentionally use non-zero exit codes.
6. **Accept only usable evidence.** Only `status: VALID_ADVISORY_VERDICT` makes the returned response actionable. A timeout, transport error, malformed response, tool violation, persistence failure, cache failure, or other no-verdict state is not a semantic verdict.
7. **Continue locally.** Validate the advice against the repository and execute all changes in Hermes.
8. **Never retry automatically.** A fresh replacement is allowed only after a returned no-verdict protocol failure and only through the explicit `--replacement-for <execution-id>` contract.

## Example

```bash
codex-senior-consult preflight \
  --mission-id hermes-example \
  --mode merge-gate \
  --bundle consultation.json

codex-senior-consult consult \
  --mission-id hermes-example \
  --mode merge-gate \
  --bundle consultation.json \
  --model gpt-5.6-sol \
  --effort low \
  --timeout 180
```

## Status handling

- `VALID_ADVISORY_VERDICT`: consume the validated response and verify it locally.
- `ESCALATION_NOT_JUSTIFIED`: continue locally without calling Codex.
- `PREFLIGHT_INVALID`, `BUNDLE_INCOMPLETE`, `SECRET_DETECTED`, or `PRIVATE_PATH_DETECTED`: repair the bundle locally; no model process should have been consumed.
- `NO_VERDICT_PROTOCOL_FAILURE`: no semantic verdict exists. Do not translate it into accept, reject, blocked, or changes-required.
- `NO_USABLE_VERDICT`: a model response is not operationally usable; do not act on it.
- `CACHE_INVALID` or evidence-integrity failures: stop consuming that evidence and diagnose locally.

Record a compact mission note containing `status`, `execution_id`, `mode`, `verdict` when present, and the persisted artifact identity. Do not inject arbitrary free text into Hermes state databases and do not copy private artifacts into the conversation unnecessarily.

## Environment

The execution environment must provide:

- `python3`;
- `codex` in `PATH`, or the backend path supported by the wrapper;
- valid Codex CLI authentication, normally through `CODEX_HOME`;
- persistent access to the configured ledger and cache directories;
- the repository and Git metadata needed while building the snapshot.

Use the local terminal backend unless an alternative backend deliberately mounts the Codex binary, authentication, repository, and persistent state.

## Verification checklist

- [ ] A fresh Hermes session discovers this skill.
- [ ] `codex-senior-consult --help` succeeds.
- [ ] An invalid preflight consumes zero Codex processes.
- [ ] A valid preflight consumes zero Codex processes.
- [ ] A real consultation returns one JSON object that Hermes classifies by `status`.
- [ ] Non-zero exits still expose and preserve diagnostic JSON.
- [ ] Cache hits, budgets, replacement rules, ledger, and artifact verification behave identically to the Codex caller flow.
