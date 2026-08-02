# Codex Senior Consult — Dogfood, Incidents, and Follow-up Experiments

This document records real-world dogfood findings for `codex-senior-consult` gathered while it supervised a long-running autonomous Hermes mission.

It is a living engineering document, not a merge authorization and not a replacement for immutable execution artifacts.

## Evidence labels

Every entry must use one of these labels:

- **Observed** — directly supported by persisted responses, bundles, status artifacts, Git, tests, or GitHub state.
- **Inferred** — a reasoned explanation not yet proven by a focused reproduction.
- **Proposed** — a future change or experiment.
- **Needs reproduction** — seen in one mission but not isolated in the skill test suite.
- **Closed** — reproduced, fixed, tested, and merged.
- **Deferred** — intentionally postponed with a concrete retry condition.

Do not include secrets, credentials, raw protected values, unredacted environment dumps, or unsanitized caller bundles.

---

# 1. Dogfood scope

The skill was exercised repeatedly as the senior decision boundary for a long autonomous mission that included:

- exact-head configuration gates;
- exact-head product gates;
- cross-repository compatibility gates;
- planning gates;
- architecture/security gates;
- plan reviews;
- implementation and publication gates;
- final milestone closure gates;
- blocked-objective reviews;
- queue-exhaustion review;
- repeated local-to-remote snapshot transitions;
- malformed/transport-history handling without reusing old verdicts.

The closing operator must replace this summary with an exact execution inventory, including mode, mission ID, execution ID, snapshot identity, response schema, verdict, decision, usability, and downstream action.

---

# 2. Confirmed strengths

## STR-001 — Frozen exact-snapshot review worked across long missions

**State:** Observed

The skill successfully reviewed local candidates, remote PR heads, cross-repository pairs, and post-merge milestones without treating a verdict for one snapshot as authorization for another.

### Preserve

- exact snapshot identity in every bundle;
- invalidation after any material change;
- separate local-candidate and remote-exact-head gates;
- no reuse of historical K8/K9 responses for later heads.

### Further dogfood

- branch moves between preflight and consult;
- remote head changes after an accepted local gate;
- merge queue or generated merge refs;
- equivalent trees with different squash/merge commit identities;
- cross-repository gate where only one head changes.

## STR-002 — Failures without a valid response did not become verdicts

**State:** Observed

Malformed responses and transport failures were preserved as protocol failures rather than interpreted as accept/reject decisions.

### Preserve

- no verdict on malformed output;
- no verdict on timeout or transport failure;
- explicit replacement rules;
- persisted canonical response required before actionability.

### Further dogfood

- one allowed replacement succeeds;
- replacement also fails;
- replacement attempted after a valid but inconvenient verdict;
- persisted response write fails after schema validation;
- cache hit versus replacement accounting.

## STR-003 — The consultant remained caller-neutral and tool-free

**State:** Observed

The senior operated from sanitized bundles without workspace access, repository reads, or tools. Local investigation remained the responsibility of Luna.

### Preserve

- one bounded inference turn;
- no tools;
- no workspace reads;
- no automatic follow-up;
- no hidden repair consultation.

## STR-004 — Security gates prevented unsafe symlink materialization

**State:** Observed

The skill rejected a non-empty redistribution allowlist when ownership and non-sensitive-content authority were not proven per entry.

### Preserve

- deny-by-default decisions;
- explicit provenance requirements;
- distinction between metadata visibility and redistribution authority;
- refusal to turn absence of evidence into clearance.

### Further dogfood

- one entry with complete authority and sensitivity evidence;
- mixed approved and denied entries;
- authority expires or source digest changes;
- ownership proven but sensitivity clearance absent;
- sensitivity clearance proven but redistribution authority absent.

---

# 3. Incidents and ambiguities

## INC-001 — Top-level verdict and domain decision can be conflated

**State:** Observed

A queue-review response had a top-level senior verdict equivalent to `continue`, while a mode-specific answer explicitly concluded `QUEUE_EXHAUSTED`. The mission ledger flattened the domain decision into a field labelled as the plan verdict.

### Risk

Automated callers may mistake a mode-specific decision for the protocol-level verdict, or vice versa.

### Required investigation

- inspect the exact v3 queue/planning response contract;
- determine whether `QUEUE_EXHAUSTED` has a first-class machine-readable field;
- confirm whether callers must parse a question-specific answer to discover it;
- decide whether the wrapper should expose both values explicitly.

### Candidate contract

```json
{
  "verdict": "continue",
  "decision": {
    "kind": "QUEUE_EXHAUSTED",
    "source_field": "Q2"
  }
}
```

### Tests to add

