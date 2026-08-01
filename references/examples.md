# Examples

## Contents

1. Bundle preparation
2. Integrated review
3. Exceptional plan
4. Replan
5. Merge gate
6. Workspace-read limitation
7. Mission status

## 1. Bundle preparation

Copy `consultation-bundle.example.json` outside the skill and replace every value with evidence from one identifiable snapshot. Keep all related questions in one array. Fingerprint locally; never ask Sol to inspect the source.

Before invoking, Luna must know which material decision the response can change, why deterministic local work is insufficient, which evidence supports each claim, which assumptions failed, what remains out of scope, and why the bundle contains no secret or unnecessary personal data.

Define the installed runner once:

```bash
CONSULT="${CODEX_HOME:-$HOME/.codex}/skills/codex-senior-consult/scripts/codex_senior_consult.py"
```

## 2. Integrated review

Use once after Luna has a credible plan and candidate decision:

```bash
python3 "$CONSULT" --mode integrated-review \
  --mission-id native-recovery \
  --bundle /tmp/native-recovery-consultation.json
```

Put plan review, risk audit, six related questions, candidate evaluation, minimum plan delta, and next safe action in this one bundle.

## 3. Exceptional plan

Use only after sufficient local research still cannot produce a viable plan:

```bash
python3 "$CONSULT" --mode plan \
  --mission-id native-recovery \
  --bundle /tmp/native-recovery-plan.json
```

## 4. Replan

Use only when new evidence materially invalidates the active plan. Preserve completed phases and the last green gate; identify the invalidated assumption and closed scope.

```bash
python3 "$CONSULT" --mode replan \
  --mission-id native-recovery \
  --bundle /tmp/native-recovery-replan.json \
  --critical conceptual_plan_failure
```

This selects `medium` and consumes the reserved third normal session. Request a delta, not a full replacement.

## 5. Merge gate

Use after implementation, local tests, runtime evidence, and claim classification:

```bash
python3 "$CONSULT" --mode merge-gate \
  --mission-id native-recovery \
  --bundle /tmp/native-recovery-merge.json
```

The schema requires `safe_to_merge`. Luna still checks every finding and owns the merge decision.

## 6. Workspace-read limitation

The current CLI exposes no way to grant repository reads while preserving the zero-tool contract. This command therefore fails before Codex executes:

```bash
python3 "$CONSULT" --mode blocker-analysis \
  --mission-id parser-isolation \
  --bundle /tmp/parser-isolation.json \
  --workspace-read /absolute/path/to/repository \
  --workspace-read-justification "Evidence cannot be represented safely in the bundle."
```

Expected status: `WORKSPACE_READ_UNSUPPORTED`, zero sessions. Put bounded evidence in the bundle instead.

## 7. Mission status

```bash
python3 "$CONSULT" --status --mission-id native-recovery
```

Expected multi-hour mission: two sessions, two observed turns, zero tools and follow-ups. Eighteen intervening Luna phases need no Sol. A deterministic mission reports zero sessions.
