# Examples

## Caller-neutral v3 flow

```bash
python3 scripts/codex_senior_consult.py build-bundle --mission-id example --mode merge-gate --repository . --output bundle.json
# Fill every null caller-owned field with bounded sanitized evidence.
python3 scripts/codex_senior_consult.py preflight --mission-id example --mode merge-gate --bundle bundle.json --normalized-output normalized.json
python3 scripts/codex_senior_consult.py consult --mission-id example --mode merge-gate --bundle bundle.json
python3 scripts/codex_senior_consult.py status --mission-id example
```

Remediation examples are guidance, never defaults. Normal construction requests `codex-senior-consult-response/v3`; validate v1/v2 only as explicit historical compatibility.

## Historical v2 merge gate

```bash
python3 scripts/codex_senior_consult.py --mode merge-gate \
  --mission-id migration-42 --bundle frozen-bundle.json --effort medium
```

The target returns only:

```json
{"schema_version":"codex-senior-consult-response/v2","verdict":"accept","safe_to_merge":true,"blocking_findings":[],"required_actions":[],"residual_risks":[],"summary":"Evidence supports the merge gate.","question_answers":[{"id":"merge-evidence","answer":"Yes; the supplied evidence supports the gate."}]}
```

## Replacement after no verdict

If the first result has `status: NO_VERDICT_PROTOCOL_FAILURE`, retain its `execution_id`. After local review, the caller may issue exactly one fresh invocation with the same frozen bundle:

```bash
python3 scripts/codex_senior_consult.py --mode merge-gate \
  --mission-id migration-42 --bundle frozen-bundle.json \
  --replacement-for 4a7b8d0e-0000-4000-8000-000000000001
```

Do not use this option after a valid verdict, for low confidence, disagreement, or an inconvenient answer. Never use `resume`, follow-up, or a repair prompt.

## Status

```bash
python3 scripts/codex_senior_consult.py --status --mission-id migration-42
```

Read `process_attempts` and `valid_verdicts` separately. `backend_requests_observed` is always `null` because the CLI does not expose that metric.