- `continue` + selected objective;
- `continue` + queue exhausted;
- `blocked` + independent work still available;
- `changes_required` + planning revision;
- caller must not overwrite protocol verdict with domain decision.

## INC-002 — `status` evidence could be valid on disk but reported unusable through default lookup

**State:** Observed / Needs reproduction

During K8, persisted v3 response JSON was verified directly, while a default `status` lookup classified its status evidence as unusable or unavailable.

### Questions

- Was the lookup pointed at the wrong execution home, cache root, mission ID, or normalized bundle identity?
- Can a canonical persisted response be valid while `status` cannot locate or attest it?
- Does `status` distinguish `response valid` from `status evidence unavailable` clearly enough?
- Is the caller required to provide an explicit execution path in multi-home workflows?

### Tests to add

- canonical response present, cache index absent;
- canonical response present under a different `CODEX_HOME`;
- execution found by ID but bundle evidence unavailable;
- response valid but status cache stale;
- status result must never invalidate a verified canonical response silently;
- status output should recommend the exact recovery command.

## INC-003 — Documentation contains a v3/v2 contradiction

**State:** Observed

`SKILL.md` says new consultations request `codex-senior-consult-response/v3`, but a later paragraph says:

> The response contract is version `codex-senior-consult-response/v2`.

This is inconsistent with the repaired ordinary v3 flow.

### Required action

- determine whether the latter sentence is stale historical documentation;
- update documentation without weakening explicit v1/v2 compatibility boundaries;
- add a documentation consistency test or grep-based contract assertion.

### Acceptance

All ordinary-flow documentation identifies v3 as current. V1/v2 are described only as explicit historical compatibility.

## INC-004 — Gate taxonomy was useful but not always machine-explicit

**State:** Observed / Inferred

The mission used planning, plan-review, architecture/security, implementation, remote exact-head, cross-repository, final closure, and queue-exhaustion gates. Some distinctions were encoded mainly in bundle questions and mission prose rather than a strongly typed mode/decision taxonomy.

### Risk

- callers may use `merge-gate` for planning decisions;
- outputs may use valid generic verdicts but ambiguous domain semantics;
- analytics cannot compare similar gates reliably.

### Investigation

Inventory all real executions and map:

- CLI mode;
- requested decision;
- response schema variant;
- top-level verdict;
- mode-specific fields;
- downstream action.

### Possible improvement

Document a canonical mapping between use cases and modes. Add examples for:

- objective selection;
- plan review;
- architecture/security boundary;
- implementation readiness;
- exact remote publication;
- cross-repository compatibility;
- milestone closure;
- queue exhaustion.

Do not add new modes unless existing mode-specific contracts cannot express these decisions safely.

## INC-005 — Consultation frequency can become excessive in multi-slice missions

**State:** Observed / Needs quantitative analysis

K9 used many valid gates across small PR slices. This was safe, but may be more expensive and slower than necessary if every bounded change receives planning, plan-review, local implementation, remote implementation, and closure consultations.

### Questions

- Which gates were materially decision-bearing?
- Which repeated a previously accepted decision against a new exact head and were therefore necessary?
- Which could have been replaced by deterministic local verification?
- Is the documented semantic budget enforced and visible enough?

### Metrics to reconstruct

- process attempts;
- valid verdicts;
- protocol failures;
- replacements;
- cache hits;
- mode distribution;
- elapsed time;
- repeated questions per snapshot;
- accepted versus changes-required versus blocked decisions.

### Possible guidance

Define a minimum sufficient gate policy:

- planning gate only when selecting among real objectives;
- plan review only for documented risk triggers;
- implementation gate for a candidate snapshot;
- remote re-gate only when publication state is itself part of the evidence;
- final closure gate only at a true milestone boundary.

## INC-006 — Caller orchestration errors can be incorrectly attributed to the skill

**State:** Observed

The mission initially treated one blocked K10 objective as a globally blocked mission. The senior safety decision itself was correct; the caller's loop transition was wrong.

### Lesson

The skill returns advisory evidence. The caller owns queue management and must distinguish:

```text
OBJECTIVE_BLOCKED != MISSION_BLOCKED
```

### Follow-up

Add caller guidance and a pressure fixture where:

- selected objective is blocked;
- an independent objective remains admissible;
- correct senior answer preserves the block but does not claim global queue exhaustion.

The skill must not silently assume it owns the caller's whole queue unless the bundle explicitly includes and asks about the complete queue.

## INC-007 — Exact remote state may require a second gate even when SHA is unchanged

**State:** Observed

A local candidate accepted by the senior still needed a new remote-exact-head gate because the fact that the SHA was actually the PR head was part of the evidence.

