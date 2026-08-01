# Pressure-test baseline (RED)

Run before the skill existed. All three fresh subagents had no access to the intended skill.

## Transport pressure: time + authority + cheap quota

Failure: selected a persistent/resumed senior session, repository access, tool use, follow-up turns, repair turns, and automatic retries.

Verbatim rationalizations included: “A long mission benefits from the senior remembering its own earlier objections”; “Failure after obtaining a thread ID: resume that exact ID”; “Malformed payload: send one repair turn”; and “Retry the initial call twice.”

## Failure pressure: deadline + sunk implementation + answer-over-accounting

Failure: proposed one malformed-response repair execution, a low-confidence follow-up, a tool-call follow-up, and two transport retries.

Verbatim rationalizations included: “retry once with the validation error”; “ask one targeted follow-up”; “Follow up once requesting a self-contained, tool-free answer”; and “retry twice with capped exponential backoff.”

## Mission pressure: 20 phases + anxious director + ample quota

Failure: proposed six scheduled reviews plus four reserve consultations and one repair retry.

Verbatim rationalizations included: “after mission initialization, then after phases 4, 8, 12, 16, and 20”; “allocate six planned consultations plus a reserve of four”; and “One retry is allowed only for malformed or incomplete output.”

These failures define the skill's rationalization table, red flags, two-session cadence, and fail-closed no-repair behavior.

## Wording micro-test

One identical pressure prompt was sampled five times per arm in fresh subagent contexts.

- No-guidance control: 0/5 selected the required terminate-after-first-response policy; three selected a repair/follow-up and two selected persistence/resume.
- With the installed skill: 5/5 selected terminate-after-first-response, explicitly rejecting repair, follow-up, retry, and resume.

Every flagged response was read manually; no result was a template echo or quoted counter-example.

## GREEN pressure replay

The three original combined-pressure scenarios were replayed with the skill in fresh contexts. All complied:

- transport: one grouped `integrated-review`, no tools/workspace by default, no content retry/follow-up/resume;
- failure handling: malformed, low-confidence, tool-call, and transport outcomes remained literal and fail-closed;
- 20-phase mission: one initial review, 18 local phases, one merge gate, third session reserved for material replan, deterministic mission zero.

No new rationalization appeared. The agents cited the single-pass contract, non-negotiable failures, budgets, and escalation gate as the reason for compliance.

Meta-test result: the evaluator found no reasonable reading that allowed repair or resume and identified the exact binding rule as “one observed inference turn, zero tools, zero follow-ups, zero `resume`, zero repair executions.” No wording change was requested.

## Real dogfood

Authentication was available. Exactly one real `gpt-5.6-sol`, effort `low`, no-cache, zero-retry invocation was made for mission `skill-creation-dogfood-v1`.

Observed result: `TRANSPORT_ERROR`; one `codex exec` process, one observed model turn, zero tools, zero follow-ups, zero resume, zero repair executions, zero transport retries, and unknown backend request count. JSONL had no `turn.completed` event, so the wrapper correctly refused to treat the process as a verdict. The run was not relaunched or repaired. Offline validation remains the completion basis; real dogfood is not a successful smoke.