### Clarification needed

Document when identical content/SHA can reuse a prior response and when changed external provenance requires a fresh consultation.

### Cases to test

- same SHA, local only versus published PR head;
- same SHA, CI absent versus CI completed;
- same SHA, PR draft versus ready;
- same SHA, mergeability changed;
- same tree, different commit SHA after squash;
- same response bundle except external-state evidence.

## INC-008 — Canonical reports cannot include their own introducing commit without a receipt pattern

**State:** Observed but primarily caller-side

Mission reports wrote `report_commit: pending` because an immutable file cannot know the commit that will introduce it.

### Relevance to this skill

Consultation responses and bundle provenance may encounter the same self-reference problem when callers want a report to name its own persistence commit.

### Experiments

- immutable response plus mutable index;
- response artifact plus immutable receipt artifact created in the next commit;
- blob SHA instead of introducing commit SHA;
- caller manifest that maps artifact hash to persistence commit.

Do not add self-referential fields that cannot be truthfully populated atomically.

## INC-009 — Historical malformed responses remain useful as a pressure corpus

**State:** Proposed

The mission preserved malformed v1/v2 responses, transport failures, and no-verdict outcomes. Sanitized structural examples could become regression fixtures.

### Requirements

- no real prompts containing secrets;
- no private repository content;
- preserve only the minimum malformed structure;
- document why each fixture is malformed;
- ensure historical compatibility paths remain opt-in.

### Candidate fixture classes

- additional unexpected properties;
- missing mode-specific fields;
- wrong schema version;
- prose surrounding JSON;
- valid JSON of wrong top-level type;
- non-string `caller_required` entries;
- malformed paths;
- response valid but persistence failure;
- response from an obsolete snapshot.

## INC-010 — Bundle completeness and sanitization worked, but real-mission ergonomics need review

**State:** Observed / Proposed

`build-bundle` and `preflight` successfully prevented incomplete or unsafe consultations. Real missions nevertheless required substantial manual assembly of exact heads, tests, evidence boundaries, and question-specific context.

### Review questions

- Which fields were repeatedly hand-filled?
- Which can be derived deterministically without reading protected content?
- Which caller-required diagnostics were confusing?
- Did path diagnostics identify array indexes precisely?
- Did preflight failures suggest exact repairs?
- Can bundle composition support a sanitized evidence manifest without copying large artifacts?

### Guardrail

Do not make bundle construction infer live evidence, merge authorization, secret safety, or factual conclusions.

---

# 4. Session-wide execution inventory

The closing operator must populate this table from persisted artifacts rather than memory.

| Purpose | Mode | Mission ID | Execution ID | Snapshot | Schema | Protocol verdict | Domain decision | Usable | Downstream action |
|---|---|---|---|---|---|---|---|---:|---|
| Skill repair merge gate | TBD | TBD | `cdd655ee-993d-49c9-bda5-c18fd0b7447c` | `96eddbb...` | v3 | accept | safe to merge | yes | canonical skill accepted |
| K8 config | TBD | TBD | `c111f1d7-93a9-4654-a75a-4b018a1eb657` | `9acd7893...` | v3 | accept | config ready | yes | proceed to product |
| K8 product local | TBD | TBD | `02d8dead-3306-4b42-b53a-4f3bfc1d0a61` | `09597eb0...` | v3 | accept | product ready | yes | publish candidate |
| K8 cross-repo pre-publication | TBD | TBD | `675e9582-d6f0-48e9-80b1-a6bbb63defef` | config + local product | v3 | changes_required | publish exact remote head | yes | push and re-gate |
| K8 cross-repo accepted | TBD | TBD | `747e6a7b-9f41-4681-98f2-d9351b958c57` | remote exact heads | v3 | accept | sequential merge | yes | merge K8 |
| K9 final | TBD | TBD | `3e499596-bbe6-49c5-bbb2-8ba706974770` | `9578c164...` | v3 | accept | K9 closed | yes | close milestone |
| K10 planning | TBD | TBD | `834b8355-6048-4f58-b744-7bf83ec8c229` | TBD | v3 | continue | pursue bounded compatibility | yes | plan review |
| K10 plan review accepted | TBD | TBD | `0d1353cd-d8f0-4b94-9a84-289e43fccf17` | plan v2 | v3 | accept | plan sufficient | yes | inventory/security gate |
| K10 security block | TBD | TBD | `13726f5b-d5cc-426a-9382-bf8a617ab9b9` | first inventory | v3 | blocked | no copier authorization | yes | create approval ledger |
| K10 corrected review | TBD | TBD | `1add56b7-5794-44d0-8553-943ae880bd80` | corrected inventory | v3 | continue | allowlist remains empty | yes | archive blocked objective |
| Queue exhaustion | TBD | TBD | `fd303acc-979c-4103-b589-54d9b1cb77b7` | final queue snapshot | v3 | continue | QUEUE_EXHAUSTED | yes | stop loop |

Add every omitted execution, including malformed/no-verdict attempts and replacements. Do not infer IDs.

---

# 5. Follow-up test backlog

## Priority P0 — Contract/documentation correctness

- [ ] Remove the ordinary-flow v2 contradiction from `SKILL.md`.
- [ ] Add a test that all current-flow docs identify v3 consistently.
- [ ] Define and test separate protocol-verdict and domain-decision fields.
- [ ] Reproduce the `status` canonical-response-versus-unusable-evidence case.
- [ ] Ensure status diagnostics identify the exact missing index/home/artifact.

## Priority P1 — Real mission semantics

- [ ] Add planning fixture: select one objective from several candidates.
- [ ] Add planning fixture: no admissible objective remains (`QUEUE_EXHAUSTED`).
- [ ] Add blocked-objective fixture where independent work remains.
- [ ] Add local-candidate versus remote-exact-head fixture.
- [ ] Add cross-repository one-head-changed fixture.
- [ ] Add same-tree/different-commit provenance fixture.
- [ ] Add plan-review trigger matrix fixture.

## Priority P1 — Protocol resilience

- [ ] Persisted valid response with missing cache index.
- [ ] Persistence failure after valid model output.
- [ ] One explicit replacement after no-verdict failure.
- [ ] Rejected replacement after a valid verdict.
- [ ] Replacement budget exhausted.
- [ ] Cache hit accounting versus process accounting.

## Priority P2 — Efficiency and ergonomics

- [ ] Reconstruct consultation cost for the complete Hermes dogfood session.
- [ ] Identify redundant versus necessary gates.
- [ ] Improve caller-required diagnostics from real bundle failures.
- [ ] Add sanitized real-world bundle skeletons for each common gate type.
- [ ] Document when a remote re-gate is required even for the same SHA.

## Priority P2 — Dogfood automation

- [ ] Add a sanitizer that extracts execution metadata without caller evidence bodies.
- [ ] Generate an execution inventory table from canonical artifacts.
- [ ] Detect documentation/schema version contradictions.
- [ ] Detect caller flattening of protocol verdict into a domain decision.
- [ ] Produce a machine-readable dogfood summary alongside this Markdown.

---

# 6. Proposed machine-readable companion

Consider adding `dogfood/session-summary.json` only after agreeing a schema.

Minimum candidate shape:

```json
{
  "schema": "codex-senior-consult-dogfood/v1",
  "session": "hermes-k8-k10-2026-08-02",
  "skill_head": "96eddbb927b54fee0f89ae297419f6affab64384",
  "executions": [],
  "incidents": [],
  "metrics": {
    "process_attempts": null,
    "valid_verdicts": null,
    "protocol_failures": null,
    "replacements": null,
    "cache_hits": null
  }
}
```

Do not add this file with guessed values.

---

# 7. Closure checklist for the original operator session

- [ ] Fetch and verify the remote skill head and canonical local installation.
- [ ] Confirm whether local and remote are identical before editing.
- [ ] Inventory all consultation artifacts produced in the session.
- [ ] Fill the execution table from persisted evidence.
- [ ] Add omitted incidents and strengths.
- [ ] Separate skill defects from caller-orchestration defects.
- [ ] Mark each claim Observed, Inferred, Proposed, or Needs reproduction.
- [ ] Link sanitized evidence paths or commit SHAs where appropriate.
- [ ] Fix only deterministic documentation defects that are proven and in scope.
- [ ] Do not implement speculative protocol changes during the retrospective.
- [ ] Run the skill's scoped tests and documentation checks.
- [ ] Run `git diff --check` and a secret-pattern scan.
- [ ] Commit and push the completed retrospective.
- [ ] Create a focused PR if the repository workflow requires one.
- [ ] Use an exact-head senior gate only if code/contracts change; a retrospective-only documentation update does not automatically require self-consultation.
- [ ] Report final branch, commit, PR, tests, and unresolved follow-ups.

---

# 8. Closing assessment

The session demonstrated that `codex-senior-consult` can support a long, multi-repository autonomous mission without receiving tools or workspace access. The most important follow-up is not to make the consultant more autonomous, but to make the boundary between protocol verdict, mode-specific decision, persisted evidence, and caller orchestration more explicit and testable.

The original operator must replace this provisional assessment with a final evidence-backed conclusion before closing the session.
